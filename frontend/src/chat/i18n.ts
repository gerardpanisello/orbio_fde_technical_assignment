import type { Language, Status } from '../api/client'

type ChatText = {
  online: string
  typing: string
  placeholder: string
  send: string
  notSent: string
  retry: string
  today: string
  newChat: string
  restoreFailed: string
  notice: string
  quickReplies: string
  addToCalendar: string
  interviewReminder: string
  banner: Record<Exclude<Status, 'in_progress'>, string>
}

/** Candidate-facing UI strings (the agent's own words come from the backend). */
export const CHAT_TEXT: Record<Language, ChatText> = {
  es: {
    online: 'en línea',
    typing: 'escribiendo…',
    placeholder: 'Escribe un mensaje',
    send: 'Enviar',
    notSent: 'No se pudo enviar',
    retry: 'Reintentar',
    today: 'HOY',
    newChat: 'Nueva conversación',
    restoreFailed: 'No pudimos recuperar tu conversación.',
    notice:
      'Sofi es una asistente automática de Grupo Sazón. Tus datos solo se usan para este proceso de selección.',
    quickReplies: 'Respuestas rápidas',
    addToCalendar: 'Añadir al calendario',
    interviewReminder: 'Recordatorio de entrevista',
    banner: {
      interview_scheduled: 'Entrevista agendada',
      qualified_unscheduled: 'Solicitud completa: el equipo te escribirá para agendar',
      waitlisted: 'En lista de espera: te avisaremos cuando haya hueco en tu zona',
      needs_review: 'Una persona del equipo revisará tu solicitud',
      disqualified: 'Proceso finalizado',
      opted_out: 'Has salido del proceso',
      abandoned: 'Conversación cerrada por inactividad',
    },
  },
  en: {
    online: 'online',
    typing: 'typing…',
    placeholder: 'Type a message',
    send: 'Send',
    notSent: 'Not sent',
    retry: 'Retry',
    today: 'TODAY',
    newChat: 'New conversation',
    restoreFailed: 'We could not restore your conversation.',
    notice:
      'Sofi is an automated assistant from Grupo Sazón. Your data is only used for this hiring process.',
    quickReplies: 'Quick replies',
    addToCalendar: 'Add to calendar',
    interviewReminder: 'Interview reminder',
    banner: {
      interview_scheduled: 'Interview booked',
      qualified_unscheduled: 'Application complete: the team will message you to book',
      waitlisted: "On the waiting list: we'll let you know when there's a spot in your area",
      needs_review: 'Someone from the team will review your application',
      disqualified: 'Process finished',
      opted_out: 'You left the process',
      abandoned: 'Conversation closed for inactivity',
    },
  },
}
