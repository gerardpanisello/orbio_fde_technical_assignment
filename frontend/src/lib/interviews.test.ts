import type { WeekSlot } from '../api/client'
import {
  availabilityPatch,
  buildWeekGrid,
  canMarkAttendance,
  mondayOf,
  normaliseTime,
  shiftWeek,
  slotCapacityText,
  validateAvailability,
  visibleDays,
} from './interviews'

function slot(time: string, extra: Partial<WeekSlot> = {}): WeekSlot {
  return {
    slot_id: `madrid:2026-10-12T${time}`,
    time,
    starts_at: '2026-10-12T08:00:00Z',
    capacity: 3,
    booked: 0,
    in_agenda: true,
    past: false,
    bookings: [],
    ...extra,
  }
}

describe('week navigation', () => {
  it('finds the Monday and moves by whole weeks', () => {
    expect(mondayOf(new Date(2026, 9, 16))).toBe('2026-10-12') // Friday
    expect(mondayOf(new Date(2026, 9, 18))).toBe('2026-10-12') // Sunday
    expect(mondayOf(new Date(2026, 9, 12))).toBe('2026-10-12') // Monday
    expect(shiftWeek('2026-10-12', 1)).toBe('2026-10-19')
    expect(shiftWeek('2026-10-12', -2)).toBe('2026-09-28')
  })
})

describe('buildWeekGrid', () => {
  const week = {
    days: [
      { date: '2026-10-12', weekday: 'mon' as const, slots: [slot('10:00'), slot('17:00')] },
      { date: '2026-10-13', weekday: 'tue' as const, slots: [slot('12:00'), slot('10:00')] },
      { date: '2026-10-17', weekday: 'sat' as const, slots: [] },
    ],
  }

  it('makes one row per time across the week and leaves gaps empty', () => {
    const grid = buildWeekGrid(week)
    expect(grid.times).toEqual(['10:00', '12:00', '17:00'])
    expect(grid.cells['12:00']['2026-10-12']).toBeNull()
    expect(grid.cells['12:00']['2026-10-13']?.time).toBe('12:00')
    expect(grid.cells['17:00']['2026-10-17']).toBeNull()
  })

  it('hides closed days', () => {
    expect(visibleDays(week).map((d) => d.weekday)).toEqual(['mon', 'tue'])
  })
})

describe('slot labels and attendance', () => {
  it('shows seats taken over capacity', () => {
    expect(slotCapacityText(slot('10:00', { booked: 1 }))).toBe('1/3')
    expect(slotCapacityText(slot('10:00', { booked: 3 }))).toBe('3/3 · completo')
    expect(slotCapacityText(slot('10:00', { booked: 1, in_agenda: false }))).toBe('1 · fuera de agenda')
  })

  it('allows attendance only on past slots with a live booking', () => {
    expect(canMarkAttendance({ past: true }, 'booked')).toBe(true)
    expect(canMarkAttendance({ past: true }, 'attended')).toBe(true)
    expect(canMarkAttendance({ past: true }, 'no_show')).toBe(true)
    expect(canMarkAttendance({ past: false }, 'booked')).toBe(false)
    expect(canMarkAttendance({ past: true }, 'cancelled')).toBe(false)
    expect(canMarkAttendance({ past: true }, 'rescheduled')).toBe(false)
  })
})

describe('availability form', () => {
  const ok = {
    weekdays: ['mon', 'wed'] as ('mon' | 'wed')[],
    times: ['10:00', '17:00'],
    capacity: 3,
    duration_min: 30,
    days_ahead: 3,
    place: 'Oficina',
  }

  it('accepts a valid form', () => {
    expect(validateAvailability(ok)).toEqual({})
  })

  it('mirrors the backend limits', () => {
    expect(
      validateAvailability({ ...ok, weekdays: [], times: ['10:00', '10:00'], capacity: 0, duration_min: 300, days_ahead: 1.5, place: '  ' }),
    ).toEqual({
      weekdays: 'Elige al menos un día',
      times: 'Cada hora solo una vez',
      capacity: 'Entre 1 y 50',
      duration_min: 'Entre 5 y 240 min',
      days_ahead: 'Entre 1 y 15 días',
      place: 'Indica el lugar',
    })
    expect(validateAvailability({ ...ok, times: [] }).times).toBe('Añade al menos una hora')
    expect(validateAvailability({ ...ok, times: ['9:00'] }).times).toBe('Formato HH:MM')
  })

  it('normalises times', () => {
    expect(normaliseTime('9:5')).toBe('09:05')
    expect(normaliseTime(' 17:30 ')).toBe('17:30')
    expect(normaliseTime('24:00')).toBeNull()
    expect(normaliseTime('ten')).toBeNull()
  })

  it('sends only what changed, in canonical order', () => {
    expect(availabilityPatch(ok, ok)).toEqual({})
    expect(
      availabilityPatch(ok, { ...ok, weekdays: ['wed', 'mon'], times: ['17:00', '09:30', '10:00'], capacity: 4 }),
    ).toEqual({ times: ['09:30', '10:00', '17:00'], capacity: 4 })
  })
})
