# Code-switching

> The candidate starts in Spanish, then switches to English mid-way; the agent follows the switch and finishes in English.

Final status: **`interview_scheduled`** · 12 candidate messages · total cost $0.0204 · client `anthropic` · today = 2026-10-13

## Transcript

**Sofi:** ¡Hola! Soy Sofi, la asistente virtual (automática) de Grupo Sazón 👋 Te haré unas preguntas rápidas (3 min) sobre el puesto de repartidor/a. Política de privacidad: https://gruposazon.example/privacidad ¿Aceptas que usemos tus datos para este proceso?

`[Sí]` `[No]`

**Candidate:** si

**Sofi:** ¡Genial! ¿Cómo te llamas? Nombre y apellido, por favor.

**Candidate:** me llamo Daniel Okafor, tengo 27

**Sofi:** ¡Encantada, Daniel! ¿Con qué vehículo repartirías?

`[Moto]` `[Coche]` `[Bici]` `[Bici eléctrica]` `[Sin vehículo]`

**Candidate:** sorry, can we continue in English? my Spanish is not great

**Sofi:** Of course, Daniel, English is no problem! Which vehicle would you deliver with?

`[Motorbike]` `[Car]` `[Bicycle]` `[E-bike]` `[No vehicle]`

**Candidate:** a motorbike

**Sofi:** Got it, Daniel, a motorbike. Do you have a valid driving licence?

`[Yes]` `[No]`

**Candidate:** yes I have a licence

**Sofi:** Great, thanks Daniel! Which city and area would you like to deliver in?

**Candidate:** I live in Ruzafa, Valencia

**Sofi:** Great, Daniel, thanks! What availability works for you: full-time, part-time or weekends?

`[Full-time]` `[Part-time]` `[Weekends]`

**Candidate:** full time please

**Sofi:** Thanks, Daniel! Which time of day would you prefer to deliver: mornings, afternoons, evenings or flexible?

`[Mornings]` `[Afternoons]` `[Evenings]` `[Flexible]`

**Candidate:** I'm flexible, any shift

**Sofi:** Great, Daniel, flexible works for us! How many years of delivery experience do you have, and with which apps?

**Candidate:** 3 years with Deliveroo in Dublin

**Sofi:** Three years with Deliveroo, that's great experience, Daniel! When could you start?

**Candidate:** I can start tomorrow

**Sofi:** Thanks, Daniel! Let's go over your details:  
• Full name: Daniel Okafor  
• Age: 27  
• Vehicle: Motorbike  
• Driving licence: Yes  
• City and area: Ruzafa (Valencia)  
• Availability: Full-time  
• Schedule: Flexible  
• Experience: 3 years (Deliveroo)  
• Start date: 14/10/2026  
Is everything correct?

`[Yes]` `[No]`

**Candidate:** yes

**Sofi:** All done, Daniel! These are the available times for your interview:  
1. Wed 14 Oct, 10:00  
2. Wed 14 Oct, 17:00  
3. Thu 15 Oct, 10:00  
4. Thu 15 Oct, 17:00  
5. Fri 16 Oct, 10:00  
6. Fri 16 Oct, 17:00  
Which one works best for you?

`[Wed 14 Oct, 10:00]` `[Wed 14 Oct, 17:00]` `[Thu 15 Oct, 10:00]` `[Thu 15 Oct, 17:00]` `[Fri 16 Oct, 10:00]` `[Fri 16 Oct, 17:00]`

**Candidate:** Thu 15 Oct, 10:00

**Sofi:** Perfect, Daniel! Your interview is booked for Thu 15 Oct, 10:00. See you then!

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
    "score": 75,
    "bucket": "high",
    "factors": [
      {
        "field": "experience",
        "value": 3,
        "points": 15,
        "reason_code": "years_of_experience"
      },
      {
        "field": "experience",
        "value": [
          "deliveroo"
        ],
        "points": 10,
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
          "flexible"
        ],
        "points": 15,
        "reason_code": "schedule_flexibility"
      },
      {
        "field": "start_date",
        "value": "2026-10-14",
        "points": 20,
        "reason_code": "start_date_proximity"
      }
    ],
    "max_score": 100
  },
  "flags": [],
  "language": "en",
  "drop_off_stage": "scheduling",
  "selected_slot_id": "2026-10-15T10:00",
  "config_version": "2026-10-11.1+2026-10-11.2",
  "consent": true,
  "fields": {
    "full_name": {
      "status": "valid",
      "value": "Daniel Okafor"
    },
    "age": {
      "status": "valid",
      "value": {
        "is_adult": null,
        "age": 27,
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
        "raw_text": "Ruzafa, Valencia",
        "country": "ES",
        "city": "valencia",
        "zone": "val-ruzafa",
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
        "flexible"
      ]
    },
    "experience": {
      "status": "valid",
      "value": {
        "years": 3,
        "platforms": [
          "deliveroo"
        ]
      }
    },
    "start_date": {
      "status": "valid",
      "value": "2026-10-14"
    }
  },
  "post_close_corrections": []
}
```

</details>

## Recruiter summary

_Generated by: llm_

**Estado:** Entrevista agendada
**Puntuación:** 75/100
**Prioridad:** Alta
**Factores principales:** Incorporación próxima (+20), Años de experiencia (+15), Disponibilidad (+15)
**Nombre completo:** Daniel Okafor
**Edad:** 27
**Vehículo:** Moto
**Carné de conducir:** Sí
**Ciudad y barrio:** Ruzafa (Valencia)
**Disponibilidad:** Jornada completa
**Horario:** Flexible
**Experiencia:** 3 años (Deliveroo)
**Fecha de inicio:** 14/10/2026
**Idioma del candidato:** Inglés
**Última etapa:** Agenda
**Entrevista:** 2026-10-15T10:00

**Resumen:** Daniel pidió continuar en inglés desde el inicio porque dice que su español no es muy bueno, y la conversación se completó en ese idioma. Respondió de forma directa a todas las preguntas, confirmó los datos resumidos y eligió un horario para la entrevista.
**Tono:** Positivo. Colaborativo y claro, sin objeciones ni quejas durante la conversación.
**Observaciones:**
- Pidió cambiar a inglés; conviene tenerlo en cuenta para la entrevista y comunicaciones posteriores.
- Dice que puede empezar "mañana", pero la fecha de inicio registrada es distinta; conviene confirmarla en la entrevista.

## Cost and latency per turn

| # | Input | Extraction | Engine action | Phrasing | Cost (USD) | Latency (ms) |
|---|---|---|---|---|---:|---:|
| 0 | greeting | skipped | `ask_field` | ok | 0.0020 | 1844 |
| 1 | message | ok | `ask_field` | ok | 0.0012 | 3296 |
| 2 | message | ok | `ask_field` | ok | 0.0013 | 3344 |
| 3 | message | ok | `ask_field` | ok | 0.0013 | 3563 |
| 4 | message | ok | `ask_field` | ok | 0.0012 | 3609 |
| 5 | message | ok | `ask_field` | ok | 0.0011 | 2875 |
| 6 | message | ok | `ask_field` | ok | 0.0012 | 3266 |
| 7 | message | ok | `ask_field` | ok | 0.0014 | 4062 |
| 8 | message | ok | `ask_field` | ok | 0.0012 | 3344 |
| 9 | message | ok | `ask_field` | ok | 0.0011 | 3312 |
| 10 | message | ok | `show_recap` | ok | 0.0031 | 3313 |
| 11 | message | ok | `offer_slots` | ok | 0.0027 | 3031 |
| 12 | message | ok | `confirm_interview` | ok | 0.0014 | 3469 |
| - | summary | - | - | llm | 0.0003 | 2375 |

**Totals:** turns $0.0201 + summary $0.0003 = **$0.0204** · average turn latency **3256 ms** · max 4062 ms
