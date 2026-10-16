/** Re-engagement (spec 008): reminder labels, the next step and when the chat polls. */
import type { CandidateDetail, Status } from '../api/client'

type Reengagement = CandidateDetail['reengagement']
type Next = NonNullable<Reengagement['next']>

/**
 * "Recordatorio 1/3", or "Recordatorio 1" while the total is unknown (see `followUpTotal`).
 */
export function followUpLabel(step: number, total: number | null = null, lang: 'es' | 'en' = 'es'): string {
  const word = lang === 'en' ? 'Reminder' : 'Recordatorio'
  return total && total >= step ? `${word} ${step}/${total}` : `${word} ${step}`
}

/**
 * The number of reminders in the schedule: `total_steps` from the API (config/reengagement.yaml).
 * Older responses without it fall back to what the data reveals: the step whose trace says
 * `last_call`, or the reminders already sent when only the abandon is left.
 */
export function followUpTotal(detail: Pick<CandidateDetail, 'traces' | 'reengagement'> | undefined): number | null {
  if (!detail) return null
  if (detail.reengagement.total_steps > 0) return detail.reengagement.total_steps
  for (const trace of detail.traces) {
    const followUp = (trace.trace as { follow_up?: { step?: unknown; kind?: unknown } } | null)?.follow_up
    if (followUp?.kind === 'last_call' && typeof followUp.step === 'number') return followUp.step
  }
  const { next, waiting_steps } = detail.reengagement
  return next?.action === 'abandon' && waiting_steps > 0 ? waiting_steps : null
}

/** "en 21 h", "en 5 min", "en 3 d", "ahora" (past or under a minute). */
export function formatRelative(at: string, now: Date = new Date()): string {
  const seconds = (new Date(at).getTime() - now.getTime()) / 1000
  if (seconds < 60) return 'ahora'
  if (seconds < 3600) return `en ${Math.round(seconds / 60)} min`
  if (seconds < 48 * 3600) return `en ${Math.round(seconds / 3600)} h`
  return `en ${Math.round(seconds / 86400)} d`
}

/** "recordatorio 2 · en 21 h" or "abandono · en 24 h". */
export function nextStepText(next: Next, total: number | null = null, now: Date = new Date()): string {
  const what = next.action === 'abandon' ? 'abandono' : followUpLabel(next.step ?? 0, total).toLowerCase()
  return `${what} · ${formatRelative(next.at, now)}`
}

export type PollState = {
  phase: string
  status: Status
  hidden: boolean
  busy: boolean
  hasConversation: boolean
}

/**
 * The chat polls only while it is open, visible and idle, and the agent may still write on
 * its own: re-engagement reminders (in progress) or the interview reminder (spec 010).
 */
export function shouldPoll(s: PollState): boolean {
  const live = s.status === 'in_progress' || s.status === 'interview_scheduled'
  return s.hasConversation && s.phase === 'chat' && live && !s.hidden && !s.busy
}
