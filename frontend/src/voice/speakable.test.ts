import { describe, expect, it } from 'vitest'
import { splitSentences, spokenQuickReplies, toSpeakable } from './speakable'

const NOW = new Date(2026, 9, 13) // 13 Oct 2026
const es = { language: 'es' as const, now: NOW }
const en = { language: 'en' as const, now: NOW }

// Real messages from the fake-mode API (config/messages/*.yaml).
const GREETING_ES =
  '¡Hola! Soy Sofi, la asistente virtual (automática) de Grupo Sazón 👋 Te haré unas preguntas rápidas (3 min) sobre el puesto de repartidor/a. Política de privacidad: https://gruposazon.example/privacidad ¿Aceptas que usemos tus datos para este proceso?'

describe('toSpeakable', () => {
  it('reads the greeting without emoji or URL, pointing to the privacy policy on screen', () => {
    const spoken = toSpeakable(GREETING_ES, { ...es, quickReplies: ['Sí', 'No'] })
    expect(spoken).toBe(
      '¡Hola! Soy Sofi, la asistente virtual (automática) de Grupo Sazón. Te haré unas preguntas rápidas (3 minutos) sobre el puesto de repartidor o repartidora. Puedes leer la política de privacidad que verás en pantalla. ¿Aceptas que usemos tus datos para este proceso? Puedes decir: Sí o No.',
    )
    expect(spoken).not.toMatch(/https?:|👋/)
  })

  it('uses the Mexican "aviso de privacidad" and the English notice', () => {
    expect(toSpeakable('Aviso de privacidad: https://x.example/p ¿Aceptas?', es)).toBe(
      'Puedes leer el aviso de privacidad que verás en pantalla. ¿Aceptas?',
    )
    expect(toSpeakable('Privacy notice: https://x.example/p Do you agree?', en)).toBe(
      "You'll find the privacy notice on your screen. Do you agree?",
    )
  })

  it('strips any other URL, emojis (with skin tones and joiners) and markdown', () => {
    expect(toSpeakable('Mira https://a.example/x?y=1 ahora 🙌🏽 👩‍💻 ✅', es)).toBe('Mira ahora.')
    expect(toSpeakable('¡Genial! 🎉 ¿Seguimos? 👍 Vale 👌 sí', es)).toBe('¡Genial! ¿Seguimos? Vale sí.')
    expect(toSpeakable('**Importante**: trae tu _DNI_ y `carné`. Ver [web](https://a.example)', es)).toBe(
      'Importante: trae tu DNI y carné. Ver web.',
    )
    expect(toSpeakable('# Hola\n> cita', es)).toBe('Hola. cita.')
  })

  it('spells dates naturally and drops the current year', () => {
    expect(toSpeakable('• Fecha de inicio: lunes 19/10/2026', es)).toBe(
      'Fecha de inicio: lunes 19 de octubre.',
    )
    // The weekday is added when missing; another year is spoken.
    expect(toSpeakable('Empiezas el 19/10/2026.', es)).toBe('Empiezas el lunes 19 de octubre.')
    expect(toSpeakable('Desde el 4/1/2027.', es)).toBe('Desde el lunes 4 de enero de 2027.')
    expect(toSpeakable('Start date: Monday 19/10/2026', en)).toBe('Start date: Monday 19 October.')
  })

  it('reads slots with their time', () => {
    expect(toSpeakable('Tu entrevista queda agendada: martes 13/10, 10:00. ¡Nos vemos!', es)).toBe(
      'Tu entrevista queda agendada: martes 13 de octubre, a las 10. ¡Nos vemos!',
    )
    expect(toSpeakable('miércoles 14/10, 17:30', es)).toBe('miércoles 14 de octubre, a las 17:30.')
    expect(toSpeakable('jueves 15/10, 1:00', es)).toBe('jueves 15 de octubre, a la 1.')
    expect(toSpeakable('Booked: Tuesday 13/10, 10:00', en)).toBe('Booked: Tuesday 13 October at 10:00.')
  })

  it('leaves things that are not dates alone', () => {
    expect(toSpeakable('Ratio 45/12 y 0/0', es)).toBe('Ratio 45/12 y 0/0.')
    expect(toSpeakable('El 31/02/2026 no existe', es)).toBe('El 31/02/2026 no existe.')
  })

  it('turns the recap bullets and the numbered slot list into sentences', () => {
    const recap = 'Repasemos tus datos:\n• Nombre completo: Lucía Martín\n• Edad: 27\n¿Está todo bien?'
    expect(toSpeakable(recap, { ...es, quickReplies: ['Sí', 'No'] })).toBe(
      'Repasemos tus datos: Nombre completo: Lucía Martín. Edad: 27. ¿Está todo bien? Puedes decir: Sí o No.',
    )
    const slots =
      '¡Todo listo! Estas son las horas disponibles para tu entrevista:\n1. martes 13/10, 10:00\n2. miércoles 14/10, 17:00\n¿Cuál te viene mejor?'
    expect(
      toSpeakable(slots, { ...es, quickReplies: ['martes 13/10, 10:00', 'miércoles 14/10, 17:00'] }),
    ).toBe(
      '¡Todo listo! Estas son las horas disponibles para tu entrevista: Opción 1: martes 13 de octubre, a las 10. Opción 2: miércoles 14 de octubre, a las 17. ¿Cuál te viene mejor? Puedes decir el número de la opción.',
    )
  })
})

describe('spokenQuickReplies', () => {
  it('lists up to three options with "o" / "or"', () => {
    expect(spokenQuickReplies(['Sí', 'No'], '¿Tienes carné?', 'es', false)).toBe('Puedes decir: Sí o No.')
    expect(spokenQuickReplies(['Mañanas', 'Tardes', 'Noches'], '¿Horario?', 'es', false)).toBe(
      'Puedes decir: Mañanas, Tardes o Noches.',
    )
    expect(spokenQuickReplies(['Yes', 'No'], 'OK?', 'en', false)).toBe('You can say: Yes or No.')
  })

  it('gives examples when there are more than three', () => {
    expect(
      spokenQuickReplies(['Moto', 'Coche', 'Bici', 'Bici eléctrica', 'Sin vehículo'], '¿Vehículo?', 'es', false),
    ).toBe('Puedes decir, por ejemplo: Moto, Coche o Bici.')
  })

  it('says nothing when there are none, or they are already in the message', () => {
    expect(spokenQuickReplies([], 'Hola', 'es', false)).toBe('')
    expect(
      spokenQuickReplies(['Jornada completa', 'Media jornada'], '¿Jornada completa o media jornada?', 'es', false),
    ).toBe('')
  })
})

describe('splitSentences', () => {
  it('splits by sentence and breaks long ones at word boundaries', () => {
    expect(splitSentences('Hola. ¿Qué tal? Bien!')).toEqual(['Hola.', '¿Qué tal?', 'Bien!'])
    const long = `${'palabra '.repeat(40).trim()}.`
    const chunks = splitSentences(long, 50)
    expect(chunks.every((c) => c.length <= 50)).toBe(true)
    expect(chunks.join(' ')).toBe(long)
  })
})
