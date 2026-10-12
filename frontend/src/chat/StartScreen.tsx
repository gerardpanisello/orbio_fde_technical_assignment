import { useState } from 'react'
import { Link } from 'react-router'
import type { Country, Language } from '../api/client'
import { Icon } from '../components/Icon'
import { LogoMark } from '../components/Logo'
import { Spinner } from '../components/States'

const COPY = {
  es: {
    title: 'Trabaja como repartidor/a',
    text: 'Responde unas preguntas rápidas a Sofi por chat y agenda tu entrevista en unos 3 minutos.',
    language: 'Idioma',
    phone: 'Tu teléfono',
    start: 'Empezar chat con Sofi',
    error: 'No pudimos conectar. Inténtalo de nuevo.',
    demo: 'Demo: el país simula el prefijo del número desde el que escribe el candidato.',
  },
  en: {
    title: 'Work as a delivery rider',
    text: 'Answer a few quick questions from Sofi in the chat and book your interview in about 3 minutes.',
    language: 'Language',
    phone: 'Your phone',
    start: 'Start chatting with Sofi',
    error: 'We could not connect. Please try again.',
    demo: "Demo: the country simulates the candidate's phone prefix.",
  },
}

/** Spec 013: the same screen starts a voice conversation on /voz. */
const VOICE_COPY = {
  es: {
    text: 'Habla con Sofi: te hará unas preguntas rápidas y podrás agendar tu entrevista en unos 3 minutos.',
    start: 'Empezar a hablar con Sofi',
    demo: 'Necesitas micrófono y Chrome o Edge. El país elige el acento (España o México).',
  },
  en: {
    text: 'Talk to Sofi: she will ask a few quick questions and book your interview in about 3 minutes.',
    start: 'Start talking to Sofi',
    demo: 'You need a microphone and Chrome or Edge. The country simulates the phone prefix.',
  },
}

/** FR-3: pick language and country (stands in for the phone number's prefix). */
export function StartScreen({
  onStart,
  starting,
  failed,
  mode = 'chat',
}: {
  onStart: (language: Language, country: Country) => void
  starting: boolean
  failed: boolean
  mode?: 'chat' | 'voice'
}) {
  const [language, setLanguage] = useState<Language>('es')
  const [country, setCountry] = useState<Country>('ES')
  const t = mode === 'voice' ? { ...COPY[language], ...VOICE_COPY[language] } : COPY[language]

  return (
    <div className="flex h-full flex-col bg-white">
      <div className="relative flex flex-col items-center bg-wa-header px-6 pt-10 pb-14 text-center text-white">
        <Link
          to="/"
          className="absolute top-3 left-2 rounded-full p-1.5 hover:bg-white/10"
          aria-label="Volver al inicio"
        >
          <Icon name="arrowLeft" className="size-5" />
        </Link>
        <LogoMark className="size-16 rounded-2xl shadow-lg ring-4 ring-white/15" />
        <h1 className="mt-4 text-xl font-semibold">{t.title}</h1>
        <p className="mt-2 text-sm text-white/85">{t.text}</p>
      </div>

      <div className="relative -mt-6 flex flex-1 flex-col rounded-t-3xl bg-white px-6 pt-7">
        <fieldset>
          <legend className="text-xs font-semibold tracking-wide text-wa-meta uppercase">
            {t.language}
          </legend>
          <Segmented
            value={language}
            onChange={setLanguage}
            options={[
              { value: 'es', label: 'Español' },
              { value: 'en', label: 'English' },
            ]}
          />
        </fieldset>

        <fieldset className="mt-5">
          <legend className="text-xs font-semibold tracking-wide text-wa-meta uppercase">
            {t.phone}
          </legend>
          <Segmented
            value={country}
            onChange={setCountry}
            options={[
              { value: 'ES', label: '+34 España' },
              { value: 'MX', label: '+52 México' },
            ]}
          />
        </fieldset>

        <div className="mt-auto pb-8">
          {failed && (
            <p role="alert" className="mb-3 text-center text-sm text-red-600">
              {t.error}
            </p>
          )}
          <button
            type="button"
            disabled={starting}
            onClick={() => onStart(language, country)}
            className="flex h-12 w-full items-center justify-center gap-2 rounded-full bg-wa-green text-[15px] font-semibold text-white shadow-sm transition hover:brightness-95 disabled:opacity-70"
          >
            {starting ? <Spinner /> : <Icon name={mode === 'voice' ? 'mic' : 'chat'} className="size-5" />}
            {t.start}
          </button>
          <p className="mt-3 text-center text-[11px] leading-snug text-wa-meta">{t.demo}</p>
        </div>
      </div>
    </div>
  )
}

function Segmented<T extends string>({
  value,
  onChange,
  options,
}: {
  value: T
  onChange: (value: T) => void
  options: { value: T; label: string }[]
}) {
  return (
    <div className="mt-2 grid grid-cols-2 gap-1 rounded-xl bg-stone-100 p-1">
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          aria-pressed={value === option.value}
          onClick={() => onChange(option.value)}
          className={`rounded-lg py-2 text-sm font-medium transition ${
            value === option.value
              ? 'bg-white text-wa-ink shadow-sm'
              : 'text-wa-meta hover:text-wa-ink'
          }`}
        >
          {option.label}
        </button>
      ))}
    </div>
  )
}
