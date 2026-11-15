"""Transcripción con faster-whisper (español, timestamps por palabra)."""
import os
import subprocess
import tempfile
from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np

# Silencia el aviso de huggingface_hub sobre symlinks en Windows: el caché
# funciona igual sin ellos, el aviso solo confunde.
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

from .utilidades import obtener_duracion


def _elegir_dispositivo() -> tuple[str, str]:
    """Usa la GPU (CUDA) si está disponible; si no, CPU con int8."""
    try:
        from ctranslate2 import get_cuda_device_count
        if get_cuda_device_count() > 0:
            return "cuda", "float16"
    except Exception:
        pass
    return "cpu", "int8"


def _extraer_audio_wav(ruta_video: str, ruta_wav: str) -> None:
    """Extrae el audio a WAV PCM 16 kHz mono con ffmpeg
    (lo que Whisper usa)."""
    subprocess.run(
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


def transcribir(ruta_video: str, modelo: str = "base", idioma: str = "es",
                  progreso: Callable[[float], None] | None = None
                  ) -> list[dict]:
    """Transcribe el audio de un video.

    Devuelve una lista de segmentos:
      [{"start": float, "end": float, "text": str,
        "words": [{"start": float, "end": float, "word": str}]}]

    `progreso` es una función opcional que recibe un valor 0.0-1.0.
    """
    from faster_whisper import WhisperModel

    duracion = obtener_duracion(ruta_video)
    dispositivo, tipo_calculo = _elegir_dispositivo()
    try:
        whisper = WhisperModel(modelo, device=dispositivo,
                               compute_type=tipo_calculo)
    except Exception:
        # Si la GPU falla por cualquier motivo, reintentar en CPU.
        if dispositivo != "cpu":
            whisper = WhisperModel(modelo, device="cpu",
                                   compute_type="int8")
        else:
            raise

    # Se extrae el audio con ffmpeg y se pasa como arreglo numpy: así no
    # se depende del decodificador interno de faster-whisper (PyAV), que
    # cambia de API entre versiones y puede fallar según la versión instalada.
    with tempfile.TemporaryDirectory(prefix="clipia_audio_") as carpeta_tmp:
        ruta_wav = os.path.join(carpeta_tmp, "audio.wav")
        _extraer_audio_wav(ruta_video, ruta_wav)
        audio = _leer_wav_numpy(ruta_wav)

        segmentos, _info = whisper.transcribe(
            audio,
            language=idioma,
            word_timestamps=True,
            vad_filter=True,          # ignora silencios largos
            vad_parameters={"min_silence_duration_ms": 500},
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
    if progreso:
        progreso(1.0)
    return resultado
