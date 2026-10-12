import type { CandidateRecord } from '../api/client'
import { FACTOR } from '../lib/labels'
import { factorValue } from '../lib/record'
import { PriorityPill } from './Badges'

/**
 * Explainability: the score is a plain sum of config-weighted factors (spec 002 FR-30),
 * so we show every factor, the value it came from and the points it earned.
 */
export function ScoreBreakdown({ score }: { score: CandidateRecord['score'] }) {
  if (!score) {
    return (
      <p className="text-sm text-stone-500">
        Sin puntuación: solo se puntúa a candidatos aptos o pendientes de revisión.
      </p>
    )
  }
  const factors = [...score.factors].sort((a, b) => b.points - a.points)
  return (
    <div>
      <div className="flex items-baseline gap-2">
        <span className="text-2xl font-semibold text-stone-900">{score.score}</span>
        <span className="text-sm text-stone-500">/ {score.max_score}</span>
        <span className="ml-auto">
          <PriorityPill bucket={score.bucket} score={null} />
        </span>
      </div>
      <div
        className="mt-2 h-1.5 overflow-hidden rounded-full bg-brand-100"
        role="meter"
        aria-valuemin={0}
        aria-valuemax={score.max_score}
        aria-valuenow={score.score}
        aria-label="Puntuación"
      >
        <div
          className="h-full rounded-full bg-brand-600"
          style={{ width: `${(score.score / score.max_score) * 100}%` }}
        />
      </div>
      <ul className="mt-3 divide-y divide-stone-100">
        {factors.map((factor) => (
          <li key={factor.reason_code + factor.field} className="flex items-center gap-3 py-1.5 text-sm">
            <span className="w-40 shrink-0 text-stone-700">{FACTOR[factor.reason_code]}</span>
            <span className="min-w-0 flex-1 truncate text-stone-500" title={factorValue(factor)}>
              {factorValue(factor)}
            </span>
            <span
              className={`w-10 text-right font-medium tabular-nums ${factor.points ? 'text-stone-900' : 'text-stone-400'}`}
            >
              +{factor.points}
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}
