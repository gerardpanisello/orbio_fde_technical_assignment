import { faqTurn, rankQuestions } from './faq'

const answeredTrace = {
  faq: 'answered' as const,
  trace: {
    faq: {
      question: '¿cuánto se paga?',
      hits: [
        { entry_id: 'pay-es', score: 5.548 },
        { entry_id: 'pay-general', score: 4.46 },
      ],
      outcome: 'answered',
      entry_ids: ['pay-es'],
    },
  },
}

describe('faqTurn', () => {
  it('labels an answered turn with the entry used and explains the match', () => {
    const turn = faqTurn(answeredTrace)
    expect(turn?.label).toBe('FAQ: pay-es')
    expect(turn?.detail).toContain('pay-es (5.55), pay-general (4.46)')
    expect(turn?.detail).toContain('«¿cuánto se paga?»')
  })

  it('labels an unanswered turn', () => {
    const turn = faqTurn({ faq: 'unanswered', trace: { faq: { question: '¿hay comedor?', hits: [], entry_ids: [] } } })
    expect(turn).toMatchObject({ outcome: 'unanswered', label: 'FAQ sin respuesta' })
  })

  it('ignores turns without a FAQ and tolerates a malformed trace', () => {
    expect(faqTurn({ faq: null, trace: {} })).toBeNull()
    expect(faqTurn({ faq: 'answered', trace: { faq: 'oops' } })?.label).toBe('FAQ')
  })
})

describe('rankQuestions', () => {
  it('sorts by count and marks unanswered questions (entry_id null)', () => {
    const ranked = rankQuestions({
      asked: 6,
      answered: 4,
      unanswered_rate: 1 / 3,
      top_questions: [
        { entry_id: 'pay-es', question: '¿Cuánto se paga?', count: 3 },
        { entry_id: null, question: '¿hay comedor?', count: 2 },
        { entry_id: 'own-vehicle', question: '¿Necesito vehículo propio?', count: 1 },
      ],
    })
    expect(ranked.map((q) => [q.question, q.answered])).toEqual([
      ['¿Cuánto se paga?', true],
      ['¿hay comedor?', false],
      ['¿Necesito vehículo propio?', true],
    ])
  })
})
