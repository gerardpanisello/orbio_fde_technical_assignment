import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { ApiError, api, type ActionName, type CandidateDetail } from '../../api/client'
import { keys } from '../../api/queries'
import { Icon } from '../../components/Icon'
import { Spinner } from '../../components/States'
import { errorMessage } from '../../lib/errors'
import { formatDateTime } from '../../lib/format'
import { ACTION } from '../../lib/labels'

/** The API's 409 reasons (spec 004 §6), in the recruiter's language. */
function actionError(error: unknown): string {
  if (error instanceof ApiError && error.status === 409) {
    if (error.detail.includes('opted out')) return 'El candidato se dio de baja: no se le puede contactar.'
    if (error.detail.includes('override'))
      return 'Solo se puede aprobar manualmente a candidatos descartados o pendientes de revisión.'
  }
  return errorMessage(error)
}

/**
 * FR-10: shortlist, reject, hire, override and notes. The agent's own outcome is never
 * changed: actions are stored next to it, so the audit trail shows both.
 */
export function ActionsPanel({ detail }: { detail: CandidateDetail }) {
  const queryClient = useQueryClient()
  const { candidate } = detail
  const [note, setNote] = useState('')
  const action = useMutation({
    mutationFn: ({ name, text }: { name: ActionName; text?: string }) =>
      api.addAction(candidate.id, name, text),
    onSuccess: (_, { name }) => {
      if (name === 'note') setNote('')
      void queryClient.invalidateQueries({ queryKey: keys.candidate(candidate.id) })
      void queryClient.invalidateQueries({ queryKey: keys.allCandidates })
    },
  })

  const optedOut = candidate.status === 'opted_out'
  const canOverride = candidate.status === 'disqualified' || candidate.status === 'needs_review'
  const current = candidate.recruiter_status
  const busy = action.isPending
  const run = (name: ActionName) => action.mutate({ name })

  function submitNote(event: FormEvent) {
    event.preventDefault()
    if (note.trim()) action.mutate({ name: 'note', text: note.trim() })
  }

  return (
    <section className="card p-4">
      <h3 className="eyebrow mb-3">Gestión</h3>
      {optedOut ? (
        <p className="mb-3 text-sm text-stone-500">
          Se dio de baja: sus datos se borraron y no se le debe contactar.
        </p>
      ) : (
        <div className="flex flex-wrap gap-2">
          {canOverride && (
            <button
              type="button"
              className="btn-primary"
              disabled={busy || candidate.recruiter_override}
              onClick={() => run('override')}
              title="Lo pasa a preseleccionado. El resultado del agente se conserva para auditoría."
            >
              <Icon name="check" /> Aprobar manualmente
            </button>
          )}
          {candidate.status !== 'disqualified' && (
            <button
              type="button"
              className={current === 'shortlisted' ? 'btn-secondary' : 'btn-primary'}
              disabled={busy || current === 'shortlisted'}
              onClick={() => run('shortlist')}
            >
              <Icon name="check" /> {current === 'shortlisted' ? 'Preseleccionado' : 'Preseleccionar'}
            </button>
          )}
          <button
            type="button"
            className="btn-secondary"
            disabled={
              busy ||
              current === 'hired' ||
              (candidate.status === 'disqualified' && !candidate.recruiter_override)
            }
            onClick={() => run('hire')}
          >
            Contratar
          </button>
          <button
            type="button"
            className="btn-secondary text-red-700 hover:bg-red-50"
            disabled={busy || current === 'rejected'}
            onClick={() => run('reject')}
          >
            <Icon name="x" /> Rechazar
          </button>
          {busy && <Spinner className="size-4 self-center text-stone-400" />}
        </div>
      )}

      {action.isError && (
        <p role="alert" className="mt-2 text-sm text-red-700">
          {actionError(action.error)}
        </p>
      )}

      <form onSubmit={submitNote} className="mt-3 flex gap-2">
        <label htmlFor="note" className="sr-only">
          Nota interna
        </label>
        <input
          id="note"
          value={note}
          onChange={(e) => setNote(e.target.value)}
          maxLength={2000}
          placeholder="Añadir una nota interna…"
          className="field h-9 min-w-0 flex-1"
        />
        <button type="submit" className="btn-secondary" disabled={busy || !note.trim()}>
          Guardar nota
        </button>
      </form>

      {detail.actions.length > 0 && (
        <ol className="mt-4 space-y-2 border-t border-stone-100 pt-3" aria-label="Historial de acciones">
          {[...detail.actions].reverse().map((a) => (
            <li key={a.id} className="flex gap-2 text-sm">
              <span className="mt-1.5 size-1.5 shrink-0 rounded-full bg-stone-300" />
              <div className="min-w-0">
                <span className="font-medium text-stone-800">{ACTION[a.action]}</span>
                <span className="ml-2 text-xs text-stone-400">{formatDateTime(a.created_at)}</span>
                {a.note && <p className="text-stone-600">{a.note}</p>}
              </div>
            </li>
          ))}
        </ol>
      )}
    </section>
  )
}
