/**
 * Spec 013: the voice page's rules as pure functions (the hooks stay thin wrappers).
 * - which browser API to use and in which language;
 * - how to read recognition results (final + interim);
 * - who has the floor (listening / thinking / Sofi speaking) and when the mic may open;
 * - what to do with what was heard (send it, or "no te he oído").
 */
import type { Country, Language, Status } from '../api/client'

// --- Web Speech API (not in TypeScript's DOM lib: Chrome ships it prefixed) -----------

export type RecognitionAlternative = { transcript: string }
export type RecognitionResult = { isFinal: boolean; length: number; [index: number]: RecognitionAlternative }
export type RecognitionResultList = { length: number; [index: number]: RecognitionResult }
export type RecognitionErrorCode =
  | 'no-speech'
  | 'aborted'
  | 'audio-capture'
  | 'network'
  | 'not-allowed'
  | 'service-not-allowed'
  | 'language-not-supported'
  | (string & {})

export interface RecognitionLike {
  lang: string
  continuous: boolean
  interimResults: boolean
  maxAlternatives: number
  onresult: ((event: { resultIndex: number; results: RecognitionResultList }) => void) | null
  onerror: ((event: { error: RecognitionErrorCode }) => void) | null
  onend: (() => void) | null
  onstart: (() => void) | null
  start(): void
  stop(): void
  abort(): void
}
export type RecognitionCtor = new () => RecognitionLike

/** The browser's SpeechRecognition constructor, or null (Firefox, old Safari, jsdom). */
export function getRecognitionCtor(scope: object | undefined = globalThis): RecognitionCtor | null {
  if (!scope) return null
  const s = scope as { SpeechRecognition?: RecognitionCtor; webkitSpeechRecognition?: RecognitionCtor }
  return s.SpeechRecognition ?? s.webkitSpeechRecognition ?? null
}

/** BCP-47 tag for recognition and for the browser voice: es-ES, es-MX, en-US or ca-ES. */
export function speechLang(language: Language, country: Country | null | undefined): string {
  if (language === 'en') return 'en-US'
  if (language === 'ca') return 'ca-ES' // spec 017: Catalan is Spain only
  return country === 'MX' ? 'es-MX' : 'es-ES'
}

/** All results so far: the settled words and the still-changing tail. */
export function readResults(results: RecognitionResultList): { final: string; interim: string } {
  let final = ''
  let interim = ''
  for (let i = 0; i < results.length; i++) {
    const result = results[i]
    const text = result[0]?.transcript ?? ''
    if (result.isFinal) final += text
    else interim += text
  }
  return { final: final.replace(/\s+/g, ' ').trim(), interim: interim.replace(/\s+/g, ' ').trim() }
}

export function heardText(parts: { final: string; interim: string }): string {
  return [parts.final, parts.interim].filter(Boolean).join(' ').trim()
}

/** Errors that mean "voice can't work here": stop and offer the text chat. */
export type MicProblem = 'denied' | 'no-mic' | 'network' | 'language' | null

export function micProblem(code: RecognitionErrorCode): MicProblem {
  switch (code) {
    case 'not-allowed':
    case 'service-not-allowed':
      return 'denied'
    case 'audio-capture':
      return 'no-mic'
    case 'network':
      return 'network'
    case 'language-not-supported':
      return 'language'
    default:
      return null // no-speech, aborted: just an empty turn
  }
}

// --- Who has the floor -------------------------------------------------------------------

export type VoicePhase = 'idle' | 'listening' | 'thinking' | 'speaking' | 'ended'

/** Sofi speaking wins (her goodbye is spoken after the call ended), then the API wait. */
export function voicePhase(s: {
  speaking: boolean
  thinking: boolean
  listening: boolean
  status: Status
}): VoicePhase {
  if (s.speaking) return 'speaking'
  if (s.thinking) return 'thinking'
  if (s.listening) return 'listening'
  if (s.status !== 'in_progress') return 'ended'
  return 'idle'
}

/** FR-6: the mic never opens while Sofi talks or while we wait for her answer. */
export function canListen(phase: VoicePhase, supported: boolean, problem: MicProblem): boolean {
  return supported && !problem && phase === 'idle'
}

/** How many "no te he oído" in a row before we stop opening the mic by ourselves. */
export const MAX_AUTO_RETRIES = 2

/** After Sofi stops talking, open the mic again by ourselves? */
export function shouldAutoListen(s: {
  autoListen: boolean
  phase: VoicePhase
  misses: number
  supported: boolean
  problem: MicProblem
}): boolean {
  return s.autoListen && s.misses < MAX_AUTO_RETRIES && canListen(s.phase, s.supported, s.problem)
}

export type AfterListening =
  | { kind: 'send'; text: string; misses: 0 }
  | { kind: 'reprompt'; misses: number } // "No te he oído, ¿puedes repetir?"
  | { kind: 'stop'; misses: number } // mic problem: no reprompt, show the message

/** What to do when recognition ends. */
export function afterListening(text: string, misses: number, problem: MicProblem): AfterListening {
  const clean = text.trim()
  if (clean) return { kind: 'send', text: clean, misses: 0 }
  if (problem) return { kind: 'stop', misses }
  return { kind: 'reprompt', misses: misses + 1 }
}

/** A tap opens the mic until a pause; holding it is push-to-talk (release sends). */
export const HOLD_MS = 400
/** Tap mode: once words are settled, this much silence ends the turn. */
export const SILENCE_MS = 1300
/** Tap mode: nothing heard at all for this long ends the turn ("no te he oído"). */
export const NOTHING_HEARD_MS = 7000

export function pressKind(downAt: number, upAt: number): 'tap' | 'hold' {
  return upAt - downAt >= HOLD_MS ? 'hold' : 'tap'
}

// --- Browser voice choice ----------------------------------------------------------------

export type VoiceInfo = { name: string; lang: string; localService?: boolean }

const PREFERRED = /natural|neural|online|google/i
const FEMALE_HINT =
  /helena|laura|elvira|sabina|paulina|dalia|m[oó]nica|lucia|luc[ií]a|elena|paloma|zira|aria|jenny|samantha|female|mujer/i

/** The best installed voice for `lang` (exact locale, then same language; nicer voices first). */
export function pickVoice<V extends VoiceInfo>(voices: readonly V[], lang: string): V | null {
  const base = lang.slice(0, 2).toLowerCase()
  let best: V | null = null
  let bestScore = 0
  for (const voice of voices) {
    const vlang = voice.lang.replace('_', '-').toLowerCase()
    let score = 0
    if (vlang === lang.toLowerCase()) score += 10
    else if (vlang.startsWith(base)) score += 5
    else continue
    if (PREFERRED.test(voice.name)) score += 2
    if (FEMALE_HINT.test(voice.name)) score += 1
    if (score > bestScore) {
      best = voice
      bestScore = score
    }
  }
  return best
}
