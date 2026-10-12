import { Link } from 'react-router'
import { Icon, type IconName } from '../components/Icon'
import { Logo } from '../components/Logo'

/** Entry point for the demo: one card per user (spec 005-006 plan). */
export function Home() {
  return (
    <div className="min-h-dvh bg-[radial-gradient(ellipse_at_top,var(--color-brand-50),transparent_60%)]">
      <header className="mx-auto flex max-w-5xl items-center justify-between px-6 py-6">
        <Logo subtitle="Selección de repartidores" />
        <span className="hidden text-xs text-stone-500 sm:block">45 locales · España y México</span>
      </header>

      <main className="mx-auto max-w-5xl px-6 pt-10 pb-20">
        <p className="eyebrow text-brand-700">Agente de preselección</p>
        <h1 className="mt-2 max-w-2xl text-3xl font-semibold tracking-tight text-balance text-stone-900 sm:text-4xl">
          Cada candidato atendido en minutos, cada recruiter centrado en quien encaja.
        </h1>
        <p className="mt-4 max-w-2xl text-stone-600">
          Sofi conversa con los candidatos por chat, comprueba los requisitos y agenda la
          entrevista. El equipo ve a quién llamar primero y por qué.
        </p>

        <div className="mt-10 grid gap-5 md:grid-cols-2">
          <EntryCard
            to="/chat"
            icon="chat"
            tone="bg-wa-green"
            title="Soy candidato"
            text="Chat estilo WhatsApp con Sofi: requisitos, datos y hora de entrevista en unos 3 minutos."
            cta="Abrir el chat"
          />
          <EntryCard
            to="/recruiter"
            icon="users"
            tone="bg-brand-600"
            title="Soy recruiter"
            text="Panel de candidatos priorizados, con la explicación de cada decisión del agente, entrevistas y analítica."
            cta="Abrir el panel"
          />
        </div>
      </main>
    </div>
  )
}

function EntryCard(props: {
  to: string
  icon: IconName
  tone: string
  title: string
  text: string
  cta: string
}) {
  return (
    <Link
      to={props.to}
      className="group card flex flex-col p-6 transition hover:-translate-y-0.5 hover:border-stone-300 hover:shadow-md"
    >
      <div className={`grid size-11 place-items-center rounded-xl text-white ${props.tone}`}>
        <Icon name={props.icon} className="size-5" />
      </div>
      <h2 className="mt-4 text-lg font-semibold text-stone-900">{props.title}</h2>
      <p className="mt-1 flex-1 text-sm text-stone-600">{props.text}</p>
      <span className="mt-5 inline-flex items-center gap-1.5 text-sm font-medium text-brand-700">
        {props.cta}
        <Icon name="arrowRight" className="size-4 transition group-hover:translate-x-0.5" />
      </span>
    </Link>
  )
}
