import type { ReactNode } from 'react'
import { errorMessage } from '../lib/errors'
import { Icon, type IconName } from './Icon'

export function Spinner({ className = 'size-4' }: { className?: string }) {
  return (
    <span
      role="status"
      aria-label="Cargando"
      className={`inline-block animate-spin rounded-full border-2 border-current border-r-transparent ${className}`}
    />
  )
}

export function Loading({ label = 'Cargando…' }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 py-16 text-sm text-stone-500">
      <Spinner /> {label}
    </div>
  )
}

export function EmptyState({
  icon = 'users',
  title,
  children,
  action,
}: {
  icon?: IconName
  title: string
  children?: ReactNode
  action?: ReactNode
}) {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-16 text-center">
      <div className="mb-3 grid size-11 place-items-center rounded-full bg-stone-100 text-stone-500">
        <Icon name={icon} className="size-5" />
      </div>
      <h3 className="font-medium text-stone-900">{title}</h3>
      {children && <p className="mt-1 max-w-sm text-sm text-stone-500">{children}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  )
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  return (
    <EmptyState
      icon="alert"
      title="No se pudieron cargar los datos"
      action={
        onRetry && (
          <button type="button" onClick={onRetry} className="btn-secondary">
            <Icon name="refresh" /> Reintentar
          </button>
        )
      }
    >
      {errorMessage(error)}
    </EmptyState>
  )
}
