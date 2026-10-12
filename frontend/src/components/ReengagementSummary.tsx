import type { CandidateDetail } from '../api/client'
import { formatDateTime } from '../lib/format'
import { nextStepText } from '../lib/reengagement'

/** Spec 008 FR-9: reminders sent, whether the candidate came back, and what happens next. */
export function ReengagementSummary({ detail, total }: { detail: CandidateDetail; total: number | null }) {
  const r = detail.reengagement
  return (
    <dl className="grid grid-cols-2 gap-2 text-xs">
      <Item
        label="Recordatorios enviados"
        value={String(r.follow_ups_sent)}
        title={r.last_follow_up_at ? `Último: ${formatDateTime(r.last_follow_up_at)}` : undefined}
      />
      <Item
        label="Volvió"
        value={r.reactivated_after_step != null ? `tras el recordatorio ${r.reactivated_after_step}` : 'no'}
      />
      <div className="col-span-2">
        <Item
          label="Próximo paso"
          value={r.next ? nextStepText(r.next, total) : 'ninguno'}
          title={r.next ? `${formatDateTime(r.next.at)}${r.next.requires_template ? ' · plantilla WhatsApp' : ''}` : undefined}
        />
      </div>
    </dl>
  )
}

function Item({ label, value, title }: { label: string; value: string; title?: string }) {
  return (
    <div className="rounded-lg bg-stone-50 px-2.5 py-1.5" title={title}>
      <dt className="text-[11px] text-stone-500">{label}</dt>
      <dd className="truncate text-stone-800">{value}</dd>
    </div>
  )
}
