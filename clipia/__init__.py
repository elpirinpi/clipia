"""ClipIA - núcleo dividido en módulos (Fase 0).

API pública del paquete; clipia_core.py re-exporta lo mismo para
compatibilidad con main.py, test_pipeline.py y los tests existentes.
"""
from .descarga import descargar_youtube
from .exportacion import exportar_clip, generar_miniatura, generar_vista_previa
from .momentos import detectar_momentos
from .rostros import detectar_rostros
from .subtitulos import generar_subtitulos_ass
from .transcripcion import transcribir
from .utilidades import formato_ass, formato_hora, obtener_duracion

__all__ = [
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
