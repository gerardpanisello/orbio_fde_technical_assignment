import type { AreaLabels, CandidateRecord } from '../api/client'
import { FIELD_STATUS } from '../lib/labels'
import { fieldRows } from '../lib/record'

const STATUS_DOT = {
  valid: 'bg-emerald-500',
  unclear: 'bg-amber-500',
  not_asked: 'bg-stone-300',
  not_required: 'bg-stone-200',
} as const

/** The record's fields with their validation status (valid / unclear / pending). */
export function RecordFields({
  record,
  areas,
  dense,
}: {
  record: CandidateRecord
  areas: AreaLabels | undefined
  dense?: boolean
}) {
  return (
    <dl className={`grid grid-cols-[auto_1fr] gap-x-4 ${dense ? 'gap-y-1.5 text-[13px]' : 'gap-y-2 text-sm'}`}>
      {fieldRows(record, areas).map((row) => (
        <div key={row.key} className="contents">
          <dt className="flex items-center gap-1.5 text-stone-500">
            <span
              className={`size-1.5 shrink-0 rounded-full ${STATUS_DOT[row.status]}`}
              title={FIELD_STATUS[row.status]}
            />
            {row.label}
          </dt>
          <dd className={row.status === 'valid' ? 'text-stone-900' : 'text-stone-400'}>
            {row.status === 'valid' || row.value !== '—' ? row.value : FIELD_STATUS[row.status]}
            {row.status === 'unclear' && (
              <span className="ml-1.5 rounded bg-amber-50 px-1 text-[11px] text-amber-700">no claro</span>
            )}
          </dd>
        </div>
      ))}
    </dl>
  )
}
