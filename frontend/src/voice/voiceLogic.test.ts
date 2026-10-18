import { describe, expect, it } from 'vitest'
import {
  afterListening,
  canListen,
  getRecognitionCtor,
  heardText,
  micProblem,
  pickVoice,
  pressKind,
  readResults,
  shouldAutoListen,
  speechLang,
  voicePhase,
  type RecognitionResultList,
} from './voiceLogic'

function results(...items: [string, boolean][]): RecognitionResultList {
  const list: RecognitionResultList = { length: items.length }
  items.forEach(([transcript, isFinal], i) => {
    list[i] = { isFinal, length: 1, 0: { transcript } }
  })
  return list
}

describe('recognition helpers', () => {
  it('finds the standard or the webkit-prefixed constructor', () => {
    class Fake {}
    expect(getRecognitionCtor({})).toBeNull()
    expect(getRecognitionCtor({ webkitSpeechRecognition: Fake })).toBe(Fake)
    expect(getRecognitionCtor({ SpeechRecognition: Fake, webkitSpeechRecognition: class {} })).toBe(Fake)
  })

  it('maps language and country to a recognition locale', () => {
    expect(speechLang('es', 'ES')).toBe('es-ES')
    expect(speechLang('es', 'MX')).toBe('es-MX')
    expect(speechLang('es', null)).toBe('es-ES')
    expect(speechLang('en', 'MX')).toBe('en-US')
  })

  it('splits settled words from the interim tail', () => {
    const parts = readResults(results([' vivo en ', true], ['Chamberí', true], [' Madr', false]))
    expect(parts).toEqual({ final: 'vivo en Chamberí', interim: 'Madr' })
    expect(heardText(parts)).toBe('vivo en Chamberí Madr')
    expect(heardText({ final: '', interim: '' })).toBe('')
  })

  it('classifies errors: only real mic problems stop the voice flow', () => {
    expect(micProblem('not-allowed')).toBe('denied')
    expect(micProblem('service-not-allowed')).toBe('denied')
    expect(micProblem('audio-capture')).toBe('no-mic')
    expect(micProblem('network')).toBe('network')
    expect(micProblem('no-speech')).toBeNull()
    expect(micProblem('aborted')).toBeNull()
  })

  it('tells a tap from push-to-talk', () => {
    expect(pressKind(1000, 1200)).toBe('tap')
    expect(pressKind(1000, 1600)).toBe('hold')
  })
})

describe('turn policy', () => {
  const base = { speaking: false, thinking: false, listening: false, status: 'in_progress' as const }

  it('gives Sofi the floor first, then the API wait, then the candidate', () => {
    expect(voicePhase(base)).toBe('idle')
    expect(voicePhase({ ...base, listening: true })).toBe('listening')
    expect(voicePhase({ ...base, thinking: true, listening: true })).toBe('thinking')
    expect(voicePhase({ ...base, speaking: true, thinking: true })).toBe('speaking')
    expect(voicePhase({ ...base, status: 'interview_scheduled' })).toBe('ended')
    expect(voicePhase({ ...base, status: 'interview_scheduled', speaking: true })).toBe('speaking')
  })

  it('never opens the mic while Sofi speaks, while waiting, or after the end', () => {
    expect(canListen('idle', true, null)).toBe(true)
    for (const phase of ['speaking', 'thinking', 'listening', 'ended'] as const) {
      expect(canListen(phase, true, null)).toBe(false)
    }
    expect(canListen('idle', false, null)).toBe(false)
    expect(canListen('idle', true, 'denied')).toBe(false)
  })

  it('auto-listens only when enabled, idle and not after repeated silence', () => {
    const s = { autoListen: true, phase: 'idle' as const, misses: 0, supported: true, problem: null }
    expect(shouldAutoListen(s)).toBe(true)
    expect(shouldAutoListen({ ...s, autoListen: false })).toBe(false)
    expect(shouldAutoListen({ ...s, phase: 'ended' })).toBe(false)
    expect(shouldAutoListen({ ...s, misses: 1 })).toBe(true)
    expect(shouldAutoListen({ ...s, misses: 2 })).toBe(false)
  })

  it('sends what was heard, or asks to repeat on silence', () => {
    expect(afterListening('  sí  ', 1, null)).toEqual({ kind: 'send', text: 'sí', misses: 0 })
    expect(afterListening('', 0, null)).toEqual({ kind: 'reprompt', misses: 1 })
    expect(afterListening(' ', 1, null)).toEqual({ kind: 'reprompt', misses: 2 })
    expect(afterListening('', 0, 'denied')).toEqual({ kind: 'stop', misses: 0 })
  })
})

describe('pickVoice', () => {
  const voices = [
    { name: 'Microsoft David - English (United States)', lang: 'en-US' },
    { name: 'Microsoft Pablo - Spanish (Spain)', lang: 'es-ES' },
    { name: 'Google español', lang: 'es-ES' },
    { name: 'Microsoft Sabina - Spanish (Mexico)', lang: 'es-MX' },
  ]

  it('prefers the exact locale, then nicer voices', () => {
    expect(pickVoice(voices, 'es-ES')?.name).toBe('Google español')
    expect(pickVoice(voices, 'es-MX')?.name).toBe('Microsoft Sabina - Spanish (Mexico)')
    expect(pickVoice(voices, 'en-US')?.name).toBe('Microsoft David - English (United States)')
  })

  it('falls back to the same language, or nothing', () => {
    expect(pickVoice(voices.slice(0, 3), 'es-MX')?.name).toBe('Google español')
    expect(pickVoice([{ name: 'Anna', lang: 'de-DE' }], 'es-ES')).toBeNull()
  })
})

describe('speechLang in Catalan (spec 017)', () => {
  it('recognises and speaks Catalan as ca-ES, whatever the country', () => {
    expect(speechLang('ca', 'ES')).toBe('ca-ES')
    expect(speechLang('ca', 'MX')).toBe('ca-ES')
    expect(speechLang('ca', null)).toBe('ca-ES')
  })
})
