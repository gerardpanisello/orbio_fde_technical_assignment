import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router'
import { ApiError, api, type Zone, type ZonePatch } from '../api/client'
import { keys, useZones } from '../api/queries'
import { Kpi } from '../components/Kpi'
import { EmptyState, ErrorState, Loading, Spinner } from '../components/States'
import { errorMessage } from '../lib/errors'
import { COUNTRY } from '../lib/labels'
import { STATUS_META } from '../lib/status'
import {
  DEFICIT_BELOW_PCT,
  OCCUPANCY_BANDS,
  applyZonePatch,
  formatOccupancy,
  groupByCity,
  hasDeficit,
  occupancyBand,
  zoneTotals,
  type CityGroup,
} from '../lib/zones'
import { PageHeader } from './common'

/**
 * Spec 015 FR-8: driver staffing per served area. Recruiters edit target and current
 * drivers inline; the change re-prices every candidate of the zone (live priority) and
 * decides whether new qualified candidates there are waitlisted.
 */
export function ZonesPage() {
  const zones = useZones()
  const navigate = useNavigate()
  const [onlyDeficit, setOnlyDeficit] = useState(false)

  const all = zones.data ?? []
  // Sorted by occupancy once, when the page loads: saving a number changes the occupancy,
  // and re-sorting then would move the row away from under the cursor.
  const [order, setOrder] = useState<string[] | null>(null)
  if (order === null && zones.data) {
    setOrder(groupByCity(zones.data).flatMap((group) => group.zones.map((zone) => zone.id)))
  }
  const totals = zoneTotals(all)
  const shown = onlyDeficit ? all.filter(hasDeficit) : all
  const groups = groupByCity(shown, order ?? undefined)
  const coverage = totals.target > 0 ? Math.floor((totals.current / totals.target) * 100) : null

  return (
    <div className="mx-auto max-w-[1200px] px-4 py-6 lg:px-8">
      <PageHeader
        title="Zonas"
        subtitle="Plantilla de repartidores por zona: dónde falta gente y quién espera hueco."
      />

      <section className="mt-5 grid grid-cols-2 gap-3 xl:grid-cols-4" aria-label="Indicadores">
        <Kpi
          label="Zonas con déficit"
          dot={OCCUPANCY_BANDS.short.color}
          value={zones.data ? String(totals.deficit) : '—'}
          hint={zones.data ? `<${DEFICIT_BELOW_PCT} % · de ${totals.withData} con datos` : undefined}
          onClick={() => setOnlyDeficit((v) => !v)}
          active={onlyDeficit}
          loading={zones.isLoading}
        />
        <Kpi
          label="Zonas cubiertas"
          dot={OCCUPANCY_BANDS.covered.color}
          value={zones.data ? String(totals.full) : '—'}
          hint="Al 100 %: aptos nuevos, a la espera"
          loading={zones.isLoading}
        />
        <Kpi
          label="Repartidores"
          value={zones.data ? `${totals.current} / ${totals.target}` : '—'}
          hint={coverage !== null ? `${coverage} % de la plantilla objetivo` : undefined}
          loading={zones.isLoading}
        />
        <Kpi
          label="En lista de espera"
          dot={STATUS_META.waitlisted.color}
          value={zones.data ? String(totals.waitlisted) : '—'}
          hint="Aptos esperando hueco · ver lista"
          onClick={() => navigate('/recruiter?status=waitlisted')}
          loading={zones.isLoading}
        />
      </section>

      <div className="mt-5 flex flex-wrap items-center justify-between gap-3">
        <div className="space-y-1">
          <Legend />
          <p className="text-xs text-stone-500">
            Edita <strong className="font-medium text-stone-700">Objetivo</strong> o{' '}
            <strong className="font-medium text-stone-700">Actuales</strong>: se guarda al pulsar
            Enter o al salir del campo (Esc lo deshace).
          </p>
        </div>
        <label className="flex items-center gap-2 text-sm text-stone-600">
          <input
            type="checkbox"
            checked={onlyDeficit}
            onChange={(e) => setOnlyDeficit(e.target.checked)}
            className="size-4 accent-brand-600"
          />
          Solo zonas con déficit
        </label>
      </div>

      <section className="card mt-3 overflow-hidden">
        {zones.isLoading ? (
          <Loading />
        ) : zones.isError ? (
          <ErrorState error={zones.error} onRetry={() => zones.refetch()} />
        ) : all.length === 0 ? (
          <EmptyState icon="map" title="No hay zonas configuradas">
            Las zonas salen de config/service_areas.yaml y la plantilla inicial de
            config/zone_staffing.yaml.
          </EmptyState>
        ) : groups.length === 0 ? (
          <EmptyState icon="check" title="Ninguna zona con déficit">
            Todas las zonas con datos están por encima del {DEFICIT_BELOW_PCT} % de su plantilla.
          </EmptyState>
        ) : (
          <ZoneTable groups={groups} />
        )}
      </section>
    </div>
  )
}

function Legend() {
  return (
    <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-stone-600" aria-label="Leyenda de ocupación">
      {(Object.keys(OCCUPANCY_BANDS) as (keyof typeof OCCUPANCY_BANDS)[]).map((band) => (
        <li key={band} className="flex items-center gap-1.5" title={OCCUPANCY_BANDS[band].hint}>
          <span className="size-2.5 rounded-sm" style={{ backgroundColor: OCCUPANCY_BANDS[band].color }} />
          {OCCUPANCY_BANDS[band].label}
        </li>
      ))}
    </ul>
  )
}

const HEAD = ['Zona', 'Ocupación', 'Objetivo', 'Actuales', 'Aptos sin entrevista', 'Entrevistas', 'En espera']

function ZoneTable({ groups }: { groups: CityGroup[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[860px] text-left text-[13px]">
        <thead className="bg-stone-50 text-[11px] font-semibold tracking-wide text-stone-500 uppercase">
          <tr>
            {HEAD.map((h, i) => (
              <th key={h} scope="col" className={`px-3 py-2 font-semibold first:pl-4 ${i >= 2 ? 'text-right' : ''}`}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        {groups.map((group) => (
          <tbody key={group.city} className="border-t border-stone-200">
            <tr className="bg-stone-50/70">
              <th scope="rowgroup" colSpan={2} className="py-2 pr-3 pl-4 text-left">
                {/* A text chip, not a flag emoji: Windows has no flag glyphs. */}
                <abbr
                  title={COUNTRY[group.country]}
                  className="mr-2 inline-block rounded bg-stone-200 px-1 py-px text-[10px] font-semibold text-stone-600 no-underline"
                >
                  {group.country}
                </abbr>
                <span className="font-semibold text-stone-900">{group.cityName}</span>
                <span className="ml-2 text-xs font-normal text-stone-500">
                  {group.zones.length === 1 ? '1 zona' : `${group.zones.length} zonas`}
                  {group.totals.target > 0 &&
                    ` · ${group.totals.current} / ${group.totals.target} repartidores`}
                  {group.totals.deficit > 0 && ` · ${group.totals.deficit} con déficit`}
                </span>
              </th>
              <td colSpan={HEAD.length - 2} />
            </tr>
            {group.zones.map((zone) => (
              <ZoneRow key={zone.id} zone={zone} />
            ))}
          </tbody>
        ))}
      </table>
    </div>
  )
}

function ZoneRow({ zone }: { zone: Zone }) {
  const queryClient = useQueryClient()
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)
  useEffect(() => {
    if (!saved) return
    const timer = setTimeout(() => setSaved(false), 2500)
    return () => clearTimeout(timer)
  }, [saved])
  const update = useMutation({
    mutationFn: (patch: ZonePatch) => api.updateZone(zone.id, patch),
    onMutate: async (patch) => {
      setError(null)
      setSaved(false)
      await queryClient.cancelQueries({ queryKey: keys.zones })
      const previous = queryClient.getQueryData<Zone[]>(keys.zones)
      queryClient.setQueryData<Zone[]>(keys.zones, (list) =>
        list?.map((z) => (z.id === zone.id ? applyZonePatch(z, patch) : z)),
      )
      return { previous }
    },
    onError: (err, _patch, context) => {
      if (context?.previous) queryClient.setQueryData(keys.zones, context.previous)
      setError(
        err instanceof ApiError && err.status === 422
          ? 'Introduce un número entero, 0 o mayor'
          : errorMessage(err),
      )
    },
    onSuccess: (row) => {
      setSaved(true)
      queryClient.setQueryData<Zone[]>(keys.zones, (list) =>
        list?.map((z) => (z.id === row.id ? row : z)),
      )
      // Live priority (FR-6): every candidate of this zone may have a new score/bucket.
      void queryClient.invalidateQueries({ queryKey: keys.allCandidates })
      void queryClient.invalidateQueries({ queryKey: ['candidate'] })
    },
  })

  const band = occupancyBand(zone.occupancy_pct)
  const meta = OCCUPANCY_BANDS[band]
  const waitlistUrl = `/recruiter?status=waitlisted&city=${encodeURIComponent(zone.city)}`

  return (
    <tr className="align-middle">
      <td className="py-2 pr-3 pl-4 font-medium whitespace-nowrap text-stone-900">{zone.name}</td>
      <td className="px-3 py-2">
        <OccupancyBar zone={zone} />
      </td>
      <td className="px-3 py-2 text-right">
        <NumberCell
          label={`Objetivo de repartidores en ${zone.name} (${zone.city_name})`}
          value={zone.target_drivers}
          onSave={(n) => update.mutate({ target_drivers: n })}
        />
      </td>
      <td className="px-3 py-2 text-right">
        <NumberCell
          label={`Repartidores actuales en ${zone.name} (${zone.city_name})`}
          value={zone.current_drivers}
          onSave={(n) => update.mutate({ current_drivers: n })}
        />
        {(error || update.isPending || saved) && (
          <div className="mt-0.5 text-right text-[11px]" role={error ? 'alert' : 'status'}>
            {error ? (
              <span className="text-red-700">{error}</span>
            ) : update.isPending ? (
              <Spinner className="inline size-3 text-stone-400" />
            ) : (
              <span className="text-emerald-700">Guardado ✓</span>
            )}
          </div>
        )}
      </td>
      <Count value={zone.pipeline.qualified_unscheduled} />
      <Count value={zone.pipeline.interview_scheduled} />
      <td className="px-3 py-2 text-right tabular-nums">
        {zone.pipeline.waitlisted > 0 ? (
          <Link
            to={waitlistUrl}
            className="inline-flex items-center gap-1.5 font-semibold text-brand-700 hover:underline"
            title={`Ver candidatos en lista de espera en ${zone.city_name}`}
          >
            <span className="size-2 rounded-full" style={{ backgroundColor: STATUS_META.waitlisted.color }} />
            {zone.pipeline.waitlisted}
          </Link>
        ) : (
          <span className="text-stone-400" title={band === 'covered' ? meta.hint : undefined}>
            0
          </span>
        )}
      </td>
    </tr>
  )
}

function Count({ value }: { value: number }) {
  return (
    <td className={`px-3 py-2 text-right tabular-nums ${value ? 'text-stone-800' : 'text-stone-400'}`}>{value}</td>
  )
}

/** Thin bar on a hairline track, % and "current/target" beside it (never colour alone). */
export function OccupancyBar({ zone }: { zone: Pick<Zone, 'occupancy_pct' | 'current_drivers' | 'target_drivers'> }) {
  const band = occupancyBand(zone.occupancy_pct)
  const meta = OCCUPANCY_BANDS[band]
  const pct = zone.occupancy_pct
  return (
    <div className="flex items-center gap-3" title={meta.hint}>
      <div
        className={`h-2 w-36 shrink-0 overflow-hidden rounded-full ${
          band === 'no_data' ? 'border border-dashed border-stone-300' : 'bg-stone-100'
        }`}
        role="meter"
        aria-label={`Ocupación: ${formatOccupancy(pct)}`}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={pct ?? undefined}
      >
        {pct !== null && (
          <div
            className="h-full rounded-full transition-[width] duration-300"
            style={{ width: `${Math.min(100, pct)}%`, backgroundColor: meta.color }}
          />
        )}
      </div>
      <div className="min-w-0 leading-tight whitespace-nowrap">
        <span className="font-semibold text-stone-900 tabular-nums">{pct === null ? '—' : `${pct} %`}</span>
        {zone.target_drivers !== null && (
          <span className="ml-1.5 text-xs text-stone-500 tabular-nums">
            {zone.current_drivers}/{zone.target_drivers}
          </span>
        )}
        <div className="text-[11px] text-stone-500">{meta.label}</div>
      </div>
    </div>
  )
}

/** Inline number edit: saves on blur or Enter when the value changed; Escape reverts. */
function NumberCell({
  label,
  value,
  onSave,
}: {
  label: string
  value: number | null
  onSave: (value: number) => void
}) {
  const [draft, setDraft] = useState(value === null ? '' : String(value))
  const cancelled = useRef(false)
  // Follow the server value (optimistic update, rollback, refetch) unless the user is typing.
  const [seen, setSeen] = useState(value)
  if (value !== seen) {
    setSeen(value)
    setDraft(value === null ? '' : String(value))
  }

  const commit = () => {
    const text = draft.trim()
    if (cancelled.current) {
      cancelled.current = false
      return
    }
    if (text === '' || Number(text) === value || Number.isNaN(Number(text))) {
      setDraft(value === null ? '' : String(value))
      return
    }
    onSave(Number(text))
  }

  return (
    <input
      type="number"
      inputMode="numeric"
      step={1}
      aria-label={label}
      value={draft}
      placeholder="—"
      onChange={(e) => setDraft(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => {
        if (e.key === 'Enter') e.currentTarget.blur()
        if (e.key === 'Escape') {
          cancelled.current = true
          setDraft(value === null ? '' : String(value))
          e.currentTarget.blur()
        }
      }}
      className="field h-7 w-20 text-right tabular-nums"
    />
  )
}
