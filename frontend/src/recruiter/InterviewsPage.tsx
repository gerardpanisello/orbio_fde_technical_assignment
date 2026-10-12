import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link, useSearchParams } from 'react-router'
import { api, type AreaLabels, type CandidateRow } from '../api/client'
import { keys, useAreaLabels } from '../api/queries'
import { PriorityPill, RecruiterTag } from '../components/Badges'
import { Icon } from '../components/Icon'
import { EmptyState, ErrorState, Loading } from '../components/States'
import { withParam } from '../lib/filters'
import { formatDayHeading } from '../lib/format'
import { groupByDay, localDayKey } from '../lib/interviews'
import { LANGUAGE, VEHICLE, placeLabel } from '../lib/labels'
import { STATUS_META } from '../lib/status'
import { CandidateDrawer } from './CandidateDrawer'
import { PageHeader, SeedButton } from './common'

const BOOKED = { status: 'interview_scheduled', sort: '-score' } as const
const UNSCHEDULED = { status: 'qualified_unscheduled', sort: '-score' } as const
const WAITLISTED = { status: 'waitlisted', sort: '-score' } as const

/** FR-12: the interview agenda. */
export function InterviewsPage() {
  const [params, setParams] = useSearchParams()
  const areas = useAreaLabels()
  const booked = useQuery({ queryKey: keys.candidates(BOOKED), queryFn: () => api.listCandidates(BOOKED) })
  const unscheduled = useQuery({
    queryKey: keys.candidates(UNSCHEDULED),
    queryFn: () => api.listCandidates(UNSCHEDULED),
  })
  const waitlisted = useQuery({
    queryKey: keys.candidates(WAITLISTED),
    queryFn: () => api.listCandidates(WAITLISTED),
  })
  const openId = params.get('id')
  const open = (id: string) => setParams(withParam(params, 'id', id))

  const [now] = useState(() => new Date())
  const today = localDayKey(now)
  const tomorrow = localDayKey(new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1))
  const groups = booked.data ? groupByDay(booked.data, today) : null
  const pending = unscheduled.data?.length ?? 0
  const waiting = waitlisted.data?.length ?? 0

  return (
    <div className="mx-auto max-w-5xl px-4 py-6 lg:px-8">
      <PageHeader title="Entrevistas" subtitle="Agendadas por Sofi en la conversación, por día." />

      {pending > 0 && (
        <Link
          to="/recruiter?status=qualified_unscheduled"
          className="card mt-5 flex items-center gap-3 px-4 py-3 text-sm transition hover:border-stone-300"
        >
          <span className="size-2 rounded-full" style={{ backgroundColor: STATUS_META.qualified_unscheduled.color }} />
          <span className="flex-1 text-stone-700">
            <strong className="font-semibold text-stone-900">
              {pending} {pending === 1 ? 'candidato apto' : 'candidatos aptos'} sin entrevista:
            </strong>{' '}
            ninguna hora les venía bien. Llámales para agendar.
          </span>
          <Icon name="arrowRight" className="size-4 text-stone-400" />
        </Link>
      )}

      {waiting > 0 && (
        <Link
          to="/recruiter?status=waitlisted"
          className={`card ${pending > 0 ? 'mt-3' : 'mt-5'} flex items-center gap-3 px-4 py-3 text-sm transition hover:border-stone-300`}
        >
          <span className="size-2 rounded-full" style={{ backgroundColor: STATUS_META.waitlisted.color }} />
          <span className="flex-1 text-stone-700">
            <strong className="font-semibold text-stone-900">
              {waiting} {waiting === 1 ? 'candidato apto' : 'candidatos aptos'} en lista de espera:
            </strong>{' '}
            su zona tiene la plantilla cubierta. Ver en Zonas cuándo hay hueco.
          </span>
          <Icon name="arrowRight" className="size-4 text-stone-400" />
        </Link>
      )}

      <div className="mt-5 space-y-6">
        {booked.isLoading ? (
          <Loading />
        ) : booked.isError ? (
          <ErrorState error={booked.error} onRetry={() => booked.refetch()} />
        ) : !groups || (groups.upcoming.length === 0 && groups.past.length === 0) ? (
          <div className="card">
            <EmptyState icon="calendar" title="No hay entrevistas agendadas" action={<SeedButton />}>
              Cuando un candidato apto elija una hora en el chat, aparecerá aquí.
            </EmptyState>
          </div>
        ) : (
          <>
            <section aria-labelledby="upcoming">
              <h2 id="upcoming" className="eyebrow mb-2">Próximas</h2>
              {groups.upcoming.length === 0 ? (
                <p className="card px-4 py-6 text-center text-sm text-stone-500">
                  No hay entrevistas a partir de hoy.
                </p>
              ) : (
                <div className="space-y-3">
                  {groups.upcoming.map((g) => (
                    <DayCard
                      key={g.day}
                      day={g.day}
                      tag={g.day === today ? 'Hoy' : g.day === tomorrow ? 'Mañana' : undefined}
                      rows={g.items}
                      areas={areas}
                      onOpen={open}
                    />
                  ))}
                </div>
              )}
            </section>
            {groups.past.length > 0 && (
              <details className="group">
                <summary className="eyebrow flex cursor-pointer items-center gap-1">
                  Anteriores ({groups.past.reduce((n, g) => n + g.items.length, 0)})
                  <Icon name="chevronDown" className="size-3.5 transition group-open:rotate-180" />
                </summary>
                <div className="mt-2 space-y-3 opacity-80">
                  {groups.past.map((g) => (
                    <DayCard key={g.day} day={g.day} rows={g.items} areas={areas} onOpen={open} />
                  ))}
                </div>
              </details>
            )}
          </>
        )}
      </div>

      {openId && <CandidateDrawer id={openId} onClose={() => setParams(withParam(params, 'id', null))} />}
    </div>
  )
}

function DayCard({
  day,
  tag,
  rows,
  areas,
  onOpen,
}: {
  day: string
  tag?: string
  rows: CandidateRow[]
  areas: AreaLabels | undefined
  onOpen: (id: string) => void
}) {
  return (
    <article className="card overflow-hidden">
      <header className="flex items-center gap-2 border-b border-stone-100 bg-stone-50/60 px-4 py-2">
        <h3 className="text-sm font-semibold text-stone-900">{formatDayHeading(day)}</h3>
        {tag && <span className="rounded bg-brand-600 px-1.5 py-px text-[11px] font-semibold text-white">{tag}</span>}
        <span className="ml-auto text-xs text-stone-500">
          {rows.length} {rows.length === 1 ? 'entrevista' : 'entrevistas'}
        </span>
      </header>
      <ul className="divide-y divide-stone-100">
        {rows.map((row) => (
          <li key={row.id}>
            <button
              type="button"
              onClick={() => onOpen(row.id)}
              className="flex w-full items-center gap-4 px-4 py-2.5 text-left text-sm transition-colors hover:bg-brand-50/50"
            >
              <span className="w-12 font-semibold text-stone-900 tabular-nums">{row.interview_slot!.slice(11, 16)}</span>
              <span className="min-w-0 flex-1">
                <span className="flex items-center gap-1.5">
                  <span className="truncate font-medium text-stone-900">{row.full_name ?? 'Sin nombre'}</span>
                  <RecruiterTag status={row.recruiter_status} override={row.recruiter_override} />
                </span>
                <span className="block truncate text-xs text-stone-500">
                  {[
                    placeLabel(row.city, row.zone, areas),
                    row.vehicle_type ? VEHICLE[row.vehicle_type] : null,
                    row.experience_years != null ? `${row.experience_years} años de experiencia` : null,
                    LANGUAGE[row.language],
                  ]
                    .filter(Boolean)
                    .join(' · ')}
                </span>
              </span>
              <PriorityPill bucket={row.bucket} score={row.score} />
            </button>
          </li>
        ))}
      </ul>
    </article>
  )
}
