import { ApiError } from '../api/client'

/** A short Spanish message for any failed request (NFR-2: never a blank screen). */
export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status >= 500 || error.status === 0) return 'El servidor no responde. ¿Está la API arrancada?'
    return error.detail
  }
  return 'No hay conexión con el servidor. ¿Está la API arrancada en el puerto 8000?'
}
