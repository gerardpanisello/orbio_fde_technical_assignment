import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, NavLink, Outlet } from 'react-router'
import { api } from '../api/client'
import { Icon, type IconName } from '../components/Icon'
import { Logo, LogoMark } from '../components/Logo'
import { Spinner } from '../components/States'

const NAV: { to: string; label: string; icon: IconName; end?: boolean }[] = [
  { to: '/recruiter', label: 'Candidatos', icon: 'users', end: true },
  { to: '/recruiter/entrevistas', label: 'Entrevistas', icon: 'calendar' },
  { to: '/recruiter/zonas', label: 'Zonas', icon: 'map' },
  { to: '/recruiter/analitica', label: 'Analítica', icon: 'chart' },
]

/** Recruiter shell: sidebar nav (icons only on tablets) + the routed page. */
export function RecruiterLayout() {
  return (
    <div className="flex h-dvh bg-stone-50">
      <aside className="flex w-16 shrink-0 flex-col border-r border-stone-200 bg-white lg:w-56">
        <Link to="/" className="flex h-16 items-center px-4 lg:px-5" aria-label="Inicio">
          <span className="lg:hidden">
            <LogoMark />
          </span>
          <span className="hidden lg:block">
            <Logo subtitle="Talento · Reparto" />
          </span>
        </Link>

        <nav className="flex flex-1 flex-col gap-0.5 px-2 pt-2 lg:px-3" aria-label="Secciones">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              title={item.label}
              className={({ isActive }) =>
                `flex items-center justify-center gap-2.5 rounded-lg px-2.5 py-2 text-sm font-medium transition-colors lg:justify-start ${
                  isActive
                    ? 'bg-brand-50 text-brand-800'
                    : 'text-stone-600 hover:bg-stone-100 hover:text-stone-900'
                }`
              }
            >
              <Icon name={item.icon} className="size-[18px] shrink-0" />
              <span className="hidden lg:inline">{item.label}</span>
            </NavLink>
          ))}
        </nav>

        <div className="space-y-2 border-t border-stone-100 p-2 lg:p-3">
          <Link to="/chat" className="btn-ghost w-full lg:justify-start" title="Abrir chat de candidato">
            <Icon name="chat" />
            <span className="hidden lg:inline">Chat de candidato</span>
          </Link>
          <DevTools />
        </div>
      </aside>

      <main className="min-w-0 flex-1 overflow-y-auto">
        <Outlet />
      </main>
    </div>
  )
}

/** FR-14: demo data, only when the API runs with APP_ENV=dev. Also shows the LLM mode. */
function DevTools() {
  const queryClient = useQueryClient()
  const health = useQuery({ queryKey: ['health'], queryFn: api.health, staleTime: 60_000 })
  const seed = useMutation({
    mutationFn: () => api.seed(40),
    onSuccess: () => queryClient.invalidateQueries(),
  })
  const reset = useMutation({
    mutationFn: api.reset,
    onSuccess: () => {
      seed.reset()
      return queryClient.invalidateQueries()
    },
  })
  const confirmReset = () => {
    const ok = window.confirm(
      'Se borrarán todos los candidatos, conversaciones, entrevistas y notas, y las zonas y ' +
        'la disponibilidad volverán a los valores de config/. No se puede deshacer. ¿Continuar?',
    )
    if (ok) reset.mutate()
  }

  if (health.isError) {
    return (
      <p className="hidden rounded-md bg-red-50 px-2 py-1.5 text-xs text-red-700 lg:block">
        API no disponible
      </p>
    )
  }
  if (!health.data || health.data.env !== 'dev') return null
  return (
    <>
      <button
        type="button"
        className="btn-secondary w-full lg:justify-start"
        onClick={() => seed.mutate()}
        disabled={seed.isPending}
        title="Genera 40 conversaciones simuladas"
      >
        {seed.isPending ? <Spinner className="size-3.5" /> : <Icon name="sparkles" />}
        <span className="hidden lg:inline">Generar datos demo</span>
      </button>
      {seed.isSuccess && (
        <p className="hidden text-center text-xs text-emerald-700 lg:block">
          {seed.data.created} conversaciones creadas
        </p>
      )}
      {seed.isError && (
        <p className="hidden text-center text-xs text-red-700 lg:block">No se pudieron generar</p>
      )}
      <button
        type="button"
        className="btn-ghost w-full text-red-700 hover:bg-red-50 lg:justify-start"
        onClick={confirmReset}
        disabled={reset.isPending || seed.isPending}
        title="Borra todos los candidatos y vuelve a empezar"
      >
        {reset.isPending ? <Spinner className="size-3.5" /> : <Icon name="trash" />}
        <span className="hidden lg:inline">Borrar todos los datos</span>
      </button>
      {reset.isSuccess && (
        <p className="hidden text-center text-xs text-emerald-700 lg:block" role="status">
          Datos borrados ({reset.data.deleted} conversaciones)
        </p>
      )}
      {reset.isError && (
        <p className="hidden text-center text-xs text-red-700 lg:block" role="alert">
          No se pudieron borrar
        </p>
      )}
      <p className="hidden items-center justify-center gap-1.5 text-[11px] text-stone-400 lg:flex">
        <span className="size-1.5 rounded-full bg-emerald-500" />
        API · LLM {health.data.llm_mode}
      </p>
    </>
  )
}
