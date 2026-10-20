import { defineMiddleware } from 'astro:middleware';
import type { APIContext } from 'astro';

/**
 * La caché de borde del portal (Cloudflare Pages).
 *
 * El sitio se renderiza en el SERVIDOR: cada visita a la portada ejecutaba
 * el SSR, que a su vez pedía datos a la API en Render (Oregon). Cloudflare
 * NO cachea el HTML de las respuestas SSR, así que esa visita se|traducía
 * en un tiempo de espera largo y repetido.
 *
 * Este middleware guarda el HTML renderizado en la Cache API del edge
 * (`caches.default`) y lo devuelve tal cual en las visitas siguientes. El
 * primer visitante paga el render; el segundo, el tercero y el cuarto no.
 *
 * REGLA DE ORO: sólo se cachea lo que es PÚBLICO y lo que NO cambia con
 * cada visita.
 *
 *  · `/en-vivo` es una transmisión: cachear su HTML sería una mentira (y el
 *    que lo viera después vería un marcador congelado). NUNCA se cachea.
 *  · `/admin/*` es el panel del organizador y el del juez: NUNCA se cachea.
 *  · La clave de la caché es la URL COMPLETA, con su query string: así
 *    `/ranking-general?fecha=2` y `/ranking-general?fecha=3` son dos
 *    páginas distintas y jamás comparten el mismo HTML. (La alternativa —
 *    dejar las rutas con query fuera de la caché — también sería válida,
 *    pero se pierde la caché justo en la página más pesada del portal.)
 *
 * La revalidación va en segundo plano (`waitUntil`): el visitante que
 * llega con la caché caducada no espera al render, y el que llega sin
 * caché tampoco se queda esperando a que se guarde la copia.
 */

/** Rutas EXACTAS que se pueden cachear en el borde. */
const RUTAS_EXACTAS = [
  '/',
  '/ranking-general',
  '/premios',
  '/eventos-especiales',
  '/inscripciones',
];

/** PREFIJOS de ruta que se pueden cachear en el borde. */
const RUTAS_PREFIJO = ['/fechas/', '/corredor/', '/equipos/'];

/**
 * Rutas que NUNCA se cachean, aunque su prefijo pareciera cacheable.
 * `/en-vivo` es la transmisión en vivo; `/admin` es el panel.
 */
const RUTAS_NUNCA = ['/en-vivo', '/admin'];

/** Cuánto tiempo guarda el edge la página (segundos). */
const TTL_SECONDS = 60;

/**
 * El runtime de Cloudflare que el adaptador deja en `locals.runtime`.
 * No está en los tipos de Astro porque sólo existe con ese adaptador.
 */
interface CloudflareRuntime {
  caches?: { default?: Cache };
  ctx?: { waitUntil?: (promise: Promise<unknown>) => void };
}

/** ¿Esta ruta se puede cachear en el borde? */
function esCacheable(pathname: string): boolean {
  const prohibida = RUTAS_NUNCA.some(
    (prefijo) => pathname === prefijo || pathname.startsWith(`${prefijo}/`)
  );
  if (prohibida) return false;

  const exacta = RUTAS_EXACTAS.some(
    (ruta) => pathname === ruta || pathname === `${ruta}/`
  );
  if (exacta) return true;

  return RUTAS_PREFIJO.some((prefijo) => pathname.startsWith(prefijo));
}

/**
 * La caché de borde (`caches.default`).
 *
 * Sólo existe en el runtime de los Workers. En `astro dev` o con el
 * adaptador Node NO existe: entonces se devuelve `null` y el middleware se
 * aparta (degrada con elegancia, no revienta).
 */
function cacheDeBorde(context: APIContext): Cache | null {
  const runtime = (context.locals as { runtime?: CloudflareRuntime }).runtime;
  if (runtime?.caches?.default) return runtime.caches.default;

  const global = (globalThis as unknown as { caches?: { default?: Cache } }).caches;
  return global?.default ?? null;
}

/**
 * Lanza una promesa en segundo plano.
 *
 * Astro 5 no expone `waitUntil` en el `APIContext`: en el adaptador de
 * Cloudflare el equivalente es el `ExecutionContext` del Worker, que el
 * adaptador deja en `context.locals.runtime.ctx`. Se busca ahí primero y,
 * por si una versión futura de Astro lo añade al contexto, también se
 * prueba `context.waitUntil`. Si no hay ninguno (adaptador Node), la
 * promesa se espera suelta: el sitio sigue siendo correcto, sólo pierde el
 * "guardar en segundo plano".
 */
function enSegundoPlano(context: APIContext, promesa: Promise<unknown>): void {
  const espera = promesa.catch(() => undefined);

  const runtime = (context.locals as { runtime?: CloudflareRuntime }).runtime;
  if (runtime?.ctx && typeof runtime.ctx.waitUntil === 'function') {
    runtime.ctx.waitUntil(espera);
    return;
  }

  const delContexto = (context as { waitUntil?: (p: Promise<unknown>) => void })
    .waitUntil;
  if (typeof delContexto === 'function') {
    delContexto.call(context, espera);
    return;
  }

  void espera;
}

export const onRequest = defineMiddleware(async (context, next) => {
  const { request, url } = context;
  const method = request.method.toUpperCase();

  // Sólo GET, y sólo rutas públicas: `/en-vivo` y `/admin/*` quedan fuera.
  const cacheable = method === 'GET' && esCacheable(url.pathname);

  const cache = cacheDeBorde(context);
  if (!cacheable || !cache) return next();

  // La clave lleva la URL COMPLETA: el query string forma parte de la
  // identidad de la página (`?fecha=2` y `?fecha=3` no son la misma).
  const key = new Request(url.toString(), { method: 'GET' });

  const hit = await cache.match(key);
  if (hit) {
    const headers = new Headers(hit.headers);
    headers.set('X-Kuspide-Cache', 'HIT');
    return new Response(hit.body, { status: hit.status, headers });
  }

  const response = await next();
  if (!response.ok || response.status !== 200) return response;

  // Una respuesta con cookies es de una persona concreta: no se cachea.
  if (response.headers.has('set-cookie')) return response;

  const headers = new Headers(response.headers);
  headers.set(
    'Cache-Control',
    `public, max-age=15, s-maxage=${TTL_SECONDS}, stale-while-revalidate=300`
  );
  headers.set('X-Kuspide-Cache', 'MISS');

  const paraElVisitante = new Response(response.body, {
    status: 200,
    statusText: response.statusText,
    headers,
  });

  // Se guarda una COPIA: la original se le entrega al visitante y la copia
  // se escribe en el edge sin que nadie espere a que termine.
  const copia = paraElVisitante.clone();
  enSegundoPlano(context, cache.put(key, copia));

  return paraElVisitante;
});
