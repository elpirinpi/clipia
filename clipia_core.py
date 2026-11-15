"""
ClipIA - núcleo (fachada compatible).

El código vive en el paquete clipia/ (Fase 0); este módulo re-exporta
todo para no romper main.py, test_pipeline.py ni los tests existentes.
"""
import subprocess  # noqa: F401  (lo usan los tests: core.subprocess)

from clipia.cache import (
                                carpeta_cache,
                                clave_archivo,
                                escribir_cache,
                                leer_cache,
)
from clipia.cola import (
                                ColaExportacion,
                                ResultadoClip,
                                TrabajoExportacion,
                                workers_efectivos,
                                workers_recomendados,
)
from clipia.descarga import (
    NAVEGADORES_COOKIES,
    ErrorDescarga,
    actualizar_ytdlp,
    clasificar_error_descarga,
    descargar_youtube,
    esta_congelado,
    mensaje_error_descarga,
    ruta_ytdlp_externo,
    version_ytdlp,
)
from clipia.encoder import (
                                descripcion_encoder,
                                detectar_encoder,
                                opciones_encoder,
)
from clipia.exportacion import (
                                ExportacionCancelada,
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
from clipia.ollama import (
                                INSTRUCCIONES_INSTALACION,
                                INSTRUCCIONES_MODELO,
                                MODELO_DEFECTO,
                                modelo_disponible,
                                ollama_disponible,
                                rerank_ollama,
)
from clipia.procesos import (
                                contar,
                                ejecutar,
                                matar_todos,
                                olvidar,
                                registrar,
)
from clipia.rostros import (
    _expresion_rostros,
    detectar_rostros,
    detectar_rostros_con_limite,
)
from clipia.subtitulos import (
                                ESTILO_DEFECTO,
                                PLANTILLA_ASS,
                                PRESETS_SUBTITULOS,
                                _escapar_ruta_subtitulos,
                                _fragmentos_subtitulo,
                                generar_subtitulos_ass,
)
from clipia.transcripcion import (
                                IDIOMAS,
                                MODELOS_WHISPER,
                                ErrorDescargaModelo,
                                _elegir_dispositivo,
                                _extraer_audio_wav,
                                _leer_wav_numpy,
                                descargar_modelo,
                                liberar_modelos,
                                obtener_modelo,
                                ram_total_gb,
                                transcribir,
)
from clipia.utilidades import (
                                formato_ass,
                                formato_hora,
                                obtener_duracion,
                                tiene_audio,
)

__all__ = [
    "DURACIONES_VENTANA",
    "ESTILO_DEFECTO",
    "IDIOMAS",
    "INSTRUCCIONES_INSTALACION",
    "INSTRUCCIONES_MODELO",
    "MODELO_DEFECTO",
    "MODELOS_WHISPER",
    "NAVEGADORES_COOKIES",
    "PALABRAS_GANCHO",
    "PLANTILLA_ASS",
    "PRESETS_SUBTITULOS",
    "ColaExportacion",
    "ErrorDescarga",
    "ErrorDescargaModelo",
    "ExportacionCancelada",
    "ResultadoClip",
    "TrabajoExportacion",
    "_elegir_dispositivo",
    "_escapar_ruta_subtitulos",
    "_expresion_rostros",
    "_extraer_audio_wav",
    "_fragmentos_subtitulo",
    "_frases_de_segmentos",
    "_leer_wav_numpy",
    "_puntuar_ventana",
    "_traslapan",
    "actualizar_ytdlp",
    "carpeta_cache",
    "clasificar_error_descarga",
    "clave_archivo",
    "contar",
    "descargar_modelo",
    "descargar_youtube",
    "descripcion_encoder",
    "detectar_encoder",
    "detectar_momentos",
    "detectar_rostros",
    "detectar_rostros_con_limite",
    "ejecutar",
    "escribir_cache",
    "esta_congelado",
    "exportar_clip",
    "formato_ass",
    "formato_hora",
    "generar_miniatura",
    "generar_subtitulos_ass",
    "generar_vista_previa",
    "leer_cache",
    "liberar_modelos",
    "matar_todos",
    "mensaje_error_descarga",
    "modelo_disponible",
    "obtener_duracion",
    "obtener_modelo",
    "ollama_disponible",
    "olvidar",
    "opciones_encoder",
    "ram_total_gb",
    "registrar",
    "rerank_ollama",
    "ruta_ytdlp_externo",
    "tiene_audio",
    "transcribir",
    "version_ytdlp",
    "workers_efectivos",
    "workers_recomendados",
]
