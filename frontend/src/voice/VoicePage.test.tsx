import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { StrictMode } from 'react'
import { MemoryRouter } from 'react-router'
import { api, type Conversation, type Turn } from '../api/client'
import { VoicePage } from './VoicePage'
import type { RecognitionLike, RecognitionResultList } from './voiceLogic'

/** A scriptable stand-in for Chrome's webkitSpeechRecognition. */
class FakeRecognition implements RecognitionLike {
  static instances: FakeRecognition[] = []
  lang = ''
  continuous = false
  interimResults = false
  maxAlternatives = 1
  started = false
  onresult: RecognitionLike['onresult'] = null
  onerror: RecognitionLike['onerror'] = null
  onend: RecognitionLike['onend'] = null
  onstart: RecognitionLike['onstart'] = null
  constructor() {
    FakeRecognition.instances.push(this)
  }
  start() {
    this.started = true
  }
  stop() {
    this.onend?.()
  }
  abort() {}
  say(text: string, isFinal = true) {
    const results: RecognitionResultList = { length: 1, 0: { isFinal, length: 1, 0: { transcript: text } } }
    this.onresult?.({ resultIndex: 0, results })
  }
  fail(error: string) {
    this.onerror?.({ error })
    this.onend?.()
  }
}

const greeting: Conversation = {
  id: 'c1',
  status: 'in_progress',
  language: 'es',
  messages: [
    {
      id: 1,
      role: 'agent',
      text: '¡Hola! Soy Sofi 👋 ¿Aceptas que usemos tus datos?',
      quick_replies: [
        { id: 'yes', label: 'Sí' },
        { id: 'no', label: 'No' },
      ],
      created_at: '2026-10-13T09:00:00Z',
    } as Conversation['messages'][number],
  ],
}

function reply(text: string): Turn {
  return { status: 'in_progress', reply: { text, quick_replies: [] } } as unknown as Turn
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  // StrictMode as in main.tsx: its double mount once dropped Sofi's first message.
  return render(
    <StrictMode>
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={['/voz']}>
          <VoicePage />
        </MemoryRouter>
      </QueryClientProvider>
    </StrictMode>,
  )
}

const lastRecognition = () => FakeRecognition.instances.at(-1)!

/** Browser voice stand-ins: record what Sofi says, finish each utterance shortly after. */
const spoken: string[] = []
class FakeUtterance {
  lang = ''
  rate = 1
  voice: unknown = null
  onend: (() => void) | null = null
  onerror: (() => void) | null = null
  text: string
  constructor(text: string) {
    this.text = text
  }
}
const fakeSynth = {
  getVoices: () => [],
  cancel: () => {},
  speak(u: FakeUtterance) {
    spoken.push(u.text)
    setTimeout(() => u.onend?.(), 5)
  },
}

beforeEach(() => {
  Element.prototype.scrollIntoView = vi.fn() // not in jsdom
  sessionStorage.clear()
  localStorage.clear()
  FakeRecognition.instances = []
  spoken.length = 0
  vi.stubGlobal('SpeechSynthesisUtterance', FakeUtterance)
  vi.stubGlobal('speechSynthesis', fakeSynth)
  vi.spyOn(api, 'voiceStatus').mockResolvedValue({ tts: 'browser', model_id: null })
  vi.spyOn(api, 'startConversation').mockResolvedValue(greeting)
})

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  delete (window as { webkitSpeechRecognition?: unknown }).webkitSpeechRecognition
})

describe('VoicePage', () => {
  it('explains and links to the text chat when the browser has no speech recognition (AC-5)', () => {
    renderPage()
    expect(screen.getByText('Tu navegador no permite hablar con Sofi')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Abrir el chat/ })).toHaveAttribute('href', '/chat')
  })

  it('speaks, then listens by itself and sends what was heard as a normal turn', async () => {
    ;(window as { webkitSpeechRecognition?: unknown }).webkitSpeechRecognition = FakeRecognition
    const send = vi.spyOn(api, 'sendMessage').mockResolvedValue(reply('¿Cómo te llamas?'))
    renderPage()

    await userEvent.click(screen.getByRole('button', { name: /Empezar a hablar con Sofi/ }))
    expect(await screen.findByTestId('voice-current', {}, { timeout: 3000 })).toHaveTextContent('Soy Sofi')
    await waitFor(() => expect(screen.getByTestId('voice-engine')).toHaveTextContent('voz: navegador'))

    // Sofi reads the greeting aloud (speakable version), then the mic opens by itself.
    await waitFor(() => expect(lastRecognition()?.started).toBe(true))
    expect(spoken.join(' ')).toContain('Soy Sofi')
    expect(spoken.join(' ')).toContain('Puedes decir: Sí o No.')
    expect(spoken.join(' ')).not.toContain('👋')
    expect(lastRecognition().lang).toBe('es-ES')
    expect(screen.getByTestId('voice-phase')).toHaveTextContent('Te escucho')

    act(() => lastRecognition().say('sí, acepto', false))
    expect(screen.getByTestId('voice-live')).toHaveTextContent('sí, acepto')
    act(() => lastRecognition().say('sí, acepto'))
    act(() => lastRecognition().stop())

    await waitFor(() => expect(send).toHaveBeenCalledWith('c1', 'sí, acepto'))
    await waitFor(() => expect(screen.getByTestId('voice-current')).toHaveTextContent('¿Cómo te llamas?'))
    expect(screen.getByTestId('voice-transcript')).toHaveTextContent('sí, acepto')
  })

  it('asks to repeat on silence and does not send an empty turn', async () => {
    ;(window as { webkitSpeechRecognition?: unknown }).webkitSpeechRecognition = FakeRecognition
    const send = vi.spyOn(api, 'sendMessage')
    renderPage()
    await userEvent.click(screen.getByRole('button', { name: /Empezar a hablar con Sofi/ }))
    await waitFor(() => expect(lastRecognition()?.started).toBe(true), { timeout: 3000 })

    const first = lastRecognition()
    act(() => first.fail('no-speech'))
    expect(await screen.findByText('No te he oído, ¿puedes repetir?')).toBeInTheDocument()
    // It listens again by itself after the reprompt.
    await waitFor(() => expect(lastRecognition()).not.toBe(first))
    expect(send).not.toHaveBeenCalled()
  })

  it('shows the microphone problem with a way out to the chat', async () => {
    ;(window as { webkitSpeechRecognition?: unknown }).webkitSpeechRecognition = FakeRecognition
    renderPage()
    await userEvent.click(screen.getByRole('button', { name: /Empezar a hablar con Sofi/ }))
    await waitFor(() => expect(lastRecognition()?.started).toBe(true), { timeout: 3000 })
    act(() => lastRecognition().fail('not-allowed'))
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('permiso para usar el micrófono')
    expect(within(alert).getByRole('link', { name: 'Prefiero escribir' })).toHaveAttribute('href', '/chat')
    expect(screen.getByRole('button', { name: 'Hablar' })).toBeDisabled()
  })

  it('quick replies can still be tapped', async () => {
    ;(window as { webkitSpeechRecognition?: unknown }).webkitSpeechRecognition = FakeRecognition
    const send = vi.spyOn(api, 'sendMessage').mockResolvedValue(reply('¿Cómo te llamas?'))
    renderPage()
    await userEvent.click(screen.getByRole('button', { name: /Empezar a hablar con Sofi/ }))
    await userEvent.click(await screen.findByRole('button', { name: 'Sí' }, { timeout: 3000 }))
    await waitFor(() => expect(send).toHaveBeenCalledWith('c1', 'Sí'))
  })
})
