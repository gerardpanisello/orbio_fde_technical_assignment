/** Zone occupancy (spec 015): colour bands, optimistic edits and the Zonas page KPIs. */
import type { Zone, ZonePatch } from '../api/client'
import { COUNTRY } from './labels'

export type OccupancyBand = 'critical' | 'short' | 'almost' | 'covered' | 'no_data'

/**
 * Bands, from the most urgent. Colours reuse the app's status steps (red, amber and green
 * are the same hexes as Descartado / Requiere revisión / Entrevista agendada), so "red"
 * means "act now" everywhere; covered is a neutral grey because there is nothing to do.
 * Colour is never the only cue: the bar always carries the % and the band label.
 */
export const OCCUPANCY_BANDS: Record<
  OccupancyBand,
  { label: string; color: string; hint: string }
> = {
  critical: { label: 'Déficit grave', color: '#d03b3b', hint: 'Menos del 50 % de la plantilla' },
  short: { label: 'Déficit', color: '#eda100', hint: 'Entre el 50 % y el 80 %' },
  almost: { label: 'Casi cubierta', color: '#0ca30c', hint: 'Entre el 80 % y el 100 %' },
  covered: { label: 'Cubierta', color: '#a8a29e', hint: 'Al 100 % o más: los nuevos aptos van a lista de espera' },
  no_data: { label: 'Sin datos', color: '#d6d3d1', hint: 'Sin objetivo de plantilla: no suma puntos ni hay lista de espera' },
}

/** Below this occupancy a zone counts as "con déficit" (KPI and filter). */
export const DEFICIT_BELOW_PCT = 80

export function occupancyBand(pct: number | null | undefined): OccupancyBand {
  if (pct === null || pct === undefined) return 'no_data'
  if (pct < 50) return 'critical'
  if (pct < DEFICIT_BELOW_PCT) return 'short'
  if (pct < 100) return 'almost'
  return 'covered'
}

export function hasDeficit(zone: Pick<Zone, 'occupancy_pct'>): boolean {
  return zone.occupancy_pct !== null && zone.occupancy_pct < DEFICIT_BELOW_PCT
}

/**
 * The zone as the API will return it after `patch`, for the optimistic update. Mirrors
 * backend api/staffing.py: an area without data starts at 0/0, occupancy is rounded
 * down and a target of 0 counts as full.
 */
export function applyZonePatch(zone: Zone, patch: ZonePatch): Zone {
  const target = patch.target_drivers ?? zone.target_drivers ?? 0
  const current = patch.current_drivers ?? zone.current_drivers ?? 0
  const ratio = target > 0 ? current / target : 1
  return {
    ...zone,
    target_drivers: target,
    current_drivers: current,
    occupancy_pct: Math.floor(ratio * 100),
    full: ratio >= 1,
  }
}

export type ZoneTotals = {
  withData: number
  deficit: number
  full: number
  current: number
  target: number
  waitlisted: number
}

export function zoneTotals(zones: Zone[]): ZoneTotals {
  const totals: ZoneTotals = { withData: 0, deficit: 0, full: 0, current: 0, target: 0, waitlisted: 0 }
  for (const zone of zones) {
    totals.waitlisted += zone.pipeline.waitlisted
    if (zone.occupancy_pct === null) continue
    totals.withData += 1
    if (hasDeficit(zone)) totals.deficit += 1
    if (zone.full) totals.full += 1
    totals.current += zone.current_drivers ?? 0
    totals.target += zone.target_drivers ?? 0
  }
  return totals
}

export type CityGroup = {
  city: string
  cityName: string
  country: Zone['country']
  zones: Zone[]
  totals: ZoneTotals
}

/** Cities by country (ES first) then name; zones by occupancy, the neediest first, no data last. */
export function groupByCity(zones: Zone[]): CityGroup[] {
  const byCity = new Map<string, Zone[]>()
  for (const zone of zones) byCity.set(zone.city, [...(byCity.get(zone.city) ?? []), zone])
  const countries = Object.keys(COUNTRY)
  return [...byCity.values()]
    .map((list) => ({
      city: list[0].city,
      cityName: list[0].city_name,
      country: list[0].country,
      zones: [...list].sort(
        (a, b) =>
          (a.occupancy_pct ?? Infinity) - (b.occupancy_pct ?? Infinity) ||
          a.name.localeCompare(b.name, 'es'),
      ),
      totals: zoneTotals(list),
    }))
    .sort(
      (a, b) =>
        countries.indexOf(a.country) - countries.indexOf(b.country) ||
        a.cityName.localeCompare(b.cityName, 'es'),
    )
}

/** Spanish number + percent, as the rest of the dashboard writes it: "45 %". */
export function formatOccupancy(pct: number | null | undefined): string {
  return pct === null || pct === undefined ? 'Sin datos' : `${pct} %`
}

/** The zone-demand factor's value (occupancy % at scoring time, or null when unknown). */
export function zoneDemandText(value: unknown): string {
  return typeof value === 'number' ? `${value} % cubierta` : 'sin datos de ocupación'
}
