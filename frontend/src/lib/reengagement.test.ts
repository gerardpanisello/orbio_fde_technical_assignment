import { followUpLabel, followUpTotal, formatRelative, nextStepText, shouldPoll } from './reengagement'

describe('followUpLabel', () => {
  it('shows n/N when the total is known, n alone otherwise', () => {
    expect(followUpLabel(1, 3)).toBe('Recordatorio 1/3')
    expect(followUpLabel(2)).toBe('Recordatorio 2')
    expect(followUpLabel(4, 3)).toBe('Recordatorio 4') // a stale total never reads "4/3"
    expect(followUpLabel(1, 3, 'en')).toBe('Reminder 1/3')
  })
})

describe('followUpTotal', () => {
  const reengagement = { follow_ups_sent: 1, waiting_steps: 1, last_follow_up_at: null, reactivated_after_step: null, total_steps: 0 }
  it('uses total_steps from the API when present', () => {
    expect(followUpTotal({ traces: [], reengagement: { ...reengagement, total_steps: 3, next: null } })).toBe(3)
  })
  it('reads the last_call step from the traces', () => {
    const traces = [{ trace: { follow_up: { step: 3, kind: 'last_call' } } }] as never
    expect(followUpTotal({ traces, reengagement: { ...reengagement, next: null } })).toBe(3)
  })
  it('infers it when only the abandon is left, and is unknown before', () => {
    const abandon = { action: 'abandon' as const, step: null, at: '2026-10-13T10:00:00Z', requires_template: false }
    expect(followUpTotal({ traces: [], reengagement: { ...reengagement, waiting_steps: 3, next: abandon } })).toBe(3)
    expect(followUpTotal({ traces: [], reengagement: { ...reengagement, next: null } })).toBeNull()
  })
})

describe('formatRelative / nextStepText', () => {
  const now = new Date('2026-10-13T10:00:00Z')
  it.each([
    ['2026-10-13T09:00:00Z', 'ahora'],
    ['2026-10-13T10:00:30Z', 'ahora'],
    ['2026-10-13T10:05:00Z', 'en 5 min'],
    ['2026-10-14T07:00:00Z', 'en 21 h'],
    ['2026-10-16T10:00:00Z', 'en 3 d'],
  ])('%s -> %s', (at, text) => {
    expect(formatRelative(at, now)).toBe(text)
  })

  it('names the next step', () => {
    expect(
      nextStepText({ action: 'follow_up', step: 2, at: '2026-10-14T07:00:00Z', requires_template: true }, 3, now),
    ).toBe('recordatorio 2/3 · en 21 h')
    expect(nextStepText({ action: 'abandon', step: null, at: '2026-10-14T10:00:00Z', requires_template: false }, 3, now)).toBe(
      'abandono · en 24 h',
    )
  })
})

describe('shouldPoll', () => {
  const open = { phase: 'chat', status: 'in_progress' as const, hidden: false, busy: false, hasConversation: true }
  it('polls an open, visible, idle conversation, and a booked one (interview reminder)', () => {
    expect(shouldPoll(open)).toBe(true)
    expect(shouldPoll({ ...open, status: 'interview_scheduled' })).toBe(true)
  })
  it.each([
    ['tab hidden', { hidden: true }],
    ['conversation closed', { status: 'abandoned' as const }],
    ['sending a message', { busy: true }],
    ['start screen', { phase: 'start' }],
    ['no conversation', { hasConversation: false }],
  ])('stops when %s', (_, change) => {
    expect(shouldPoll({ ...open, ...change })).toBe(false)
  })
})
