import { toQueryString } from './client'

describe('toQueryString', () => {
  it('drops empty filters and keeps the rest', () => {
    expect(
      toQueryString({ status: 'interview_scheduled', city: '', q: '  ana ', sort: '-score' }),
    ).toBe('?status=interview_scheduled&q=ana&sort=-score')
  })

  it('returns an empty string without filters', () => {
    expect(toQueryString({})).toBe('')
  })
})
