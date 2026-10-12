/**
 * Spec 013 FR-4: what Sofi *says* when she reads a message aloud. The screen keeps the
 * original text; this only changes the words sent to text-to-speech. Pure functions, so
 * every rule is unit-tested.
 */
import type { Country, Language } from '../api/client'

export type SpeakOptions = {
  language: Language
  country?: Country | null
  /** The message's quick replies: read as "Puedes decir: Sí o No". */
  quickReplies?: readonly string[]
  /** "Today", for dropping the current year from dates. Defaults to now. */
  now?: Date
}

const MONTHS: Record<Language, string[]> = {
  es: [
    'enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
    'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre',
  ],
  en: [
    'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December',
  ],
}
const WEEKDAYS: Record<Language, string[]> = {
  es: ['domingo', 'lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado'],
  en: ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'],
}
const WEEKDAY_WORDS = [...WEEKDAYS.es, ...WEEKDAYS.en, 'miercoles', 'sabado'].join('|')

// Emojis, skin tones, flags, and the invisible joiners/selectors that glue them together.
const EMOJI_RE =
  /\p{Extended_Pictographic}|[\u{1F3FB}-\u{1F3FF}]|[\u{1F1E6}-\u{1F1FF}]|\u{FE0F}|\u{200D}|\u{20E3}/gu
const EMOJI_BEFORE_SENTENCE_RE = new RegExp(
  String.raw`\s*(?:${EMOJI_RE.source})+(?=\s+[¿¡]?\p{Lu})`,
  'gu',
)
const URL_RE = /\bhttps?:\/\/[^\s)]+/gi
const PRIVACY_RE =
  /(pol[ií]tica de privacidad|aviso de privacidad|privacy notice|privacy policy)\s*:?\s*https?:\/\/[^\s)]+/gi

/** The privacy link can't be read aloud: point to the screen instead. */
function privacySentence(label: string, language: Language): string {
  const lower = label.toLowerCase()
  if (language === 'en') return `You'll find the ${lower} on your screen.`
  const article = lower.startsWith('aviso') ? 'el' : 'la'
  return `Puedes leer ${article} ${lower} que verás en pantalla.`
}

function stripMarkdown(text: string): string {
  return text
    .replace(/\[([^\]]+)\]\((?:[^)]+)\)/g, '$1') // [text](url) -> text
    .replace(/(\*\*|__)(.+?)\1/g, '$2') // **bold**
    .replace(/(^|[\s(])[*_]([^*_\n]+)[*_](?=[\s).,!?:;]|$)/gm, '$1$2') // *italic*
    .replace(/`+([^`]*)`+/g, '$1') // `code`
    .replace(/^\s{0,3}#{1,6}\s+/gm, '') // # heading
    .replace(/^\s{0,3}>\s?/gm, '') // > quote
}

function spokenTime(hour: number, minute: number, language: Language): string {
  const hh = String(hour)
  const mm = String(minute).padStart(2, '0')
  if (language === 'en') return `at ${hh}:${mm}`
  const clock = minute === 0 ? hh : `${hh}:${mm}`
  return `${hour === 1 ? 'a la' : 'a las'} ${clock}`
}

function validDate(year: number, month: number, day: number): Date | null {
  const date = new Date(year, month - 1, day)
  return date.getMonth() === month - 1 && date.getDate() === day ? date : null
}

/**
 * "lunes 19/10/2026" -> "lunes 19 de octubre"; "martes 13/10, 10:00" -> "martes 13 de
 * octubre, a las 10". The weekday is added when missing (only if the year is known) and
 * the year is spoken only when it isn't the current one.
 */
function spellDates(text: string, language: Language, now: Date): string {
  const re = new RegExp(
    `(?:\\b(${WEEKDAY_WORDS})\\s+)?\\b(\\d{1,2})/(\\d{1,2})(?:/(\\d{4}|\\d{2}))?\\b(?:,?\\s*(?:a las\\s+|at\\s+)?(\\d{1,2}):(\\d{2})\\b)?`,
    'giu',
  )
  return text.replace(re, (match, weekday: string | undefined, d, m, y, hh, mi) => {
    const day = Number(d)
    const month = Number(m)
    if (month < 1 || month > 12 || day < 1 || day > 31) return match
    const year = y ? (y.length === 2 ? 2000 + Number(y) : Number(y)) : null
    const date = year !== null ? validDate(year, month, day) : null
    if (year !== null && !date) return match
    const name = weekday ?? (date ? WEEKDAYS[language][date.getDay()] : undefined)
    const monthName = MONTHS[language][month - 1]
    let spoken =
      language === 'en' ? `${day} ${monthName}` : `${day} de ${monthName}`
    if (year !== null && year !== now.getFullYear()) {
      spoken += language === 'en' ? ` ${year}` : ` de ${year}`
    }
    if (name) spoken = `${name} ${spoken}`
    if (hh !== undefined) {
      spoken += `${language === 'en' ? ' ' : ', '}${spokenTime(Number(hh), Number(mi), language)}`
    }
    return spoken
  })
}

/** Bullets and numbered options become sentences; line breaks become pauses. */
function linesToSentences(text: string, language: Language): { text: string; numbered: boolean } {
  let numbered = false
  const lines = text
    .split(/\n+/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const option = /^(\d{1,2})[.)]\s+(.*)$/.exec(line)
      if (option) {
        numbered = true
        return `${language === 'en' ? 'Option' : 'Opción'} ${option[1]}: ${option[2]}`
      }
      return line.replace(/^[•·\-*–]\s+/, '')
    })
    .map((line) => (/[.!?¿¡:;,…]$/.test(line) ? line : `${line}.`))
  return { text: lines.join(' '), numbered }
}

function smallWords(text: string, language: Language): string {
  let out = text
    .replace(/[«»"“”]/g, '')
    .replace(/\b(\d+)\s?min\b\.?/g, language === 'en' ? '$1 minutes' : '$1 minutos')
  if (language === 'es') {
    out = out
      .replace(/\b(\w+)or\/a\b/g, '$1or o $1ora') // repartidor/a -> repartidor o repartidora
      .replace(/\b(\w+)o\/a\b/g, '$1o o $1a') // interesado/a
  }
  return out
}

function joinOr(items: string[], language: Language): string {
  const or = language === 'en' ? 'or' : 'o'
  if (items.length <= 1) return items.join('')
  return `${items.slice(0, -1).join(', ')} ${or} ${items.at(-1)}`
}

const normalise = (s: string) =>
  s
    .toLocaleLowerCase()
    .normalize('NFD')
    .replace(/\p{Diacritic}/gu, '')
    .replace(/\s+/g, ' ')
    .trim()

/** "Puedes decir: Sí o No." / "Puedes decir, por ejemplo: Moto, Coche o Bici." */
export function spokenQuickReplies(
  replies: readonly string[],
  original: string,
  language: Language,
  numbered: boolean,
): string {
  const labels = replies.map((r) => r.replace(EMOJI_RE, '').trim()).filter(Boolean)
  if (!labels.length) return ''
  const text = normalise(original)
  if (labels.every((label) => text.includes(normalise(label)))) {
    // The options are already in the message (e.g. the interview slots): don't repeat them.
    if (!numbered) return ''
    return language === 'en'
      ? 'You can say the option number.'
      : 'Puedes decir el número de la opción.'
  }
  if (labels.length <= 3) {
    return language === 'en'
      ? `You can say: ${joinOr(labels, language)}.`
      : `Puedes decir: ${joinOr(labels, language)}.`
  }
  const sample = joinOr(labels.slice(0, 3), language)
  return language === 'en'
    ? `You can say, for example: ${sample}.`
    : `Puedes decir, por ejemplo: ${sample}.`
}

/** The text-to-speech version of one of Sofi's messages. */
export function toSpeakable(text: string, options: SpeakOptions): string {
  const { language, quickReplies = [], now = new Date() } = options
  let out = text.replace(PRIVACY_RE, (_m, label: string) => ` ${privacySentence(label, language)} `)
  out = stripMarkdown(out)
  out = out.replace(URL_RE, '')
  // "Grupo Sazón 👋 Te haré…": an emoji that ends a sentence becomes a full stop (a pause).
  out = out.replace(EMOJI_BEFORE_SENTENCE_RE, '.')
  out = out.replace(EMOJI_RE, '')
  out = spellDates(out, language, now)
  const lines = linesToSentences(out, language)
  out = smallWords(lines.text, language)
  const replies = spokenQuickReplies(quickReplies, text, language, lines.numbered)
  if (replies) out = `${out} ${replies}`
  return tidy(out)
}

function tidy(text: string): string {
  return text
    .replace(/\(\s*\)/g, '')
    .replace(/\s+([.,!?;:])/g, '$1')
    .replace(/([.!?])\s*\.+/g, '$1')
    .replace(/:\s*\./g, '.')
    .replace(/\s{2,}/g, ' ')
    .trim()
}

/**
 * Browser voices cut long utterances (Chrome stops after ~15 s), so the fallback speaks
 * sentence by sentence. Sentences longer than `max` are split at commas, then at spaces.
 */
export function splitSentences(text: string, max = 180): string[] {
  const sentences = text.match(/[^.!?…]+[.!?…]*\s*/g) ?? []
  const chunks: string[] = []
  for (const raw of sentences) {
    const sentence = raw.trim()
    if (!sentence) continue
    if (sentence.length <= max) {
      chunks.push(sentence)
      continue
    }
    let current = ''
    for (const word of sentence.split(/\s+/)) {
      if (current && `${current} ${word}`.length > max) {
        chunks.push(current)
        current = word
      } else {
        current = current ? `${current} ${word}` : word
      }
    }
    if (current) chunks.push(current)
  }
  return chunks
}
