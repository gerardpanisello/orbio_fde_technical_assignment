import { useMutation, useQueryClient } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { api } from '../api/client'
import { Icon } from '../components/Icon'
import { Spinner } from '../components/States'

export function PageHeader({
  title,
  subtitle,
  actions,
}: {
  title: string
  subtitle?: string
  actions?: ReactNode
}) {
  return (
    <header className="flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-stone-900">{title}</h1>
        {subtitle && <p className="mt-0.5 text-sm text-stone-500">{subtitle}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </header>
  )
}

/** FR-14: "Generar datos demo" for empty states (the API refuses it outside APP_ENV=dev). */
export function SeedButton() {
  const queryClient = useQueryClient()
  const seed = useMutation({
    mutationFn: () => api.seed(40),
    onSuccess: () => queryClient.invalidateQueries(),
  })
  return (
    <div className="flex flex-col items-center gap-2">
      <button type="button" className="btn-primary" onClick={() => seed.mutate()} disabled={seed.isPending}>
        {seed.isPending ? <Spinner className="size-3.5" /> : <Icon name="sparkles" />}
        Generar datos demo
      </button>
      {seed.isError && (
        <p className="text-xs text-red-700">
          No se pudieron generar (¿la API está en modo dev?).
        </p>
      )}
    </div>
  )
}
