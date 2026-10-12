import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { ApiError, api, type CandidateDetail, type Language } from '../../api/client'
import { keys } from '../../api/queries'
import { Spinner } from '../../components/States'
import { errorMessage } from '../../lib/errors'
import { formatSlot } from '../../lib/format'

const SENTIMENT = {
  positive: { es: 'Positivo', en: 'Positive', className: 'bg-emerald-50 text-emerald-800' },
  neutral: { es: 'Neutro', en: 'Neutral', className: 'bg-stone-100 text-stone-700' },
  negative: { es: 'Negativo', en: 'Negative', className: 'bg-red-50 text-red-800' },
}

/**
 * The recruiter summary (003 FR-19): facts rendered by code from the record, plus a short
 * narrative by the model. ES/EN toggle loads (and the API stores) the other language.
 */
export function SummaryCard({ detail }: { detail: CandidateDetail }) {
  const [lang, setLang] = useState<Language>(detail.summary?.language ?? 'es')
  const id = detail.candidate.id
  const finished = detail.candidate.status !== 'in_progress'
  const initial = detail.summary?.language === lang ? detail.summary : undefined
  const summary = useQuery({
    queryKey: keys.summary(id, lang),
    queryFn: () => api.getSummary(id, lang),
    enabled: finished,
    initialData: initial,
    retry: (count, error) => !(error instanceof ApiError && error.status === 409) && count < 1,
  })

  return (
    <section className="card p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="eyebrow">Resumen del agente</h3>
        <div className="flex items-center gap-2">
          {summary.data && (
            <span className="text-[11px] text-stone-400">
              {summary.data.generated_by === 'llm' ? 'Redactado por el modelo' : 'Plantilla (sin modelo)'}
            </span>
          )}
          <div className="flex rounded-md bg-stone-100 p-0.5 text-xs font-medium" role="group" aria-label="Idioma del resumen">
            {(['es', 'en'] as const).map((l) => (
              <button
                key={l}
                type="button"
                aria-pressed={lang === l}
                onClick={() => setLang(l)}
                className={`rounded px-2 py-0.5 uppercase ${lang === l ? 'bg-white text-stone-900 shadow-xs' : 'text-stone-500'}`}
              >
                {l}
              </button>
            ))}
          </div>
        </div>
      </div>

      {!finished ? (
        <p className="text-sm text-stone-500">
          La conversación sigue abierta: el resumen se genera cuando termina.
        </p>
      ) : summary.isLoading ? (
        <p className="flex items-center gap-2 text-sm text-stone-500">
          <Spinner className="size-3.5" /> Generando resumen{lang === 'en' ? ' en inglés' : ''}…
        </p>
      ) : summary.isError ? (
        <p className="text-sm text-red-700">
          {summary.error instanceof ApiError && summary.error.status === 409
            ? 'El resumen estará disponible cuando termine la conversación.'
            : errorMessage(summary.error)}
        </p>
      ) : summary.data ? (
        <div className={summary.isFetching ? 'opacity-60' : ''}>
          {summary.data.narrative && (
            <div className="mb-4 rounded-lg bg-brand-50/60 p-3">
              <p className="text-sm text-stone-800">{summary.data.narrative.overview}</p>
              <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
                <span className={`rounded px-1.5 py-0.5 font-medium ${SENTIMENT[summary.data.narrative.sentiment].className}`}>
                  {SENTIMENT[summary.data.narrative.sentiment][lang]}
                </span>
                <span className="text-stone-500">{summary.data.narrative.sentiment_reason}</span>
              </div>
              {summary.data.narrative.observations.length > 0 && (
                <ul className="mt-2 list-disc space-y-0.5 pl-5 text-sm text-stone-700">
                  {summary.data.narrative.observations.map((o) => (
                    <li key={o}>{o}</li>
                  ))}
                </ul>
              )}
            </div>
          )}
          <dl className="grid grid-cols-1 gap-x-6 gap-y-1.5 text-sm sm:grid-cols-2">
            {summary.data.facts.map((fact) => (
              <div key={fact.key} className="flex gap-2">
                <dt className="shrink-0 text-stone-500">{fact.label}:</dt>
                <dd className="min-w-0 text-stone-900">
                  {fact.key === 'selected_slot' ? formatSlot(fact.value, lang) : fact.value}
                </dd>
              </div>
            ))}
          </dl>
        </div>
      ) : null}
    </section>
  )
}
