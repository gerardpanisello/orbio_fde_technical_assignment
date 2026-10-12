import { useCallback, useEffect, useRef, useState } from 'react'
import { api, type Country, type Language } from '../api/client'
import { splitSentences } from './speakable'
import { pickVoice, speechLang } from './voiceLogic'

export type VoiceEngine = 'checking' | 'elevenlabs' | 'browser'

/** After this many ElevenLabs failures in a row, stay on the browser voice. */
const MAX_PROVIDER_FAILURES = 2

/**
 * Spec 013 FR-5: Sofi's voice. ElevenLabs through our backend when it is configured
 * (`GET /api/voice/status`), the browser's speechSynthesis otherwise or when a request
 * fails. `speak()` never rejects: it resolves `true` when she finished, `false` when
 * `cancel()` cut her off (the caller decides whether to say it again).
 */
export function useSpeaker({ language, country }: { language: Language; country: Country | null }) {
  const [engine, setEngine] = useState<VoiceEngine>('checking')
  const [speaking, setSpeaking] = useState(false)
  const engineRef = useRef<VoiceEngine>('checking')
  const failures = useRef(0)
  const generation = useRef(0) // bumped by cancel(): stale playbacks stop
  const stopCurrent = useRef<(() => void) | null>(null)
  const ready = useRef<Promise<void>>(Promise.resolve())

  useEffect(() => {
    let alive = true
    function use(value: VoiceEngine) {
      engineRef.current = value
      if (alive) setEngine(value)
    }
    ready.current = api
      .voiceStatus()
      .then((s) => use(s.tts))
      .catch(() => use('browser'))
    return () => {
      alive = false
    }
  }, [])

  const playAudio = useCallback(async (blob: Blob, gen: number) => {
    const url = URL.createObjectURL(blob)
    try {
      const audio = new Audio(url)
      await new Promise<void>((resolve, reject) => {
        stopCurrent.current = () => {
          audio.pause()
          resolve()
        }
        audio.onended = () => resolve()
        audio.onerror = () => reject(new Error('audio error'))
        if (gen !== generation.current) return resolve()
        audio.play().catch(reject) // autoplay blocked -> browser voice
      })
    } finally {
      stopCurrent.current = null
      URL.revokeObjectURL(url)
    }
  }, [])

  const speakWithBrowser = useCallback(
    async (text: string, gen: number) => {
      const synth = typeof window !== 'undefined' ? window.speechSynthesis : undefined
      if (!synth || typeof SpeechSynthesisUtterance === 'undefined') return // text is on screen
      const lang = speechLang(language, country)
      const voice = pickVoice(synth.getVoices(), lang)
      for (const chunk of splitSentences(text)) {
        if (gen !== generation.current) return
        await new Promise<void>((resolve) => {
          const utterance = new SpeechSynthesisUtterance(chunk)
          utterance.lang = voice?.lang ?? lang
          if (voice) utterance.voice = voice
          utterance.rate = 1.03
          // Chrome sometimes never fires onend: don't let the conversation hang on it.
          const safety = setTimeout(resolve, 2500 + chunk.length * 110)
          const finish = () => {
            clearTimeout(safety)
            resolve()
          }
          utterance.onend = finish
          utterance.onerror = finish
          stopCurrent.current = () => {
            synth.cancel()
            finish()
          }
          synth.speak(utterance)
        })
        stopCurrent.current = null
      }
    },
    [language, country],
  )

  const speak = useCallback(
    async (text: string): Promise<boolean> => {
      if (!text.trim()) return true
      const gen = ++generation.current
      const current = () => gen === generation.current
      setSpeaking(true)
      try {
        await ready.current // the first message waits for GET /api/voice/status
        if (!current()) return false
        if (engineRef.current === 'elevenlabs') {
          try {
            const blob = await api.tts(text, language, country)
            if (!current()) return false
            await playAudio(blob, gen)
            failures.current = 0
            return current()
          } catch {
            failures.current += 1
            if (failures.current >= MAX_PROVIDER_FAILURES) {
              engineRef.current = 'browser'
              setEngine('browser')
            }
            if (!current()) return false
          }
        }
        await speakWithBrowser(text, gen)
        return current()
      } finally {
        if (gen === generation.current) setSpeaking(false)
      }
    },
    [country, language, playAudio, speakWithBrowser],
  )

  const cancel = useCallback(() => {
    generation.current++
    stopCurrent.current?.()
    stopCurrent.current = null
    if (typeof window !== 'undefined') window.speechSynthesis?.cancel()
    setSpeaking(false)
  }, [])

  useEffect(() => cancel, [cancel])

  // Browsers load their voice list lazily; asking early makes the first utterance pick well.
  useEffect(() => {
    if (typeof window !== 'undefined') window.speechSynthesis?.getVoices()
  }, [])

  return { engine, speaking, speak, cancel }
}
