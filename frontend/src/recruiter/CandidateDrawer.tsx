import { useEffect, useRef, useState } from 'react'
import type { CandidateDetail } from '../api/client'
import { useAreaLabels, useCandidate } from '../api/queries'
import { ChannelBadge, PriorityPill, RecruiterTag, StatusBadge } from '../components/Badges'
import { Icon } from '../components/Icon'
import { Reasons } from '../components/Reasons'
import { RecordFields } from '../components/RecordFields'
import { ReengagementSummary } from '../components/ReengagementSummary'
import { ScoreBreakdown } from '../components/ScoreBreakdown'
import { ErrorState, Loading } from '../components/States'
import { formatDateTime, formatSlot } from '../lib/format'
import { LANGUAGE, STAGE, placeLabel } from '../lib/labels'
import { followUpTotal } from '../lib/reengagement'
import { ActionsPanel } from './detail/ActionsPanel'
import { BookingCard } from './detail/BookingCard'
import { SummaryCard } from './detail/SummaryCard'
import { TechnicalTab } from './detail/TechnicalTab'
import { Transcript } from './detail/Transcript'

type Tab = 'overview' | 'transcript' | 'technical'

/**
 * FR-9: everything a recruiter needs to trust (or overrule) the agent: summary, score
 * factors, reasons, extracted data, transcript, raw JSON and per-turn traces.
 */
export function CandidateDrawer({ id, onClose }: { id: string; onClose: () => void }) {
  const detail = useCandidate(id)
  const closeButton = useRef<HTMLButtonElement>(null)
  const [tab, setTab] = useState<Tab>('overview')

  useEffect(() => {
    closeButton.current?.focus()
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div className="fixed inset-0 z-40 flex justify-end" role="dialog" aria-modal="true" aria-label="Detalle del candidato">
      <button
        type="button"
        aria-label="Cerrar"
        tabIndex={-1}
        className="absolute inset-0 bg-stone-900/20 backdrop-blur-[1px]"
        onClick={onClose}
      />
      <div className="relative flex h-full w-full max-w-[720px] animate-slide-in flex-col bg-white shadow-2xl">
        <button
          ref={closeButton}
          type="button"
          onClick={onClose}
          className="absolute top-3 right-3 z-10 rounded-lg p-1.5 text-stone-500 hover:bg-stone-100 hover:text-stone-900"
          aria-label="Cerrar detalle"
        >
          <Icon name="x" className="size-5" />
        </button>
        {detail.isLoading ? (
          <Loading />
        ) : detail.isError || !detail.data ? (
          <ErrorState error={detail.error} onRetry={() => detail.refetch()} />
        ) : (
          <DrawerBody detail={detail.data} tab={tab} setTab={setTab} />
        )}
      </div>
    </div>
  )
}

function DrawerBody({
  detail,
  tab,
  setTab,
}: {
  detail: CandidateDetail
  tab: Tab
  setTab: (tab: Tab) => void
}) {
  const areas = useAreaLabels()
  const { candidate, record } = detail
  const tabs: { id: Tab; label: string }[] = [
    { id: 'overview', label: 'Resumen' },
    { id: 'transcript', label: `Conversación (${detail.transcript.length})` },
    { id: 'technical', label: 'Datos técnicos' },
  ]

  return (
    <>
      <header className="border-b border-stone-200 px-6 pt-5">
        <div className="pr-10">
          <h2 className="text-lg font-semibold text-stone-900">
            {candidate.full_name ?? <span className="text-stone-400 italic">Candidato sin nombre</span>}
          </h2>
          <p className="mt-0.5 text-sm text-stone-500">
            {[
              candidate.city ? placeLabel(candidate.city, candidate.zone, areas) : null,
              LANGUAGE[candidate.language],
              `Inicio ${formatDateTime(candidate.created_at)}`,
            ]
              .filter(Boolean)
              .join(' · ')}
          </p>
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <StatusBadge status={candidate.status} size="md" />
          <ChannelBadge channel={candidate.channel} />
          {candidate.bucket && <PriorityPill bucket={candidate.bucket} score={candidate.score} />}
          <RecruiterTag status={candidate.recruiter_status} override={candidate.recruiter_override} />
          {candidate.interview_slot && (
            <span className="inline-flex items-center gap-1 text-sm text-stone-700">
              <Icon name="calendar" className="size-4 text-stone-400" />
              {formatSlot(candidate.interview_slot)}
            </span>
          )}
          {record.drop_off_stage && candidate.status === 'abandoned' && (
            <span className="text-sm text-stone-500">Abandonó en: {STAGE[record.drop_off_stage]}</span>
          )}
        </div>
        <nav className="mt-4 -mb-px flex gap-4" role="tablist">
          {tabs.map((t) => (
            <button
              key={t.id}
              type="button"
              role="tab"
              aria-selected={tab === t.id}
              onClick={() => setTab(t.id)}
              className={`border-b-2 pb-2 text-sm font-medium transition-colors ${
                tab === t.id
                  ? 'border-brand-600 text-stone-900'
                  : 'border-transparent text-stone-500 hover:text-stone-800'
              }`}
            >
              {t.label}
            </button>
          ))}
        </nav>
      </header>

      <div className="scrollbar-thin flex-1 overflow-y-auto bg-stone-50/60 px-6 py-5">
        {tab === 'overview' && (
          <div className="space-y-4">
            <Reasons record={record} />
            <ActionsPanel detail={detail} />
            <BookingCard detail={detail} />
            <SummaryCard detail={detail} />
            {(detail.reengagement.follow_ups_sent > 0 || detail.reengagement.next) && (
              <section className="card p-4">
                <h3 className="eyebrow mb-3">Re-engagement</h3>
                <ReengagementSummary detail={detail} total={followUpTotal(detail)} />
              </section>
            )}
            <div className="grid gap-4 md:grid-cols-2">
              <section className="card p-4">
                <h3 className="eyebrow mb-3">Puntuación y factores</h3>
                <ScoreBreakdown
                  score={detail.live_score ?? record.score}
                  atClose={detail.live_score ? record.score : null}
                />
              </section>
              <section className="card p-4">
                <h3 className="eyebrow mb-3">Datos extraídos</h3>
                <RecordFields record={record} areas={areas} />
              </section>
            </div>
          </div>
        )}
        {tab === 'transcript' && <Transcript messages={detail.transcript} traces={detail.traces} followUpTotal={followUpTotal(detail)} />}
        {tab === 'technical' && <TechnicalTab detail={detail} />}
      </div>
    </>
  )
}
