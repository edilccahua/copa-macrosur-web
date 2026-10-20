/**
 * admin.ts — la puerta del panel del organizador.
 *
 * La clave de administrador **nunca** viaja en el bundle: antes estaba
 * escrita en el código de la página (`const ADMIN_KEY = '…'`), de modo que
 * cualquiera que abriera el DevTools podía leerla yapprove pagos, subir
 * Excels que pisan la base de datos o abrir y cerrar la transmisión en vivo.
 *
 * Ahora el organizador la escribe una vez por sesión en el gate de
 * `/admin` y queda en `sessionStorage`: se pierde al cerrar la pestaña (no
 * sobrevive a un "cerrar y volver a abrir"), y nunca se incluye en el
 * HTML, en el bundle ni en el historial de Git.
 *
 * La clave real vive en el servidor: `ADMIN_API_KEY` en el entorno del
 * backend (Render) y en el `.env` de la raíz del repositorio.
 */

const ADMIN_KEY_STORAGE = 'kuspide_admin_key';

/** La clave de la sesión actual, o `''` si no hay ninguna. */
export function adminKey(): string {
  try {
    return sessionStorage.getItem(ADMIN_KEY_STORAGE) ?? '';
  } catch {
    return '';
  }
}

/** Guarda la clave en la sesión actual. */
export function setAdminKey(value: string): void {
  try {
    sessionStorage.setItem(ADMIN_KEY_STORAGE, value.trim());
  } catch {
    /* sin almacenamiento: la clave vive sólo en memoria */
  }
}

/** Olvida la clave de la sesión. */
export function clearAdminKey(): void {
  try {
    sessionStorage.removeItem(ADMIN_KEY_STORAGE);
  } catch {
    /* nada que limpiar */
  }
}

/** Las cabeceras que exigen los endpoints de administración. */
export function adminHeaders(): Record<string, string> {
  return { 'X-Admin-Key': adminKey() };
}

/**
 * Una URL que se puede abrir sin riesgo.
 *
 * `voucher_url` lo escribe quien se inscribe: si se pinta como `href` sin
 * filtrar, un `javascript:` en él es un vector de XSS en el panel del
 * organizador. Sólo pasan las URLs `http` y `https`.
 */
export function safeUrl(raw: string | null | undefined): string | null {
  if (!raw) return null;
  try {
    const url = new URL(raw);
    return url.protocol === 'http:' || url.protocol === 'https:' ? url.toString() : null;
  } catch {
    return null;
  }
}
