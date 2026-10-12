import { useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router'
import type { Country, QuickReply } from '../api/client'
import { keys, useCandidate } from '../api/queries'
import { CHAT_TEXT } from '../chat/i18n'
import { StartScreen } from '../chat/StartScreen'
import { useChat, type UiMessage } from '../chat/useChat'
import { Icon } from '../components/Icon'
import { Logo, LogoMark } from '../components/Logo'
import { Spinner } from '../components/States'
import { formatSlot } from '../lib/format'
import { MicButton } from './MicButton'
import { toSpeakable } from './speakable'
import { useSpeaker } from './useSpeaker'
import { useSpeechRecognition } from './useSpeechRecognition'
import {
  afterListening,
  canListen,
  getRecognitionCtor,
  shouldAutoListen,
  speechLang,
  voicePhase,
  type MicProblem,
} from './voiceLogic'
import { VOICE_TEXT } from './voiceText'

const STORAGE_KEY = 'sazon.voice.conversationId'
const COUNTRY_KEY = 'sazon.voice.country'
const AUTO_KEY = 'sazon.voice.autoListen'

function readCountry(): Country | null {
  try {
    const value = sessionStorage.getItem(COUNTRY_KEY)
    return value === 'ES' || value === 'MX' ? value : null
  } catch {
    return null
  }
}

function storeCountry(country: Country) {
  try {
    sessionStorage.setItem(COUNTRY_KEY, country)
  } catch {
    // only used to pick the accent after a reload
  }
}

function readAutoListen(): boolean {
  try {
    return localStorage.getItem(AUTO_KEY) !== 'off'
  } catch {
    return true
  }
}

/**
 * /voz (spec 013): the same screening by voice. The browser turns speech into text, the
 * turn goes through the normal conversation API, and Sofi's reply is shown and spoken.
 */
export function VoicePage() {
  const queryClient = useQueryClient()
  const onTurn = useCallback(
    (id: string) => {
      void queryClient.invalidateQueries({ queryKey: keys.candidate(id) })
      void queryClient.invalidateQueries({ queryKey: keys.allCandidates })
    },
    [queryClient],
  )
  const chat = useChat(onTurn, { storageKey: STORAGE_KEY })
  const [country, setCountry] = useState<Country | null>(readCountry)
  const supported = useMemo(
    () => getRecognitionCtor(typeof window === 'undefined' ? undefined : window) !== null,
    [],
  )

  const starting = chat.phase === 'start' || chat.phase === 'starting'
  let screen
  if (starting && !supported) screen = <Unsupported />
  else if (starting)
    screen = (
      <StartScreen
        mode="voice"
        onStart={(language, c) => {
          storeCountry(c)
          setCountry(c)
          void chat.start(language, c)
        }}
        starting={chat.phase === 'starting'}
        failed={chat.error === 'start'}
      />
    )
  else screen = <VoiceCall chat={chat} country={country} supported={supported} />

  return (
    <div className="flex h-dvh flex-col bg-stone-50 md:bg-[radial-gradient(ellipse_at_top,var(--color-brand-50),transparent_60%)]">
      <header className="hidden items-center justify-between px-6 py-3 md:flex">
        <Link to="/" className="rounded-lg">
          <Logo subtitle="Entrevista por voz" />
        </Link>
        <div className="flex items-center gap-2">
          <Link to="/chat" className="btn-ghost">
            <Icon name="chat" /> Chat
          </Link>
          <Link to="/recruiter" className="btn-ghost">
            <Icon name="users" /> Panel recruiter
          </Link>
        </div>
      </header>
      <main className="min-h-0 flex-1 md:flex md:justify-center md:px-6 md:pb-6">
        <div className="h-full w-full overflow-hidden bg-white md:h-[min(820px,100%)] md:max-w-[440px] md:rounded-3xl md:border md:border-stone-200 md:shadow-xl md:shadow-stone-900/5">
          {screen}
        </div>
      </main>
    </div>
  )
}

type Chat = ReturnType<typeof useChat>
type Queued = { key: string; text: string; quickReplies: QuickReply[] }
type Latest = {
  heard: (text: string, problem: MicProblem) => void
  afterSpeaking: () => void
  speaker: ReturnType<typeof useSpeaker>
  recognizer: ReturnType<typeof useSpeechRecognition>
  language: Chat['language']
  country: Country | null
}

function VoiceCall({ chat, country, supported }: { chat: Chat; country: Country | null; supported: boolean }) {
  const language = chat.language
  const t = VOICE_TEXT[language]
  const speaker = useSpeaker({ language, country })
  const detail = useCandidate(chat.status === 'interview_scheduled' ? chat.conversationId : null)

  const [autoListen, setAutoListen] = useState(readAutoListen)
  const [misses, setMisses] = useState(0)
  const [notice, setNotice] = useState<string | null>(null)
  const [talking, setTalking] = useState(false) // the speech queue is busy
  const [speakingKey, setSpeakingKey] = useState<string | null>(null)
  const [heardProblem, setHeardProblem] = useState<MicProblem>(null)

  // Callbacks that outlive a render (speech queue, recognition end) read fresh values here.
  const latest = useRef<Latest | null>(null)
  const onDone = useCallback((text: string, problem: MicProblem) => {
    latest.current?.heard(text, problem)
  }, [])
  const recognizer = useSpeechRecognition({ lang: speechLang(language, country), onDone })
  const problem = recognizer.problem ?? heardProblem

  const phase = voicePhase({
    speaking: talking || speaker.speaking,
    thinking: chat.typing,
    listening: recognizer.listening,
    status: chat.status,
  })
  const micEnabled = canListen(phase, supported, problem) && chat.phase === 'chat'

  // --- Sofi's messages are spoken in order, each once ------------------------------------
  const queue = useRef<Queued[]>([])
  const spoken = useRef<Set<string> | null>(null)
  const restoredAtMount = useRef(chat.phase === 'restoring')
  const draining = useRef(false)
  const interruptions = useRef(0) // bumped when the candidate cuts Sofi off on purpose
  const mounted = useRef(false)
  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
    }
  }, [])

  async function drain() {
    if (draining.current) return
    draining.current = true
    setTalking(true)
    latest.current?.recognizer.abort() // never record Sofi herself
    while (queue.current.length) {
      const item = queue.current.shift()!
      const now = latest.current
      if (!now) break
      setSpeakingKey(item.key)
      const before = interruptions.current
      const finished = await now.speaker.speak(
        toSpeakable(item.text, {
          language: now.language,
          country: now.country,
          quickReplies: item.quickReplies.map((q) => q.label),
        }),
      )
      if (!finished && before === interruptions.current) {
        // Cut off by something other than the candidate (React's dev double mount, the
        // page closing): say it again if we are still here, else keep it for later.
        queue.current.unshift(item)
        if (!mounted.current) break
      }
    }
    draining.current = false
    setSpeakingKey(null)
    setTalking(false)
    latest.current?.afterSpeaking()
  }

  function enqueue(item: Queued) {
    queue.current.push(item)
    void drain()
  }

  useEffect(() => {
    if (chat.phase !== 'chat') return
    if (spoken.current === null) {
      // After a reload, the history is shown but not read aloud again.
      spoken.current = new Set(restoredAtMount.current ? chat.messages.map((m) => m.key) : [])
    }
    for (const message of chat.messages) {
      if (message.role !== 'agent' || spoken.current.has(message.key)) continue
      spoken.current.add(message.key)
      enqueue({ key: message.key, text: message.text, quickReplies: message.quickReplies })
    }
    // enqueue/drain read everything else through `latest`
  }, [chat.messages, chat.phase])

  // FR-6: after Sofi finishes, open the mic by ourselves (toggleable).
  function afterSpeaking() {
    const next = voicePhase({ speaking: false, thinking: chat.typing, listening: false, status: chat.status })
    if (chat.phase === 'chat' && shouldAutoListen({ autoListen, phase: next, misses, supported, problem })) {
      recognizer.start('tap')
    }
  }

  function heard(text: string, micIssue: MicProblem) {
    const next = afterListening(text, misses, micIssue)
    if (next.kind === 'send') {
      setMisses(0)
      setNotice(null)
      chat.send(next.text)
    } else if (next.kind === 'reprompt') {
      setMisses(next.misses)
      setNotice(t.notHeard)
      enqueue({ key: `notHeard${next.misses}`, text: t.notHeard, quickReplies: [] })
    } else {
      setHeardProblem(micIssue)
    }
  }

  // A layout effect runs before every passive effect, so the speech queue never sees null.
  useLayoutEffect(() => {
    latest.current = { heard, afterSpeaking, speaker, recognizer, language, country }
  })

  function startListening() {
    // Guard on the queue itself, not the rendered phase: Sofi may have started a few ms
    // before the button re-rendered as disabled.
    if (draining.current || queue.current.length || chat.typing) return
    setNotice(null)
    setHeardProblem(null)
    setMisses(0)
    recognizer.start('tap')
  }

  function pick(label: string) {
    // FR-7: tapping a quick reply still works, and interrupts Sofi.
    interruptions.current++
    queue.current = []
    speaker.cancel()
    recognizer.abort()
    setMisses(0)
    setNotice(null)
    chat.send(label)
  }

  function toggleAuto() {
    setAutoListen((current) => {
      try {
        localStorage.setItem(AUTO_KEY, current ? 'off' : 'on')
      } catch {
        // preference only
      }
      return !current
    })
  }

  const lastAgent = chat.messages.findLast((m) => m.role === 'agent')
  const shown = (speakingKey && chat.messages.find((m) => m.key === speakingKey)) || lastAgent
  const replies =
    lastAgent && chat.messages.at(-1) === lastAgent && !chat.typing && chat.status === 'in_progress'
      ? lastAgent.quickReplies
      : []

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <header className="flex items-center gap-2 border-b border-stone-100 px-2 py-2">
        <Link to="/" className="rounded-full p-1.5 text-stone-600 hover:bg-stone-100" aria-label={t.back}>
          <Icon name="arrowLeft" className="size-5" />
        </Link>
        <LogoMark className="size-9 rounded-full" />
        <div className="min-w-0 flex-1 leading-tight">
          <div className="truncate text-[15px] font-semibold text-stone-900">Sofi · Grupo Sazón</div>
          <div className="text-xs text-stone-500" aria-live="polite" data-testid="voice-phase">
            {t.phase[phase]}
          </div>
        </div>
        <span
          className="rounded-full border border-stone-200 px-2 py-0.5 text-[11px] text-stone-500"
          title={speaker.engine === 'browser' ? 'ELEVENLABS_API_KEY no configurada o no disponible' : undefined}
          data-testid="voice-engine"
        >
          {t.engine[speaker.engine]}
        </span>
        <button
          type="button"
          onClick={chat.reset}
          className="rounded-full p-2 text-stone-600 hover:bg-stone-100"
          title={t.newCall}
          aria-label={t.newCall}
        >
          <Icon name="refresh" className="size-5" />
        </button>
      </header>

      {/* Stage: what Sofi is saying now */}
      <section className="bg-gradient-to-b from-brand-50 to-white px-5 pt-5 pb-4" aria-live="polite">
        {chat.phase === 'restoring' && !chat.error && (
          <div className="flex justify-center py-6 text-stone-400">
            <Spinner className="size-5" />
          </div>
        )}
        {chat.error === 'restore' && (
          <div className="rounded-xl bg-white p-4 text-center text-sm shadow-sm">
            <p>{CHAT_TEXT[language].restoreFailed}</p>
            <div className="mt-3 flex justify-center gap-2">
              <button
                type="button"
                className="btn-primary"
                onClick={() => chat.conversationId && chat.restore(chat.conversationId)}
              >
                {CHAT_TEXT[language].retry}
              </button>
              <button type="button" className="btn-ghost" onClick={chat.reset}>
                {t.newCall}
              </button>
            </div>
          </div>
        )}
        {shown && (
          <div className="flex gap-3">
            <div className="relative mt-0.5 shrink-0">
              <LogoMark className="size-10 rounded-full" />
              {phase === 'speaking' && (
                <span className="absolute -right-1 -bottom-1 grid size-5 place-items-center rounded-full bg-white text-brand-600 shadow">
                  <Icon name="volume" className="size-3.5" />
                </span>
              )}
            </div>
            <p
              className={`text-[17px] leading-snug whitespace-pre-wrap ${phase === 'speaking' ? 'text-stone-900' : 'text-stone-700'}`}
              data-testid="voice-current"
            >
              {shown.text}
            </p>
          </div>
        )}
        {replies.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-1.5 pl-[52px]" role="group" aria-label={CHAT_TEXT[language].quickReplies}>
            {replies.map((reply) => (
              <button
                key={reply.id}
                type="button"
                onClick={() => pick(reply.label)}
                className="rounded-full border border-brand-200 bg-white px-3 py-1.5 text-[13px] font-medium text-brand-800 shadow-xs transition hover:bg-brand-50 active:scale-95"
              >
                {reply.label}
              </button>
            ))}
          </div>
        )}
        {chat.status !== 'in_progress' && chat.phase === 'chat' && (
          <EndBanner chat={chat} slot={detail.data?.candidate.interview_slot ?? null} />
        )}
      </section>

      {/* Transcript */}
      <Transcript messages={chat.messages} speakingKey={speakingKey} chat={chat} />

      {/* Mic bar */}
      <footer className="border-t border-stone-100 bg-white px-4 pt-2 pb-[max(env(safe-area-inset-bottom),12px)]">
        <div className="min-h-[2.75rem] text-center" aria-live="polite">
          {problem ? (
            <p className="text-sm text-red-700" role="alert">
              {t.problem[problem]}{' '}
              <Link to="/chat" className="font-medium underline">
                {t.typeInstead}
              </Link>
            </p>
          ) : recognizer.listening ? (
            <p className="text-[15px] text-stone-900" data-testid="voice-live">
              {recognizer.live || <span className="text-stone-400">…</span>}
            </p>
          ) : notice ? (
            <p className="text-sm text-amber-700">{notice}</p>
          ) : phase === 'idle' ? (
            <p className="text-xs text-stone-500">{t.hint}</p>
          ) : null}
        </div>
        <div className="flex items-center justify-between">
          <label className="flex w-24 cursor-pointer flex-col items-start gap-1 text-[11px] leading-tight text-stone-500">
            <input
              type="checkbox"
              role="switch"
              checked={autoListen}
              onChange={toggleAuto}
              className="peer sr-only"
            />
            <span
              aria-hidden="true"
              className="relative h-5 w-9 rounded-full bg-stone-300 transition peer-checked:bg-brand-600 peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-brand-500 after:absolute after:top-0.5 after:left-0.5 after:size-4 after:rounded-full after:bg-white after:transition peer-checked:after:translate-x-4"
            />
            {t.autoListen}
          </label>
          <MicButton
            phase={phase}
            enabled={micEnabled}
            label={t.button[phase]}
            onStart={startListening}
            onStop={recognizer.stop}
          />
          <Link to="/chat" className="w-24 text-right text-[11px] leading-tight text-stone-500 underline-offset-2 hover:underline">
            {t.typeInstead}
          </Link>
        </div>
        <p className="mt-1 text-center text-xs font-medium text-stone-600" aria-hidden="true">
          {t.button[phase]}
        </p>
      </footer>
    </div>
  )
}

function Transcript({
  messages,
  speakingKey,
  chat,
}: {
  messages: UiMessage[]
  speakingKey: string | null
  chat: Chat
}) {
  const t = VOICE_TEXT[chat.language]
  const bottom = useRef<HTMLDivElement>(null)
  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages.length, chat.typing])

  return (
    <section className="scrollbar-thin min-h-0 flex-1 overflow-y-auto px-4 py-3" aria-label={t.transcript}>
      <h2 className="eyebrow mb-2 text-[11px] font-semibold tracking-wide text-stone-400 uppercase">{t.transcript}</h2>
      {messages.length === 0 && <p className="text-sm text-stone-400">{t.empty}</p>}
      <ol role="log" className="space-y-1.5" data-testid="voice-transcript">
        {messages.map((m) => {
          const mine = m.role === 'candidate'
          return (
            <li key={m.key} className={`flex ${mine ? 'justify-end' : 'justify-start'}`}>
              <div
                className={`max-w-[85%] rounded-2xl px-3 py-1.5 text-[13.5px] leading-snug whitespace-pre-wrap [overflow-wrap:anywhere] ${
                  mine ? 'rounded-br-md bg-brand-600 text-white' : 'rounded-bl-md bg-stone-100 text-stone-800'
                } ${m.key === speakingKey ? 'ring-2 ring-brand-300' : ''}`}
              >
                <span className="sr-only">{mine ? `${t.you}: ` : 'Sofi: '}</span>
                {m.text}
                {m.delivery === 'failed' && (
                  <button
                    type="button"
                    onClick={() => chat.retry(m.key)}
                    className="mt-1 block text-xs font-medium text-white underline"
                  >
                    {CHAT_TEXT[chat.language].notSent} · {CHAT_TEXT[chat.language].retry}
                  </button>
                )}
              </div>
            </li>
          )
        })}
        {chat.typing && (
          <li className="flex justify-start">
            <span className="rounded-2xl rounded-bl-md bg-stone-100 px-3 py-2 text-stone-400">
              <Spinner className="size-3" />
            </span>
          </li>
        )}
      </ol>
      <div ref={bottom} />
    </section>
  )
}

function EndBanner({ chat, slot }: { chat: Chat; slot: string | null }) {
  if (chat.status === 'in_progress') return null
  const booked = chat.status === 'interview_scheduled'
  return (
    <div
      role="status"
      data-testid="voice-end"
      className={`mt-4 flex items-center gap-2 rounded-xl px-3 py-2 text-[13px] font-medium ${
        booked ? 'bg-emerald-50 text-emerald-800 ring-1 ring-emerald-200' : 'bg-stone-100 text-stone-700'
      }`}
    >
      <Icon name={booked ? 'calendar' : chat.status === 'waitlisted' ? 'clock' : 'check'} className="size-4 shrink-0" />
      <span>
        {CHAT_TEXT[chat.language].banner[chat.status]}
        {booked && slot && `: ${formatSlot(slot, chat.language)}`}
      </span>
    </div>
  )
}

function Unsupported() {
  const t = VOICE_TEXT.es
  return (
    <div className="flex h-full flex-col items-center justify-center px-8 text-center" data-testid="voice-unsupported">
      <div className="grid size-14 place-items-center rounded-full bg-brand-50 text-brand-600">
        <Icon name="mic" className="size-7" />
      </div>
      <h1 className="mt-4 text-lg font-semibold text-stone-900">{t.unsupportedTitle}</h1>
      <p className="mt-2 text-sm text-stone-600">{t.unsupportedText}</p>
      <Link to="/chat" className="btn-primary mt-6">
        <Icon name="chat" /> {t.openChat}
      </Link>
      <Link to="/" className="btn-ghost mt-2">
        {t.back}
      </Link>
    </div>
  )
}
