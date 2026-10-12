import { Fragment } from 'react'
import type { Language } from '../api/client'
import { formatTime } from '../lib/format'
import { followUpLabel } from '../lib/reengagement'
import { CHAT_TEXT } from './i18n'
import { Tail } from './TypingIndicator'
import type { UiMessage } from './useChat'

const URL_RE = /(https?:\/\/[^\s]+)/g

/** Plain text with clickable links (the greeting carries the privacy URL). */
function Linkified({ text }: { text: string }) {
  return text.split(URL_RE).map((part, i) =>
    i % 2 === 1 ? (
      <a
        key={i}
        href={part}
        target="_blank"
        rel="noreferrer"
        className="break-all text-[#027eb5] underline-offset-2 hover:underline"
      >
        {part}
      </a>
    ) : (
      <Fragment key={i}>{part}</Fragment>
    ),
  )
}

export function MessageBubble({
  message,
  first,
  read,
  language,
  onRetry,
  followUpTotal = null,
}: {
  message: UiMessage
  followUpTotal?: number | null
  first: boolean // first of a group: gets the tail
  read: boolean // the agent answered after it: blue ticks
  language: Language
  onRetry: (key: string) => void
}) {
  const followUp = message.role === 'agent' && message.followUpStep != null
  const mine = message.role === 'candidate'
  const t = CHAT_TEXT[language]
  return (
    <div
      className={`flex animate-pop ${mine ? 'justify-end pr-3' : 'justify-start pl-3'} ${first ? 'mt-2' : 'mt-0.5'}`}
    >
      <div className={`flex max-w-[85%] flex-col ${mine ? 'items-end' : 'items-start'}`}>
        <div
          className={`relative rounded-lg px-2 pt-1.5 pb-1 text-[14.2px] leading-[19px] text-wa-ink shadow-[0_1px_0.5px_rgba(11,20,26,0.13)] ${
            mine ? 'bg-wa-out' : 'bg-white'
          } ${first ? (mine ? 'rounded-tr-none' : 'rounded-tl-none') : ''}`}
        >
          {first && <Tail side={mine ? 'right' : 'left'} />}
          {followUp && (
            // Spec 008: a reminder Sofi sent on her own. The template tag is a demo hint for
            // reminders past WhatsApp's 24 h window (in production: an approved template).
            <span className="mb-0.5 flex items-center gap-1.5 text-[11px] text-wa-meta">
              {followUpLabel(message.followUpStep!, followUpTotal, language)}
              {message.requiresTemplate && (
                <span
                  className="rounded border border-wa-meta/30 px-1 text-[10px] leading-tight"
                  title="Fuera de la ventana de 24 h de WhatsApp: en producción se envía como plantilla aprobada"
                >
                  plantilla WhatsApp
                </span>
              )}
            </span>
          )}
          <span className="whitespace-pre-wrap [overflow-wrap:anywhere]">
            <Linkified text={message.text} />
          </span>
          {/* Spacer: reserves room so the time never overlaps the last line. */}
          <span className={`inline-block ${mine ? 'w-[66px]' : 'w-[44px]'}`} aria-hidden="true" />
          <span className="absolute right-2 bottom-1 flex items-center gap-1 text-[11px] text-wa-meta">
            {formatTime(message.createdAt, language)}
            {mine && <Ticks delivery={message.delivery} read={read} />}
          </span>
        </div>
        {message.delivery === 'failed' && (
          <button
            type="button"
            onClick={() => onRetry(message.key)}
            className="mt-1 flex items-center gap-1 rounded px-1 text-xs font-medium text-red-600 hover:underline"
          >
            <span className="grid size-3.5 place-items-center rounded-full bg-red-600 text-[10px] font-bold text-white">
              !
            </span>
            {t.notSent} · {t.retry}
          </button>
        )}
      </div>
    </div>
  )
}

function Ticks({ delivery, read }: { delivery?: UiMessage['delivery']; read: boolean }) {
  if (delivery === 'sending') {
    return (
      <svg viewBox="0 0 16 16" className="size-3.5" role="img" aria-label="Enviando">
        <circle cx="8" cy="8" r="6" fill="none" stroke="currentColor" strokeWidth="1.4" />
        <path
          d="M8 4.5V8l2 1.5"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.4"
          strokeLinecap="round"
        />
      </svg>
    )
  }
  if (delivery === 'failed') return null
  return (
    <svg
      viewBox="0 0 18 12"
      className={`h-3 w-[18px] ${read ? 'text-wa-tick' : 'text-wa-meta'}`}
      role="img"
      aria-label={read ? 'Leído' : 'Entregado'}
    >
      <path
        d="M1 6.5 4.5 10 11 2.5M7.5 9.2 8.3 10 14.8 2.5"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}
