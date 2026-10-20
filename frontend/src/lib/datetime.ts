/**
 * Utilidades de formato de la ficha de fecha.
 *
 * `start_time` se guarda en la BD como texto libre ("08:00 AM", "02:30 PM").
 * Convertirlo a ISO sin interpretar el meridiem desplaza la cuenta regresiva
 * seis horas: "02:30 PM" se leía como las 02:30 de la mañana.
 */

/** Convierte "08:00 AM" / "02:30 PM" / "14:30" en una hora ISO de 24h. */
export function toIsoTime(startTime: string | null | undefined): string {
  const raw = (startTime ?? '').trim();
  if (!raw) return '08:00:00';

  const match = raw.match(/^(\d{1,2})[:.](\d{2})\s*(AM|PM|am|pm)?$/);
  if (!match) return '08:00:00';

  let hours = Number(match[1]);
  const minutes = Number(match[2]);
  const meridiem = match[3]?.toUpperCase();

  if (meridiem === 'PM' && hours < 12) hours += 12;
  if (meridiem === 'AM' && hours === 12) hours = 0;

  if (hours > 23 || minutes > 59) return '08:00:00';

  return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:00`;
}

/** "08:00 AM" → "08:00 HRS" (el rótulo que muestra la cuenta regresiva). */
export function toDisplayTime(startTime: string | null | undefined): string {
  const iso = toIsoTime(startTime);
  return `${iso.slice(0, 5)} HRS`;
}

/** ISO completo del instante de largada, en la zona horaria de Lima (UTC-5). */
export function toStartInstant(date: string, startTime: string | null | undefined): string {
  return `${date}T${toIsoTime(startTime)}-05:00`;
}
