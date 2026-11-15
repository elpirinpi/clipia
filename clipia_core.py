"""
ClipIA - núcleo (fachada compatible).

El código vive en el paquete clipia/ (Fase 0); este módulo re-exporta
todo para no romper main.py, test_pipeline.py ni los tests existentes.
"""
import subprocess  # noqa: F401  (lo usan los tests: core.subprocess)

from clipia.descarga import descargar_youtube
from clipia.encoder import (
                                descripcion_encoder,
                                detectar_encoder,
                                opciones_encoder,
)
from clipia.exportacion import (
                                exportar_clip,
                                generar_miniatura,
                                generar_vista_previa,
)
from clipia.momentos import (
                                DURACIONES_VENTANA,
                                PALABRAS_GANCHO,
                                _frases_de_segmentos,
                                _puntuar_ventana,
                                _traslapan,
                                detectar_momentos,
)
from clipia.rostros import _expresion_rostros, detectar_rostros
from clipia.subtitulos import (
                                PLANTILLA_ASS,
                                _escapar_ruta_subtitulos,
                                _fragmentos_subtitulo,
                                generar_subtitulos_ass,
)
from clipia.transcripcion import (
                                IDIOMAS,
                                MODELOS_WHISPER,
                                _elegir_dispositivo,
                                _extraer_audio_wav,
                                _leer_wav_numpy,
                                liberar_modelos,
                                obtener_modelo,
                                ram_total_gb,
                                transcribir,
)
from clipia.utilidades import formato_ass, formato_hora, obtener_duracion

__all__ = [
    "DURACIONES_VENTANA",
    "IDIOMAS",
    "MODELOS_WHISPER",
    "PALABRAS_GANCHO",
    "PLANTILLA_ASS",
    "_elegir_dispositivo",
    "_escapar_ruta_subtitulos",
    "_expresion_rostros",
    "_extraer_audio_wav",
    "_fragmentos_subtitulo",
    "_frases_de_segmentos",
    "_leer_wav_numpy",
    "_puntuar_ventana",
    "_traslapan",
    "descargar_youtube",
    "descripcion_encoder",
    "detectar_encoder",
    "detectar_momentos",
    "detectar_rostros",
    "exportar_clip",
    "formato_ass",
    "formato_hora",
    "generar_miniatura",
    "generar_subtitulos_ass",
    "generar_vista_previa",
    "liberar_modelos",
    "obtener_duracion",
    "obtener_modelo",
    "opciones_encoder",
    "ram_total_gb",
    "transcribir",
]
