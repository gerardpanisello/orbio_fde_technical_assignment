import type { CandidateRow } from '../api/client'
import { slotDayKey } from './format'

export function localDayKey(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

/** Booked interviews grouped by day, upcoming first; slots are local times as offered. */
export function groupByDay(rows: CandidateRow[], today: string) {
  const days = new Map<string, CandidateRow[]>()
  for (const row of rows) {
    if (!row.interview_slot) continue
    const key = slotDayKey(row.interview_slot)
    days.set(key, [...(days.get(key) ?? []), row])
  }
  const sorted = [...days.entries()].map(([day, items]) => ({
    day,
    items: items.sort((a, b) => a.interview_slot!.localeCompare(b.interview_slot!)),
  }))
  return {
    upcoming: sorted.filter((d) => d.day >= today).sort((a, b) => a.day.localeCompare(b.day)),
    past: sorted.filter((d) => d.day < today).sort((a, b) => b.day.localeCompare(a.day)),
  }
}
