import type { ChatMessage } from '../../api/client'
import { EmptyState } from '../../components/States'
import { formatTime } from '../../lib/format'

/** The stored conversation, read-only, in the same left/right layout as the chat. */
export function Transcript({ messages }: { messages: ChatMessage[] }) {
  if (!messages.length) return <EmptyState icon="chat" title="Sin mensajes" />
  return (
    <ol className="space-y-1.5" aria-label="Transcripción">
      {messages.map((m) => {
        const agent = m.role === 'agent'
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
                <span>{agent ? 'Sofi' : 'Candidato'}</span>
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
