import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { ApiError, api, type CandidateDetail } from '../api/client'
import { useAreaLabels } from '../api/queries'
import { StatusBadge } from '../components/Badges'
import { Icon } from '../components/Icon'
import { Reasons } from '../components/Reasons'
import { RecordFields } from '../components/RecordFields'
import { ScoreBreakdown } from '../components/ScoreBreakdown'
import { Spinner } from '../components/States'
import { errorMessage } from '../lib/errors'
import { STAGE } from '../lib/labels'
import { followUpLabel, followUpTotal, nextStepText } from '../lib/reengagement'
import { ReengagementSummary } from '../components/ReengagementSummary'

/**
 * FR-7 (demo only): what the engine has extracted and validated so far, refreshed after
 * every turn, so the presenter can show the record filling up as the candidate types.
 */
export function LiveRecordPanel({
  conversationId,
  detail,
  loading,
  onAdvanced,
}: {
  conversationId: string | null
  detail: CandidateDetail | undefined
  loading: boolean
  /** Pull the new reminder (or the abandon) into the chat. */
  onAdvanced: () => Promise<void>
}) {
  const areas = useAreaLabels()
  const [advancing, setAdvancing] = useState(false)
  const [toast, setToast] = useState<string | null>(null)
  const lastTrace = detail?.traces.at(-1)
  const total = followUpTotal(detail)
  const next = detail?.reengagement.next

  useEffect(() => {
    if (!toast) return
    const timer = setTimeout(() => setToast(null), 4000)
    return () => clearTimeout(timer)
  }, [toast])

  /** Spec 008 FR-8 (dev): run the next re-engagement step now instead of waiting hours. */
  async function advance() {
    if (!conversationId) return
    setAdvancing(true)
    setToast(null)
    try {
      const result = await api.advance(conversationId)
      await onAdvanced()
      setToast(
        result.action === 'abandon'
          ? 'Conversación abandonada (sin respuesta tras el último recordatorio)'
          : `${followUpLabel(result.step ?? 0, total)} enviado${result.requires_template ? ' · plantilla WhatsApp' : ''}`,
      )
    } catch (e) {
      // 409 "nothing to advance: <reason>" is the useful answer here, not an error page.
      setToast(e instanceof ApiError && e.status === 409 ? `Nada que avanzar: ${e.detail.replace(/^nothing to advance:\s*/, '')}` : errorMessage(e))
    } finally {
      setAdvancing(false)
    }
  }

  return (
    <aside className="flex h-full flex-col overflow-hidden rounded-2xl border border-stone-200 bg-white shadow-sm">
      <div className="flex items-center justify-between border-b border-stone-100 px-4 py-3">
        <div>
          <h2 className="text-sm font-semibold text-stone-900">Registro en vivo</h2>
          <p className="text-xs text-stone-500">Lo que el motor ha extraído y validado</p>
        </div>
        {loading && <Spinner className="size-3.5 text-stone-400" />}
      </div>

      {!conversationId || !detail ? (
        <div className="flex flex-1 items-center justify-center p-6 text-center text-sm text-stone-500">
          {conversationId ? <Spinner /> : 'Empieza una conversación para ver el registro.'}
        </div>
      ) : (
        <div className="scrollbar-thin flex-1 space-y-5 overflow-y-auto px-4 py-4">
          <section className="flex flex-wrap items-center gap-2">
            <StatusBadge status={detail.candidate.status} size="md" />
            {detail.record.drop_off_stage && detail.candidate.status === 'in_progress' && (
              <span className="text-xs text-stone-500">
                Etapa: {STAGE[detail.record.drop_off_stage]}
              </span>
            )}
          </section>

          <Reasons record={detail.record} />

          <section>
            <h3 className="eyebrow mb-2">Datos</h3>
            <RecordFields record={detail.record} areas={areas} dense />
          </section>

          <section>
            <h3 className="eyebrow mb-2">Puntuación</h3>
            <ScoreBreakdown
              score={detail.live_score ?? detail.record.score}
              atClose={detail.live_score ? detail.record.score : null}
            />
          </section>

          <section>
            <h3 className="eyebrow mb-2">Re-engagement</h3>
            <ReengagementSummary detail={detail} total={total} />
          </section>

          {lastTrace && (
            <section>
              <h3 className="eyebrow mb-2">Último turno</h3>
              <dl className="grid grid-cols-2 gap-2 text-xs">
                <Stat label="Acción del motor" value={lastTrace.action ?? '—'} mono />
                <Stat label="Extracción" value={lastTrace.extraction} mono />
                <Stat label="Cliente LLM" value={lastTrace.client} mono />
                <Stat label="Latencia" value={`${lastTrace.latency_ms} ms`} />
                <Stat label="Coste" value={`${lastTrace.cost_usd.toFixed(4)} $`} />
                <Stat label="Respuesta" value={lastTrace.fallback ? 'Plantilla (fallback)' : 'Modelo'} />
              </dl>
            </section>
          )}
        </div>
      )}

      {toast && (
        <p role="status" className="mx-4 mb-2 rounded-lg bg-stone-900 px-3 py-2 text-xs text-white shadow-lg">
          {toast}
        </p>
      )}
      {conversationId && (
        <div className="flex flex-wrap gap-2 border-t border-stone-100 px-4 py-3">
          <Link to={`/recruiter?id=${conversationId}`} className="btn-secondary flex-1" target="_blank">
            <Icon name="external" /> Ver en el panel
          </Link>
          <button
            type="button"
            className="btn-ghost flex-1 whitespace-nowrap"
            onClick={advance}
            disabled={advancing || detail?.candidate.status !== 'in_progress'}
            title={
              next
                ? `Próximo paso: ${nextStepText(next, total)} (dev: lo ejecuta ya)`
                : 'Ejecuta el siguiente paso de re-engagement (dev)'
            }
          >
            {advancing ? <Spinner className="size-3.5" /> : <Icon name="clock" />} Avanzar tiempo ⏩
          </button>
        </div>
      )}
    </aside>
  )
}

function Stat({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="rounded-lg bg-stone-50 px-2.5 py-1.5">
      <dt className="text-[11px] text-stone-500">{label}</dt>
      <dd className={`truncate text-stone-800 ${mono ? 'font-mono text-[11.5px]' : ''}`}>{value}</dd>
    </div>
  )
}
