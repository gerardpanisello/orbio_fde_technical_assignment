import { useState, type ReactNode } from 'react'
import {
  Bar,
  BarChart,
  Cell,
  LabelList,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { Analytics, Status } from '../api/client'
import { useAnalytics } from '../api/queries'
import { Kpi } from '../components/Kpi'
import { EmptyState, ErrorState, Loading } from '../components/States'
import { formatDuration, formatPercent, formatUsd } from '../lib/format'
import { buildFunnel } from '../lib/funnel'
import { COUNTRY, DISQUALIFICATION, STAGE } from '../lib/labels'
import { STATUS_META, STATUS_ORDER } from '../lib/status'
import { PageHeader, SeedButton } from './common'

/**
 * Chart colours (checked with the dataviz palette validator):
 * - funnel: one terracotta hue, light -> dark as candidates go deeper (ordinal ramp);
 * - everything about a status uses that status's colour from lib/status.ts.
 */
const FUNNEL_RAMP = ['#e98a5f', '#dc6a3a', '#c2531f', '#9c4019', '#753012']
const INK = '#44403c'
const MUTED = '#78716c'
const BAR = 22 // px, thin marks with air between them
const ROW = 40

/** FR-13: funnel, drop-off, disqualification reasons, countries and agent health. */
export function AnalyticsPage() {
  const analytics = useAnalytics()

  return (
    <div className="mx-auto max-w-[1200px] px-4 py-6 lg:px-8">
      <PageHeader
        title="Analítica"
        subtitle="Embudo de selección y salud del agente, sobre todas las candidaturas."
      />
      {analytics.isLoading ? (
        <Loading />
      ) : analytics.isError || !analytics.data ? (
        <ErrorState error={analytics.error} onRetry={() => analytics.refetch()} />
      ) : analytics.data.total === 0 ? (
        <div className="card mt-5">
          <EmptyState icon="chart" title="Sin datos todavía" action={<SeedButton />}>
            La analítica aparece en cuanto haya conversaciones. Para la demo puedes generar datos
            simulados.
          </EmptyState>
        </div>
      ) : (
        <Dashboard a={analytics.data} refreshing={analytics.isFetching} />
      )}
    </div>
  )
}

function Dashboard({ a, refreshing }: { a: Analytics; refreshing: boolean }) {
  const funnel = buildFunnel(a)
  const dropOff = (Object.keys(STAGE) as (keyof typeof STAGE)[])
    .filter((stage) => (a.drop_off_by_stage[stage] ?? 0) > 0)
    .map((stage) => ({ label: STAGE[stage], value: a.drop_off_by_stage[stage] ?? 0 }))
  const reasons = (Object.keys(DISQUALIFICATION) as (keyof typeof DISQUALIFICATION)[])
    .map((r) => ({ label: DISQUALIFICATION[r], value: a.disqualification_reasons[r] ?? 0 }))
    .filter((r) => r.value > 0)
    .sort((x, y) => y.value - x.value)
  const abandoned = a.by_status.abandoned ?? 0
  const disqualified = a.by_status.disqualified ?? 0

  return (
    <div className={`mt-5 space-y-5 transition-opacity ${refreshing ? 'opacity-70' : ''}`}>
      <section className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6" aria-label="Indicadores">
        <Kpi label="Candidaturas" value={String(a.total)} hint={`${a.by_status.in_progress ?? 0} en curso`} />
        <Kpi
          label="Tasa de finalización"
          value={formatPercent(a.completion_rate)}
          hint={`${a.finished} con resultado`}
        />
        <Kpi
          label="Duración mediana"
          value={formatDuration(a.median_duration_s)}
          hint="Del primer al último mensaje"
        />
        <Kpi label="Turnos del agente" value={String(a.agent_turns)} hint="Respuestas enviadas" />
        <Kpi
          label="Respuestas de plantilla"
          value={formatPercent(a.fallback_rate, 1)}
          hint="Fallback cuando falla el modelo"
        />
        <Kpi label="Coste medio" value={formatUsd(a.avg_cost_usd)} hint="LLM por candidatura" />
      </section>

      <div className="grid gap-5 lg:grid-cols-2">
        <ChartCard
          title="Embudo de selección"
          note="Conversaciones cerradas. Las bajas cuentan como salida en el consentimiento; las revisiones manuales no cuentan como requisitos superados."
          table={{
            head: ['Etapa', 'Candidaturas', '% de iniciadas'],
            rows: funnel.map((s) => [s.label, String(s.value), formatPercent(s.share)]),
          }}
          className="lg:col-span-2"
        >
          <HBars
            data={funnel.map((s, i) => ({
              label: s.label,
              value: s.value,
              color: FUNNEL_RAMP[i],
              tip: `${s.value} · ${formatPercent(s.share)}`,
            }))}
            labelWidth={150}
          />
        </ChartCard>

        <ChartCard
          title="Abandonos por etapa"
          note={`${abandoned} conversaciones abandonadas, por la última etapa alcanzada.`}
          table={{ head: ['Etapa', 'Abandonos'], rows: dropOff.map((d) => [d.label, String(d.value)]) }}
        >
          {dropOff.length ? (
            <HBars
              data={dropOff.map((d) => ({ ...d, color: STATUS_META.abandoned.color, tip: String(d.value) }))}
              labelWidth={130}
            />
          ) : (
            <NoData text="Ningún abandono." />
          )}
        </ChartCard>

        <ChartCard
          title="Motivos de descarte"
          note={`${disqualified} candidatos descartados por un requisito eliminatorio (decidido por reglas, no por el modelo).`}
          table={{ head: ['Motivo', 'Candidatos'], rows: reasons.map((r) => [r.label, String(r.value)]) }}
        >
          {reasons.length ? (
            <HBars
              data={reasons.map((r) => ({ ...r, color: STATUS_META.disqualified.color, tip: String(r.value) }))}
              labelWidth={150}
            />
          ) : (
            <NoData text="Ningún descarte." />
          )}
        </ChartCard>

        <ByCountry a={a} />
      </div>
    </div>
  )
}

// --- building blocks ----------------------------------------------------------------------

type Datum = { label: string; value: number; color: string; tip: string }

/** Horizontal bars: thin, rounded data end, value at the tip, tooltip on hover. */
function HBars({ data, labelWidth }: { data: Datum[]; labelWidth: number }) {
  const max = Math.max(1, ...data.map((d) => d.value))
  return (
    <ResponsiveContainer width="100%" height={data.length * ROW + 8}>
      <BarChart data={data} layout="vertical" margin={{ top: 4, right: 104, bottom: 4, left: 0 }}>
        <XAxis type="number" hide domain={[0, max]} />
        <YAxis
          type="category"
          dataKey="label"
          width={labelWidth}
          tickLine={false}
          axisLine={{ stroke: '#d6d3d1' }}
          tick={{ fill: INK, fontSize: 12 }}
        />
        <Tooltip
          cursor={{ fill: '#f5f5f4' }}
          content={({ active, payload }) => {
            const d = payload?.[0]?.payload as Datum | undefined
            return active && d ? <TooltipBox title={d.label} rows={[{ color: d.color, label: '', value: d.tip }]} /> : null
          }}
        />
        <Bar dataKey="value" barSize={BAR} radius={[0, 4, 4, 0]} isAnimationActive={false}>
          {data.map((d) => (
            <Cell key={d.label} fill={d.color} />
          ))}
          <LabelList dataKey="tip" position="right" fill={INK} fontSize={12} offset={8} />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}

const COUNTRY_LABEL: Record<string, string> = { ...COUNTRY, unknown: 'Sin país' }

/** Status mix per country: stacked bars in the shared status colours, with a legend. */
function ByCountry({ a }: { a: Analytics }) {
  const countries = Object.keys(a.by_country).sort((x, y) =>
    x === 'unknown' ? 1 : y === 'unknown' ? -1 : x.localeCompare(y),
  )
  const present = STATUS_ORDER.filter((s) => countries.some((c) => (a.by_country[c][s] ?? 0) > 0))
  const data = countries.map((c) => ({
    label: `${COUNTRY_LABEL[c] ?? c} (${Object.values(a.by_country[c]).reduce((x, y) => x + y, 0)})`,
    ...Object.fromEntries(present.map((s) => [s, a.by_country[c][s] ?? 0])),
  }))

  return (
    <ChartCard
      title="Estado por país"
      note="«Sin país»: aún no se conocía la ubicación ni el prefijo del teléfono."
      className="lg:col-span-2"
      table={{
        head: ['País', ...present.map((s) => STATUS_META[s].label), 'Total'],
        rows: countries.map((c) => [
          COUNTRY_LABEL[c] ?? c,
          ...present.map((s) => String(a.by_country[c][s] ?? 0)),
          String(Object.values(a.by_country[c]).reduce((x, y) => x + y, 0)),
        ]),
      }}
    >
      <Legend statuses={present} />
      <ResponsiveContainer width="100%" height={data.length * ROW + 8}>
        <BarChart data={data} layout="vertical" margin={{ top: 4, right: 16, bottom: 4, left: 0 }}>
          <XAxis type="number" hide />
          <YAxis
            type="category"
            dataKey="label"
            width={110}
            tickLine={false}
            axisLine={{ stroke: '#d6d3d1' }}
            tick={{ fill: INK, fontSize: 12 }}
          />
          <Tooltip
            cursor={{ fill: '#f5f5f4' }}
            content={({ active, payload, label }) =>
              active && payload?.length ? (
                <TooltipBox
                  title={String(label)}
                  rows={payload
                    .filter((p) => Number(p.value) > 0)
                    .map((p) => ({
                    color: STATUS_META[p.dataKey as Status].color,
                    label: STATUS_META[p.dataKey as Status].label,
                    value: String(p.value),
                  }))}
                />
              ) : null
            }
          />
          {present.map((s) => (
            <Bar
              key={s}
              dataKey={s}
              stackId="status"
              fill={STATUS_META[s].color}
              stroke="#ffffff"
              strokeWidth={2}
              barSize={BAR}
              isAnimationActive={false}
            />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  )
}

function Legend({ statuses }: { statuses: Status[] }) {
  return (
    <ul className="mb-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-stone-600" aria-label="Leyenda">
      {statuses.map((s) => (
        <li key={s} className="flex items-center gap-1.5">
          <span className="size-2.5 rounded-sm" style={{ backgroundColor: STATUS_META[s].color }} />
          {STATUS_META[s].label}
        </li>
      ))}
    </ul>
  )
}

function TooltipBox({ title, rows }: { title: string; rows: { color: string; label: string; value: string }[] }) {
  return (
    <div className="rounded-lg border border-stone-200 bg-white px-3 py-2 text-xs shadow-lg">
      <div className="mb-1 text-stone-500">{title}</div>
      {rows.map((r) => (
        <div key={r.label + r.value} className="flex items-center gap-2">
          <span className="h-0.5 w-3 rounded" style={{ backgroundColor: r.color }} />
          <span className="font-semibold text-stone-900 tabular-nums">{r.value}</span>
          {r.label && <span className="text-stone-500">{r.label}</span>}
        </div>
      ))}
    </div>
  )
}

/** Card with a "Ver datos" toggle: every chart has a table twin (values never hover-only). */
function ChartCard({
  title,
  note,
  table,
  className = '',
  children,
}: {
  title: string
  note?: string
  table: { head: string[]; rows: string[][] }
  className?: string
  children: ReactNode
}) {
  const [showTable, setShowTable] = useState(false)
  return (
    <section className={`card p-4 ${className}`}>
      <div className="mb-3 flex items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-stone-900">{title}</h2>
          {note && <p className="mt-0.5 text-xs text-stone-500">{note}</p>}
        </div>
        <button
          type="button"
          className="shrink-0 text-xs font-medium text-brand-700 hover:underline"
          aria-pressed={showTable}
          onClick={() => setShowTable((v) => !v)}
        >
          {showTable ? 'Ver gráfico' : 'Ver datos'}
        </button>
      </div>
      {showTable ? (
        <table className="w-full text-left text-[13px]">
          <thead className="text-[11px] tracking-wide text-stone-500 uppercase">
            <tr>
              {table.head.map((h, i) => (
                <th key={h} className={`py-1.5 font-semibold ${i > 0 ? 'text-right' : ''}`}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-stone-100">
            {table.rows.map((row) => (
              <tr key={row[0]}>
                {row.map((cell, i) => (
                  <td key={i} className={`py-1.5 ${i > 0 ? 'text-right tabular-nums' : 'text-stone-800'}`}>
                    {cell}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        children
      )}
    </section>
  )
}

function NoData({ text }: { text: string }) {
  return <p className="py-8 text-center text-sm" style={{ color: MUTED }}>{text}</p>
}
