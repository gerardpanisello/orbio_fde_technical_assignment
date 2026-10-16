/** Interview scheduling (spec 010): week grid, slot labels, attendance and the availability form. */
import type { Availability, AvailabilityPatch, Booking, Week, WeekBooking, WeekSlot } from '../api/client'

export function localDayKey(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

/** The Monday of the week that contains `date`, as "YYYY-MM-DD" (the week endpoint's `start`). */
export function mondayOf(date: Date): string {
  const d = new Date(date.getFullYear(), date.getMonth(), date.getDate())
  d.setDate(d.getDate() - ((d.getDay() + 6) % 7))
  return localDayKey(d)
}

/** "2026-10-12" + 1 week -> "2026-10-19" (calendar maths on the date only, no timezones). */
export function shiftWeek(start: string, weeks: number): string {
  const [y, m, d] = start.split('-').map(Number)
  return localDayKey(new Date(y, m - 1, d + 7 * weeks))
}

export type WeekGrid = {
  days: Week['days']
  /** Every time any day has, sorted: the grid's rows. */
  times: string[]
  /** cells[time][date] = the slot, or null where that day has no slot at that time. */
  cells: Record<string, Record<string, WeekSlot | null>>
}

export function buildWeekGrid(week: Pick<Week, 'days'>): WeekGrid {
  const times = [...new Set(week.days.flatMap((d) => d.slots.map((s) => s.time)))].sort()
  const cells: WeekGrid['cells'] = {}
  for (const time of times) {
    cells[time] = {}
    for (const day of week.days) cells[time][day.date] = day.slots.find((s) => s.time === time) ?? null
  }
  return { days: week.days, times, cells }
}

/** Days worth a column: open days, plus any day that has a slot (e.g. a booking kept after an agenda change). */
export function visibleDays(week: Pick<Week, 'days'>): Week['days'] {
  return week.days.filter((d) => d.slots.length > 0)
}

/** "1/3", "3/3 · completo", "1 · fuera de agenda" (a booking kept after the agenda changed). */
export function slotCapacityText(slot: Pick<WeekSlot, 'booked' | 'capacity' | 'in_agenda'>): string {
  if (!slot.in_agenda) return `${slot.booked} · fuera de agenda`
  return slot.booked >= slot.capacity ? `${slot.booked}/${slot.capacity} · completo` : `${slot.booked}/${slot.capacity}`
}

/** Attendance can be marked once the interview has started, on a live booking (else the API says 409). */
export function canMarkAttendance(slot: Pick<WeekSlot, 'past'>, status: WeekBooking['status'] | Booking['status']): boolean {
  return slot.past && (status === 'booked' || status === 'attended' || status === 'no_show')
}

export const BOOKING_STATUS: Record<Booking['status'], string> = {
  booked: 'Agendada',
  attended: 'Asistió',
  no_show: 'No se presentó',
  cancelled: 'Cancelada',
  rescheduled: 'Cambiada de hora',
}

export const WEEKDAYS: { id: Availability['weekdays'][number]; short: string; long: string }[] = [
  { id: 'mon', short: 'L', long: 'Lunes' },
  { id: 'tue', short: 'M', long: 'Martes' },
  { id: 'wed', short: 'X', long: 'Miércoles' },
  { id: 'thu', short: 'J', long: 'Jueves' },
  { id: 'fri', short: 'V', long: 'Viernes' },
  { id: 'sat', short: 'S', long: 'Sábado' },
  { id: 'sun', short: 'D', long: 'Domingo' },
]

/** "9:5" / "9:05" / "09:05" -> "09:05"; anything else -> null. */
export function normaliseTime(text: string): string | null {
  const match = /^(\d{1,2}):(\d{1,2})$/.exec(text.trim())
  if (!match) return null
  const [h, m] = [Number(match[1]), Number(match[2])]
  if (h > 23 || m > 59) return null
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`
}

export type AvailabilityForm = Pick<Availability, 'weekdays' | 'times' | 'capacity' | 'duration_min' | 'days_ahead' | 'place'>
export type FormErrors = Partial<Record<keyof AvailabilityForm, string>>

/**
 * Mirrors the backend rules (scheduling/config.py AvailabilitySettings), so most mistakes are
 * caught before saving; the server stays the authority (its 422 is shown too).
 */
export function validateAvailability(form: AvailabilityForm): FormErrors {
  const errors: FormErrors = {}
  const int = (n: number) => Number.isInteger(n)
  if (form.weekdays.length === 0) errors.weekdays = 'Elige al menos un día'
  if (form.times.length === 0) errors.times = 'Añade al menos una hora'
  else if (form.times.length > 24) errors.times = 'Como mucho 24 horas'
  else if (form.times.some((t) => normaliseTime(t) !== t)) errors.times = 'Formato HH:MM'
  else if (new Set(form.times).size !== form.times.length) errors.times = 'Cada hora solo una vez'
  if (!int(form.capacity) || form.capacity < 1 || form.capacity > 50) errors.capacity = 'Entre 1 y 50'
  if (!int(form.duration_min) || form.duration_min < 5 || form.duration_min > 240) errors.duration_min = 'Entre 5 y 240 min'
  if (!int(form.days_ahead) || form.days_ahead < 1 || form.days_ahead > 15) errors.days_ahead = 'Entre 1 y 15 días'
  const place = form.place.trim()
  if (!place) errors.place = 'Indica el lugar'
  else if (place.length > 200) errors.place = 'Como mucho 200 caracteres'
  return errors
}

/** Only what changed, in the backend's canonical order (sorted times, Monday-first days). */
export function availabilityPatch(original: AvailabilityForm, form: AvailabilityForm): AvailabilityPatch {
  const order = WEEKDAYS.map((w) => w.id)
  const weekdays = [...form.weekdays].sort((a, b) => order.indexOf(a) - order.indexOf(b))
  const times = [...form.times].sort()
  const patch: AvailabilityPatch = {}
  if (weekdays.join() !== original.weekdays.join()) patch.weekdays = weekdays
  if (times.join() !== original.times.join()) patch.times = times
  if (form.capacity !== original.capacity) patch.capacity = form.capacity
  if (form.duration_min !== original.duration_min) patch.duration_min = form.duration_min
  if (form.days_ahead !== original.days_ahead) patch.days_ahead = form.days_ahead
  if (form.place.trim() !== original.place) patch.place = form.place.trim()
  return patch
}
