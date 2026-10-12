import type { Language } from '../api/client'
import type { VoicePhase } from './voiceLogic'
import type { VoiceEngine } from './useSpeaker'
import type { MicProblem } from './voiceLogic'

type VoiceText = {
  phase: Record<VoicePhase, string>
  button: Record<VoicePhase, string>
  hint: string
  notHeard: string
  autoListen: string
  engine: Record<VoiceEngine, string>
  transcript: string
  empty: string
  you: string
  typeInstead: string
  newCall: string
  problem: Record<Exclude<MicProblem, null>, string>
  unsupportedTitle: string
  unsupportedText: string
  openChat: string
  back: string
}

/** Candidate-facing strings of the voice page (spec 013); Sofi's words come from the API. */
export const VOICE_TEXT: Record<Language, VoiceText> = {
  es: {
    phase: {
      idle: 'Tu turno',
      listening: 'Te escucho…',
      thinking: 'Sofi está pensando…',
      speaking: 'Sofi está hablando…',
      ended: 'Llamada terminada',
    },
    button: {
      idle: 'Hablar',
      listening: 'Terminar de hablar',
      thinking: 'Esperando a Sofi',
      speaking: 'Sofi está hablando',
      ended: 'Llamada terminada',
    },
    hint: 'Toca y habla, o mantén pulsado mientras hablas',
    notHeard: 'No te he oído, ¿puedes repetir?',
    autoListen: 'Escuchar al terminar Sofi',
    engine: { checking: 'voz: …', elevenlabs: 'voz: ElevenLabs', browser: 'voz: navegador' },
    transcript: 'Transcripción',
    empty: 'La conversación aparecerá aquí.',
    you: 'Tú',
    typeInstead: 'Prefiero escribir',
    newCall: 'Nueva conversación',
    problem: {
      denied:
        'No tenemos permiso para usar el micrófono. Actívalo en el candado de la barra de direcciones, o sigue por chat.',
      'no-mic': 'No encontramos ningún micrófono. Conecta uno o sigue por chat.',
      network: 'El reconocimiento de voz necesita conexión a internet. Inténtalo de nuevo o sigue por chat.',
      language: 'Tu navegador no reconoce este idioma por voz. Sigue por chat.',
    },
    unsupportedTitle: 'Tu navegador no permite hablar con Sofi',
    unsupportedText:
      'El reconocimiento de voz funciona en Chrome y Edge (ordenador o Android). Puedes hacer la misma entrevista por chat.',
    openChat: 'Abrir el chat',
    back: 'Volver al inicio',
  },
  en: {
    phase: {
      idle: 'Your turn',
      listening: 'Listening…',
      thinking: 'Sofi is thinking…',
      speaking: 'Sofi is speaking…',
      ended: 'Call ended',
    },
    button: {
      idle: 'Talk',
      listening: 'Done talking',
      thinking: 'Waiting for Sofi',
      speaking: 'Sofi is speaking',
      ended: 'Call ended',
    },
    hint: 'Tap and talk, or hold while you talk',
    notHeard: "I didn't hear you, could you say that again?",
    autoListen: 'Listen when Sofi finishes',
    engine: { checking: 'voice: …', elevenlabs: 'voice: ElevenLabs', browser: 'voice: browser' },
    transcript: 'Transcript',
    empty: 'The conversation will show up here.',
    you: 'You',
    typeInstead: "I'd rather type",
    newCall: 'New conversation',
    problem: {
      denied:
        'We are not allowed to use the microphone. Allow it from the padlock in the address bar, or continue by chat.',
      'no-mic': 'No microphone found. Plug one in or continue by chat.',
      network: 'Speech recognition needs an internet connection. Try again or continue by chat.',
      language: 'Your browser cannot recognise this language. Continue by chat.',
    },
    unsupportedTitle: "Your browser can't talk to Sofi",
    unsupportedText:
      'Speech recognition works in Chrome and Edge (desktop or Android). You can do the same interview by chat.',
    openChat: 'Open the chat',
    back: 'Back to home',
  },
}
