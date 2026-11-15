"""ClipIA - núcleo dividido en módulos (Fase 0).

API pública del paquete; clipia_core.py re-exporta lo mismo para
compatibilidad con main.py, test_pipeline.py y los tests existentes.
"""
from .descarga import descargar_youtube
from .encoder import (
    descripcion_encoder,
    detectar_encoder,
    opciones_encoder,
)
from .exportacion import exportar_clip, generar_miniatura, generar_vista_previa
from .momentos import detectar_momentos
from .rostros import detectar_rostros
from .subtitulos import generar_subtitulos_ass
from .transcripcion import (
    IDIOMAS,
    MODELOS_WHISPER,
    liberar_modelos,
    obtener_modelo,
    ram_total_gb,
    transcribir,
)
from .utilidades import formato_ass, formato_hora, obtener_duracion

__all__ = [
    "IDIOMAS",
    "MODELOS_WHISPER",
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
