import { formatDate, formatDuration, formatSlot, formatStartDate, timeAgo } from './format'

describe('format', () => {
  it('formats an interview slot as weekday dd/mm, hh:mm without timezone shifts', () => {
    expect(formatSlot('2026-10-13T10:00')).toBe('martes 13/10, 10:00')
    expect(formatSlot('2026-10-13T17:00', 'en')).toBe('Tuesday 13/10, 17:00')
    expect(formatSlot(null)).toBe('—')
  })

  it('formats dates, durations and relative times', () => {
    expect(formatDate('2026-10-05')).toBe('05/10/2026')
    expect(formatDuration(979)).toBe('16 min')
    expect(formatDuration(null)).toBe('—')
    const now = new Date('2026-10-12T12:00:00Z')
    expect(timeAgo('2026-10-12T09:00:00Z', now)).toBe('hace 3 h')
    expect(timeAgo('2026-10-10T12:00:00Z', now)).toBe('hace 2 d')
  })

  it('shows a month-level start date as the month only', () => {
    expect(formatStartDate('2026-11-01', true)).toBe('a partir de noviembre')
    expect(formatStartDate('2027-01-01', true)).toBe('a partir de enero')
    expect(formatStartDate('2026-11-01', false)).toBe('01/11/2026')
    expect(formatStartDate(null, true)).toBe('—')
  })
})
