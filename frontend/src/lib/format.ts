/** Date, number and duration formatting (es-ES for recruiters, es/en/ca for the chat). */
import type { Language } from '../api/client'

type Lang = Language
const LOCALE: Record<Lang, string> = { es: 'es-ES', en: 'en-GB', ca: 'ca-ES' }

/**
 * Interview slots are ISO *local* date-times without a timezone ("2026-10-13T10:00"):
 * the time the candidate was offered. Parse the parts as-is, never convert timezones.
 */
export function parseSlot(slot: string): Date | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(slot)
  if (!match) return null
  const [, y, mo, d, h, mi] = match.map(Number)
  return new Date(y, mo - 1, d, h, mi)
}

/** "martes 13/10, 10:00" (es), "Tuesday 13/10, 10:00" (en) or "dimarts 13/10, 10:00" (ca). */
export function formatSlot(slot: string | null | undefined, lang: Lang = 'es'): string {
  if (!slot) return '—'
  const date = parseSlot(slot)
  if (!date) return slot
  const weekday = date.toLocaleDateString(LOCALE[lang], { weekday: 'long' })
  const dd = String(date.getDate()).padStart(2, '0')
  const mm = String(date.getMonth() + 1).padStart(2, '0')
  return `${weekday} ${dd}/${mm}, ${slot.slice(11, 16)}`
}

/** Day key and heading for grouping interviews: "2026-10-13", "martes, 13 de octubre". */
export function slotDayKey(slot: string): string {
  return slot.slice(0, 10)
}

export function formatDayHeading(dayKey: string): string {
  const date = parseSlot(`${dayKey}T00:00`)
  if (!date) return dayKey
  const text = date.toLocaleDateString('es-ES', { weekday: 'long', day: 'numeric', month: 'long' })
  return text.charAt(0).toUpperCase() + text.slice(1)
}

export function formatTime(iso: string, lang: Lang = 'es'): string {
  return new Date(iso).toLocaleTimeString(LOCALE[lang], { hour: '2-digit', minute: '2-digit' })
}

export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString('es-ES', {
    day: '2-digit',
    month: '2-digit',
    year: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

const MONTHS_ES = [
  'enero',
  'febrero',
  'marzo',
  'abril',
  'mayo',
  'junio',
  'julio',
  'agosto',
  'septiembre',
  'octubre',
  'noviembre',
  'diciembre',
]

/**
 * A start date: "15/10/2026", or "a partir de noviembre" when the candidate only gave a
 * month ("el mes que viene"; flag `start_date_approximate`): the stored 1st is not a day
 * they chose.
 */
export function formatStartDate(isoDate: string | null | undefined, approximate: boolean): string {
  if (!isoDate || !approximate) return formatDate(isoDate)
  const month = Number(isoDate.slice(5, 7))
  return `a partir de ${MONTHS_ES[month - 1]}`
}

/** ISO date ("2026-10-15") -> "15/10/2026". */
export function formatDate(isoDate: string | null | undefined): string {
  if (!isoDate) return '—'
  const [y, m, d] = isoDate.slice(0, 10).split('-')
  return `${d}/${m}/${y}`
}

/** "hace 5 min", "hace 3 h", "hace 2 d" (dense table column). */
export function timeAgo(iso: string, now: Date = new Date()): string {
  const seconds = Math.max(0, (now.getTime() - new Date(iso).getTime()) / 1000)
  if (seconds < 60) return 'ahora'
  if (seconds < 3600) return `hace ${Math.floor(seconds / 60)} min`
  if (seconds < 86400) return `hace ${Math.floor(seconds / 3600)} h`
  return `hace ${Math.floor(seconds / 86400)} d`
}

export function formatDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return '—'
  if (seconds < 60) return `${Math.round(seconds)} s`
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return `${minutes} min`
  return `${Math.floor(minutes / 60)} h ${minutes % 60} min`
}

export function formatPercent(ratio: number, digits = 0): string {
  return `${(ratio * 100).toFixed(digits).replace('.', ',')} %`
}

export function formatUsd(value: number): string {
  return `${value.toLocaleString('es-ES', { minimumFractionDigits: 3, maximumFractionDigits: 4 })} $`
}
