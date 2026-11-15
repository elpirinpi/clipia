"""Exportación de clips verticales con ffmpeg."""
import os
import shutil
import subprocess
import tempfile
import threading
from collections.abc import Callable

from .encoder import detectar_encoder, opciones_encoder
from .procesos import olvidar, registrar
from .rostros import _expresion_rostros


class ExportacionCancelada(Exception):
    """La exportación se canceló (el usuario pulsó Cancelar o la app
    se está cerrando). El archivo parcial ya se borró."""


def _vigilar_cancelacion(proceso: subprocess.Popen,
                         cancelar: threading.Event | None) -> None:
    """Hilo que mata el ffmpeg si se marca `cancelar`.

    Hace falta un hilo aparte porque el bucle que lee el avance puede
    quedarse bloqueado esperando la siguiente línea: sin él, la
    cancelación tardaría en notarse. Con él, el proceso muere en
    cuanto se marca el evento (mucho menos de 2 s).
    """
    if cancelar is None:
        return

    def vigilar() -> None:
        # Espera el evento sin bloquear para siempre: si el proceso
        # termina solo, el hilo termina también (no se acumulan hilos
        # esperando en exportaciones ya terminadas).
        while proceso.poll() is None:
            if cancelar.wait(timeout=0.2):
                if proceso.poll() is None:
                    try:
                        proceso.kill()
                    except OSError:
                        pass
                return

    threading.Thread(target=vigilar, daemon=True).start()


def exportar_clip(ruta_video: str, inicio: float, fin: float,
                  ruta_ass: str | None, ruta_salida: str,
                  progreso: Callable[[float], None] | None = None,
                  rostros: list[tuple[float, float]] | None = None,
                  ancho: int = 1080, alto: int = 1920,
                  con_subtitulos: bool = True,
                  encoder: str | None = None,
                  cancelar: threading.Event | None = None) -> str:
    """Exporta un clip vertical con subtítulos quemados.

    `progreso` es una función opcional que recibe un valor 0.0-1.0.
    `rostros` es la lista de (t, x) de detectar_rostros: si se da, el
    recorte vertical sigue la cara en vez de centrarse. `ancho`/`alto`
    son el tamaño de salida (1080x1920 por defecto). `encoder` es el
    codificador concreto (p. ej. "h264_nvenc"); con None se autodetecta
    el mejor disponible (hardware o libx264). Si `cancelar` (un
    threading.Event) se marca durante la exportación, se mata el
    ffmpeg, se borra el archivo parcial y se lanza
    ExportacionCancelada. Devuelve la ruta del clip exportado.
    """
    duracion = max(0.1, fin - inicio)
    encoder_usado = encoder or detectar_encoder("auto")
    # Rutas absolutas: la exportación puede cambiar el cwd (ver B9).
    ruta_video = os.path.abspath(ruta_video)
    ruta_salida = os.path.abspath(ruta_salida)
    expresion = _expresion_rostros(rostros, ancho) if rostros else None
    if expresion:
        recorte = "crop=%d:%d:x='%s'" % (ancho, alto, expresion)
    else:
        recorte = "crop=%d:%d" % (ancho, alto)
    filtro = ("scale=%d:%d:force_original_aspect_ratio=increase,%s"
              % (ancho, alto, recorte))
    # B9: el ASS se copia a un cwd temporal con nombre relativo simple:
    # así el filtro subtitles no necesita escapar comas, corchetes ni
    # dos puntos de la ruta real (el escapado era frágil).
    tmp_ass = None
    if con_subtitulos and ruta_ass:
        tmp_ass = tempfile.TemporaryDirectory(prefix="clipia_ass_")
        shutil.copyfile(ruta_ass, os.path.join(tmp_ass.name, "subs.ass"))
        filtro += ",subtitles='subs.ass'"
    comando = [
        "ffmpeg", "-y", "-v", "error",
        "-ss", "%.3f" % inicio,
        "-t", "%.3f" % duracion,
        "-i", ruta_video,
        "-vf", filtro,
        # B9: fijar el primer video y el primer audio; en videos
        # multipista ffmpeg elegía otro audio. La "?" hace el audio
        # opcional (videos sin pista de audio).
        "-map", "0:v:0", "-map", "0:a:0?",
        *opciones_encoder(encoder_usado),
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        "-progress", "pipe:1", "-nostats",
        ruta_salida,
    ]
    # Los mensajes de ffmpeg van por el MISMO tubo que el avance: si
    # fueran por un tubo aparte que nadie lee, en Windows ese tubo se
    # llena (unos 4 KB) y ffmpeg se queda esperando para siempre, con
    # la barra congelada y la exportación sin terminar.
    proceso = None
    try:
        proceso = registrar(subprocess.Popen(
            comando, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, cwd=tmp_ass.name if tmp_ass else None,
        ))
        _vigilar_cancelacion(proceso, cancelar)
        cola_error = ""
        if proceso.stdout is not None:
            for linea in proceso.stdout:
                cola_error = (cola_error + linea)[-4000:]
                linea = linea.strip()
                if linea.startswith("out_time_ms="):
                    try:
                        ms = int(linea.split("=", 1)[1])
                        if progreso:
                            progreso(min(1.0, (ms / 1_000_000) / duracion))
                    except ValueError:
                        pass
                elif linea.startswith("progress=end") and progreso:
                    progreso(1.0)
        proceso.wait()
        if cancelar is not None and cancelar.is_set():
            # El usuario canceló: borrar el parcial y avisar con la
            # excepción propia (no es un error de ffmpeg).
            try:
                if os.path.exists(ruta_salida):
                    os.remove(ruta_salida)
            except OSError:
                pass
            raise ExportacionCancelada("exportación cancelada")
        if proceso.returncode != 0:
            raise RuntimeError("ffmpeg falló al exportar el clip:\n%s"
                               % cola_error.strip()[-2000:])
    finally:
        if proceso is not None:
            olvidar(proceso)
        if tmp_ass is not None:
            tmp_ass.cleanup()
    if progreso:
        progreso(1.0)
    return ruta_salida


def generar_miniatura(ruta_video: str, instante: float, ruta_salida: str,
                      ancho: int = 135, alto: int = 240) -> str:
    """Guarda un fotograma vertical (9:16) del `instante` como imagen."""
    filtro = ("scale=1080:1920:force_original_aspect_ratio=increase,"
              "crop=1080:1920,scale=%d:%d" % (ancho, alto))
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-ss", "%.3f" % instante,
         "-i", ruta_video, "-frames:v", "1", "-vf", filtro, ruta_salida],
        check=True)
    return ruta_salida


def generar_vista_previa(ruta_video: str, inicio: float, fin: float,
                         ruta_salida: str,
                         rostros: list[tuple[float, float]] | None = None,
                         progreso: Callable[[float], None] | None = None,
                         encoder: str | None = None,
                         cancelar: threading.Event | None = None) -> str:
    """Genera una vista previa rápida (540x960, sin subtítulos)."""
    return exportar_clip(ruta_video, inicio, fin, None, ruta_salida,
                         progreso=progreso, rostros=rostros,
                         ancho=540, alto=960, con_subtitulos=False,
                         encoder=encoder, cancelar=cancelar)
