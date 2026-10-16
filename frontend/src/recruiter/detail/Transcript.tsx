import type { ChatMessage, Trace } from '../../api/client'
import { FaqChip } from '../../components/FaqChip'
import { EmptyState } from '../../components/States'
import { faqTurn, type FaqTurn } from '../../lib/faq'
import { followUpLabel } from '../../lib/reengagement'
import { formatTime } from '../../lib/format'

/** The stored conversation, read-only, in the same left/right layout as the chat. */
export function Transcript({
  messages,
  traces = [],
  followUpTotal = null,
}: {
  messages: ChatMessage[]
  traces?: Trace[]
  followUpTotal?: number | null
}) {
  if (!messages.length) return <EmptyState icon="chat" title="Sin mensajes" />
  // A trace belongs to the agent message it produced (same id).
  const faqByMessage = new Map<number, FaqTurn>()
  for (const trace of traces) {
    const turn = faqTurn(trace)
    if (turn) faqByMessage.set(trace.message_id, turn)
  }
  return (
    <ol className="space-y-1.5" aria-label="Transcripción">
      {messages.map((m) => {
        const agent = m.role === 'agent'
        const faq = agent ? faqByMessage.get(m.id) : undefined
        return (
          <li key={m.id} className={`flex ${agent ? 'justify-start' : 'justify-end'}`}>
            <div
              className={`max-w-[80%] rounded-xl px-3 py-1.5 text-[13px] leading-snug ${
                agent
                  ? 'rounded-tl-sm border border-stone-200 bg-white text-stone-800'
                  : 'rounded-tr-sm bg-[#e7f6e4] text-stone-900'
              }`}
            >
              <div className="mb-0.5 flex items-center justify-between gap-3 text-[10.5px] font-medium tracking-wide text-stone-400 uppercase">
                <span className="flex items-center gap-1.5">
                  {agent ? 'Sofi' : 'Candidato'}
                  {faq && <FaqChip turn={faq} />}
                  {m.kind === 'reminder' && <span className="font-normal normal-case">· Recordatorio de entrevista</span>}
                  {m.kind === 'follow_up' && m.follow_up_step != null && (
                    <span className="font-normal normal-case">
                      · {followUpLabel(m.follow_up_step, followUpTotal)}
                      {m.requires_template && (
                        <span
                          className="ml-1 rounded border border-stone-200 px-1 text-[10px]"
                          title="Fuera de la ventana de 24 h de WhatsApp: en producción, plantilla aprobada"
                        >
                          plantilla WhatsApp
                        </span>
                      )}
                    </span>
                  )}
                </span>
                <span className="normal-case">{formatTime(m.created_at)}</span>
              </div>
              <p className="whitespace-pre-wrap [overflow-wrap:anywhere]">{m.text}</p>
              {m.quick_replies.length > 0 && (
                <div className="mt-1.5 flex flex-wrap gap-1">
                  {m.quick_replies.map((q) => (
                    <span key={q.id} className="rounded-full border border-stone-200 px-2 py-px text-[11px] text-stone-500">
                      {q.label}
                    </span>
                  ))}
                </div>
              )}
            </div>
          </li>
        )
      })}
    </ol>
  )
}
