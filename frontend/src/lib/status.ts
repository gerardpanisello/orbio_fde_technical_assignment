import type { Bucket, Status } from '../api/client'

/**
 * One source of truth for status colours: badges, table and charts all read from here,
 * so "Entrevista agendada" is the same green everywhere.
 *
 * The five chromatic steps were checked with the dataviz palette validator in this
 * (stacking) order: lightness band, chroma, colour-blind and normal-vision separation of
 * neighbours all pass. Greys are the "no outcome" statuses on purpose. Colour is never
 * the only cue: every badge and chart also shows the label.
 */
export const STATUS_ORDER: Status[] = [
  'interview_scheduled',
  'qualified_unscheduled',
  'needs_review',
  'in_progress',
  'abandoned',
  'disqualified',
  'opted_out',
]

export const STATUS_META: Record<Status, { label: string; color: string; hint: string }> = {
  interview_scheduled: {
    label: 'Entrevista agendada',
    color: '#0ca30c',
    hint: 'Apto y con hora de entrevista',
  },
  qualified_unscheduled: {
    label: 'Apto, sin entrevista',
    color: '#2a78d6',
    hint: 'Apto, pero ninguna hora le venía bien: llamar para agendar',
  },
  needs_review: {
    label: 'Requiere revisión',
    color: '#eda100',
    hint: 'El agente no pudo decidir: revisar antes de contactar',
  },
  in_progress: { label: 'En curso', color: '#6250d6', hint: 'Conversación abierta' },
  abandoned: { label: 'Abandonado', color: '#a8a29e', hint: 'Dejó de responder' },
  disqualified: {
    label: 'Descartado',
    color: '#d03b3b',
    hint: 'No cumple un requisito eliminatorio',
  },
  opted_out: { label: 'Se dio de baja', color: '#57534e', hint: 'Pidió no seguir; datos borrados' },
}

/** Statuses after which the conversation is over (FR-5 banner). */
export const FINAL_STATUSES: Status[] = STATUS_ORDER.filter((s) => s !== 'in_progress')

/** Priority = one terracotta hue, darker is higher (an ordinal scale, not a status). */
export const BUCKET_META: Record<Bucket, { label: string; className: string; rank: number }> = {
  high: { label: 'Alta', className: 'bg-brand-600 text-white', rank: 0 },
  medium: { label: 'Media', className: 'bg-brand-100 text-brand-800', rank: 1 },
  low: { label: 'Baja', className: 'bg-stone-100 text-stone-600', rank: 2 },
}
