import type { Bucket, RecruiterStatus, Status } from '../api/client'
import { RECRUITER_STATUS } from '../lib/labels'
import { BUCKET_META, STATUS_META } from '../lib/status'

/** Status = coloured dot + label on a soft tint; text stays ink so it is always readable. */
export function StatusBadge({ status, size = 'sm' }: { status: Status; size?: 'sm' | 'md' }) {
  const meta = STATUS_META[status]
  return (
    <span
      title={meta.hint}
      className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-full font-medium text-stone-800 ${
        size === 'md' ? 'px-2.5 py-1 text-sm' : 'px-2 py-0.5 text-xs'
      }`}
      style={{ backgroundColor: `${meta.color}1f` }}
    >
      <span className="size-1.5 rounded-full" style={{ backgroundColor: meta.color }} />
      {meta.label}
    </span>
  )
}

/** Priority pill: bucket + score, e.g. "Alta · 70". */
export function PriorityPill({ bucket, score }: { bucket: Bucket | null; score: number | null }) {
  if (!bucket) return <span className="text-xs text-stone-400">—</span>
  const meta = BUCKET_META[bucket]
  return (
    <span
      className={`inline-flex items-center gap-1 whitespace-nowrap rounded-md px-1.5 py-0.5 text-xs font-semibold tabular-nums ${meta.className}`}
    >
      {meta.label}
      {score !== null && <span className="font-normal opacity-80">· {score}</span>}
    </span>
  )
}

const RECRUITER_STYLE: Record<RecruiterStatus, string> = {
  new: '',
  shortlisted: 'border-brand-200 bg-brand-50 text-brand-800',
  rejected: 'border-stone-200 bg-stone-100 text-stone-600',
  hired: 'border-emerald-200 bg-emerald-50 text-emerald-800',
}

export function RecruiterTag({ status, override }: { status: RecruiterStatus; override?: boolean }) {
  if (status === 'new') return null
  return (
    <span
      className={`inline-flex items-center rounded border px-1.5 py-px text-[11px] font-medium ${RECRUITER_STYLE[status]}`}
    >
      {RECRUITER_STATUS[status]}
      {override && ' (manual)'}
    </span>
  )
}
