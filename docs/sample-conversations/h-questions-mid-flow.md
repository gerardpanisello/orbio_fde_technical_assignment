# Questions mid-flow

> The candidate asks about pay (before and after giving their city) and whether they need their own bike; the agent answers only from the client's approved FAQ (spec 009), with the Spain figures once the city is known, and resumes the screening.

Final status: **`interview_scheduled`** · 15 candidate messages · total cost $0.0353 · client `anthropic` · today = 2026-10-13

## Transcript

**Sofi:** ¡Hola! Soy Sofi, la asistente virtual (automática) de Grupo Sazón 👋 Te haré unas preguntas rápidas (3 min) sobre el puesto de repartidor/a. Aquí tienes la política de privacidad: https://gruposazon.example/privacidad ¿Aceptas que usemos tus datos para este proceso?

`[Sí]` `[No]`

**Candidate:** sí acepto

**Sofi:** Gracias. ¿Cómo te llamas? Nombre y apellido, por favor.

**Candidate:** Raúl Jiménez

**Sofi:** Perfecto, Raúl. ¿Cuántos años tienes?

**Candidate:** ¿cuánto se paga?

**Sofi:** Depende del país y de la ciudad: se paga por hora, más un extra por pedido en las horas de más trabajo. En cuanto sepa dónde quieres repartir, el equipo te da el rango exacto. ¿Cuántos años tienes?

**Candidate:** vale. tengo 22

**Sofi:** Gracias. ¿Con qué vehículo repartirías?

`[Moto]` `[Coche]` `[Bici]` `[Bici eléctrica]` `[Sin vehículo]`

**Candidate:** ¿hace falta moto propia?

**Sofi:** No hace falta que sea moto: puedes repartir con tu propio vehículo (moto, bici, bici eléctrica o coche), y en algunos locales hay motos de empresa para turnos completos. Si usas el tuyo, se compensa el desgaste por kilómetro. ¿Con qué vehículo repartirías?

`[Moto]` `[Coche]` `[Bici]` `[Bici eléctrica]` `[Sin vehículo]`

**Candidate:** ok pues tengo una scooter de 125

**Sofi:** Vale, Raúl. ¿Tienes carné de conducir en vigor?

`[Sí]` `[No]`

**Candidate:** sí tengo carnet

**Sofi:** Perfecto. ¿En qué ciudad y barrio te gustaría repartir?

**Candidate:** Triana, Sevilla

**Sofi:** ¿Qué disponibilidad tienes: jornada completa, media jornada o fines de semana?

`[Jornada completa]` `[Media jornada]` `[Fines de semana]`

**Candidate:** ¿y entonces en Sevilla cuánto se paga la hora?

**Sofi:** En España se paga entre 9 y 12 € brutos la hora, según la ciudad y la franja, más un extra por pedido en noches y fines de semana. El importe exacto te lo confirma el equipo en la entrevista. ¿Qué disponibilidad tienes: jornada completa, media jornada o fines de semana?

`[Jornada completa]` `[Media jornada]` `[Fines de semana]`

**Candidate:** media jornada

**Sofi:** Vale, Raúl. ¿En qué horario prefieres repartir: mañanas, tardes, noches o flexible?

`[Mañanas]` `[Tardes]` `[Noches]` `[Flexible]`

**Candidate:** mañanas

**Sofi:** ¿Cuánta experiencia tienes repartiendo? Por ejemplo: «2 años en Glovo».

**Candidate:** nada de experiencia

**Sofi:** Gracias. ¿Cuándo podrías empezar?

**Candidate:** en 3 días

**Sofi:** Repasemos tus datos:  
• Nombre completo: Raúl Jiménez  
• Edad: 22  
• Vehículo: Moto  
• Carné de conducir: Sí  
• Ciudad y barrio: Triana (Sevilla)  
• Disponibilidad: Media jornada  
• Horario: Mañanas  
• Experiencia: Sin experiencia  
• Fecha de inicio: viernes 16/10/2026  
  
¿Está todo bien?

`[Sí]` `[No]`

**Candidate:** sí

**Sofi:** Todo listo. Estas son las horas disponibles para tu entrevista:  
1. miércoles 14/10, 10:00  
2. jueves 15/10, 17:00  
3. viernes 16/10, 10:00  
  
¿Cuál te viene mejor?

`[miércoles 14/10, 10:00]` `[jueves 15/10, 17:00]` `[viernes 16/10, 10:00]`

**Candidate:** el viernes por la mañana

**Sofi:** Vale, tu entrevista queda agendada: viernes 16/10, a las 10:00. ¡Nos vemos!

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
      },
      {
        "field": "location",
        "value": null,
        "points": 0,
        "reason_code": "zone_demand"
      }
    ],
    "max_score": 120
  },
  "flags": [],
  "language": "es",
  "drop_off_stage": "scheduling",
  "selected_slot_id": "2026-10-16T10:00",
  "config_version": "2026-10-12.1+2026-10-11.2",
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
**Puntuación:** 33/120
**Prioridad:** Baja
**Factores principales:** Incorporación próxima (+20), Disponibilidad (+8), Flexibilidad horaria (+5)
**Nombre completo:** Raúl Jiménez
**Edad:** 22
**Vehículo:** Moto
**Carné de conducir:** Sí
**Ciudad y barrio:** Triana (Sevilla)
**Disponibilidad:** Media jornada
**Horario:** Mañanas
**Experiencia:** Sin experiencia
**Fecha de inicio:** viernes 16/10/2026
**Idioma del candidato:** Español
**Última etapa:** Agenda
**Entrevista:** 2026-10-16T10:00

**Resumen:** Raúl Jiménez completó la conversación de principio a fin y eligió entrevista para el viernes 16/10 a las 10:00. Preguntó varias veces cuánto se paga la hora y si necesitaba moto propia, y sus preguntas recibieron respuesta orientativa; el pago exacto quedó pendiente de confirmar en la entrevista.
**Tono:** Neutro. Respuestas breves y directas, con interés en las condiciones económicas pero sin quejas.
**Observaciones:**
- Preguntó varias veces por el salario por hora; conviene confirmarle el importe exacto en la entrevista.
- Dice que puede empezar en 3 días, aunque la fecha de inicio registrada es posterior; conviene aclararla.
- Indica que tiene una scooter de 125 cc como vehículo de reparto.

## Cost and latency per turn

| # | Input | Extraction | Engine action | Phrasing | Cost (USD) | Latency (ms) |
|---|---|---|---|---|---:|---:|
| 0 | greeting | skipped | `ask_field` | ok | 0.0023 | 1657 |
| 1 | message | ok | `ask_field` | ok | 0.0017 | 4390 |
| 2 | message | ok | `ask_field` | ok | 0.0017 | 3360 |
| 3 | message | ok | `ask_field` | ok | 0.0024 | 4484 |
| 4 | message | ok | `ask_field` | ok | 0.0017 | 3766 |
| 5 | message | ok | `ask_field` | ok | 0.0029 | 3984 |
| 6 | message | ok | `ask_field` | ok | 0.0018 | 3359 |
| 7 | message | ok | `ask_field` | ok | 0.0018 | 3360 |
| 8 | message | ok | `ask_field` | ok | 0.0017 | 3375 |
| 9 | message | ok | `ask_field` | ok | 0.0028 | 3781 |
| 10 | message | ok | `ask_field` | ok | 0.0020 | 3813 |
| 11 | message | ok | `ask_field` | ok | 0.0019 | 3500 |
| 12 | message | ok | `ask_field` | ok | 0.0015 | 3375 |
| 13 | message | ok | `show_recap` | ok | 0.0037 | 5015 |
| 14 | message | ok | `offer_slots` | ok | 0.0027 | 3485 |
| 15 | message | ok | `confirm_interview` | ok | 0.0022 | 3640 |
| - | summary | - | - | llm | 0.0005 | 2891 |

**Totals:** turns $0.0348 + summary $0.0005 = **$0.0353** · average turn latency **3646 ms** · max 5015 ms
