import { toQueryString } from '../api/client'
import { clearFilters, filtersFromParams, hasActiveFilters, withParam } from './filters'

describe('filters <-> URL <-> API query', () => {
  it('reads filters from the URL and defaults to priority order', () => {
    const filters = filtersFromParams(new URLSearchParams('status=needs_review&city=madrid&id=abc'))
    expect(filters).toEqual({ status: 'needs_review', city: 'madrid', sort: '-score' })
    expect(toQueryString(filters)).toBe('?status=needs_review&city=madrid&sort=-score')
  })

  it('ignores blank values and unknown params', () => {
    expect(filtersFromParams(new URLSearchParams('q=%20%20&foo=bar'))).toEqual({ sort: '-score' })
  })

  it('sets and removes one param while keeping the open candidate', () => {
    const params = new URLSearchParams('id=abc&bucket=high')
    expect(withParam(params, 'bucket', '').toString()).toBe('id=abc')
    expect(withParam(params, 'country', 'MX').toString()).toBe('id=abc&bucket=high&country=MX')
  })

  it('clears filters but not the sort or the drawer', () => {
    const params = new URLSearchParams('id=abc&status=abandoned&q=ana&sort=-updated')
    expect(clearFilters(params).toString()).toBe('id=abc&sort=-updated')
    expect(hasActiveFilters(filtersFromParams(params))).toBe(true)
    expect(hasActiveFilters(filtersFromParams(clearFilters(params)))).toBe(false)
  })
})

describe('channel filter (spec 016)', () => {
  it('round-trips the channel through the URL and the API query', () => {
    const filters = filtersFromParams(new URLSearchParams('channel=whatsapp'))
    expect(filters).toEqual({ channel: 'whatsapp', sort: '-score' })
    expect(toQueryString(filters)).toBe('?channel=whatsapp&sort=-score')
    expect(hasActiveFilters(filters)).toBe(true)
    expect(clearFilters(new URLSearchParams('channel=web')).toString()).toBe('')
  })
})
