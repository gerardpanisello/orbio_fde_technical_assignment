import type { CandidateRow } from '../api/client'
import { groupByDay } from './interviews'

const row = (id: string, slot: string | null) => ({ id, interview_slot: slot }) as CandidateRow

describe('groupByDay', () => {
  it('splits upcoming (ascending) from past (most recent first), sorted by time within a day', () => {
    const rows = [
      row('a', '2026-10-13T17:00'),
      row('b', '2026-10-13T10:00'),
      row('c', '2026-10-12T10:00'),
      row('d', '2026-10-09T10:00'),
      row('e', '2026-10-07T17:00'),
      row('f', null),
    ]
    const { upcoming, past } = groupByDay(rows, '2026-10-12')
    expect(upcoming.map((g) => g.day)).toEqual(['2026-10-12', '2026-10-13'])
    expect(upcoming[1].items.map((r) => r.id)).toEqual(['b', 'a'])
    expect(past.map((g) => g.day)).toEqual(['2026-10-09', '2026-10-07'])
  })
})
