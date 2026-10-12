/** FAQ answers (spec 009): what the dashboard shows about each grounded or unanswered question. */
import type { Analytics, Trace } from '../api/client'

export type FaqTurn = {
  outcome: 'answered' | 'unanswered'
  /** "FAQ: pay-es" or "FAQ sin respuesta" (subtle chip on the turn). */
  label: string
  /** Tooltip: the question and the retrieval scores, so the match is explainable. */
  detail: string
}

type Hit = { entry_id: string; score: number }

function record(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : null
}

/** Reads `trace.faq` defensively: the trace is free-form JSON from the backend. */
export function faqTurn(trace: Pick<Trace, 'faq' | 'trace'>): FaqTurn | null {
  if (!trace.faq) return null
  const faq = record(record(trace.trace)?.faq)
  const question = typeof faq?.question === 'string' ? faq.question : null
  const used = Array.isArray(faq?.entry_ids) ? faq.entry_ids.filter((x): x is string => typeof x === 'string') : []
  const hits = (Array.isArray(faq?.hits) ? faq.hits : [])
    .map(record)
    .filter((h): h is Hit => !!h && typeof h.entry_id === 'string' && typeof h.score === 'number')
  const lines = [
    question ? `Pregunta: «${question}»` : null,
    hits.length ? `Recuperadas: ${hits.map((h) => `${h.entry_id} (${h.score.toFixed(2)})`).join(', ')}` : null,
  ].filter(Boolean)

  if (trace.faq === 'answered') {
    return {
      outcome: 'answered',
      label: used.length ? `FAQ: ${used.join(', ')}` : 'FAQ',
      detail: ['Respondida con la FAQ aprobada', ...lines].join('\n'),
    }
  }
  return {
    outcome: 'unanswered',
    label: 'FAQ sin respuesta',
    detail: ['Sin respuesta en la FAQ: se pasó al equipo', ...lines].join('\n'),
  }
}

export type RankedQuestion = { key: string; question: string; count: number; answered: boolean; entryId: string | null }

/** Top questions, most asked first; unanswered ones keep their own row (they tell the client what to add). */
export function rankQuestions(faq: Analytics['faq']): RankedQuestion[] {
  return faq.top_questions
    .map((q, i) => ({
      key: q.entry_id ?? `unanswered-${i}`,
      question: q.question,
      count: q.count,
      answered: q.entry_id !== null,
      entryId: q.entry_id,
    }))
    .sort((a, b) => b.count - a.count || Number(a.answered) - Number(b.answered))
}
