# -*- coding: utf-8 -*-
"""Subtítulos ASS estilo Shorts."""
from .momentos import _frases_de_segmentos
from .utilidades import formato_ass

PLANTILLA_ASS = """[Script Info]
Title: ClipIA
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,64,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,3,0,2,60,60,300,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
{eventos}
"""


def _escapar_ruta_subtitulos(ruta):
    """Escapa una ruta para el filtro subtitles de ffmpeg.

    En Windows las rutas con unidad (C:\\...) rompen el filtro si no se
    escapan los dos puntos y se usan barras normales.
    Desde B9 exportar_clip ya no la necesita (el ASS va a un cwd temporal
    con nombre relativo), pero se conserva por compatibilidad.
    """
    ruta = ruta.replace("\\", "/")
    ruta = ruta.replace(":", "\\:")
    ruta = ruta.replace("'", "\\'")
    return ruta


def _fragmentos_subtitulo(frase, max_palabras=7):
    """Divide una frase en fragmentos cortos para subtítulos legibles."""
    palabras = frase.get("words") or []
    if not palabras:
        return [(frase["start"], frase["end"], frase["text"])]
    fragmentos = []
    for i in range(0, len(palabras), max_palabras):
        grupo = palabras[i:i + max_palabras]
        texto = "".join(p["word"] for p in grupo).strip()
        if texto:
            fragmentos.append((grupo[0]["start"], grupo[-1]["end"], texto))
    return fragmentos


def generar_subtitulos_ass(segmentos, inicio_clip, fin_clip, ruta_salida):
    """Genera un archivo .ass con los subtítulos del clip.

    Tiempos relativos al inicio del clip. Estilo Shorts: negrita, blanco
    con borde negro, abajo al centro.
    """
    frases = _frases_de_segmentos(segmentos)
    lineas = []
    for frase in frases:
        if frase["end"] <= inicio_clip or frase["start"] >= fin_clip:
            continue
        for inicio, fin, texto in _fragmentos_subtitulo(frase):
            inicio_rel = max(0.0, inicio - inicio_clip)
            fin_rel = min(fin_clip - inicio_clip, fin - inicio_clip)
            if fin_rel - inicio_rel < 0.15:
                continue
            texto = texto.replace("{", "").replace("}", "")
            lineas.append(
                "Dialogue: 0,%s,%s,Default,,0,0,0,,%s"
                % (formato_ass(inicio_rel), formato_ass(fin_rel), texto)
            )
    contenido = PLANTILLA_ASS.format(eventos="\n".join(lineas))
    with open(ruta_salida, "w", encoding="utf-8") as archivo:
        archivo.write(contenido)
    return ruta_salida
