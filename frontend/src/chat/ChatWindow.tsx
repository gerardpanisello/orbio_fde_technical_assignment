import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link } from 'react-router'
import { Icon } from '../components/Icon'
import { LogoMark } from '../components/Logo'
import { Spinner } from '../components/States'
import { formatSlot } from '../lib/format'
import { CHAT_TEXT } from './i18n'
import { MessageBubble } from './MessageBubble'
import { QuickReplies } from './QuickReplies'
import { TypingIndicator } from './TypingIndicator'
import type { useChat } from './useChat'

type Chat = ReturnType<typeof useChat>

/** The WhatsApp-like conversation screen (FR-1, FR-2, FR-5, FR-6, NFR-4). */
export function ChatWindow({ chat, slot }: { chat: Chat; slot: string | null }) {
  const t = CHAT_TEXT[chat.language]
  const [draft, setDraft] = useState('')
  const bottom = useRef<HTMLDivElement>(null)
  const { messages, typing, status } = chat

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages, typing, status])

  const last = messages.at(-1)
  const lastAgentIndex = messages.findLastIndex((m) => m.role === 'agent')
  const showReplies = !!last && last.role === 'agent' && !typing

  function submit(event: FormEvent) {
    event.preventDefault()
    if (!draft.trim() || typing) return
    chat.send(draft)
    setDraft('')
  }

  return (
    <div className="flex h-full flex-col bg-wa-bg">
      <header className="flex items-center gap-2 bg-wa-header px-2 py-2 text-white">
        <Link to="/" className="rounded-full p-1.5 hover:bg-white/10" aria-label="Volver al inicio">
          <Icon name="arrowLeft" className="size-5" />
        </Link>
        <div className="relative">
          <LogoMark className="size-9 rounded-full" />
        </div>
        <div className="min-w-0 flex-1 leading-tight">
          <div className="truncate text-[15px] font-semibold">Sofi · Grupo Sazón</div>
          <div className="text-xs text-white/80" aria-live="polite">
            {typing ? t.typing : t.online}
          </div>
        </div>
        <button
          type="button"
          onClick={chat.reset}
          className="rounded-full p-2 hover:bg-white/10"
          title={t.newChat}
          aria-label={t.newChat}
        >
          <Icon name="refresh" className="size-5" />
        </button>
      </header>

      <div className="wa-wallpaper scrollbar-thin flex-1 overflow-y-auto pb-3">
        {chat.phase === 'restoring' && !chat.error && (
          <div className="flex justify-center pt-10 text-wa-meta">
            <Spinner className="size-5" />
          </div>
        )}
        {chat.error === 'restore' && (
          <div className="mx-6 mt-10 rounded-lg bg-white p-4 text-center text-sm shadow-sm">
            <p className="text-wa-ink">{t.restoreFailed}</p>
            <div className="mt-3 flex justify-center gap-2">
              <button
                type="button"
                className="rounded-full bg-wa-green px-4 py-1.5 text-sm font-medium text-white"
                onClick={() => chat.conversationId && chat.restore(chat.conversationId)}
              >
                {t.retry}
              </button>
              <button
                type="button"
                className="rounded-full px-4 py-1.5 text-sm font-medium text-wa-header hover:bg-stone-100"
                onClick={chat.reset}
              >
                {t.newChat}
              </button>
            </div>
          </div>
        )}

        {chat.phase === 'chat' && (
          <>
            <div className="flex justify-center pt-3">
              <span className="rounded-md bg-white/90 px-2.5 py-1 text-[11.5px] font-medium text-wa-meta shadow-[0_1px_0.5px_rgba(11,20,26,0.13)]">
                {t.today}
              </span>
            </div>
            <p className="mx-auto mt-2 mb-1 max-w-[88%] rounded-md bg-[#ffeecd] px-3 py-1.5 text-center text-[11.5px] leading-snug text-[#54656f]">
              {t.notice}
            </p>
          </>
        )}

        <div role="log" aria-live="polite" aria-label="Conversación con Sofi">
          {messages.map((message, i) => (
            <div key={message.key}>
              <MessageBubble
                message={message}
                first={i === 0 || messages[i - 1].role !== message.role}
                read={i < lastAgentIndex || chat.status !== 'in_progress'}
                language={chat.language}
                onRetry={chat.retry}
              />
              {showReplies && i === messages.length - 1 && (
                <QuickReplies
                  replies={message.quickReplies}
                  onPick={chat.send}
                  disabled={typing}
                  label={t.quickReplies}
                />
              )}
            </div>
          ))}
        </div>
        {typing && <TypingIndicator />}

        {status !== 'in_progress' && !typing && chat.phase === 'chat' && (
          <FinalBanner status={status} slot={slot} chat={chat} />
        )}
        <div ref={bottom} />
      </div>

      <form onSubmit={submit} className="flex items-center gap-2 bg-[#f0f2f5] px-2 py-2">
        <label htmlFor="chat-input" className="sr-only">
          {t.placeholder}
        </label>
        <input
          id="chat-input"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder={t.placeholder}
          autoComplete="off"
          maxLength={4000}
          disabled={chat.phase !== 'chat'}
          className="h-10 min-w-0 flex-1 rounded-full bg-white px-4 text-[15px] text-wa-ink placeholder:text-wa-meta focus:outline-none focus-visible:ring-2 focus-visible:ring-wa-green/40"
        />
        <button
          type="submit"
          disabled={!draft.trim() || typing || chat.phase !== 'chat'}
          aria-label={t.send}
          className="grid size-10 shrink-0 place-items-center rounded-full bg-wa-green text-white transition hover:brightness-95 disabled:opacity-60"
        >
          <Icon name="send" className="size-5 -translate-x-px" />
        </button>
      </form>
    </div>
  )
}

function FinalBanner({ status, slot, chat }: { status: Chat['status']; slot: string | null; chat: Chat }) {
  if (status === 'in_progress') return null
  const t = CHAT_TEXT[chat.language]
  const booked = status === 'interview_scheduled'
  return (
    <div className="mt-4 flex justify-center px-6" role="status">
      <div
        className={`flex items-center gap-2 rounded-lg px-3 py-2 text-[13px] font-medium shadow-[0_1px_0.5px_rgba(11,20,26,0.13)] ${
          booked ? 'bg-[#d9fdd3] text-[#0b5d3b]' : 'bg-white/95 text-wa-meta'
        }`}
      >
        <Icon
          name={booked ? 'calendar' : status === 'waitlisted' ? 'clock' : 'check'}
          className="size-4 shrink-0"
        />
        <span>
          {t.banner[status]}
          {booked && slot && `: ${formatSlot(slot, chat.language)}`}
        </span>
      </div>
    </div>
  )
}
