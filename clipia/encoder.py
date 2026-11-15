"""Detección del codificador de video por hardware (NVENC/QSV/AMF).

La autodetección prueba cada codificador con una codificación real de
1 segundo usando las MISMAS opciones que la exportación: así, si un
preset no existe en el ffmpeg instalado, la prueba falla y se cae al
siguiente candidato en vez de romper la exportación. Sin hardware
compatible (o si ffmpeg no trae el codificador), siempre se usa
libx264: la exportación nunca depende de que haya GPU.
"""
import subprocess

ENCODER_CPU = "libx264"
ENCODERS_HW = ["h264_nvenc", "h264_qsv", "h264_amf"]
TODOS_ENCODERS = ENCODERS_HW + [ENCODER_CPU]

_OPCIONES = {
    # libx264: lo que usaba ClipIA desde la v1.0.0.
    "libx264": ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23"],
    # NVENC (NVIDIA): preset p4 (equivalente a "medium" en calidad) y
    # calidad constante 23, comparable al crf 23 de libx264.
    "h264_nvenc": ["-c:v", "h264_nvenc", "-preset", "p4", "-cq", "23"],
    # Quick Sync (Intel): calidad global 23, comparable al crf 23.
    "h264_qsv": ["-c:v", "h264_qsv", "-preset", "medium",
                 "-global_quality", "23"],
    # AMF (AMD): calidad equilibrada, QP 23 en fotogramas I y P.
    "h264_amf": ["-c:v", "h264_amf", "-quality", "balanced",
                 "-qp_i", "23", "-qp_p", "23"],
}

_DESCRIPCIONES = {
    "libx264": "libx264 (CPU)",
    "h264_nvenc": "NVENC (GPU NVIDIA)",
    "h264_qsv": "Quick Sync (GPU Intel)",
    "h264_amf": "AMF (GPU AMD)",
}

# Caché por preferencia: la prueba tarda ~1 s y el hardware no cambia
# mientras la app está abierta.
_cache: dict[str, str] = {}


def opciones_encoder(encoder: str) -> list[str]:
    """Argumentos ffmpeg del codificador (sin el formato de píxel)."""
    if encoder not in _OPCIONES:
        raise ValueError("codificador desconocido: %s" % encoder)
    return list(_OPCIONES[encoder])


def descripcion_encoder(encoder: str) -> str:
    """Nombre legible del codificador para la interfaz."""
    return _DESCRIPCIONES.get(encoder, encoder)


def _probar_encoder(encoder: str, timeout: int = 20) -> bool:
    """True si ffmpeg puede codificar 1 s con `encoder`.

    Usa las mismas opciones que la exportación real, con un video
    generado (testsrc) y salida nula: no escribe ningún archivo.
    """
    try:
        opciones = opciones_encoder(encoder)
    except ValueError:
        return False
    comando = [
        "ffmpeg", "-v", "error", "-nostdin",
        "-f", "lavfi", "-i", "testsrc=duration=1:size=320x240:rate=30",
        *opciones, "-pix_fmt", "yuv420p", "-f", "null", "-",
    ]
    try:
        resultado = subprocess.run(comando, capture_output=True,
                                   timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return resultado.returncode == 0


def detectar_encoder(preferencia: str = "auto") -> str:
    """Devuelve el codificador concreto que se debe usar.

    `preferencia` puede ser "auto" (prueba NVENC, QSV, AMF y luego
    libx264) o un codificador concreto; si el preferido falla la
    prueba, se cae a los siguientes y en último caso a libx264.
    El resultado se cachea por preferencia.
    """
    if preferencia in _cache:
        return _cache[preferencia]
    candidatos = []
    if preferencia in TODOS_ENCODERS:
        candidatos.append(preferencia)
    candidatos.extend(e for e in ENCODERS_HW if e not in candidatos)
    if ENCODER_CPU not in candidatos:
        candidatos.append(ENCODER_CPU)
    elegido = ENCODER_CPU
    for candidato in candidatos:
        if candidato == ENCODER_CPU:
            # libx264 es el respaldo final: no se prueba (si ffmpeg no
            # pudiera codificar con él, la exportación informaría el
            # error real).
            elegido = ENCODER_CPU
            break
        if _probar_encoder(candidato):
            elegido = candidato
            break
    _cache[preferencia] = elegido
    return elegido


def limpiar_cache_deteccion() -> None:
    """Olvida los resultados cacheados (solo para tests)."""
    _cache.clear()
