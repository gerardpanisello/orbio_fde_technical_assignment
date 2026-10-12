import type { ReactNode } from 'react'
import type { CandidateRecord } from '../api/client'
import { DISQUALIFICATION, FLAG, REVIEW } from '../lib/labels'
import { Icon } from './Icon'

/** Why the agent stopped or escalated: disqualification, review reasons and flags. */
export function Reasons({ record }: { record: CandidateRecord }) {
  const { disqualification_reason: dq, needs_review_reasons: review, flags } = record
  if (!dq && !review.length && !flags.length) return null
  return (
    <div className="space-y-2">
      {dq && (
        <Callout tone="red" title="Motivo de descarte">
          {DISQUALIFICATION[dq]}
          <span className="text-red-700/70"> · requisito eliminatorio, decidido por reglas</span>
        </Callout>
      )}
      {review.length > 0 && (
        <Callout tone="amber" title="Motivos de revisión">
          {review.map((r) => REVIEW[r]).join(', ')}
        </Callout>
      )}
      {flags.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {flags.map((flag) => (
            <span
              key={flag}
              className="inline-flex items-center gap-1 rounded-md border border-stone-200 bg-stone-50 px-1.5 py-0.5 text-xs text-stone-700"
            >
              <Icon name="alert" className="size-3 text-stone-500" />
              {FLAG[flag]}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}

function Callout({ tone, title, children }: { tone: 'red' | 'amber'; title: string; children: ReactNode }) {
  const styles = tone === 'red' ? 'border-red-200 bg-red-50 text-red-900' : 'border-amber-200 bg-amber-50 text-amber-900'
  return (
    <div className={`rounded-lg border px-3 py-2 text-sm ${styles}`}>
      <span className="font-semibold">{title}: </span>
      {children}
    </div>
  )
}
