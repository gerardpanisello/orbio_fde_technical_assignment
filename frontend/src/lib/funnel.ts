import type { Analytics } from '../api/client'

/** Stages after the knock-out questions (age, vehicle/licence, location). */
const AFTER_KNOCKOUTS = ['availability', 'schedule', 'experience', 'start_date', 'recap', 'scheduling']

export type FunnelStep = { key: string; label: string; value: number; share: number }

/**
 * FR-13 funnel, derived from /api/analytics. Counts closed conversations only (in-progress
 * ones have no outcome yet). Opt-outs count as leaving at consent, and candidates sent to
 * manual review are not counted as having passed the knock-outs. Each step is clamped to
 * the previous one, so the funnel never widens. Waitlisted candidates (spec 015) are
 * qualified: they count as "Aptas" but not as booked (their zone was full).
 */
export function buildFunnel(a: Analytics): FunnelStep[] {
  const n = (status: string) => a.by_status[status] ?? 0
  const drop = (stage: string) => a.drop_off_by_stage[stage] ?? 0
  const booked = n('interview_scheduled')
  const qualified = booked + n('qualified_unscheduled') + n('waitlisted')
  const started = a.total - n('in_progress')
  const consented = started - n('opted_out') - drop('consent')
  const passed = qualified + AFTER_KNOCKOUTS.reduce((sum, stage) => sum + drop(stage), 0)

  const raw: [string, string, number][] = [
    ['started', 'Iniciadas', started],
    ['consented', 'Con consentimiento', consented],
    ['passed', 'Superan requisitos', passed],
    ['qualified', 'Aptas', qualified],
    ['booked', 'Entrevista agendada', booked],
  ]
  let previous = Infinity
  return raw.map(([key, label, value]) => {
    const clamped = Math.max(0, Math.min(value, previous))
    previous = clamped
    return { key, label, value: clamped, share: started > 0 ? clamped / started : 0 }
  })
}
