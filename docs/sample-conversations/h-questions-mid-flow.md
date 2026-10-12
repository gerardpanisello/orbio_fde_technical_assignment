# Questions mid-flow

> The candidate asks about pay and whether they need their own bike; the agent answers what it can without making promises and gets back to the screening.

Final status: **`interview_scheduled`** · 14 candidate messages · total cost $0.0245 · client `anthropic` · today = 2026-10-13

## Transcript

**Sofi:** ¡Hola! Soy Sofi, la asistente virtual (automática) de Grupo Sazón 👋 Te haré unas preguntas rápidas (3 min) sobre el puesto de repartidor/a. Política de privacidad: https://gruposazon.example/privacidad ¿Aceptas que usemos tus datos para este proceso?

`[Sí]` `[No]`

**Candidate:** sí acepto

**Sofi:** ¡Genial, gracias! ¿Cómo te llamas? Nombre y apellido, por favor.

**Candidate:** Raúl Jiménez

**Sofi:** ¡Gracias, Raúl! ¿Cuántos años tienes?

**Candidate:** ¿cuánto se paga?

**Sofi:** Buena pregunta, Raúl: eso lo consulto con el equipo. Mientras tanto, ¿cuántos años tienes?

**Candidate:** vale. tengo 22

**Sofi:** ¡Perfecto, Raúl! ¿Con qué vehículo repartirías?

`[Moto]` `[Coche]` `[Bici]` `[Bici eléctrica]` `[Sin vehículo]`

**Candidate:** ¿hace falta moto propia?

**Sofi:** Buena pregunta, Raúl: eso lo consulto con el equipo. Mientras tanto, ¿con qué vehículo repartirías?

`[Moto]` `[Coche]` `[Bici]` `[Bici eléctrica]` `[Sin vehículo]`

**Candidate:** ok pues tengo una scooter de 125

**Sofi:** ¡Genial, Raúl, gracias por contármelo! ¿Tienes carné de conducir en vigor?

`[Sí]` `[No]`

**Candidate:** sí tengo carnet

**Sofi:** ¡Perfecto, Raúl! ¿En qué ciudad y barrio te gustaría repartir?

**Candidate:** Triana, Sevilla

**Sofi:** ¡Genial, Raúl! ¿Qué disponibilidad tienes: jornada completa, media jornada o fines de semana?

`[Jornada completa]` `[Media jornada]` `[Fines de semana]`

**Candidate:** media jornada

**Sofi:** Entendido, Raúl. ¿En qué horario prefieres repartir: mañanas, tardes, noches o flexible?

`[Mañanas]` `[Tardes]` `[Noches]` `[Flexible]`

**Candidate:** mañanas

**Sofi:** ¡Genial, Raúl, mañanas entonces! ¿Cuántos años de experiencia tienes como repartidor/a y con qué apps?

**Candidate:** nada de experiencia

**Sofi:** Vale, Raúl, no pasa nada por no tener experiencia. ¿Cuándo podrías empezar?

**Candidate:** en 3 días

**Sofi:** Gracias, Raúl. Repasemos tus datos:  
• Nombre completo: Raúl Jiménez  
• Edad: 22  
• Vehículo: Moto  
• Carné de conducir: Sí  
• Ciudad y barrio: Triana (Sevilla)  
• Disponibilidad: Media jornada  
• Horario: Mañanas  
• Experiencia: 0 años  
• Fecha de inicio: 16/10/2026  
  
¿Está todo bien?

`[Sí]` `[No]`

**Candidate:** sí

**Sofi:** ¡Todo listo, Raúl! Estas son las horas disponibles para tu entrevista:  
1. miércoles 14/10, 10:00  
2. miércoles 14/10, 17:00  
3. jueves 15/10, 10:00  
4. jueves 15/10, 17:00  
5. viernes 16/10, 10:00  
6. viernes 16/10, 17:00  
¿Cuál te viene mejor?

`[miércoles 14/10, 10:00]` `[miércoles 14/10, 17:00]` `[jueves 15/10, 10:00]` `[jueves 15/10, 17:00]` `[viernes 16/10, 10:00]` `[viernes 16/10, 17:00]`

**Candidate:** el viernes por la mañana

**Sofi:** ¡Perfecto, Raúl! Tu entrevista queda agendada: viernes 16/10, 10:00. ¡Nos vemos!

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
    "score": 33,
    "bucket": "low",
    "factors": [
      {
        "field": "experience",
        "value": 0,
        "points": 0,
        "reason_code": "years_of_experience"
      },
      {
        "field": "experience",
        "value": [],
        "points": 0,
        "reason_code": "known_platforms"
      },
      {
        "field": "availability",
        "value": [
          "part_time"
        ],
        "points": 8,
        "reason_code": "availability_breadth"
      },
      {
        "field": "schedule",
        "value": [
          "morning"
        ],
        "points": 5,
        "reason_code": "schedule_flexibility"
      },
      {
        "field": "start_date",
        "value": "2026-10-16",
        "points": 20,
        "reason_code": "start_date_proximity"
      }
    ],
    "max_score": 100
  },
  "flags": [],
  "language": "es",
  "drop_off_stage": "scheduling",
  "selected_slot_id": "2026-10-16T10:00",
  "config_version": "2026-10-11.1+2026-10-11.2",
  "consent": true,
  "fields": {
    "full_name": {
      "status": "valid",
      "value": "Raúl Jiménez"
    },
    "age": {
      "status": "valid",
      "value": {
        "is_adult": null,
        "age": 22,
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
        "raw_text": "Triana, Sevilla",
        "country": "ES",
        "city": "sevilla",
        "zone": "sev-triana",
        "in_service_area": true
      }
    },
    "availability": {
      "status": "valid",
      "value": [
        "part_time"
      ]
    },
    "schedule": {
      "status": "valid",
      "value": [
        "morning"
      ]
    },
    "experience": {
      "status": "valid",
      "value": {
        "years": 0,
        "platforms": []
      }
    },
    "start_date": {
      "status": "valid",
      "value": "2026-10-16"
    }
  },
  "post_close_corrections": []
}
```

</details>

## Recruiter summary

_Generated by: llm_

**Estado:** Entrevista agendada
**Puntuación:** 33/100
**Prioridad:** Baja
**Factores principales:** Incorporación próxima (+20), Disponibilidad (+8), Flexibilidad horaria (+5)
**Nombre completo:** Raúl Jiménez
**Edad:** 22
**Vehículo:** Moto
**Carné de conducir:** Sí
**Ciudad y barrio:** Triana (Sevilla)
**Disponibilidad:** Media jornada
**Horario:** Mañanas
**Experiencia:** 0 años
**Fecha de inicio:** 16/10/2026
**Idioma del candidato:** Español
**Última etapa:** Agenda
**Entrevista:** 2026-10-16T10:00

**Resumen:** Raúl respondió a todas las preguntas del proceso y terminó agendando la entrevista. Preguntó dos veces (sueldo y si hace falta moto propia) y ambas quedaron sin respuesta, con la promesa de consultarlas con el equipo. Su tono fue breve y directo, sin quejas.
**Tono:** Neutro. Respuestas cortas y directas, sin entusiasmo ni frustración explícita.
**Observaciones:**
- Preguntó cuánto se paga; el asistente no pudo responder y quedó pendiente de consultar con el equipo.
- Preguntó si hace falta moto propia; quedó sin respuesta. Dice tener una scooter de 125 cc.
- Dice que puede empezar en 3 días y eligió la entrevista del viernes 16/10 a las 10:00.

## Cost and latency per turn

| # | Input | Extraction | Engine action | Phrasing | Cost (USD) | Latency (ms) |
|---|---|---|---|---|---:|---:|
| 0 | greeting | skipped | `ask_field` | ok | 0.0020 | 1875 |
| 1 | message | ok | `ask_field` | ok | 0.0012 | 3719 |
| 2 | message | ok | `ask_field` | ok | 0.0011 | 2891 |
| 3 | message | ok | `ask_field` | ok | 0.0014 | 3609 |
| 4 | message | ok | `ask_field` | ok | 0.0012 | 3438 |
| 5 | message | ok | `ask_field` | ok | 0.0015 | 3156 |
| 6 | message | ok | `ask_field` | ok | 0.0013 | 3344 |
| 7 | message | ok | `ask_field` | ok | 0.0013 | 3328 |
| 8 | message | ok | `ask_field` | ok | 0.0014 | 2718 |
| 9 | message | ok | `ask_field` | ok | 0.0014 | 3329 |
| 10 | message | ok | `ask_field` | ok | 0.0014 | 3828 |
| 11 | message | ok | `ask_field` | ok | 0.0013 | 3406 |
| 12 | message | ok | `show_recap` | ok | 0.0033 | 3484 |
| 13 | message | ok | `offer_slots` | ok | 0.0028 | 3391 |
| 14 | message | ok | `confirm_interview` | ok | 0.0015 | 3094 |
| - | summary | - | - | llm | 0.0004 | 2547 |

**Totals:** turns $0.0241 + summary $0.0004 = **$0.0245** · average turn latency **3241 ms** · max 3828 ms
