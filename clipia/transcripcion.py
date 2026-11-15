"""Transcripción con faster-whisper (español, timestamps por palabra).

El modelo se cachea en memoria (singleton por modelo/dispositivo): la
primera transcripción tarda unos segundos en cargarlo y las siguientes
reutilizan la misma instancia. La transcripción usa
BatchedInferencePipeline, que procesa varios fragmentos de audio a la
vez: en CPU es ~30% más rápido que el modo normal y en GPU mucho más.

Fase 4: el modelo se descarga en el primer uso con progreso visible
(gancho de Hugging Face) y con un mensaje claro si no hay red, en vez
del error técnico de faster-whisper.
"""
import logging
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

log = logging.getLogger("clipia.transcripcion")

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

# Archivos del modelo que descarga faster-whisper (los mismos que
# faster_whisper.utils.download_model pide a Hugging Face).
_PATRONES_MODELO = ["config.json", "preprocessor_config.json",
                    "model.bin", "tokenizer.json", "vocabulary.*"]


class ErrorDescargaModelo(Exception):
    """El modelo de voz no se pudo descargar (sin red, sin espacio...).
    El mensaje ya es accionable y se muestra al usuario tal cual."""


def _repo_modelo(modelo: str) -> str:
    """Repositorio de Hugging Face del modelo (el mismo que usa
    faster-whisper: Systran/faster-whisper-<tamaño>)."""
    try:
        from faster_whisper.utils import _MODELS

        repo = _MODELS.get(modelo)
        if repo:
            return repo
    except ImportError:
        pass
    if "/" in modelo:
        return modelo
    return "Systran/faster-whisper-%s" % modelo


class _ProgresoDescarga:
    """Acumulador del avance de la descarga del modelo.

    Hugging Face descarga varios archivos y crea una barra tqdm por
    archivo: este acumulador suma los totales y los avances de todas
    para reportar un único porcentaje global.
    """

    def __init__(self, progreso: Callable[[float], None] | None) -> None:
        self.progreso = progreso
        self.total = 0
        self.descargado = 0

    def nueva_barra(self, total) -> None:
        if total:
            self.total += total

    def avanzar(self, cantidad: int) -> None:
        self.descargado += cantidad
        if self.progreso and self.total:
            self.progreso(min(1.0, self.descargado / self.total))


def _clase_barra(acumulador: _ProgresoDescarga):
    """Fábrica de la clase tqdm que Hugging Face usa para cada
    archivo: cada instancia suma su total al acumulador y reporta
    cada avance. La barra no escribe en consola (disable=True): el
    avance va a la interfaz de la app."""
    from tqdm import tqdm

    class _Barra(tqdm):
        def __init__(self, *args, **kwargs):
            kwargs.setdefault("disable", True)
            super().__init__(*args, **kwargs)
            acumulador.nueva_barra(self.total)

        def update(self, n=1):
            super().update(n)
            acumulador.avanzar(n)

    return _Barra


def descargar_modelo(modelo: str = "base",
                     progreso: Callable[[float], None] | None = None
                     ) -> str:
    """Asegura que el modelo Whisper esté descargado.

    Si ya está en la caché de Hugging Face, devuelve su ruta sin
    descargar nada. Si no, lo descarga con progreso visible
    (0.0-1.0). Sin red, lanza ErrorDescargaModelo con un mensaje
    accionable. Devuelve la ruta local del modelo.
    """
    import huggingface_hub

    repo = _repo_modelo(modelo)
    try:
        # Comprobación local: si está en caché, no hay red ni espera.
        return huggingface_hub.snapshot_download(
            repo, allow_patterns=_PATRONES_MODELO, local_files_only=True)
    except Exception:
        pass  # no está (o está incompleto): descargar
    acumulador = _ProgresoDescarga(progreso)
    try:
        ruta = huggingface_hub.snapshot_download(
            repo, allow_patterns=_PATRONES_MODELO,
            tqdm_class=_clase_barra(acumulador))
    except Exception as error:  # noqa: BLE001 - traducir cualquier error
        log.warning("no se pudo descargar el modelo %s (%s)", modelo,
                    error)
        tamano = MODELOS_WHISPER.get(modelo, {}).get("tamano_mb")
        detalle = (" (~%d MB)" % tamano) if tamano else ""
        raise ErrorDescargaModelo(
            "No se pudo descargar el modelo de voz «%s»%s. Revisa tu "
            "conexión a internet y vuelve a intentarlo."
            % (modelo, detalle)) from error
    if progreso:
        progreso(1.0)
    return ruta


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
                   tipo_calculo: str | None = None,
                   progreso_descarga: Callable[[float], None] | None = None):
    """Devuelve el WhisperModel cacheado (singleton por modelo y
    dispositivo). La primera llamada lo carga (unos segundos); las
    siguientes devuelven la misma instancia. Si el modelo no está
    descargado, se descarga primero (con `progreso_descarga` como
    avance 0.0-1.0); sin red, lanza ErrorDescargaModelo."""
    if dispositivo is None:
        dispositivo, tipo_calculo = _elegir_dispositivo()
    clave = (modelo, dispositivo, tipo_calculo)
    if clave in _MODELOS:
        return _MODELOS[clave]
    # La descarga va FUERA del bloqueo: puede tardar minutos con
    # modelos grandes y no debe bloquear a otros hilos. Si dos hilos
    # la disparan a la vez, la caché de Hugging Face lo resuelve (el
    # segundo encuentra los archivos ya descargados).
    descargar_modelo(modelo, progreso_descarga)
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


def _es_error_vad(error: Exception) -> bool:
    """True si el error parece de la detección de voz (VAD): falta el
    modelo silero_vad_v6.onnx en el paquete instalado (ONNXRuntimeError
    NO_SUCHFILE) o el VAD falló por otro motivo. Sirve para decidir
    si vale la pena reintentar sin VAD."""
    if type(error).__name__ == "ONNXRuntimeError":
        return True
    texto = str(error).lower()
    return "silero" in texto or "vad" in texto or "onnx" in texto


def _transcribir_intento(pipeline, audio: "np.ndarray",
                         idioma_param: str | None, batch_size: int,
                         duracion: float,
                         progreso: Callable[[float], None] | None,
                         usar_vad: bool) -> list[dict]:
    """Un intento de transcripción (con o sin filtro VAD). La llamada
    y el consumo de los segmentos van juntos: el error del VAD puede
    saltar al llamar a transcribe() o al iterar los segmentos."""
    parametros = {
        "language": idioma_param,
        "word_timestamps": True,
        "batch_size": batch_size,
    }
    if usar_vad:
        parametros["vad_filter"] = True
        parametros["vad_parameters"] = {"min_silence_duration_ms": 500}
    else:
        parametros["vad_filter"] = False
    segmentos, _info = pipeline.transcribe(audio, **parametros)
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


def _transcribir_con_modelo(whisper, audio: "np.ndarray",
                            idioma_param: str | None, batch_size: int,
                            duracion: float,
                            progreso: Callable[[float], None] | None
                            ) -> list[dict]:
    """Transcribe con un modelo ya cargado, en lotes (batched).

    Si la detección de voz falla (p. ej. falta silero_vad_v6.onnx
    en el paquete instalado), reintenta UNA vez sin VAD: la
    transcripción sale igual, solo sin ignorar los silencios. Si el
    reintento también falla, el error sube como antes.
    """
    from faster_whisper import BatchedInferencePipeline

    pipeline = BatchedInferencePipeline(whisper)
    try:
        return _transcribir_intento(pipeline, audio, idioma_param,
                                    batch_size, duracion, progreso,
                                    usar_vad=True)
    except Exception as error:  # noqa: BLE001 - decidir si reintentar
        if not _es_error_vad(error):
            raise
        log.warning(
            "la detección de voz (VAD) falló (%s); se transcribe sin "
            "ella", error)
        return _transcribir_intento(pipeline, audio, idioma_param,
                                    batch_size, duracion, progreso,
                                    usar_vad=False)


def transcribir(ruta_video: str, modelo: str = "base", idioma: str = "es",
                progreso: Callable[[float], None] | None = None,
                batch_size: int | None = None,
                usar_cache: bool = True,
                progreso_descarga: Callable[[float], None] | None = None
                ) -> list[dict]:
    """Transcribe el audio de un video.

    Devuelve una lista de segmentos:
      [{"start": float, "end": float, "text": str,
        "words": [{"start": float, "end": float, "word": str}]}]

    `modelo` es tiny/base/small/medium/large-v3 (base por defecto).
    `idioma` es un código ("es") o "auto" para autodetectar.
    `batch_size` es el tamaño de lote (16 en GPU, 8 en CPU por defecto).
    `progreso` es una función opcional que recibe un valor 0.0-1.0.
    `progreso_descarga` es una función opcional que recibe el avance
    de la descarga del modelo en el primer uso (0.0-1.0).
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
    whisper = obtener_modelo(modelo, dispositivo, tipo_calculo,
                             progreso_descarga)

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
                whisper_cpu = obtener_modelo(modelo, "cpu", "int8",
                                             progreso_descarga)
                resultado = _transcribir_con_modelo(
                    whisper_cpu, audio, idioma_param, 8, duracion, progreso)
            else:
                raise
    if clave is not None:
        escribir_cache("transcripcion", clave, {"segmentos": resultado})
    if progreso:
        progreso(1.0)
    return resultado
