"""ClipIA - núcleo dividido en módulos (Fase 0).

API pública del paquete; clipia_core.py re-exporta lo mismo para
compatibilidad con main.py, test_pipeline.py y los tests existentes.
"""
from .cache import (
    carpeta_cache,
    clave_archivo,
    escribir_cache,
    leer_cache,
)
from .cola import (
    ColaExportacion,
    ResultadoClip,
    TrabajoExportacion,
    workers_efectivos,
    workers_recomendados,
)
from .descarga import (
    NAVEGADORES_COOKIES,
    ErrorDescarga,
    clasificar_error_descarga,
    descargar_youtube,
    mensaje_error_descarga,
)
from .encoder import (
    descripcion_encoder,
    detectar_encoder,
    opciones_encoder,
)
from .exportacion import (
    ExportacionCancelada,
    exportar_clip,
    generar_miniatura,
    generar_vista_previa,
)
from .momentos import detectar_momentos
from .ollama import (
    INSTRUCCIONES_INSTALACION,
    INSTRUCCIONES_MODELO,
    MODELO_DEFECTO,
    modelo_disponible,
    ollama_disponible,
    rerank_ollama,
)
from .procesos import contar, ejecutar, matar_todos, olvidar, registrar
from .rostros import detectar_rostros, detectar_rostros_con_limite
from .subtitulos import (
    ESTILO_DEFECTO,
    PRESETS_SUBTITULOS,
    generar_subtitulos_ass,
)
from .transcripcion import (
    IDIOMAS,
    MODELOS_WHISPER,
    liberar_modelos,
    obtener_modelo,
    ram_total_gb,
    transcribir,
)
from .utilidades import (
    formato_ass,
    formato_hora,
    obtener_duracion,
    tiene_audio,
)

__all__ = [
    "ESTILO_DEFECTO",
    "IDIOMAS",
    "INSTRUCCIONES_INSTALACION",
    "INSTRUCCIONES_MODELO",
    "MODELO_DEFECTO",
    "MODELOS_WHISPER",
    "NAVEGADORES_COOKIES",
    "PRESETS_SUBTITULOS",
    "ColaExportacion",
    "ErrorDescarga",
    "ExportacionCancelada",
    "ResultadoClip",
    "TrabajoExportacion",
    "carpeta_cache",
    "clasificar_error_descarga",
    "clave_archivo",
    "contar",
    "descargar_youtube",
    "descripcion_encoder",
    "detectar_encoder",
    "detectar_momentos",
    "detectar_rostros",
    "detectar_rostros_con_limite",
    "ejecutar",
    "escribir_cache",
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
    "tiene_audio",
    "transcribir",
    "workers_efectivos",
    "workers_recomendados",
]
