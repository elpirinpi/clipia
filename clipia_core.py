# -*- coding: utf-8 -*-
"""
ClipIA - núcleo (fachada compatible).

El código vive en el paquete clipia/ (Fase 0); este módulo re-exporta
todo para no romper main.py, test_pipeline.py ni los tests existentes.
"""
import subprocess  # noqa: F401  (lo usan los tests: core.subprocess)

from clipia.descarga import descargar_youtube
from clipia.exportacion import (exportar_clip, generar_miniatura,
                                generar_vista_previa)
from clipia.momentos import (DURACIONES_VENTANA, PALABRAS_GANCHO,
                             _frases_de_segmentos, _puntuar_ventana,
                             _traslapan, detectar_momentos)
from clipia.rostros import _expresion_rostros, detectar_rostros
from clipia.subtitulos import (PLANTILLA_ASS, _escapar_ruta_subtitulos,
                               _fragmentos_subtitulo,
                               generar_subtitulos_ass)
from clipia.transcripcion import (_elegir_dispositivo, _extraer_audio_wav,
                                  _leer_wav_numpy, transcribir)
from clipia.utilidades import formato_ass, formato_hora, obtener_duracion

__all__ = [
    "DURACIONES_VENTANA",
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
    "detectar_momentos",
    "detectar_rostros",
    "exportar_clip",
    "formato_ass",
    "formato_hora",
    "generar_miniatura",
    "generar_subtitulos_ass",
    "generar_vista_previa",
    "obtener_duracion",
    "transcribir",
]
