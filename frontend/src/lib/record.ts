/** Turns the engine's CandidateRecord (spec 002) into short Spanish display values. */
import type { AreaLabels, CandidateRecord, ScoreFactor } from '../api/client'
import type { components } from '../api/schema'
import { formatDate, formatStartDate } from './format'
import { zoneDemandText } from './zones'
import { AVAILABILITY, FACTOR, FIELD, SCHEDULE, VEHICLE, list, placeLabel, platformLabel } from './labels'

type Fields = CandidateRecord['fields']
export type FieldKey = keyof Fields
type FieldStatus = components['schemas']['FieldStatus']

export const FIELD_ORDER: FieldKey[] = [
  'full_name',
  'age',
  'vehicle_type',
  'has_license',
  'location',
  'availability',
  'schedule',
  'experience',
  'start_date',
]

export type FieldRow = { key: FieldKey; label: string; status: FieldStatus; value: string }

export function fieldRows(record: CandidateRecord, areas: AreaLabels | undefined): FieldRow[] {
  return FIELD_ORDER.map((key) => ({
    key,
    label: FIELD[key],
    status: record.fields[key].status,
    value: fieldValue(record, key, areas),
  }))
}

function fieldValue(record: CandidateRecord, key: FieldKey, areas: AreaLabels | undefined): string {
  const fields = record.fields
  switch (key) {
    case 'full_name':
      return fields.full_name.value ?? '—'
    case 'age': {
      const age = fields.age.value
      if (!age) return '—'
      if (age.age != null) return `${age.age} años`
      if (age.birth_year != null) return `Nacido en ${age.birth_year}`
      if (age.is_adult != null) return age.is_adult ? 'Mayor de edad' : 'Menor de edad'
      return '—'
    }
    case 'vehicle_type':
      return fields.vehicle_type.value ? VEHICLE[fields.vehicle_type.value] : '—'
    case 'has_license':
      return fields.has_license.value == null ? '—' : fields.has_license.value ? 'Sí' : 'No'
    case 'location': {
      const location = fields.location.value
      if (!location) return '—'
      if (!location.in_service_area) return `${location.raw_text} (fuera de zona)`
      return placeLabel(location.city, location.zone, areas)
    }
    case 'availability':
      return list(fields.availability.value, AVAILABILITY)
    case 'schedule':
      return list(fields.schedule.value, SCHEDULE)
    case 'experience': {
      const experience = fields.experience.value
      if (!experience) return '—'
      const years = experience.years === 1 ? '1 año' : `${experience.years} años`
      return experience.platforms.length
        ? `${years} (${experience.platforms.map(platformLabel).join(', ')})`
        : years
    }
    case 'start_date':
      return formatStartDate(fields.start_date.value, record.flags.includes('start_date_approximate'))
  }
}

/** The value a score factor was computed from, e.g. "5 años", "Glovo, Just Eat". */
export function factorValue(factor: ScoreFactor): string {
  const value = factor.value
  // null is meaningful here: the area has no staffing data, so no bonus (spec 015 AC-5)
  if (factor.reason_code === 'zone_demand') return zoneDemandText(value)
  if (value === null || value === undefined) return 'sin dato'
  switch (factor.reason_code) {
    case 'years_of_experience':
      return `${value} ${value === 1 ? 'año' : 'años'}`
    case 'known_platforms':
      return Array.isArray(value) && value.length ? value.map(platformLabel).join(', ') : 'ninguna'
    case 'availability_breadth':
      return Array.isArray(value) ? list(value as (keyof typeof AVAILABILITY)[], AVAILABILITY) : String(value)
    case 'schedule_flexibility':
      return Array.isArray(value) ? list(value as (keyof typeof SCHEDULE)[], SCHEDULE) : String(value)
    case 'start_date_proximity':
      return typeof value === 'string' ? formatDate(value) : String(value)
    default:
      return Array.isArray(value) ? value.join(', ') : String(value)
  }
}

/** One factor as a sentence: "Demanda en su zona: 45 % cubierta (+20)". */
export function factorSentence(factor: ScoreFactor): string {
  return `${FACTOR[factor.reason_code]}: ${factorValue(factor)} (+${factor.points})`
}
