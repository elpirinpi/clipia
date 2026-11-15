"""Descarga de YouTube con yt-dlp (máximo 1080p).

Fase 4: cookies del navegador (anti-bot) opcionales y errores
accionables: cada fallo de yt-dlp se traduce a un mensaje en español
que dice qué hacer (iniciar sesión en YouTube, actualizar yt-dlp,
revisar la conexión...), en vez del texto técnico de yt-dlp.

Actualización de yt-dlp: en modo dev/venv se actualiza con pip; en
el instalador (PyInstaller) la librería empaquetada NO se puede
actualizar con pip, así que la app descarga el binario standalone
oficial (yt-dlp.exe, ~23 MB) y lo prefiere sobre la librería cuando
existe. El binario se auto-actualiza con `yt-dlp -U`.
"""
import logging
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from collections.abc import Callable

from .procesos import ejecutar, olvidar, registrar

log = logging.getLogger("clipia.descarga")

# Navegadores de los que yt-dlp puede leer las cookies de YouTube
# (anti-bot): el usuario debe tener sesión iniciada en YouTube en
# ese navegador. yt-dlp admite más, pero estos tres son los que
# cubren casi todos los PCs con Windows.
NAVEGADORES_COOKIES = ("chrome", "edge", "firefox")

FORMATO_VIDEO = ("bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/"
                 "bestvideo[height<=1080]+bestaudio/"
                 "best[height<=1080]/best")

# Binario standalone oficial de yt-dlp para Windows (el que usa el
# instalador: la librería empaquetada no se puede actualizar con
# pip). "latest" redirige al último release (~23 MB, verificado
# 13-11-2026: 200 OK, 23.575.744 bytes).
URL_YTDLP_EXE = ("https://github.com/yt-dlp/yt-dlp/releases/latest/"
                 "download/yt-dlp.exe")
# Tamaño mínimo aceptable del binario descargado (el real pesa
# ~23 MB; por debajo de 1 MB es un error de descarga o una página).
_TAMANO_MINIMO_YTDLP_EXE = 1_000_000

# Línea de avance de yt-dlp en modo CLI: "[download]  45.2% of ...".
_RE_AVANCE = re.compile(r"\[download\]\s+(\d+(?:\.\d+)?)%")

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


# --- Binario externo de yt-dlp (instalador) ------------------------------

def esta_congelado() -> bool:
    """True si la app corre empaquetada con PyInstaller (instalador)
    en vez de desde el código fuente."""
    return bool(getattr(sys, "frozen", False))


def carpeta_bin_yt_dlp() -> str:
    """Carpeta de los binarios de ClipIA: %LOCALAPPDATA%/ClipIA/bin
    en Windows (~/.local/share/ClipIA/bin en otros sistemas)."""
    base = os.environ.get("LOCALAPPDATA")
    if base:
        return os.path.join(base, "ClipIA", "bin")
    return os.path.join(os.path.expanduser("~"), ".local", "share",
                        "ClipIA", "bin")


def ruta_ytdlp_externo() -> str | None:
    """Ruta del binario standalone yt-dlp.exe, si existe.

    Solo en Windows: en otros sistemas el .exe no puede ejecutarse.
    Se busca junto al ejecutable de la app (instalador) y en la
    carpeta de binarios de ClipIA (donde lo deja «Actualizar yt-dlp»).
    """
    if os.name != "nt":
        return None
    candidatos = []
    if esta_congelado():
        candidatos.append(
            os.path.join(os.path.dirname(sys.executable), "yt-dlp.exe"))
    candidatos.append(os.path.join(carpeta_bin_yt_dlp(), "yt-dlp.exe"))
    for ruta in candidatos:
        if os.path.isfile(ruta):
            return ruta
    return None


def version_ytdlp() -> str | None:
    """Versión de yt-dlp en uso (del binario externo si existe; si
    no, de la librería). None si no se puede saber."""
    exe = ruta_ytdlp_externo()
    if exe:
        try:
            resultado = ejecutar([exe, "--version"], timeout=15,
                                 capture_output=True, text=True)
            if resultado.returncode == 0 and resultado.stdout:
                return resultado.stdout.strip().splitlines()[0].strip()
        except (OSError, subprocess.SubprocessError):
            pass
        return None
    try:
        import yt_dlp

        return yt_dlp.version.__version__
    except (ImportError, AttributeError):
        return None


def _descargar_ytdlp_exe(progreso: Callable[[float], None] | None = None,
                         timeout: int = 300) -> str:
    """Descarga el binario standalone yt-dlp.exe a la carpeta de
    binarios (escritura atómica). Verifica que sea un ejecutable
    Windows ("MZ") de tamaño razonable. Devuelve su ruta."""
    carpeta = carpeta_bin_yt_dlp()
    os.makedirs(carpeta, exist_ok=True)
    destino = os.path.join(carpeta, "yt-dlp.exe")
    tmp = destino + ".tmp"
    try:
        peticion = urllib.request.Request(
            URL_YTDLP_EXE, headers={"User-Agent": "ClipIA"})
        with urllib.request.urlopen(peticion,
                                    timeout=timeout) as respuesta:
            total = int(respuesta.headers.get("Content-Length") or 0)
            descargado = 0
            with open(tmp, "wb") as archivo:
                while True:
                    bloque = respuesta.read(65536)
                    if not bloque:
                        break
                    archivo.write(bloque)
                    descargado += len(bloque)
                    if progreso and total:
                        progreso(min(1.0, descargado / total))
    except (OSError, urllib.error.URLError, ValueError) as error:
        log.warning("no se pudo descargar yt-dlp.exe (%s)", error)
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise RuntimeError("No se pudo descargar yt-dlp. Revisa tu "
                           "conexión a internet y reintenta.") from error
    try:
        with open(tmp, "rb") as archivo:
            cabecera = archivo.read(2)
        tamano = os.path.getsize(tmp)
    except OSError as error:
        raise RuntimeError("No se pudo descargar yt-dlp. Revisa tu "
                           "conexión a internet y reintenta.") from error
    if cabecera != b"MZ" or tamano < _TAMANO_MINIMO_YTDLP_EXE:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise RuntimeError("La descarga de yt-dlp no es válida "
                           "(archivo corrupto o incompleto). Reintenta.")
    os.replace(tmp, destino)
    if progreso:
        progreso(1.0)
    return destino


def actualizar_ytdlp(progreso: Callable[[float], None] | None = None
                     ) -> str:
    """Actualiza yt-dlp y devuelve la versión nueva.

    En el instalador: si ya existe el binario externo, lo
    auto-actualiza (`yt-dlp -U`); si no, lo descarga. En modo
    dev/venv: `pip install --upgrade yt-dlp` (la versión nueva se
    usa al reiniciar la app, porque este proceso ya cargó la vieja).
    Lanza RuntimeError con un mensaje accionable si falla.
    """
    if esta_congelado():
        exe = ruta_ytdlp_externo()
        if exe:
            resultado = ejecutar([exe, "-U"], timeout=300,
                                 capture_output=True, text=True)
            if resultado.returncode != 0:
                raise RuntimeError("No se pudo actualizar yt-dlp. "
                                   "Revisa tu conexión a internet y "
                                   "reintenta.")
        else:
            _descargar_ytdlp_exe(progreso)
    else:
        resultado = ejecutar(
            [sys.executable, "-m", "pip", "install", "--upgrade",
             "yt-dlp"],
            timeout=300, capture_output=True, text=True)
        if resultado.returncode != 0:
            raise RuntimeError("No se pudo actualizar yt-dlp con pip. "
                               "Revisa tu conexión a internet y "
                               "reintenta.")
        # La versión nueva se lee en un proceso aparte: este proceso
        # ya tiene cargada (o cargará) la versión vieja.
        resultado = ejecutar(
            [sys.executable, "-c",
             "import yt_dlp; print(yt_dlp.version.__version__)"],
            timeout=60, capture_output=True, text=True)
        if resultado.returncode == 0 and resultado.stdout:
            return resultado.stdout.strip().splitlines()[0].strip()
        raise RuntimeError("yt-dlp se actualizó, pero no se pudo "
                           "confirmar la versión nueva. Reinicia la app.")
    version = version_ytdlp()
    if not version:
        raise RuntimeError("yt-dlp se actualizó, pero no se pudo "
                           "confirmar la versión nueva. Reinicia la app.")
    return version


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


def _descargar_con_binario(exe: str, url: str, carpeta_destino: str,
                           progreso: Callable[[float], None] | None,
                           navegador: str | None) -> str:
    """Descarga con el binario standalone yt-dlp.exe (instalador).

    Mismas opciones que la librería. El avance se lee de las líneas
    "[download] NN%"; la ruta final se pide con --print-to-file
    (equivalente a requested_downloads: tras el merge). La salida de
    error va por el MISMO tubo que el avance (v1.1.3): un tubo aparte
    sin leer se llena en Windows y congela el proceso.
    """
    os.makedirs(carpeta_destino, exist_ok=True)
    descriptor, ruta_tmp = tempfile.mkstemp(
        prefix="clipia_ruta_", suffix=".txt", dir=carpeta_destino)
    os.close(descriptor)
    comando = [exe,
               "--format", FORMATO_VIDEO,
               "--merge-output-format", "mp4",
               "--no-playlist",
               "--restrict-filenames",
               "-o", os.path.join(carpeta_destino, "%(title)s.%(ext)s"),
               "--no-warnings",
               "--newline", "--progress",
               "--print-to-file", "after_move:filepath", ruta_tmp]
    if navegador:
        comando += ["--cookies-from-browser", navegador]
    comando.append(url)
    proceso = None
    cola_error = ""
    try:
        proceso = registrar(subprocess.Popen(
            comando, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True))
        if proceso.stdout is not None:
            for linea in proceso.stdout:
                cola_error = (cola_error + linea)[-4000:]
                coincidencia = _RE_AVANCE.search(linea)
                if coincidencia and progreso:
                    try:
                        progreso(min(1.0, float(coincidencia.group(1))
                                     / 100.0))
                    except ValueError:
                        pass
        proceso.wait()
    except OSError as error:
        raise _error_descarga(error) from error
    finally:
        if proceso is not None:
            olvidar(proceso)
    if proceso.returncode != 0:
        raise _error_descarga(RuntimeError(
            cola_error.strip()
            or "yt-dlp terminó con código %d" % proceso.returncode))
    ruta = None
    try:
        with open(ruta_tmp, encoding="utf-8") as archivo:
            ruta = archivo.read().strip()
    except OSError:
        pass
    finally:
        try:
            os.remove(ruta_tmp)
        except OSError:
            pass
    if ruta and os.path.isfile(ruta):
        if progreso:
            progreso(1.0)
        return ruta
    # Respaldo: el mp4 más reciente de la carpeta (por si el
    # --print-to-file no dejó la ruta).
    try:
        mp4s = [os.path.join(carpeta_destino, nombre)
                for nombre in os.listdir(carpeta_destino)
                if nombre.lower().endswith(".mp4")]
    except OSError:
        mp4s = []
    if mp4s:
        reciente = max(mp4s, key=os.path.getmtime)
        if progreso:
            progreso(1.0)
        return reciente
    raise ErrorDescarga(
        "yt-dlp terminó sin dejar el archivo descargado. Reintenta; "
        "si sigue pasando, descarga el video con el navegador y usa "
        "el archivo local.", "otro")


def _descargar(url: str, carpeta_destino: str,
               progreso: Callable[[float], None] | None,
               navegador: str | None) -> str:
    """Descarga con el binario externo si existe; si no, con la
    librería yt_dlp."""
    exe = ruta_ytdlp_externo()
    if exe:
        log.info("descargando con el binario externo de yt-dlp")
        return _descargar_con_binario(exe, url, carpeta_destino,
                                      progreso, navegador)
    return _descargar_con_libreria(url, carpeta_destino, progreso,
                                   navegador)


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
        return _descargar(url, carpeta_destino, progreso, None)
    try:
        return _descargar(url, carpeta_destino, progreso, navegador)
    except ErrorDescarga as error:
        if error.codigo != "cookies":
            raise
        # Las cookies no sirvieron (sin sesión, navegador cerrado con
        # llave...): un intento sin ellas, que basta para la mayoría
        # de videos.
        log.warning("las cookies de %s fallaron; reintentando "
                    "sin cookies", navegador)
        return _descargar(url, carpeta_destino, progreso, None)
