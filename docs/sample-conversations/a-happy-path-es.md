# Happy path, Spain

> A Madrid candidate gives several fields per message (name, age and vehicle at once; hours and shift together) and books an interview by writing the day and time.

Final status: **`interview_scheduled`** · 9 candidate messages · total cost $0.0183 · client `anthropic` · today = 2026-10-13

## Transcript

**Sofi:** ¡Hola! Soy Sofi, la asistente virtual (automática) de Grupo Sazón 👋 Te haré unas preguntas rápidas (3 min) sobre el puesto de repartidor/a. Política de privacidad: https://gruposazon.example/privacidad ¿Aceptas que usemos tus datos para este proceso?

`[Sí]` `[No]`

**Candidate:** hola!! si vale, adelante

**Sofi:** ¡Genial, gracias! ¿Cómo te llamas? Nombre y apellido, por favor.

**Candidate:** soy Lucía Fernández, tengo 24 años y voy en moto, una scoopy de 125

**Sofi:** ¡Encantada, Lucía! ¿Tienes carné de conducir en vigor?

`[Sí]` `[No]`

**Candidate:** sii carnet A2 desde hace 3 años

**Sofi:** ¡Genial, Lucía! ¿En qué ciudad y barrio te gustaría repartir?

**Candidate:** vivo en chamberi, madrid

**Sofi:** ¡Perfecto, Lucía, Chamberí! ¿Qué disponibilidad tienes: jornada completa, media jornada o fines de semana?

`[Jornada completa]` `[Media jornada]` `[Fines de semana]`

**Candidate:** jornada completa y mejor por las tardes

**Sofi:** ¡Genial, Lucía, jornada completa por las tardes! ¿Cuántos años de experiencia tienes como repartidora y con qué apps?

**Candidate:** unos 2 años en glovo y antes unos meses en just eat

**Sofi:** ¡Qué bien, Lucía, con esa experiencia vas sobrada! ¿Cuándo podrías empezar?

**Candidate:** podría empezar el lunes que viene sin problema

**Sofi:** ¡Genial, Lucía! Repasemos tus datos:  
• Nombre completo: Lucía Fernández  
• Edad: 24  
• Vehículo: Moto  
• Carné de conducir: Sí  
• Ciudad y barrio: Chamberí (Madrid)  
• Disponibilidad: Jornada completa  
• Horario: Tardes  
• Experiencia: 2 años (Glovo, Just Eat)  
• Fecha de inicio: 19/10/2026  
  
¿Está todo bien?

`[Sí]` `[No]`

**Candidate:** Sí

**Sofi:** ¡Todo listo, Lucía! Estas son las horas disponibles para tu entrevista:  
1. miércoles 14/10, 10:00  
2. miércoles 14/10, 17:00  
3. jueves 15/10, 10:00  
4. jueves 15/10, 17:00  
5. viernes 16/10, 10:00  
6. viernes 16/10, 17:00  
¿Cuál te viene mejor?

`[miércoles 14/10, 10:00]` `[miércoles 14/10, 17:00]` `[jueves 15/10, 10:00]` `[jueves 15/10, 17:00]` `[viernes 16/10, 10:00]` `[viernes 16/10, 17:00]`

**Candidate:** el jueves a las 5 de la tarde me va genial

**Sofi:** ¡Perfecto, Lucía! Tu entrevista queda agendada: jueves 15/10, 17:00. ¡Nos vemos!

## Outcome

Status: **`interview_scheduled`**

<details>
<summary>Candidate record (JSON)</summary>

```json
{
  "record_version": 1,
  "status": "interview_scheduled",
  "disqualification_reason": null,
  "needs_review_reasons": [],
  "score": {
    "score": 60,
    "bucket": "high",
    "factors": [
      {
        "field": "experience",
        "value": 2,
        "points": 10,
        "reason_code": "years_of_experience"
      },
      {
        "field": "experience",
        "value": [
          "glovo",
          "just_eat"
        ],
        "points": 20,
        "reason_code": "known_platforms"
      },
      {
        "field": "availability",
        "value": [
          "full_time"
        ],
        "points": 15,
        "reason_code": "availability_breadth"
      },
      {
        "field": "schedule",
        "value": [
          "afternoon"
        ],
        "points": 5,
        "reason_code": "schedule_flexibility"
      },
      {
        "field": "start_date",
        "value": "2026-10-19",
        "points": 10,
        "reason_code": "start_date_proximity"
      }
    ],
    "max_score": 100
  },
  "flags": [],
  "language": "es",
  "drop_off_stage": "scheduling",
  "selected_slot_id": "2026-10-15T17:00",
  "config_version": "2026-10-11.1+2026-10-11.2",
  "consent": true,
  "fields": {
    "full_name": {
      "status": "valid",
      "value": "Lucía Fernández"
    },
    "age": {
      "status": "valid",
      "value": {
        "is_adult": null,
        "age": 24,
        "birth_year": null
      }
    },
    "vehicle_type": {
      "status": "valid",
      "value": "motorbike"
    },
    "has_license": {
      "status": "valid",
      "value": true
    },
    "location": {
      "status": "valid",
      "value": {
        "raw_text": "chamberi, Madrid",
        "country": "ES",
        "city": "madrid",
        "zone": "mad-chamberi",
        "in_service_area": true
      }
    },
    "availability": {
      "status": "valid",
      "value": [
        "full_time"
      ]
    },
    "schedule": {
      "status": "valid",
      "value": [
        "afternoon"
      ]
    },
    "experience": {
      "status": "valid",
      "value": {
        "years": 2,
        "platforms": [
          "glovo",
          "just_eat"
        ]
      }
    },
    "start_date": {
      "status": "valid",
      "value": "2026-10-19"
    }
  },
  "post_close_corrections": []
}
```

</details>

## Recruiter summary

_Generated by: llm_

**Estado:** Entrevista agendada
**Puntuación:** 60/100
**Prioridad:** Alta
**Factores principales:** Plataformas conocidas (+20), Disponibilidad (+15), Años de experiencia (+10)
**Nombre completo:** Lucía Fernández
**Edad:** 24
**Vehículo:** Moto
**Carné de conducir:** Sí
**Ciudad y barrio:** Chamberí (Madrid)
**Disponibilidad:** Jornada completa
**Horario:** Tardes
**Experiencia:** 2 años (Glovo, Just Eat)
**Fecha de inicio:** 19/10/2026
**Idioma del candidato:** Español
**Última etapa:** Agenda
**Entrevista:** 2026-10-15T17:00

**Resumen:** Lucía respondió a todas las preguntas con tono cercano y colaborador, confirmó los datos resumidos y eligió un horario para la entrevista sin dudas. La conversación se completó sin incidencias.
**Tono:** Positivo. Respuestas entusiastas y colaborativas durante todo el proceso.
**Observaciones:**
- Afirma tener unos 2 años en Glovo y unos meses en Just Eat; la experiencia no está verificada.
- Dice que podría empezar el lunes que viene; la fecha de inicio registrada es posterior, conviene confirmarla en la entrevista.
- Prefiere horario de tardes con jornada completa; confirmar que la tarde es compatible con las necesidades del puesto.

## Cost and latency per turn

| # | Input | Extraction | Engine action | Phrasing | Cost (USD) | Latency (ms) |
|---|---|---|---|---|---:|---:|
| 0 | greeting | skipped | `ask_field` | ok | 0.0020 | 1625 |
| 1 | message | ok | `ask_field` | ok | 0.0012 | 3704 |
| 2 | message | ok | `ask_field` | ok | 0.0013 | 3343 |
| 3 | message | ok | `ask_field` | ok | 0.0013 | 2891 |
| 4 | message | ok | `ask_field` | ok | 0.0015 | 3031 |
| 5 | message | ok | `ask_field` | ok | 0.0014 | 4063 |
| 6 | message | ok | `ask_field` | ok | 0.0013 | 3422 |
| 7 | message | ok | `show_recap` | ok | 0.0035 | 3437 |
| 8 | message | ok | `offer_slots` | ok | 0.0028 | 3891 |
| 9 | message | ok | `confirm_interview` | ok | 0.0015 | 3422 |
| - | summary | - | - | llm | 0.0004 | 2625 |

**Totals:** turns $0.0179 + summary $0.0004 = **$0.0183** · average turn latency **3283 ms** · max 4063 ms
