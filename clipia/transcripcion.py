"""Transcripción con faster-whisper (español, timestamps por palabra).

El modelo se cachea en memoria (singleton por modelo/dispositivo): la
primera transcripción tarda unos segundos en cargarlo y las siguientes
reutilizan la misma instancia. La transcripción usa
BatchedInferencePipeline, que procesa varios fragmentos de audio a la
vez: en CPU es ~30% más rápido que el modo normal y en GPU mucho más.
"""
import os
import tempfile
import threading
from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np

# Silencia el aviso de huggingface_hub sobre symlinks en Windows: el caché
# funciona igual sin ellos, el aviso solo confunde.
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

from .cache import clave_archivo, escribir_cache, leer_cache
from .procesos import ejecutar
from .utilidades import obtener_duracion

# Modelos Whisper disponibles: tamaño de descarga y RAM aproximada que
# necesitan (el aviso de RAM de los ajustes usa estos valores).
MODELOS_WHISPER: dict[str, dict] = {
    "tiny": {"tamano_mb": 75, "ram_gb": 1,
             "descripcion": "Tiny · ~75 MB · el más rápido"},
    "base": {"tamano_mb": 150, "ram_gb": 1,
             "descripcion": "Base · ~150 MB · equilibrio (recomendado)"},
    "small": {"tamano_mb": 470, "ram_gb": 2,
              "descripcion": "Small · ~470 MB · más preciso"},
    "medium": {"tamano_mb": 1500, "ram_gb": 5,
                "descripcion": "Medium · ~1.5 GB · mucho más preciso"},
    "large-v3": {"tamano_mb": 3100, "ram_gb": 10,
                 "descripcion": "Large v3 · ~3.1 GB · máxima precisión"},
}

# Idiomas del selector (código Whisper, etiqueta). "auto" deja que el
# modelo detecte el idioma del audio.
IDIOMAS: list[tuple[str, str]] = [
    ("es", "Español"),
    ("en", "Inglés"),
    ("pt", "Portugués"),
    ("fr", "Francés"),
    ("it", "Italiano"),
    ("de", "Alemán"),
    ("auto", "Autodetectar"),
]

# Como mucho 2 modelos distintos en memoria a la vez (un large-v3 ya
# ocupa ~3 GB); al cargar un tercero se olvida el más antiguo.
_MAX_MODELOS_CACHEADOS = 2
_MODELOS: dict = {}
_BLOQUEO_MODELOS = threading.Lock()


def ram_total_gb() -> float | None:
    """RAM total del equipo en GB (None si no se puede saber)."""
    try:
        if os.path.exists("/proc/meminfo"):
            with open("/proc/meminfo", encoding="utf-8") as archivo:
                for linea in archivo:
                    if linea.startswith("MemTotal:"):
                        kb = float(linea.split()[1])
                        return kb / 1024 / 1024
        if os.name == "nt":
            import ctypes

            class Memoria(ctypes.Structure):
                _fields_ = [("longitud", ctypes.c_ulong),
                            ("porcentaje", ctypes.c_ulong),
                            ("total_fisica", ctypes.c_ulonglong),
                            ("disp_fisica", ctypes.c_ulonglong),
                            ("total_pagina", ctypes.c_ulonglong),
                            ("disp_pagina", ctypes.c_ulonglong),
                            ("total_virtual", ctypes.c_ulonglong),
                            ("disp_virtual", ctypes.c_ulonglong),
                            ("extendida", ctypes.c_ulonglong)]

            estado = Memoria()
            estado.longitud = ctypes.sizeof(Memoria)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(estado))
            return estado.total_fisica / 1024 / 1024 / 1024
    except Exception:
        pass
    return None


def _elegir_dispositivo() -> tuple[str, str]:
    """Usa la GPU (CUDA) si está disponible; si no, CPU con int8."""
    try:
        from ctranslate2 import get_cuda_device_count
        if get_cuda_device_count() > 0:
            return "cuda", "float16"
    except Exception:
        pass
    return "cpu", "int8"


def _crear_modelo(modelo: str, dispositivo: str, tipo_calculo: str):
    """Crea un WhisperModel; si la GPU falla, reintenta en CPU."""
    from faster_whisper import WhisperModel

    try:
        return WhisperModel(modelo, device=dispositivo,
                            compute_type=tipo_calculo), dispositivo
    except Exception:
        if dispositivo != "cpu":
            return WhisperModel(modelo, device="cpu",
                                compute_type="int8"), "cpu"
        raise


def obtener_modelo(modelo: str = "base", dispositivo: str | None = None,
                   tipo_calculo: str | None = None):
    """Devuelve el WhisperModel cacheado (singleton por modelo y
    dispositivo). La primera llamada lo carga (unos segundos); las
    siguientes devuelven la misma instancia."""
    if dispositivo is None:
        dispositivo, tipo_calculo = _elegir_dispositivo()
    clave = (modelo, dispositivo, tipo_calculo)
    if clave in _MODELOS:
        return _MODELOS[clave]
    with _BLOQUEO_MODELOS:
        if clave in _MODELOS:
            return _MODELOS[clave]
        whisper, dispositivo_real = _crear_modelo(modelo, dispositivo,
                                                  tipo_calculo)
        clave = (modelo, dispositivo_real,
                 tipo_calculo if dispositivo_real == dispositivo else "int8")
        _MODELOS[clave] = whisper
        while len(_MODELOS) > _MAX_MODELOS_CACHEADOS:
            _MODELOS.pop(next(iter(_MODELOS)))
        return whisper


def _olvidar_modelo(modelo: str, dispositivo: str,
                    tipo_calculo: str) -> None:
    """Saca un modelo del caché (p. ej. tras un error de GPU)."""
    with _BLOQUEO_MODELOS:
        _MODELOS.pop((modelo, dispositivo, tipo_calculo), None)


def liberar_modelos() -> None:
    """Vacía el caché de modelos (libera la RAM/VRAM)."""
    with _BLOQUEO_MODELOS:
        _MODELOS.clear()


def _extraer_audio_wav(ruta_video: str, ruta_wav: str) -> None:
    """Extrae el audio a WAV PCM 16 kHz mono con ffmpeg
    (lo que Whisper usa)."""
    ejecutar(
        ["ffmpeg", "-y", "-v", "error", "-i", ruta_video,
         "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", ruta_wav],
        check=True,
    )


def _leer_wav_numpy(ruta_wav: str) -> "np.ndarray":
    """Lee un WAV PCM 16 bits a un arreglo float32 normalizado [-1, 1]."""
    import wave

    import numpy as np

    with wave.open(ruta_wav, "rb") as archivo:
        datos = archivo.readframes(archivo.getnframes())
    return np.frombuffer(datos, dtype=np.int16).astype(np.float32) / 32768.0


def _transcribir_con_modelo(whisper, audio: "np.ndarray",
                            idioma_param: str | None, batch_size: int,
                            duracion: float,
                            progreso: Callable[[float], None] | None
                            ) -> list[dict]:
    """Transcribe con un modelo ya cargado, en lotes (batched)."""
    from faster_whisper import BatchedInferencePipeline

    pipeline = BatchedInferencePipeline(whisper)
    segmentos, _info = pipeline.transcribe(
        audio,
        language=idioma_param,
        word_timestamps=True,
        vad_filter=True,          # ignora silencios largos
        vad_parameters={"min_silence_duration_ms": 500},
        batch_size=batch_size,
    )
    resultado = []
    for seg in segmentos:
        palabras = []
        for palabra in (seg.words or []):
            palabras.append({
                "start": float(palabra.start),
                "end": float(palabra.end),
                "word": palabra.word,
            })
        resultado.append({
            "start": float(seg.start),
            "end": float(seg.end),
            "text": seg.text.strip(),
            "words": palabras,
        })
        if progreso and duracion > 0:
            progreso(min(1.0, float(seg.end) / duracion))
    return resultado


def transcribir(ruta_video: str, modelo: str = "base", idioma: str = "es",
                progreso: Callable[[float], None] | None = None,
                batch_size: int | None = None,
                usar_cache: bool = True) -> list[dict]:
    """Transcribe el audio de un video.

    Devuelve una lista de segmentos:
      [{"start": float, "end": float, "text": str,
        "words": [{"start": float, "end": float, "word": str}]}]

    `modelo` es tiny/base/small/medium/large-v3 (base por defecto).
    `idioma` es un código ("es") o "auto" para autodetectar.
    `batch_size` es el tamaño de lote (16 en GPU, 8 en CPU por defecto).
    `progreso` es una función opcional que recibe un valor 0.0-1.0.
    Con `usar_cache` se reutiliza la transcripción guardada si el video
    no cambió (misma ruta, tamaño y fecha de modificación).
    """
    duracion = obtener_duracion(ruta_video)
    clave = None
    if usar_cache:
        try:
            clave = clave_archivo(ruta_video, version=1, modelo=modelo,
                                  idioma=idioma)
            guardado = leer_cache("transcripcion", clave)
        except OSError:
            guardado = None
        if isinstance(guardado, dict) and isinstance(
                guardado.get("segmentos"), list):
            if progreso:
                progreso(1.0)
            return guardado["segmentos"]
    dispositivo, tipo_calculo = _elegir_dispositivo()
    batch = batch_size or (16 if dispositivo == "cuda" else 8)
    # "auto" (o None) deja que Whisper detecte el idioma del audio.
    idioma_param = None if idioma in (None, "auto") else idioma
    whisper = obtener_modelo(modelo, dispositivo, tipo_calculo)

    # Se extrae el audio con ffmpeg y se pasa como arreglo numpy: así no
    # se depende del decodificador interno de faster-whisper (PyAV), que
    # cambia de API entre versiones y puede fallar según la versión instalada.
    with tempfile.TemporaryDirectory(prefix="clipia_audio_") as carpeta_tmp:
        ruta_wav = os.path.join(carpeta_tmp, "audio.wav")
        _extraer_audio_wav(ruta_video, ruta_wav)
        audio = _leer_wav_numpy(ruta_wav)
        try:
            resultado = _transcribir_con_modelo(
                whisper, audio, idioma_param, batch, duracion, progreso)
        except Exception:
            # Si la GPU falla a mitad (p. ej. sin VRAM), reintentar en
            # CPU con el mismo audio; si la CPU también falla, el error
            # sube tal cual.
            if dispositivo != "cpu":
                _olvidar_modelo(modelo, dispositivo, tipo_calculo)
                whisper_cpu = obtener_modelo(modelo, "cpu", "int8")
                resultado = _transcribir_con_modelo(
                    whisper_cpu, audio, idioma_param, 8, duracion, progreso)
            else:
                raise
    if clave is not None:
        escribir_cache("transcripcion", clave, {"segmentos": resultado})
    if progreso:
        progreso(1.0)
    return resultado
