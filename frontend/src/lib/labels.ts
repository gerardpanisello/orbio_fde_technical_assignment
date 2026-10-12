/**
 * Spanish display labels for backend enums (recruiter UI copy is Spanish, NFR-1).
 * Wording follows the recruiter summary labels in config/messages/es-ES.yaml.
 */
import type { components } from '../api/schema'
import type { ActionName, AreaLabels, RecruiterStatus } from '../api/client'

type S = components['schemas']

/** Spec 016: where the candidate talks to Sofi. */
export const CHANNEL: Record<S['CandidateRow']['channel'], string> = {
  web: 'Chat web',
  whatsapp: 'WhatsApp',
}

export const VEHICLE: Record<S['VehicleType'], string> = {
  motorbike: 'Moto',
  car: 'Coche',
  bicycle: 'Bici',
  e_bike: 'Bici eléctrica',
  none: 'Sin vehículo',
}

export const AVAILABILITY: Record<S['Availability'], string> = {
  full_time: 'Jornada completa',
  part_time: 'Media jornada',
  weekends: 'Fines de semana',
}

export const SCHEDULE: Record<S['ScheduleSlot'], string> = {
  morning: 'Mañanas',
  afternoon: 'Tardes',
  evening: 'Noches',
  flexible: 'Flexible',
}

export const DISQUALIFICATION: Record<S['DisqualificationReason'], string> = {
  under_age: 'Menor de edad',
  no_license: 'Sin carné de conducir',
  out_of_area: 'Fuera de zona',
}

export const REVIEW: Record<S['ReviewReason'], string> = {
  age_unclear: 'Edad no clara',
  license_unclear: 'Carné no claro',
  vehicle_unclear: 'Vehículo no claro',
  location_unclear: 'Ubicación no clara',
  human_requested: 'Pidió hablar con una persona',
  system_failure: 'Fallo técnico',
  abuse: 'Lenguaje abusivo',
  recap_loop: 'No confirmó el resumen',
  post_close_correction: 'Corrección tras el cierre',
  engine_error: 'Error interno',
}

export const FLAG: Record<S['Flag'], string> = {
  surname_missing: 'Falta el apellido',
  name_unclear: 'Nombre no claro',
  start_date_normalised: 'Fecha de inicio ajustada a hoy',
  human_requested: 'Pidió una persona',
  post_close_correction: 'Corrección tras el cierre',
  system_failure: 'Fallo técnico',
  abuse: 'Lenguaje abusivo',
  do_not_contact: 'No contactar',
  engine_error: 'Error interno',
  correction_unclear: 'Corrección no entendida',
}

/** Conversation stages, in flow order (vocab.Stage declaration order). */
export const STAGE: Record<S['Stage'], string> = {
  consent: 'Consentimiento',
  name: 'Nombre',
  age: 'Edad',
  vehicle_license: 'Vehículo y carné',
  location: 'Ubicación',
  availability: 'Disponibilidad',
  schedule: 'Horario',
  experience: 'Experiencia',
  start_date: 'Fecha de inicio',
  recap: 'Resumen',
  scheduling: 'Agenda',
}

export const FACTOR: Record<S['FactorReason'], string> = {
  years_of_experience: 'Años de experiencia',
  known_platforms: 'Plataformas conocidas',
  availability_breadth: 'Disponibilidad',
  schedule_flexibility: 'Flexibilidad horaria',
  start_date_proximity: 'Incorporación próxima',
  zone_demand: 'Demanda en su zona',
  unknown: 'Dato no disponible',
}

export const FIELD: Record<keyof S['RecordFields'], string> = {
  full_name: 'Nombre',
  age: 'Edad',
  vehicle_type: 'Vehículo',
  has_license: 'Carné',
  location: 'Ubicación',
  availability: 'Disponibilidad',
  schedule: 'Horario',
  experience: 'Experiencia',
  start_date: 'Fecha de inicio',
}

export const FIELD_STATUS: Record<S['FieldStatus'], string> = {
  valid: 'Válido',
  unclear: 'No claro',
  not_asked: 'Pendiente',
  not_required: 'No aplica',
}

export const RECRUITER_STATUS: Record<RecruiterStatus, string> = {
  new: 'Sin gestionar',
  shortlisted: 'Preseleccionado',
  rejected: 'Rechazado',
  hired: 'Contratado',
}

export const ACTION: Record<ActionName, string> = {
  shortlist: 'Preseleccionado',
  reject: 'Rechazado',
  hire: 'Contratado',
  override: 'Aprobado manualmente',
  note: 'Nota',
}

export const LANGUAGE: Record<S['Language'], string> = { es: 'Español', en: 'Inglés' }
export const COUNTRY: Record<S['Country'], string> = { ES: 'España', MX: 'México' }

/** Platform ids from config/screening.yaml ("just_eat" -> "Just Eat"). */
export function platformLabel(id: string): string {
  const known: Record<string, string> = { didi_food: 'DiDi Food', uber_eats: 'Uber Eats' }
  return known[id] ?? id.split('_').map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(' ')
}

/** "Chamberí · Madrid", "Madrid", or "—". Unknown ids fall back to the id itself. */
export function placeLabel(
  city: string | null | undefined,
  zone: string | null | undefined,
  labels: AreaLabels | undefined,
): string {
  const cityName = city ? (labels?.cities[city] ?? city) : null
  const zoneName = zone ? (labels?.zones[zone] ?? zone) : null
  if (cityName && zoneName) return `${zoneName} · ${cityName}`
  return cityName ?? zoneName ?? '—'
}

export function list<T extends string>(values: T[] | null | undefined, labels: Record<T, string>) {
  return values && values.length ? values.map((v) => labels[v]).join(', ') : '—'
}
