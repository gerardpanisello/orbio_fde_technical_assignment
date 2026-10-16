import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, type ReactNode } from 'react'
import { Link, useSearchParams } from 'react-router'
import {
  ApiError,
  api,
  type Availability,
  type AttendanceStatus,
  type Week,
  type WeekBooking,
  type WeekSlot,
} from '../api/client'
import { keys } from '../api/queries'
import { Icon } from '../components/Icon'
import { EmptyState, ErrorState, Loading, Spinner } from '../components/States'
import { errorMessage } from '../lib/errors'
import { withParam } from '../lib/filters'
import {
  BOOKING_STATUS,
  WEEKDAYS,
  availabilityPatch,
  buildWeekGrid,
  canMarkAttendance,
  localDayKey,
  mondayOf,
  normaliseTime,
  shiftWeek,
  slotCapacityText,
  validateAvailability,
  visibleDays,
  type AvailabilityForm,
} from '../lib/interviews'
import { STATUS_META } from '../lib/status'
import { CandidateDrawer } from './CandidateDrawer'
import { PageHeader, SeedButton } from './common'

const UNSCHEDULED = { status: 'qualified_unscheduled', sort: '-score' } as const
const WAITLISTED = { status: 'waitlisted', sort: '-score' } as const

/** Spec 010 FR-7: the interview agenda as a week per city, and the availability settings. */
export function InterviewsPage() {
  const [params, setParams] = useSearchParams()
  const tab = params.get('tab') === 'disponibilidad' ? 'availability' : 'agenda'
  const openId = params.get('id')
  const set = (key: string, value: string | null) => setParams(withParam(params, key, value), { replace: true })

  return (
    <div className="mx-auto max-w-[1200px] px-4 py-6 lg:px-8">
      <PageHeader title="Entrevistas" subtitle="Agendadas por Sofi en la conversación, por ciudad y semana." />

      <nav className="mt-4 flex gap-4 border-b border-stone-200" role="tablist">
        {(
          [
            ['agenda', 'Agenda', null],
            ['availability', 'Disponibilidad', 'disponibilidad'],
          ] as const
        ).map(([id, label, value]) => (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={tab === id}
            onClick={() => set('tab', value)}
            className={`-mb-px border-b-2 pb-2 text-sm font-medium transition-colors ${
              tab === id ? 'border-brand-600 text-stone-900' : 'border-transparent text-stone-500 hover:text-stone-800'
            }`}
          >
            {label}
          </button>
        ))}
      </nav>

      {tab === 'agenda' ? (
        <Agenda
          city={params.get('city')}
          week={params.get('week')}
          onCity={(c) => set('city', c)}
          onWeek={(w) => set('week', w)}
          onOpen={(id) => setParams(withParam(params, 'id', id))}
        />
      ) : (
        <AvailabilityTab />
      )}

      {openId && <CandidateDrawer id={openId} onClose={() => setParams(withParam(params, 'id', null))} />}
    </div>
  )
}

// --- agenda ------------------------------------------------------------------------------

function Agenda({
  city: cityParam,
  week: weekParam,
  onCity,
  onWeek,
  onOpen,
}: {
  city: string | null
  week: string | null
  onCity: (city: string) => void
  onWeek: (week: string | null) => void
  onOpen: (conversationId: string) => void
}) {
  const [thisWeek] = useState(() => mondayOf(new Date()))
  const availability = useQuery({ queryKey: keys.availability, queryFn: api.availability })
  const cities = availability.data ?? []
  const city = cityParam ?? cities[0]?.city ?? null
  const start = weekParam ?? thisWeek
  const week = useQuery({
    queryKey: keys.week(city ?? '', start),
    queryFn: () => api.week(city!, start),
    enabled: !!city,
    placeholderData: keepPreviousData,
  })
  const unscheduled = useQuery({ queryKey: keys.candidates(UNSCHEDULED), queryFn: () => api.listCandidates(UNSCHEDULED) })
  const waitlisted = useQuery({ queryKey: keys.candidates(WAITLISTED), queryFn: () => api.listCandidates(WAITLISTED) })
  const pending = unscheduled.data?.length ?? 0
  const waiting = waitlisted.data?.length ?? 0

  return (
    <>
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
            ninguna hora les venía bien o cancelaron. Llámales para agendar.
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

      <div className="mt-5 flex flex-wrap items-center gap-2">
        <select
          aria-label="Ciudad"
          className="field text-[13px]"
          value={city ?? ''}
          onChange={(e) => onCity(e.target.value)}
          disabled={!cities.length}
        >
          {cities.map((c) => (
            <option key={c.city} value={c.city}>
              {c.city_name} ({c.country})
            </option>
          ))}
        </select>
        <div className="flex items-center gap-1">
          <button type="button" className="btn-ghost" onClick={() => onWeek(shiftWeek(start, -1))} aria-label="Semana anterior">
            <Icon name="arrowLeft" />
          </button>
          <span className="min-w-44 text-center text-sm font-medium text-stone-800">{weekLabel(start)}</span>
          <button type="button" className="btn-ghost" onClick={() => onWeek(shiftWeek(start, 1))} aria-label="Semana siguiente">
            <Icon name="arrowRight" />
          </button>
        </div>
        {start !== thisWeek && (
          <button type="button" className="btn-secondary" onClick={() => onWeek(null)}>
            Esta semana
          </button>
        )}
        {week.isFetching && !week.isLoading && <Spinner className="size-3.5 text-stone-400" />}
        {week.data && (
          <span className="ml-auto text-xs text-stone-500">Horas locales de {week.data.city_name} ({week.data.timezone})</span>
        )}
      </div>

      <section className="card mt-3 overflow-hidden">
        {availability.isLoading || (week.isLoading && !!city) ? (
          <Loading />
        ) : availability.isError ? (
          <ErrorState error={availability.error} onRetry={() => availability.refetch()} />
        ) : !city ? (
          <EmptyState icon="calendar" title="No hay ciudades con agenda de entrevistas" />
        ) : week.isError || !week.data ? (
          <ErrorState error={week.error} onRetry={() => week.refetch()} />
        ) : (
          <WeekView week={week.data} onOpen={onOpen} />
        )}
      </section>
    </>
  )
}

function weekLabel(start: string): string {
  const [y, m, d] = start.split('-').map(Number)
  const from = new Date(y, m - 1, d)
  const to = new Date(y, m - 1, d + 6)
  const day = (date: Date) => date.toLocaleDateString('es-ES', { day: 'numeric', month: 'short' })
  return `${day(from)} – ${day(to)} ${to.getFullYear()}`
}

function WeekView({ week, onOpen }: { week: Week; onOpen: (id: string) => void }) {
  const days = visibleDays(week)
  const grid = buildWeekGrid({ days })
  const [today] = useState(() => localDayKey(new Date()))
  if (!days.length) {
    return (
      <EmptyState icon="calendar" title="Sin entrevistas esta semana" action={<SeedButton />}>
        Esta ciudad no tiene horas de entrevista estos días. Revisa la pestaña Disponibilidad.
      </EmptyState>
    )
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[720px] table-fixed text-left text-[13px]">
        <thead className="bg-stone-50 text-[11px] font-semibold tracking-wide text-stone-500 uppercase">
          <tr>
            <th scope="col" className="w-16 px-3 py-2">Hora</th>
            {days.map((d) => (
              <th key={d.date} scope="col" className={`px-2 py-2 ${d.date === today ? 'text-brand-700' : ''}`}>
                {WEEKDAYS.find((w) => w.id === d.weekday)?.long.slice(0, 3)} {Number(d.date.slice(8))}
                {d.date === today && <span className="ml-1 normal-case">· hoy</span>}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-stone-100">
          {grid.times.map((time) => (
            <tr key={time} className="align-top">
              <th scope="row" className="px-3 py-2 font-semibold text-stone-900 tabular-nums">{time}</th>
              {days.map((d) => (
                <td key={d.date} className="px-1.5 py-1.5">
                  <SlotCell slot={grid.cells[time][d.date]} onOpen={onOpen} />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function SlotCell({ slot, onOpen }: { slot: WeekSlot | null; onOpen: (id: string) => void }) {
  if (!slot) return <div className="h-full min-h-10 rounded-md bg-stone-50/60" aria-hidden="true" />
  const full = slot.in_agenda && slot.booked >= slot.capacity
  return (
    <div
      className={`min-h-10 rounded-md border px-2 py-1.5 ${
        slot.past ? 'border-stone-100 bg-stone-50 text-stone-500' : full ? 'border-brand-200 bg-brand-50/60' : 'border-stone-200 bg-white'
      }`}
      title={slot.past ? 'Hora pasada' : undefined}
    >
      <div className={`text-[11px] tabular-nums ${slot.booked ? 'font-semibold text-stone-700' : 'text-stone-400'}`}>
        {slotCapacityText(slot)}
      </div>
      {slot.bookings.length > 0 && (
        <ul className="mt-1 space-y-1">
          {slot.bookings.map((b) => (
            <BookingChip key={b.booking_id} booking={b} slot={slot} onOpen={onOpen} />
          ))}
        </ul>
      )}
    </div>
  )
}

const ATTENDANCE_MARK: Record<WeekBooking['status'], { icon: string; className: string }> = {
  booked: { icon: '', className: 'border-stone-200 bg-white text-stone-800' },
  attended: { icon: '✓', className: 'border-emerald-200 bg-emerald-50 text-emerald-900' },
  no_show: { icon: '✗', className: 'border-red-200 bg-red-50 text-red-900' },
}

function BookingChip({ booking, slot, onOpen }: { booking: WeekBooking; slot: WeekSlot; onOpen: (id: string) => void }) {
  const queryClient = useQueryClient()
  const [error, setError] = useState<string | null>(null)
  const mark = useMutation({
    mutationFn: (status: AttendanceStatus) => api.markAttendance(booking.booking_id, status),
    onMutate: () => setError(null),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: keys.allWeeks })
      void queryClient.invalidateQueries({ queryKey: keys.analytics })
      void queryClient.invalidateQueries({ queryKey: keys.candidate(booking.conversation_id) })
    },
    onError: (e) =>
      setError(
        e instanceof ApiError && e.status === 409
          ? 'No se puede marcar todavía (la entrevista no ha empezado o ya no está vigente)'
          : errorMessage(e),
      ),
  })
  const mark_ = ATTENDANCE_MARK[booking.status]
  const name = booking.full_name ?? 'Sin nombre'
  return (
    <li>
      <button
        type="button"
        onClick={() => onOpen(booking.conversation_id)}
        className={`flex w-full items-center gap-1 truncate rounded border px-1.5 py-0.5 text-left text-xs font-medium hover:border-brand-300 ${mark_.className}`}
        title={`${name} · ${BOOKING_STATUS[booking.status]}`}
      >
        {mark_.icon && <span aria-hidden="true">{mark_.icon}</span>}
        <span className="truncate">{name}</span>
        <span className="sr-only"> · {BOOKING_STATUS[booking.status]}</span>
      </button>
      {canMarkAttendance(slot, booking.status) && (
        <div className="mt-0.5 flex flex-wrap items-center gap-1 text-[11px]">
          {mark.isPending ? (
            <Spinner className="size-3 text-stone-400" />
          ) : booking.status === 'booked' ? (
            <>
              <button type="button" className="rounded px-1 text-emerald-800 hover:bg-emerald-50" onClick={() => mark.mutate('attended')}>
                Asistió
              </button>
              <button type="button" className="rounded px-1 text-red-800 hover:bg-red-50" onClick={() => mark.mutate('no_show')}>
                No se presentó
              </button>
            </>
          ) : (
            <button type="button" className="rounded px-1 text-stone-600 hover:bg-stone-100" onClick={() => mark.mutate('booked')}>
              Deshacer
            </button>
          )}
        </div>
      )}
      {error && (
        <p role="alert" className="mt-0.5 text-[11px] text-red-700">
          {error}
        </p>
      )}
    </li>
  )
}

// --- availability ------------------------------------------------------------------------

function AvailabilityTab() {
  const availability = useQuery({ queryKey: keys.availability, queryFn: api.availability })
  return (
    <div className="mt-5 space-y-4">
      <p className="rounded-lg bg-brand-50/60 px-3 py-2 text-sm text-stone-700">
        Los cambios se aplican a los huecos que Sofi ofrezca a partir de ahora; las entrevistas ya agendadas no cambian.
      </p>
      {availability.isLoading ? (
        <Loading />
      ) : availability.isError || !availability.data ? (
        <ErrorState error={availability.error} onRetry={() => availability.refetch()} />
      ) : availability.data.length === 0 ? (
        <div className="card">
          <EmptyState icon="calendar" title="No hay ciudades con agenda de entrevistas" />
        </div>
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          {availability.data.map((a) => (
            <AvailabilityEditor key={a.city} availability={a} />
          ))}
        </div>
      )}
    </div>
  )
}

function formOf(a: Availability): AvailabilityForm {
  return {
    weekdays: a.weekdays,
    times: a.times,
    capacity: a.capacity,
    duration_min: a.duration_min,
    days_ahead: a.days_ahead,
    place: a.place,
  }
}

function AvailabilityEditor({ availability }: { availability: Availability }) {
  const queryClient = useQueryClient()
  const original = formOf(availability)
  const [form, setForm] = useState<AvailabilityForm>(original)
  const [newTime, setNewTime] = useState('')
  const [timeError, setTimeError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)
  const errors = validateAvailability(form)
  const patch = availabilityPatch(original, form)
  const dirty = Object.keys(patch).length > 0
  const valid = Object.keys(errors).length === 0

  const save = useMutation({
    mutationFn: () => api.updateAvailability(availability.city, patch),
    onSuccess: (updated) => {
      queryClient.setQueryData<Availability[]>(keys.availability, (list) =>
        list?.map((a) => (a.city === updated.city ? updated : a)),
      )
      void queryClient.invalidateQueries({ queryKey: keys.allWeeks })
      setSaved(true)
    },
  })

  const update = (change: Partial<AvailabilityForm>) => {
    setSaved(false)
    setForm((f) => ({ ...f, ...change }))
  }
  const addTime = () => {
    const time = normaliseTime(newTime)
    if (!time) return setTimeError('Formato HH:MM, p. ej. 09:30')
    if (form.times.includes(time)) return setTimeError('Esa hora ya está')
    setTimeError(null)
    setNewTime('')
    update({ times: [...form.times, time].sort() })
  }

  return (
    <form
      className="card space-y-3 p-4"
      onSubmit={(e) => {
        e.preventDefault()
        if (dirty && valid) save.mutate()
      }}
      aria-label={`Disponibilidad de ${availability.city_name}`}
    >
      <header className="flex items-baseline justify-between gap-2">
        <h2 className="text-sm font-semibold text-stone-900">
          {availability.city_name} <span className="text-xs font-normal text-stone-500">· {availability.timezone}</span>
        </h2>
        <span className="text-[11px] text-stone-400">
          Actualizado {new Date(availability.updated_at).toLocaleString('es-ES', { dateStyle: 'short', timeStyle: 'short' })}
        </span>
      </header>

      <Field label="Días" error={errors.weekdays}>
        <div className="flex gap-1" role="group" aria-label="Días de entrevista">
          {WEEKDAYS.map((w) => {
            const on = form.weekdays.includes(w.id)
            return (
              <button
                key={w.id}
                type="button"
                aria-pressed={on}
                title={w.long}
                onClick={() => update({ weekdays: on ? form.weekdays.filter((d) => d !== w.id) : [...form.weekdays, w.id] })}
                className={`size-8 rounded-full border text-xs font-semibold transition ${
                  on ? 'border-brand-600 bg-brand-600 text-white' : 'border-stone-200 bg-white text-stone-500 hover:border-stone-300'
                }`}
              >
                {w.short}
              </button>
            )
          })}
        </div>
      </Field>

      <Field label="Horas" error={errors.times ?? timeError ?? undefined}>
        <div className="flex flex-wrap items-center gap-1.5">
          {form.times.map((t) => (
            <span key={t} className="inline-flex items-center gap-1 rounded-full bg-stone-100 py-0.5 pr-1 pl-2 text-xs font-medium text-stone-800 tabular-nums">
              {t}
              <button
                type="button"
                aria-label={`Quitar ${t}`}
                onClick={() => update({ times: form.times.filter((x) => x !== t) })}
                className="rounded-full p-0.5 text-stone-500 hover:bg-stone-200 hover:text-stone-900"
              >
                <Icon name="x" className="size-3" />
              </button>
            </span>
          ))}
          <input
            value={newTime}
            onChange={(e) => setNewTime(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault()
                addTime()
              }
            }}
            placeholder="HH:MM"
            aria-label={`Nueva hora en ${availability.city_name}`}
            className="field h-7 w-20 text-xs tabular-nums"
          />
          <button type="button" className="btn-ghost h-7 text-xs" onClick={addTime}>
            Añadir
          </button>
        </div>
      </Field>

      <div className="grid grid-cols-3 gap-3">
        <NumberField label="Plazas por hora" value={form.capacity} error={errors.capacity} onChange={(n) => update({ capacity: n })} />
        <NumberField label="Duración (min)" value={form.duration_min} error={errors.duration_min} onChange={(n) => update({ duration_min: n })} />
        <NumberField label="Días a ofrecer" value={form.days_ahead} error={errors.days_ahead} onChange={(n) => update({ days_ahead: n })} />
      </div>

      <Field label="Lugar" error={errors.place}>
        <input
          value={form.place}
          onChange={(e) => update({ place: e.target.value })}
          aria-label={`Lugar en ${availability.city_name}`}
          className="field w-full text-[13px]"
        />
      </Field>

      <div className="flex items-center gap-3 pt-1">
        <button type="submit" className="btn-primary" disabled={!dirty || !valid || save.isPending}>
          {save.isPending && <Spinner className="size-3.5" />} Guardar
        </button>
        {dirty && (
          <button
            type="button"
            className="btn-ghost"
            onClick={() => {
              setForm(original)
              setTimeError(null)
              save.reset()
            }}
          >
            Descartar
          </button>
        )}
        <span aria-live="polite" className="text-xs">
          {save.isError ? (
            <span className="text-red-700">{errorMessage(save.error)}</span>
          ) : saved && !dirty ? (
            <span className="text-emerald-700">Guardado: se aplica a los próximos huecos ofrecidos</span>
          ) : null}
        </span>
      </div>
    </form>
  )
}

function Field({ label, error, children }: { label: string; error?: string; children: ReactNode }) {
  return (
    <div>
      <div className="mb-1 text-xs font-medium text-stone-600">{label}</div>
      {children}
      {error && <p className="mt-1 text-xs text-red-700">{error}</p>}
    </div>
  )
}

function NumberField({
  label,
  value,
  error,
  onChange,
}: {
  label: string
  value: number
  error?: string
  onChange: (value: number) => void
}) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium text-stone-600">{label}</span>
      <input
        type="number"
        inputMode="numeric"
        value={Number.isNaN(value) ? '' : value}
        onChange={(e) => onChange(e.target.value === '' ? Number.NaN : Number(e.target.value))}
        className="field h-8 w-full text-right tabular-nums"
      />
      {error && <span className="mt-1 block text-xs text-red-700">{error}</span>}
    </label>
  )
}
