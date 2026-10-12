import { useCallback, useEffect, useRef, useState } from 'react'
import {
  ApiError,
  api,
  type ChatMessage,
  type Country,
  type Language,
  type QuickReply,
  type Status,
  type Turn,
} from '../api/client'

const STORAGE_KEY = 'sazon.chat.conversationId'
/** Minimum time the typing indicator shows, so instant (fake-mode) replies still feel human. */
const MIN_TYPING_MS = 650

export type Delivery = 'sending' | 'sent' | 'failed'

export type UiMessage = {
  key: string
  role: 'agent' | 'candidate'
  text: string
  quickReplies: QuickReply[]
  createdAt: string
  delivery?: Delivery // candidate messages only
}

type Phase = 'restoring' | 'start' | 'starting' | 'chat'

function fromServer(message: ChatMessage): UiMessage {
  return {
    key: `m${message.id}`,
    role: message.role,
    text: message.text,
    quickReplies: message.quick_replies,
    createdAt: message.created_at,
    delivery: message.role === 'candidate' ? 'sent' : undefined,
  }
}

function readStoredId(): string | null {
  try {
    return sessionStorage.getItem(STORAGE_KEY)
  } catch {
    return null
  }
}

function storeId(id: string | null) {
  try {
    if (id) sessionStorage.setItem(STORAGE_KEY, id)
    else sessionStorage.removeItem(STORAGE_KEY)
  } catch {
    // storage blocked (private mode): the chat still works, it just won't survive a reload
  }
}

const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))
let localCounter = 0

/**
 * The candidate chat's state (FR-1..6): start, send, retry, restore from sessionStorage.
 * The backend is the source of truth; this only keeps what the screen needs.
 */
export function useChat(onTurn?: (conversationId: string) => void) {
  const [conversationId, setConversationId] = useState<string | null>(readStoredId)
  const [phase, setPhase] = useState<Phase>(conversationId ? 'restoring' : 'start')
  const [messages, setMessages] = useState<UiMessage[]>([])
  const [status, setStatus] = useState<Status>('in_progress')
  const [language, setLanguage] = useState<Language>('es')
  const [typing, setTyping] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const restored = useRef(false)

  // FR-4: reload restores the transcript.
  const restore = useCallback(async (id: string) => {
    setPhase('restoring')
    setError(null)
    try {
      const conversation = await api.getConversation(id)
      setMessages(conversation.messages.map(fromServer))
      setStatus(conversation.status)
      setLanguage(conversation.language)
      setPhase('chat')
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) {
        storeId(null)
        setConversationId(null)
        setPhase('start')
      } else {
        setError('restore')
      }
    }
  }, [])

  useEffect(() => {
    if (conversationId && !restored.current) {
      restored.current = true
      void restore(conversationId)
    }
  }, [conversationId, restore])

  const start = useCallback(async (lang: Language, country: Country) => {
    setPhase('starting')
    setError(null)
    try {
      const conversation = await api.startConversation(lang, country)
      storeId(conversation.id)
      restored.current = true
      setConversationId(conversation.id)
      setLanguage(conversation.language)
      setStatus(conversation.status)
      setTyping(true)
      await wait(MIN_TYPING_MS) // Sofi "types" her greeting
      setTyping(false)
      setMessages(conversation.messages.map(fromServer))
      setPhase('chat')
    } catch {
      setTyping(false)
      setError('start')
      setPhase('start')
    }
  }, [])

  const deliver = useCallback(
    async (key: string, text: string) => {
      if (!conversationId) return
      setTyping(true)
      const startedAt = Date.now()
      try {
        const turn = await api.sendMessage(conversationId, text)
        await wait(Math.max(0, MIN_TYPING_MS - (Date.now() - startedAt)))
        setMessages((current) => {
          const next = current.map((m) =>
            m.key === key ? { ...m, delivery: 'sent' as const } : m,
          )
          if (turn.reply) {
            next.push({
              key: `r${++localCounter}`,
              role: 'agent',
              text: turn.reply.text,
              quickReplies: turn.reply.quick_replies,
              createdAt: new Date().toISOString(),
            })
          }
          return next
        })
        setStatus(turn.status)
        onTurn?.(conversationId)
      } catch {
        // FR-6: never a blank screen; the bubble offers a retry.
        setMessages((current) =>
          current.map((m) => (m.key === key ? { ...m, delivery: 'failed' as const } : m)),
        )
      } finally {
        setTyping(false)
      }
    },
    [conversationId, onTurn],
  )

  const send = useCallback(
    (raw: string) => {
      const text = raw.trim()
      if (!text || typing) return
      const key = `c${++localCounter}`
      setMessages((current) => [
        ...current,
        {
          key,
          role: 'candidate',
          text,
          quickReplies: [],
          createdAt: new Date().toISOString(),
          delivery: 'sending',
        },
      ])
      void deliver(key, text)
    },
    [deliver, typing],
  )

  const retry = useCallback(
    (key: string) => {
      const message = messages.find((m) => m.key === key)
      if (!message || typing) return
      setMessages((current) =>
        current.map((m) => (m.key === key ? { ...m, delivery: 'sending' as const } : m)),
      )
      void deliver(key, message.text)
    },
    [deliver, messages, typing],
  )

  const reset = useCallback(() => {
    storeId(null)
    setConversationId(null)
    setMessages([])
    setStatus('in_progress')
    setTyping(false)
    setError(null)
    setPhase('start')
  }, [])

  /** Dev helper: the silence timer fired (spec 004 FR-13); show whatever the agent sent. */
  const applyTurn = useCallback(
    (turn: Turn) => {
      const reply = turn.reply
      if (reply) {
        setMessages((current) => [
          ...current,
          {
            key: `r${++localCounter}`,
            role: 'agent',
            text: reply.text,
            quickReplies: reply.quick_replies,
            createdAt: new Date().toISOString(),
          },
        ])
      }
      setStatus(turn.status)
      if (conversationId) onTurn?.(conversationId)
    },
    [conversationId, onTurn],
  )

  return {
    conversationId,
    phase,
    messages,
    status,
    language,
    typing,
    error,
    start,
    send,
    retry,
    reset,
    restore,
    applyTurn,
  }
}
