import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useSearchParams } from 'react-router'
import { api } from '../api/client'
import { keys, useAnalytics, useAreaLabels } from '../api/queries'
import { Icon } from '../components/Icon'
import { Kpi } from '../components/Kpi'
import { EmptyState, ErrorState, Loading, Spinner } from '../components/States'
import { clearFilters, filtersFromParams, hasActiveFilters, withParam } from '../lib/filters'
import { formatPercent } from '../lib/format'
import { STATUS_META } from '../lib/status'
import { CandidateDrawer } from './CandidateDrawer'
import { CandidateTable } from './CandidateTable'
import { FilterBar, SortSelect } from './FilterBar'
import { PageHeader, SeedButton } from './common'

/** FR-8: KPIs, filter bar and the candidate table; FR-9 detail opens as a side drawer (?id=). */
export function CandidatesPage() {
  const [params, setParams] = useSearchParams()
  const filters = filtersFromParams(params)
  const areas = useAreaLabels()
  const analytics = useAnalytics()
  const list = useQuery({
    queryKey: keys.candidates(filters),
    queryFn: () => api.listCandidates(filters),
    placeholderData: keepPreviousData, // refetch keeps the table, no flash
  })
  const openId = params.get('id')

  const setFilter = (key: string, value: string | null) =>
    setParams(withParam(params, key, value), { replace: true })
  const toggleStatus = (status: string) =>
    setFilter('status', filters.status === status ? null : status)

  const a = analytics.data
  return (
    <div className="mx-auto max-w-[1400px] px-4 py-6 lg:px-8">
      <PageHeader
        title="Candidatos"
        subtitle="Ordenados por prioridad: a quién llamar primero y por qué."
        actions={
          <a
            href={api.exportUrl(filters)}
            download="candidatos.csv"
            className="btn-secondary"
            title="Exporta las filas con los filtros actuales"
          >
            <Icon name="download" /> Exportar CSV
          </a>
        }
      />

      <section className="mt-5 grid grid-cols-2 gap-3 xl:grid-cols-4" aria-label="Indicadores">
        <Kpi
          label="Candidaturas"
          value={a ? String(a.total) : '—'}
          hint={a ? `${a.by_status.in_progress ?? 0} en curso` : undefined}
          loading={analytics.isLoading}
        />
        <Kpi
          label="Entrevistas agendadas"
          dot={STATUS_META.interview_scheduled.color}
          value={a ? String(a.by_status.interview_scheduled ?? 0) : '—'}
          hint={a ? `${a.by_status.qualified_unscheduled ?? 0} aptos sin entrevista` : undefined}
          onClick={() => toggleStatus('interview_scheduled')}
          active={filters.status === 'interview_scheduled'}
          loading={analytics.isLoading}
        />
        <Kpi
          label="Requieren revisión"
          dot={STATUS_META.needs_review.color}
          value={a ? String(a.by_status.needs_review ?? 0) : '—'}
          hint="El agente no pudo decidir"
          onClick={() => toggleStatus('needs_review')}
          active={filters.status === 'needs_review'}
          loading={analytics.isLoading}
        />
        <Kpi
          label="Tasa de finalización"
          value={a ? formatPercent(a.completion_rate) : '—'}
          hint={a ? `${a.finished} de ${a.total} llegaron a un resultado` : undefined}
          loading={analytics.isLoading}
        />
      </section>

      <div className="mt-5">
        <FilterBar
          filters={filters}
          areas={areas}
          onChange={setFilter}
          onClear={() => setParams(clearFilters(params), { replace: true })}
        />
      </div>

      <section className="card mt-3 overflow-hidden">
        <div className="flex items-center justify-between border-b border-stone-100 px-4 py-2 text-xs text-stone-500">
          <span aria-live="polite">
            {list.data ? `${list.data.length} candidatos` : 'Cargando…'}
          </span>
          <div className="flex items-center gap-3">
            {list.isFetching && !list.isLoading && <Spinner className="size-3 text-stone-400" />}
            <SortSelect value={filters.sort} onChange={(v) => setFilter('sort', v)} />
          </div>
        </div>
        {list.isLoading ? (
          <Loading />
        ) : list.isError && !list.data ? (
          <ErrorState error={list.error} onRetry={() => list.refetch()} />
        ) : list.data && list.data.length === 0 ? (
          hasActiveFilters(filters) ? (
            <EmptyState
              icon="search"
              title="Ningún candidato coincide con los filtros"
              action={
                <button
                  type="button"
                  className="btn-secondary"
                  onClick={() => setParams(clearFilters(params), { replace: true })}
                >
                  Limpiar filtros
                </button>
              }
            />
          ) : (
            <EmptyState title="Todavía no hay candidaturas" action={<SeedButton />}>
              Cuando los candidatos escriban a Sofi aparecerán aquí. Para la demo puedes generar
              conversaciones simuladas.
            </EmptyState>
          )
        ) : (
          <div className={list.isPlaceholderData ? 'opacity-60 transition-opacity' : ''}>
            <CandidateTable
              rows={list.data ?? []}
              areas={areas}
              selectedId={openId}
              onOpen={(id) => setParams(withParam(params, 'id', id))}
            />
          </div>
        )}
      </section>

      {openId && (
        <CandidateDrawer id={openId} onClose={() => setParams(withParam(params, 'id', null))} />
      )}
    </div>
  )
}
