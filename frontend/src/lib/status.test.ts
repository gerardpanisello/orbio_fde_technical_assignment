import type { Status } from '../api/client'
import { FINAL_STATUSES, STATUS_META, STATUS_ORDER } from './status'

const ALL: Status[] = [
  'in_progress',
  'interview_scheduled',
  'qualified_unscheduled',
  'disqualified',
  'needs_review',
  'abandoned',
  'opted_out',
]

describe('status map', () => {
  it('covers every backend status exactly once, in one order', () => {
    expect([...STATUS_ORDER].sort()).toEqual([...ALL].sort())
  })

  it('gives every status a distinct colour and label (badges, table and charts share it)', () => {
    const colors = ALL.map((s) => STATUS_META[s].color)
    const labels = ALL.map((s) => STATUS_META[s].label)
    expect(new Set(colors).size).toBe(ALL.length)
    expect(new Set(labels).size).toBe(ALL.length)
  })

  it('treats everything but in_progress as final', () => {
    expect(FINAL_STATUSES).not.toContain('in_progress')
    expect(FINAL_STATUSES).toHaveLength(ALL.length - 1)
  })
})
