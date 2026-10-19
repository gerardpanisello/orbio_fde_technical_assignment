import type { Zone } from '../api/client'
import { factorSentence, factorValue } from './record'
import {
  OCCUPANCY_BANDS,
  applyZonePatch,
  groupByCity,
  occupancyBand,
  zoneDemandText,
  zoneTotals,
} from './zones'

function zone(overrides: Partial<Zone>): Zone {
  return {
    id: 'mad-centro',
    name: 'Centro',
    city: 'madrid',
    city_name: 'Madrid',
    country: 'ES',
    target_drivers: 40,
    current_drivers: 20,
    occupancy_pct: 50,
    full: false,
    pipeline: { qualified_unscheduled: 0, interview_scheduled: 0, waitlisted: 0 },
    updated_at: null,
    ...overrides,
  }
}

describe('occupancy bands (spec 015 FR-8)', () => {
  it.each([
    [0, 'critical'],
    [49, 'critical'],
    [50, 'short'],
    [79, 'short'],
    [80, 'almost'],
    [99, 'almost'],
    [100, 'covered'],
    [140, 'covered'],
    [null, 'no_data'],
  ] as const)('%s %% -> %s', (pct, band) => {
    expect(occupancyBand(pct)).toBe(band)
  })

  it('reuses the status hues: red, amber, green, then neutral greys', () => {
    expect(OCCUPANCY_BANDS.critical.color).toBe('#d03b3b')
    expect(OCCUPANCY_BANDS.short.color).toBe('#eda100')
    expect(OCCUPANCY_BANDS.almost.color).toBe('#0ca30c')
    expect(OCCUPANCY_BANDS.covered.label).toBe('Cubierta')
    expect(OCCUPANCY_BANDS.no_data.label).toBe('Sin datos')
  })
})

describe('applyZonePatch (optimistic edit mirrors the API)', () => {
  it('recomputes occupancy, rounded down', () => {
    const next = applyZonePatch(zone({}), { target_drivers: 30 })
    expect(next).toMatchObject({ target_drivers: 30, current_drivers: 20, occupancy_pct: 66, full: false })
  })

  it('marks the zone full at 100 % and a 0 target as full', () => {
    expect(applyZonePatch(zone({}), { current_drivers: 40 }).full).toBe(true)
    expect(applyZonePatch(zone({}), { target_drivers: 0 })).toMatchObject({ occupancy_pct: 100, full: true })
  })

  it('starts an area without data at 0/0', () => {
    const empty = zone({ target_drivers: null, current_drivers: null, occupancy_pct: null })
    expect(applyZonePatch(empty, { target_drivers: 10 })).toMatchObject({
      target_drivers: 10,
      current_drivers: 0,
      occupancy_pct: 0,
    })
  })
})

describe('zone totals and grouping', () => {
  const zones = [
    zone({ id: 'a', occupancy_pct: 40, current_drivers: 4, target_drivers: 10 }),
    zone({ id: 'b', name: 'Salamanca', occupancy_pct: 100, full: true, current_drivers: 10, target_drivers: 10,
      pipeline: { qualified_unscheduled: 0, interview_scheduled: 1, waitlisted: 2 } }),
    zone({ id: 'c', occupancy_pct: null, current_drivers: null, target_drivers: null }),
    zone({ id: 'cdmx', city: 'cdmx', city_name: 'Ciudad de México', country: 'MX', occupancy_pct: 85,
      current_drivers: 17, target_drivers: 20 }),
  ]

  it('counts deficit (<80 %), full zones, drivers and the waitlist; no-data zones only add their waitlist', () => {
    expect(zoneTotals(zones)).toEqual({ withData: 3, deficit: 1, full: 1, current: 31, target: 40, waitlisted: 2 })
  })

  it('groups by city, Spain first, neediest zone first and no data last', () => {
    const groups = groupByCity(zones)
    expect(groups.map((g) => g.city)).toEqual(['madrid', 'cdmx'])
    expect(groups[0].zones.map((z) => z.id)).toEqual(['a', 'b', 'c'])
  })

  it('keeps a given order, so an edited row does not move away from the cursor', () => {
    const edited = zones.map((z) => (z.id === 'a' ? applyZonePatch(z, { target_drivers: 1 }) : z))
    expect(groupByCity(edited)[0].zones.map((z) => z.id)).not.toEqual(['a', 'b', 'c'])
    expect(groupByCity(edited, ['a', 'b', 'c', 'cdmx'])[0].zones.map((z) => z.id)).toEqual(['a', 'b', 'c'])
  })
})

describe('zone-demand factor text', () => {
  it('shows occupancy, or says there is no data', () => {
    expect(zoneDemandText(45)).toBe('45 % cubierta')
    expect(zoneDemandText(null)).toBe('sin datos de ocupación')
  })

  it('reads as one sentence in the score breakdown', () => {
    const factor = { field: 'location', reason_code: 'zone_demand', value: 45, points: 20 } as const
    expect(factorValue(factor)).toBe('45 % cubierta')
    expect(factorSentence(factor)).toBe('Demanda en su zona: 45 % cubierta (+20)')
    expect(factorSentence({ ...factor, value: null, points: 0 })).toBe(
      'Demanda en su zona: sin datos de ocupación (+0)',
    )
  })
})
