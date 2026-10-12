import type { AreaLabels, CandidateRow } from '../api/client'
import { ChannelBadge, PriorityPill, RecruiterTag, StatusBadge } from '../components/Badges'
import { formatDate, formatSlot, timeAgo } from '../lib/format'
import { AVAILABILITY, DISQUALIFICATION, VEHICLE, list, placeLabel } from '../lib/labels'

const COLUMNS = [
  'Candidato',
  'Ciudad / zona',
  'Estado',
  'Prioridad',
  'Disponibilidad',
  'Experiencia',
  'Inicio',
  'Entrevista',
  'Idioma',
  'Actualizado',
]

/** Dense, scannable table (FR-8). A row opens the detail drawer (click or Enter). */
export function CandidateTable({
  rows,
  areas,
  selectedId,
  onOpen,
}: {
  rows: CandidateRow[]
  areas: AreaLabels | undefined
  selectedId: string | null
  onOpen: (id: string) => void
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[1080px] text-left text-[13px]">
        <thead className="bg-stone-50 text-[11px] font-semibold tracking-wide text-stone-500 uppercase">
          <tr>
            {COLUMNS.map((c) => (
              <th key={c} scope="col" className="px-3 py-2 font-semibold first:pl-4">
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-stone-100">
          {rows.map((row) => (
            <tr
              key={row.id}
              tabIndex={0}
              onClick={() => onOpen(row.id)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault()
                  onOpen(row.id)
                }
              }}
              aria-selected={row.id === selectedId}
              className={`cursor-pointer align-middle transition-colors hover:bg-brand-50/50 focus-visible:bg-brand-50 focus-visible:outline-none ${
                row.id === selectedId ? 'bg-brand-50' : ''
              }`}
            >
              <td className="py-2 pr-3 pl-4">
                <div className="flex items-center gap-1.5 whitespace-nowrap">
                  {row.full_name ? (
                    <span className="font-medium text-stone-900">{row.full_name}</span>
                  ) : (
                    <span className="text-stone-400 italic">Sin nombre</span>
                  )}
                  <RecruiterTag status={row.recruiter_status} override={row.recruiter_override} />
                  {row.channel === 'whatsapp' && <ChannelBadge channel={row.channel} />}
                </div>
                {row.vehicle_type && (
                  <div className="text-xs text-stone-500">{VEHICLE[row.vehicle_type]}</div>
                )}
              </td>
              <td className="px-3 py-2 whitespace-nowrap">
                {row.city ? (
                  <>
                    <div className="text-stone-800">
                      {placeLabel(row.city, null, areas)}
                      {row.country && <span className="ml-1 text-[11px] text-stone-400">{row.country}</span>}
                    </div>
                    {row.zone && <div className="text-xs text-stone-500">{placeLabel(null, row.zone, areas)}</div>}
                  </>
                ) : (
                  <span className="text-stone-400">—</span>
                )}
              </td>
              <td className="px-3 py-2">
                <StatusBadge status={row.status} />
                {row.disqualification_reason && (
                  <div className="mt-0.5 text-xs text-stone-500">
                    {DISQUALIFICATION[row.disqualification_reason]}
                  </div>
                )}
              </td>
              <td className="px-3 py-2">
                <PriorityPill bucket={row.bucket} score={row.score} />
                {row.score_at_close != null && row.score != null && row.score_at_close !== row.score && (
                  <div
                    className="mt-0.5 text-[11px] whitespace-nowrap text-stone-400 tabular-nums"
                    title="La prioridad usa la ocupación actual de su zona; esta es la puntuación al cerrar"
                  >
                    Al cerrar: {row.score_at_close}
                  </div>
                )}
              </td>
              <td className="max-w-40 px-3 py-2 text-stone-700">{list(row.availability, AVAILABILITY)}</td>
              <td className="px-3 py-2 whitespace-nowrap text-stone-700 tabular-nums">
                {row.experience_years == null
                  ? '—'
                  : row.experience_years === 1
                    ? '1 año'
                    : `${row.experience_years} años`}
              </td>
              <td className="px-3 py-2 whitespace-nowrap text-stone-700 tabular-nums">
                {formatDate(row.start_date)}
              </td>
              <td className="px-3 py-2 whitespace-nowrap text-stone-700">
                {row.interview_slot ? formatSlot(row.interview_slot) : '—'}
              </td>
              <td className="px-3 py-2 text-xs font-medium text-stone-500 uppercase">{row.language}</td>
              <td
                className="px-3 py-2 whitespace-nowrap text-stone-500"
                title={new Date(row.updated_at).toLocaleString('es-ES')}
              >
                {timeAgo(row.updated_at)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
