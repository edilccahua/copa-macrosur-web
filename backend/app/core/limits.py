"""Límites de entrada: cuota por IP, tope del cuerpo y tope del archivo.

Tres fronteras, todas en el BORDE de la API (antes de tocar la base de
datos):

  · **cuota**: cuántas peticiones admite una IP y una ruta en una ventana
    (ventana deslizante, en memoria);
  · **tope del cuerpo**: un JSON gigante se rechaza por su `Content-Length`
    SIN leerlo;
  · **tope del archivo**: las subidas (`.xlsx`, `.gpx`) tienen su propio
    límite, más generoso que el de los JSON.
"""
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from backend.app.core.config import origen_permitido, settings
from backend.app.core.rate_limit import SlidingWindowLimiter

# Rutas que suben un archivo. Tienen su propio tope (`MAX_UPLOAD_BYTES`),
# así que el tope del cuerpo JSON no las aplica.
RUTAS_DE_SUBIDA: Tuple[str, ...] = ("/import-excel", "/upload-gpx")


@dataclass(frozen=True)
class RateRule:
    """Una regla de cuota.

    `prefix` es el prefijo de la ruta, `bucket` el nombre de la cuota (dos
    reglas del mismo bucket comparten contador) y `limit` cuántas peticiones
    se admiten por ventana.

    `methods` acota la regla a ciertos verbos. Hace falta porque el sitio
    se sirve desde Cloudflare Pages con SSR: TODAS las páginas del mundo
    llegan a la API desde la MISMA IP de salida. Limitar por IP las lecturas
    públicas dejaría la web entera sin responder, así que las reglas de
    lectura quedan fuera y sólo se limitan las escrituras y las subidas.
    """

    prefix: str
    bucket: str
    limit: int
    window_seconds: int = 60
    methods: Optional[Tuple[str, ...]] = None


# La tabla de reglas. El ORDEN importa: gana la PRIMERA regla que coincide,
# así que las específicas van antes que las generales.
#
# Las dos primeras reglas comparten el bucket `admin`: la actividad del
# organizador (consola + subidas) sale de UNA sola cuota. Por eso las dos
# declaran el MISMO límite: el limitador es uno por bucket, así que si
# declararan números distintos, el efectivo sería el más apretado y la
# tabla estaría mintiendo sobre lo que hace el código.
RATE_LIMIT_RULES: List[RateRule] = [
    # La consola del organizador: la usa una persona desde su navegador.
    RateRule(prefix="/api/v1/admin", bucket="admin", limit=60),
    # Ingesta de Excel, subida de GPX y acciones de carrera: sólo las
    # escrituras (las lecturas de `/api/v1/stages` las hace el SSR desde una
    # sola IP compartida).
    RateRule(
        prefix="/api/v1/stages",
        bucket="admin",
        limit=60,
        methods=("POST", "PUT", "PATCH", "DELETE"),
    ),
    # El juez marca tiempos desde su panel: muchas marcas seguidas son
    # normales, pero no infinitas.
    RateRule(
        prefix="/api/v1/timing",
        bucket="judge",
        limit=600,
        methods=("POST", "PUT", "PATCH", "DELETE"),
    ),
    # Inscripción y reclamos: los escribe el público.
    RateRule(
        prefix="/api/v1/public/pre-register",
        bucket="public_write",
        limit=10,
        methods=("POST",),
    ),
    RateRule(
        prefix="/api/v1/public/feedback",
        bucket="public_write",
        limit=10,
        methods=("POST",),
    ),
]

# Un limitador por bucket. Vive aquí (y no dentro del middleware) para que
# las pruebas puedan vaciar su ventana: `rate_limiter_registry["public_write"]`.
rate_limiter_registry: Dict[str, SlidingWindowLimiter] = {}

# La fábrica recibe la regla y la tabla completa: con las dos puede decidir
# qué tan apretado es el bucket (ver `default_limiter_factory`).
LimiterFactory = Callable[[RateRule, Sequence[RateRule]], SlidingWindowLimiter]


def default_limiter_factory(
    rule: RateRule, rules: Sequence[RateRule]
) -> SlidingWindowLimiter:
    """Un limitador por bucket, guardado en el registro.

    Si dos reglas comparten bucket (las dos de `admin`), manda la más
    APRETA: un bucket es un bucket, y ensancharlo por una regla regalaría
    cuota a la otra.
    """
    existente = rate_limiter_registry.get(rule.bucket)
    if existente is not None:
        return existente
    del_mismo_bucket = [r for r in rules if r.bucket == rule.bucket] or [rule]
    limite = min(r.limit for r in del_mismo_bucket)
    ventana = min(r.window_seconds for r in del_mismo_bucket)
    limitador = SlidingWindowLimiter(limit=limite, window_seconds=ventana)
    rate_limiter_registry[rule.bucket] = limitador
    return limitador


def poblar_registro(rules: Sequence[RateRule]) -> Dict[str, SlidingWindowLimiter]:
    """Crea un limitador por bucket y deja el registro listo."""
    for rule in rules:
        default_limiter_factory(rule, rules)
    return rate_limiter_registry


# Los limitadores existen desde que se importa el módulo (y no desde que se
# monta el middleware): así el registro está disponible aunque todavía no
# haya llegado ninguna petición, y las pruebas siempre encuentran su bucket.
poblar_registro(RATE_LIMIT_RULES)


def client_ip(request: Request) -> str:
    """La IP del cliente, en el orden en que la confiamos.

    `CF-Connecting-IP` lo pone Cloudflare (el sitio se sirve desde Pages) y
    `X-Forwarded-For` lo pone Render: los dos llegan de un proxy que sí
    sabemos quién es. `request.client.host` es el último recurso: en local
    es `127.0.0.1` para todo el mundo.
    """
    de_cloudflare = request.headers.get("cf-connecting-ip")
    if de_cloudflare:
        return de_cloudflare.strip()
    encadenadas = request.headers.get("x-forwarded-for")
    if encadenadas:
        return encadenadas.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return "desconocido"


def es_ruta_de_subida(path: str) -> bool:
    """¿Esta ruta sube un archivo? (tiene su propio tope, `MAX_UPLOAD_BYTES`)."""
    return any(path.endswith(suffix) for suffix in RUTAS_DE_SUBIDA)


def detalle_excede_tope(limite_bytes: int) -> str:
    """El mensaje que ve el organizador cuando su archivo no cabe."""
    if limite_bytes >= 1024 * 1024:
        return f"El archivo supera el límite de {limite_bytes // (1024 * 1024)} MB."
    return f"El archivo supera el límite de {limite_bytes // 1024} KB."


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Cuota por IP y tope del cuerpo, antes de tocar la base de datos."""

    def __init__(
        self,
        app,
        rules: List[RateRule],
        limiter_factory: LimiterFactory,
    ) -> None:
        super().__init__(app)
        self.rules = list(rules)
        self.limiter_factory = limiter_factory
        # Los limitadores de esta tabla quedan registrados al montar el
        # middleware (por si la tabla no es la de por defecto).
        for rule in self.rules:
            self.limiter_factory(rule, self.rules)

    # ── Reglas ──────────────────────────────────────────────────────────────
    def _regla_para(self, request: Request) -> Optional[RateRule]:
        """La PRIMERA regla que coincide con la ruta (y con el verbo) gana."""
        path = request.url.path
        for rule in self.rules:
            if not path.startswith(rule.prefix):
                continue
            if rule.methods and request.method not in rule.methods:
                continue
            return rule
        return None

    # ── Respuestas ──────────────────────────────────────────────────────────
    def _cabeceras_cors(self, request: Request) -> Dict[str, str]:
        """Las cabeceras de CORS de las respuestas que genera este middleware.

        El limitador se registra DESPUÉS del middleware de CORS, así que se
        ejecuta ANTES: las respuestas que genera aquí (413, 429) no pasan por
        el de CORS. Sin estas cabeceras, el navegador escondería el 413 o el
        429 detrás de un error de CORS y el usuario vería un simple "fallo de
        red" en vez de "la petición es demasiado grande" o "espera un poco".
        """
        cabeceras: Dict[str, str] = {}
        origin = request.headers.get("origin")
        if origin and origen_permitido(origin):
            cabeceras["Access-Control-Allow-Origin"] = origin
            cabeceras["Access-Control-Allow-Credentials"] = "true"
            cabeceras["Vary"] = "Origin"
        return cabeceras

    def _respuesta_413(self, request: Request, limite: int) -> JSONResponse:
        if limite >= 1024 * 1024:
            detalle = f"La petición es demasiado grande (máximo {limite // (1024 * 1024)} MB)."
        else:
            detalle = f"La petición es demasiado grande (máximo {limite // 1024} KB)."
        return JSONResponse(
            status_code=413,
            content={"detail": detalle},
            headers=self._cabeceras_cors(request),
        )

    def _respuesta_429(self, request: Request, retry_after: int) -> JSONResponse:
        cabeceras = {"Retry-After": str(retry_after)}
        cabeceras.update(self._cabeceras_cors(request))
        return JSONResponse(
            status_code=429,
            content={
                "detail": "Demasiadas peticiones. Inténtalo de nuevo en unos segundos."
            },
            headers=cabeceras,
        )

    # ── Dispatch ────────────────────────────────────────────────────────────
    async def dispatch(self, request: Request, call_next):
        if not settings.RATE_LIMIT_ENABLED:
            return await call_next(request)

        # 1. Tope del cuerpo. Se mira el `Content-Length` y NO se lee el
        #    cuerpo: un atacante puede mandar 2 GB y el servidor los
        #    descarta sin leerlos.
        limite = (
            settings.MAX_UPLOAD_BYTES
            if es_ruta_de_subida(request.url.path)
            else settings.MAX_JSON_BYTES
        )
        if await self._excede_largo(request, limite):
            return self._respuesta_413(request, limite)

        # 2. Cuota por IP y bucket. Los preflight (OPTIONS) no gastan cuota:
        #    son la negociación de CORS y no consumen nada del servidor.
        if request.method != "OPTIONS":
            rule = self._regla_para(request)
            if rule is not None:
                limitador = self.limiter_factory(rule, self.rules)
                permitido, retry_after = limitador.allow(client_ip(request))
                if not permitido:
                    return self._respuesta_429(request, retry_after)

        return await call_next(request)

    async def _excede_largo(self, request: Request, limite: int) -> bool:
        """Compara el tamaño del cuerpo con el tope.

        En las rutas de SUBIDA el tope es `MAX_UPLOAD_BYTES` (el archivo tiene
        su propio límite, más generoso que el de los JSON), pero el corte
        tiene que ocurrir AQUÍ: FastAPI parsea el multipart ANTES de resolver
        las dependencias, así que el archivo se escribe en un temporal de
        disco antes del 403 y un atacante sin credencial podría llenar el
        disco del servidor con una sola subida.

        Con `Content-Length` (lo normal) la comparación es inmediata y el
        cuerpo NO se lee. Sin `Content-Length` (transfer-encoding chunked) no
        hay nada que comparar, así que se MIDE el cuerpo real.

        En las subidas, el `Content-Length` del multipart incluye el sobre
        (boundaries y cabeceras de las partes): unas decenas de bytes más
        que el archivo. Por eso el tope efectivo de un archivo es
        `MAX_UPLOAD_BYTES` menos ese sobre (irrelevante frente a 25 MB, pero
        conviene saberlo).
        """
        bruto = request.headers.get("content-length")
        if bruto is not None:
            try:
                largo = int(bruto)
            except ValueError:
                largo = None
            if largo is not None:
                return largo > limite
        return await self._cuerpo_real_excede(request, limite)

    async def _cuerpo_real_excede(self, request: Request, limite: int) -> bool:
        """Mide el cuerpo cuando no hay `Content-Length` (chunked).

        Se lee por trozos y se para en cuanto se pasa del tope: nunca se
        acumulan más de `limite` bytes en memoria. Si el cuerpo cabe, se
        cachea en `request._body` —la misma caché que usa el
        `Request.body()` de Starlette— para que la ruta lo reciba intacto.
        """
        total = 0
        trozos: List[bytes] = []
        async for trozo in request.stream():
            total += len(trozo)
            if total > limite:
                return True
            trozos.append(trozo)
        request._body = b"".join(trozos)
        return False
