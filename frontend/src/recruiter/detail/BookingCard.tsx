import type { Booking, CandidateDetail } from '../../api/client'
import { Icon } from '../../components/Icon'
import { formatDateTime, formatSlot } from '../../lib/format'
import { BOOKING_STATUS } from '../../lib/interviews'

const STATUS_STYLE: Record<Booking['status'], string> = {
  booked: 'bg-emerald-50 text-emerald-800',
  attended: 'bg-emerald-100 text-emerald-900',
  no_show: 'bg-red-50 text-red-800',
  cancelled: 'bg-stone-100 text-stone-600',
  rescheduled: 'bg-stone-100 text-stone-600',
}

/** Spec 010 FR-8: the interview (slot, place, status, .ics) and its reschedule/cancel history. */
export function BookingCard({ detail }: { detail: CandidateDetail }) {
  const live = detail.booking
  const history = detail.bookings.filter((b) => b.id !== live?.id)
  if (!live && history.length === 0) return null
  return (
    <section className="card p-4">
      <h3 className="eyebrow mb-3">Entrevista</h3>
      {live ? (
        <div className="flex flex-wrap items-start gap-3">
          <div className="min-w-0 flex-1 text-sm">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-semibold text-stone-900">{formatSlot(live.local_start)}</span>
              <span className="text-xs text-stone-500">
                {live.duration_min} min · {live.timezone}
              </span>
              <StatusPill status={live.status} />
            </div>
            <p className="mt-1 text-stone-600">{live.place}</p>
            {live.reminder_sent_at && (
              <p className="mt-1 text-xs text-stone-500">Recordatorio enviado {formatDateTime(live.reminder_sent_at)}</p>
            )}
          </div>
          <a href={live.ics_url} download className="btn-secondary" title="Invitación de calendario (.ics)">
            <Icon name="download" /> .ics
          </a>
        </div>
      ) : (
        <p className="text-sm text-stone-500">Sin entrevista vigente.</p>
      )}
      {history.length > 0 && (
        <div className="mt-3 border-t border-stone-100 pt-2">
          <h4 className="mb-1 text-[11px] font-medium text-stone-500">Historial</h4>
          <ul className="space-y-1 text-xs">
            {[...history]
              .sort((a, b) => b.created_at.localeCompare(a.created_at))
              .map((b) => (
                <li key={b.id} className="flex flex-wrap items-center gap-2 text-stone-600">
                  <StatusPill status={b.status} />
                  <span className={b.status === 'cancelled' || b.status === 'rescheduled' ? 'line-through' : ''}>
                    {formatSlot(b.local_start)}
                  </span>
                  <span className="text-stone-400">· actualizado {formatDateTime(b.updated_at)}</span>
                </li>
              ))}
          </ul>
        </div>
      )}
    </section>
  )
}

function StatusPill({ status }: { status: Booking['status'] }) {
  return (
    <span className={`rounded px-1.5 py-px text-[11px] font-medium ${STATUS_STYLE[status]}`}>{BOOKING_STATUS[status]}</span>
  )
}
