import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  getRecognitionCtor,
  heardText,
  micProblem,
  NOTHING_HEARD_MS,
  readResults,
  SILENCE_MS,
  type MicProblem,
  type RecognitionLike,
} from './voiceLogic'

export type ListenMode = 'tap' | 'hold'

/**
 * Spec 013 FR-2: the browser's speech-to-text (Chrome/Edge). Thin wrapper; the rules
 * are in voiceLogic.ts.
 * - `start('tap')`: listens until a pause (SILENCE_MS after the last settled words).
 * - `start('hold')`: push-to-talk, listens until `stop()` (the button is released).
 * - `onDone(text, problem)` fires once per turn, with "" when nothing was heard.
 */
export function useSpeechRecognition({
  lang,
  onDone,
}: {
  lang: string
  onDone: (text: string, problem: MicProblem) => void
}) {
  const Ctor = useMemo(() => getRecognitionCtor(typeof window === 'undefined' ? undefined : window), [])
  const [listening, setListening] = useState(false)
  const [live, setLive] = useState('') // what has been heard so far (final + interim)
  const [problem, setProblem] = useState<MicProblem>(null)
  const recognition = useRef<RecognitionLike | null>(null)
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const done = useRef(onDone)
  useEffect(() => {
    done.current = onDone
  }, [onDone])

  const clearTimer = () => {
    if (timer.current) clearTimeout(timer.current)
    timer.current = null
  }

  const stop = useCallback(() => {
    clearTimer()
    recognition.current?.stop() // results still arrive, then onend
  }, [])

  /** Drop the turn without sending (e.g. Sofi is about to speak). */
  const abort = useCallback(() => {
    clearTimer()
    const current = recognition.current
    recognition.current = null
    if (current) {
      current.onend = null
      current.onresult = null
      current.onerror = null
      current.abort()
    }
    setListening(false)
    setLive('')
  }, [])

  const start = useCallback(
    (mode: ListenMode) => {
      if (!Ctor || recognition.current) return
      const rec = new Ctor()
      rec.lang = lang
      rec.continuous = true // we decide when the turn ends (pause or button release)
      rec.interimResults = true
      rec.maxAlternatives = 1
      let heard = { final: '', interim: '' }
      let turnProblem: MicProblem = null
      const armSilence = (ms: number) => {
        if (mode !== 'tap') return
        clearTimer()
        timer.current = setTimeout(() => rec.stop(), ms)
      }
      rec.onresult = (event) => {
        heard = readResults(event.results)
        setLive(heardText(heard))
        // Settled words and nothing pending: a short pause ends the turn.
        armSilence(heard.interim ? SILENCE_MS * 2 : SILENCE_MS)
      }
      rec.onerror = (event) => {
        turnProblem = micProblem(event.error)
        if (turnProblem) setProblem(turnProblem)
      }
      rec.onend = () => {
        clearTimer()
        if (recognition.current !== rec) return
        recognition.current = null
        setListening(false)
        setLive('')
        done.current(heardText(heard), turnProblem)
      }
      recognition.current = rec
      setProblem(null)
      setLive('')
      setListening(true)
      armSilence(NOTHING_HEARD_MS)
      try {
        rec.start()
      } catch {
        // already started / not allowed without a gesture: report an empty turn
        recognition.current = null
        setListening(false)
        done.current('', null)
      }
    },
    [Ctor, lang],
  )

  useEffect(() => abort, [abort]) // never leave the mic open when the page goes away

  return { supported: Ctor !== null, listening, live, problem, start, stop, abort }
}
