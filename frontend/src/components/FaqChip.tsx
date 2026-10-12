import type { FaqTurn } from '../lib/faq'

/** Subtle marker on a turn that went through the FAQ (spec 009); the tooltip shows the retrieval. */
export function FaqChip({ turn }: { turn: FaqTurn }) {
  return (
    <span
      title={turn.detail}
      className={`inline-flex items-center rounded border px-1 py-px font-mono text-[10.5px] leading-tight normal-case ${
        turn.outcome === 'answered'
          ? 'border-sky-200 bg-sky-50 text-sky-800'
          : 'border-amber-200 bg-amber-50 text-amber-900'
      }`}
    >
      {turn.label}
    </span>
  )
}
