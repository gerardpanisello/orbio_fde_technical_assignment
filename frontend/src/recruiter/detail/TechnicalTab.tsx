import { Fragment, useState } from 'react'
import type { CandidateDetail } from '../../api/client'
import { FaqChip } from '../../components/FaqChip'
import { Icon } from '../../components/Icon'
import { faqTurn } from '../../lib/faq'
import { formatTime } from '../../lib/format'

/**
 * "How did the agent get here": one row per agent turn (model, latency, cost, fallback,
 * extraction outcome), each expandable to the full trace, plus the raw record JSON.
 */
export function TechnicalTab({ detail }: { detail: CandidateDetail }) {
  const [open, setOpen] = useState<number | null>(null)
  const totalCost = detail.traces.reduce((sum, t) => sum + t.cost_usd, 0)
  const fallbacks = detail.traces.filter((t) => t.fallback).length
  const models = detail.traces.at(-1)?.models ?? {}

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-3 gap-3">
        <Mini label="Turnos del agente" value={String(detail.traces.length)} />
        <Mini label="Coste total" value={`${totalCost.toFixed(4)} $`} />
        <Mini label="Respuestas de plantilla" value={String(fallbacks)} />
      </div>
      {Object.keys(models).length > 0 && (
        <p className="text-xs text-stone-500">
          Modelos (config/llm.yaml):{' '}
          {Object.entries(models).map(([role, model], i) => (
            <span key={role}>
              {i > 0 && ' · '}
              {role} <code className="rounded bg-stone-100 px-1 font-mono text-stone-700">{model}</code>
            </span>
          ))}
        </p>
      )}

      <details className="card group">
        <summary className="flex cursor-pointer items-center justify-between px-4 py-3 text-sm font-medium text-stone-800">
          Trazas por turno ({detail.traces.length})
          <Icon name="chevronDown" className="size-4 text-stone-400 transition group-open:rotate-180" />
        </summary>
        <div className="overflow-x-auto border-t border-stone-100">
          <table className="w-full text-left text-xs">
            <thead className="bg-stone-50 text-[10.5px] tracking-wide text-stone-500 uppercase">
              <tr>
                {['Hora', 'Acción', 'Extracción', 'Cliente', 'Latencia', 'Coste', 'Respuesta'].map((h) => (
                  <th key={h} className="px-3 py-2 font-semibold">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-stone-100">
              {detail.traces.map((t) => {
                const faq = faqTurn(t)
                return (
                <Fragment key={t.message_id}>
                  <tr
                    className="cursor-pointer hover:bg-stone-50"
                    onClick={() => setOpen(open === t.message_id ? null : t.message_id)}
                    aria-expanded={open === t.message_id}
                  >
                    <td className="px-3 py-1.5 text-stone-500 tabular-nums">{formatTime(t.created_at)}</td>
                    <td className="px-3 py-1.5 font-mono text-stone-800">
                      <span className="flex flex-wrap items-center gap-1.5">
                        {t.action ?? '—'}
                        {faq && <FaqChip turn={faq} />}
                      </span>
                    </td>
                    <td className="px-3 py-1.5">
                      <span
                        className={`rounded px-1 py-px font-mono ${
                          t.extraction === 'failed' ? 'bg-red-50 text-red-700' : 'text-stone-600'
                        }`}
                      >
                        {t.extraction}
                      </span>
                    </td>
                    <td
                      className="px-3 py-1.5 font-mono text-[11px] whitespace-nowrap text-stone-500"
                      title={Object.entries(t.models).map(([k, v]) => `${k}: ${v}`).join(' · ')}
                    >
                      {t.client}
                    </td>
                    <td className="px-3 py-1.5 whitespace-nowrap text-stone-700 tabular-nums">{t.latency_ms} ms</td>
                    <td className="px-3 py-1.5 whitespace-nowrap text-stone-700 tabular-nums">{t.cost_usd.toFixed(4)} $</td>
                    <td className="px-3 py-1.5">
                      {t.fallback ? (
                        <span className="rounded bg-amber-50 px-1 py-px text-amber-800">plantilla</span>
                      ) : (
                        <span className="text-stone-500">modelo</span>
                      )}
                    </td>
                  </tr>
                  {open === t.message_id && (
                    <tr>
                      <td colSpan={7} className="bg-stone-900 p-0">
                        <Json value={t.trace} />
                      </td>
                    </tr>
                  )}
                </Fragment>
                )
              })}
            </tbody>
          </table>
        </div>
      </details>

      <details className="card group">
        <summary className="flex cursor-pointer items-center justify-between px-4 py-3 text-sm font-medium text-stone-800">
          Registro JSON (esquema 002 · config {detail.record.config_version})
          <Icon name="chevronDown" className="size-4 text-stone-400 transition group-open:rotate-180" />
        </summary>
        <div className="overflow-hidden rounded-b-xl bg-stone-900">
          <Json value={detail.record} />
        </div>
      </details>
    </div>
  )
}

function Json({ value }: { value: unknown }) {
  return (
    <pre className="scrollbar-thin max-h-[420px] overflow-auto p-4 font-mono text-[11.5px] leading-relaxed text-stone-100">
      {JSON.stringify(value, null, 2)}
    </pre>
  )
}

function Mini({ label, value }: { label: string; value: string }) {
  return (
    <div className="card px-3 py-2">
      <div className="text-[11px] text-stone-500">{label}</div>
      <div className="text-base font-semibold text-stone-900">{value}</div>
    </div>
  )
}
