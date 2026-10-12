import type { Analytics } from '../api/client'
import { buildFunnel } from './funnel'

const base: Analytics = {
  total: 40,
  by_status: {
    abandoned: 8,
    disqualified: 10,
    interview_scheduled: 15,
    needs_review: 2,
    opted_out: 2,
    qualified_unscheduled: 3,
  },
  finished: 30,
  completion_rate: 0.75,
  drop_off_by_stage: { availability: 3, consent: 3, start_date: 1, vehicle_license: 1 },
  median_duration_s: 979,
  disqualification_reasons: { no_license: 2, out_of_area: 5, under_age: 3 },
  agent_turns: 351,
  fallback_rate: 0,
  avg_cost_usd: 0,
  by_country: {},
}

describe('buildFunnel', () => {
  it('derives each stage from the analytics counts (seeded demo data)', () => {
    const steps = buildFunnel(base)
    expect(steps.map((s) => [s.key, s.value])).toEqual([
      ['started', 40],
      ['consented', 35], // minus 2 opt-outs and 3 who left at consent
      ['passed', 22], // 18 qualified + 4 who left after the knock-outs
      ['qualified', 18],
      ['booked', 15],
    ])
    expect(steps[4].share).toBeCloseTo(15 / 40)
  })

  it('leaves in-progress conversations out and never widens', () => {
    const steps = buildFunnel({ ...base, total: 41, by_status: { ...base.by_status, in_progress: 1 } })
    expect(steps[0].value).toBe(40)
    for (let i = 1; i < steps.length; i++) expect(steps[i].value).toBeLessThanOrEqual(steps[i - 1].value)
  })

  it('counts waitlisted candidates as qualified, not booked (spec 015)', () => {
    const steps = buildFunnel({
      ...base,
      total: 42,
      by_status: { ...base.by_status, waitlisted: 2 },
    })
    const value = (key: string) => steps.find((s) => s.key === key)?.value
    expect(value('qualified')).toBe(20)
    expect(value('booked')).toBe(15)
  })

  it('handles no data', () => {
    const steps = buildFunnel({ ...base, total: 0, by_status: {}, drop_off_by_stage: {} })
    expect(steps.every((s) => s.value === 0 && s.share === 0)).toBe(true)
  })
})
