# -*- coding: utf-8 -*-
"""Utilidades de ClipIA: formatos de tiempo y duración de video."""
import subprocess


def formato_hora(segundos):
    """Convierte segundos a 'M:SS' (ej. 52 -> '0:52')."""
    segundos = max(0, int(round(segundos)))
    return "%d:%02d" % (segundos // 60, segundos % 60)


def formato_ass(segundos):
    """Convierte segundos a formato de tiempo ASS 'H:MM:SS.cc'."""
    segundos = max(0.0, float(segundos))
    h = int(segundos // 3600)
    m = int((segundos % 3600) // 60)
    s = int(segundos % 60)
    cs = int(round((segundos - int(segundos)) * 100))
    if cs == 100:
        s += 1
        cs = 0
    return "%d:%02d:%02d.%02d" % (h, m, s, cs)


def obtener_duracion(ruta_video):
    """Duración en segundos de un video, usando ffprobe.

    B8: algunos MKV/WebM devuelven format=duration "N/A" y el float()
    reventaba; en ese caso se usa la duración del primer flujo de video.
    """
    resultado = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", ruta_video],
        capture_output=True, text=True, timeout=60,
    )
    if resultado.returncode != 0:
        raise RuntimeError("ffprobe no pudo leer el video: %s"
                           % resultado.stderr.strip())
    try:
        return float(resultado.stdout.strip())
    except ValueError:
        pass
    # Fallback: duración del primer flujo de video.
    resultado = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", ruta_video],
        capture_output=True, text=True, timeout=60,
    )
    if resultado.returncode != 0:
        raise RuntimeError("ffprobe no pudo leer el video: %s"
                           % resultado.stderr.strip())
    try:
        return float(resultado.stdout.strip())
    except ValueError:
        pass
    raise RuntimeError("ffprobe no pudo determinar la duración de: %s"
                       % ruta_video)
