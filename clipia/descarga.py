"""Descarga de YouTube con yt-dlp (máximo 1080p).

Fase 4: cookies del navegador (anti-bot) opcionales y errores
accionables: cada fallo de yt-dlp se traduce a un mensaje en español
que dice qué hacer (iniciar sesión en YouTube, actualizar yt-dlp,
revisar la conexión...), en vez del texto técnico de yt-dlp.
"""
import logging
import os
from collections.abc import Callable

log = logging.getLogger("clipia.descarga")

# Navegadores de los que yt-dlp puede leer las cookies de YouTube
# (anti-bot): el usuario debe tener sesión iniciada en YouTube en
# ese navegador. yt-dlp admite más, pero estos tres son los que
# cubren casi todos los PCs con Windows.
NAVEGADORES_COOKIES = ("chrome", "edge", "firefox")

FORMATO_VIDEO = ("bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/"
                 "bestvideo[height<=1080]+bestaudio/"
                 "best[height<=1080]/best")

# Mensajes accionables por código de error (ver
# clasificar_error_descarga). "%s" es el detalle técnico, solo en
# "otro": en los demás el mensaje ya dice qué hacer sin él.
_MENSAJES_ERROR = {
    "bot": ("YouTube pide verificar que no eres un bot. Inicia sesión "
            "en YouTube en tu navegador, elige ese navegador en "
            "Ajustes → «Cookies de YouTube» y reintenta. Si sigue "
            "fallando, descarga el video con el navegador y usa el "
            "archivo local con «Examinar…»."),
    "cookies": ("No se encontraron cookies de YouTube en el navegador "
                "elegido. Inicia sesión en YouTube en ese navegador y "
                "reintenta, o elige «Sin cookies» en Ajustes."),
    "obsoleto": ("YouTube cambió algo y yt-dlp no lo entiende "
                 "(versión desactualizada). Pulsa «Actualizar yt-dlp» "
                 "en Ajustes y reintenta."),
    "no_disponible": ("El video no está disponible (privado, eliminado "
                      "o la URL no existe). Revisa la URL e inténtalo "
                      "con otro video."),
    "url": "Esa URL no es un video de YouTube válido. Revisa la URL.",
    "prohibido": ("YouTube rechazó la descarga (error 403). Prueba con "
                  "las cookies de tu navegador en Ajustes → «Cookies "
                  "de YouTube», o descarga el video con el navegador "
                  "y usa el archivo local."),
    "red": ("No se pudo conectar con YouTube. Revisa tu conexión a "
            "internet y reintenta."),
    "espacio": ("No queda espacio en disco para descargar el video. "
                "Libera espacio y reintenta."),
    "permisos": ("No se puede escribir en la carpeta de descarga. "
                 "Elige otra carpeta de salida y reintenta."),
    "otro": ("No se pudo descargar el video: %s. Prueba con las "
             "cookies de tu navegador en Ajustes, o descarga el video "
             "con el navegador y usa el archivo local."),
}


class ErrorDescarga(Exception):
    """La descarga de YouTube falló. El mensaje ya es accionable
    (dice qué hacer) y se muestra al usuario tal cual; `codigo`
    clasifica el fallo ("bot", "cookies", "obsoleto", "red"...)."""

    def __init__(self, mensaje: str, codigo: str = "otro") -> None:
        super().__init__(mensaje)
        self.codigo = codigo


def clasificar_error_descarga(texto: str) -> str:
    """Clasifica un error de yt-dlp por su texto (minúsculas).

    El orden importa: el mensaje de anti-bot menciona las cookies,
    así que "bot" se comprueba antes que "cookies".
    """
    mensaje = (texto or "").lower()
    if "not a bot" in mensaje or "sign in to confirm" in mensaje:
        return "bot"
    if "cookies" in mensaje:
        return "cookies"
    if ("unable to extract" in mensaje or "failed to extract" in mensaje
            or "regex" in mensaje):
        return "obsoleto"
    if ("video unavailable" in mensaje or "private video" in mensaje
            or "video is private" in mensaje
            or "this video is not available" in mensaje
            or "http error 404" in mensaje or "404: not found" in mensaje):
        return "no_disponible"
    if "unsupported url" in mensaje:
        return "url"
    if "http error 403" in mensaje or "403 forbidden" in mensaje:
        return "prohibido"
    if ("connection" in mensaje or "network" in mensaje
            or "timed out" in mensaje or "name or service not known"
            in mensaje or "failed to establish" in mensaje
            or "temporary failure in name resolution" in mensaje
            or "max retries" in mensaje):
        return "red"
    if "no space left" in mensaje or "no space on device" in mensaje:
        return "espacio"
    if "permission denied" in mensaje or "errno 13" in mensaje:
        return "permisos"
    return "otro"


def mensaje_error_descarga(error: Exception) -> str:
    """Traduce un error de yt-dlp a un mensaje accionable en español."""
    codigo = clasificar_error_descarga(str(error))
    plantilla = _MENSAJES_ERROR[codigo]
    if codigo == "otro":
        return plantilla % error
    return plantilla


def _error_descarga(error: Exception) -> ErrorDescarga:
    """Envuelve un error de yt-dlp en ErrorDescarga (con su código)."""
    return ErrorDescarga(mensaje_error_descarga(error),
                         clasificar_error_descarga(str(error)))


def _opciones_descarga(carpeta_destino: str, gancho_estado,
                       navegador: str | None) -> dict:
    """Opciones de yt-dlp para la descarga (máximo 1080p, MP4)."""
    opciones = {
        "format": FORMATO_VIDEO,
        "merge_output_format": "mp4",
        "noplaylist": True,
        "restrictfilenames": True,
        "outtmpl": os.path.join(carpeta_destino, "%(title)s.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "progress_hooks": [gancho_estado],
    }
    if navegador:
        # Tupla (navegador, perfil, ...): yt-dlp lee las cookies de
        # YouTube del perfil por defecto de ese navegador.
        opciones["cookiesfrombrowser"] = (navegador,)
    return opciones


def _descargar_con_libreria(url: str, carpeta_destino: str,
                            progreso: Callable[[float], None] | None,
                            navegador: str | None) -> str:
    """Descarga con la librería yt_dlp (modo dev/venv)."""
    import yt_dlp

    os.makedirs(carpeta_destino, exist_ok=True)

    def gancho_estado(info):
        if progreso and info.get("status") == "downloading":
            total = info.get("total_bytes") or info.get("total_bytes_estimate")
            descargado = info.get("downloaded_bytes", 0)
            if total:
                progreso(min(1.0, descargado / total))

    opciones = _opciones_descarga(carpeta_destino, gancho_estado, navegador)
    try:
        with yt_dlp.YoutubeDL(opciones) as ydl:
            info = ydl.extract_info(url, download=True)
            # B1: tras el merge (p. ej. webm->mp4), prepare_filename()
            # devuelve la ruta previa al merge (un .webm que ya no
            # existe). requested_downloads trae la ruta final real.
            descargas = info.get("requested_downloads") or []
            if descargas and descargas[0].get("filepath"):
                ruta = descargas[0]["filepath"]
            else:
                ruta = ydl.prepare_filename(info)
    except Exception as error:  # noqa: BLE001 - traducir cualquier error
        raise _error_descarga(error) from error
    if progreso:
        progreso(1.0)
    return ruta


def descargar_youtube(url: str, carpeta_destino: str,
                      progreso: Callable[[float], None] | None = None,
                      navegador: str | None = None) -> str:
    """Descarga un video de YouTube en MP4, máximo 1080p.

    Devuelve la ruta del archivo descargado. `navegador` es "chrome",
    "edge" o "firefox" (cookies de YouTube de ese navegador, para el
    anti-bot); "ninguno", None o cualquier otro valor no usa cookies.
    Si las cookies fallan (p. ej. el navegador no tiene sesión), se
    reintenta una vez sin ellas: muchos videos no las necesitan. Los
    fallos se lanzan como ErrorDescarga, con un mensaje accionable.
    """
    navegador = navegador if navegador in NAVEGADORES_COOKIES else None
    if navegador is None:
        return _descargar_con_libreria(url, carpeta_destino,
                                       progreso, None)
    try:
        return _descargar_con_libreria(url, carpeta_destino,
                                       progreso, navegador)
    except ErrorDescarga as error:
        if error.codigo != "cookies":
            raise
        # Las cookies no sirvieron (sin sesión, navegador cerrado con
        # llave...): un intento sin ellas, que basta para la mayoría
        # de videos.
        log.warning("las cookies de %s fallaron; reintentando "
                    "sin cookies", navegador)
        return _descargar_con_libreria(url, carpeta_destino,
                                       progreso, None)
