"""Subtítulos ASS estilo Shorts, con karaoke y presets.

Colores ASS en formato &HAABBGGRR. En karaoke (tags \\k) libass pinta
cada palabra de forma progresiva: empieza en el color secundario y
termina en el primario cuando se pronuncia.
"""
from .momentos import _frases_de_segmentos
from .utilidades import formato_ass

# Presets de subtítulos. "Shorts clásico" es el estilo original de la
# v1 (se conserva idéntico para no cambiar el aspecto por defecto).
PRESETS_SUBTITULOS: dict[str, dict] = {
    "Shorts clásico": {
        "fuente": "Arial", "tamano": 64,
        "primario": "&H00FFFFFF", "secundario": "&H00FFFFFF",
        "borde_color": "&H00000000", "negrita": True,
        "borde": 3, "sombra": 0, "margen_v": 300,
        "karaoke": False, "mayusculas": False,
    },
    "Hormozi": {
        "fuente": "Arial", "tamano": 72,
        "primario": "&H0000FFFF", "secundario": "&H00FFFFFF",
        "borde_color": "&H00000000", "negrita": True,
        "borde": 4, "sombra": 0, "margen_v": 300,
        "karaoke": True, "mayusculas": True,
    },
    "Minimal": {
        "fuente": "Arial", "tamano": 48,
        "primario": "&H00FFFFFF", "secundario": "&H00FFFFFF",
        "borde_color": "&H00000000", "negrita": False,
        "borde": 1, "sombra": 0, "margen_v": 200,
        "karaoke": False, "mayusculas": False,
    },
    "Neón": {
        "fuente": "Arial", "tamano": 64,
        "primario": "&H00FFFF00", "secundario": "&H00FF00FF",
        "borde_color": "&H00000000", "negrita": True,
        "borde": 2, "sombra": 0, "margen_v": 300,
        "karaoke": True, "mayusculas": False,
    },
}

ESTILO_DEFECTO = "Shorts clásico"

_CABECERA_ASS = """[Script Info]
Title: KellyAiClip
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,%s,%d,%s,%s,%s,&H00000000,%s,0,0,0,100,100,0,0,1,%d,%d,2,60,60,%d,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
{eventos}
"""

# Plantilla original (Shorts clásico, MarginV 300): se conserva por
# compatibilidad (la fachada la exporta).
PLANTILLA_ASS: str = _CABECERA_ASS % (
    "Arial", 64, "&H00FFFFFF", "&H00FFFFFF", "&H00000000", "-1", 3, 0, 300)


def _plantilla_ass(preset: dict, margen_vertical: int | None) -> str:
    """Plantilla ASS completa del preset."""
    return _CABECERA_ASS % (
        preset["fuente"], preset["tamano"], preset["primario"],
        preset["secundario"], preset["borde_color"],
        "-1" if preset["negrita"] else "0",
        preset["borde"], preset["sombra"],
        preset["margen_v"] if margen_vertical is None
        else margen_vertical)


def _escapar_ruta_subtitulos(ruta: str) -> str:
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


def _fragmentos_subtitulo(frase: dict, max_palabras: int = 7
                          ) -> list[tuple[float, float, str]]:
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


def _fragmentos_karaoke(frase: dict, max_palabras: int = 7
                        ) -> list[tuple[float, float, list[tuple[str, int]]]]:
    """Divide una frase en fragmentos karaoke.

    Devuelve (inicio, fin, [(palabra, centésimas), ...]) por fragmento:
    cada palabra lleva su duración en centésimas para el tag \\k.
    Sin timestamps por palabra devuelve [] (el llamador usa el
    fragmento normal sin karaoke).
    """
    palabras = frase.get("words") or []
    if not palabras:
        return []
    fragmentos = []
    for i in range(0, len(palabras), max_palabras):
        grupo = palabras[i:i + max_palabras]
        silabas = []
        for p in grupo:
            texto = p["word"].strip().replace("{", "").replace("}", "")
            if not texto:
                continue
            centesimas = max(1, int(round((p["end"] - p["start"]) * 100)))
            silabas.append((texto, centesimas))
        if silabas:
            fragmentos.append((grupo[0]["start"], grupo[-1]["end"], silabas))
    return fragmentos


def _texto_karaoke(silabas: list[tuple[str, int]],
                   mayusculas: bool) -> str:
    """Texto de un evento karaoke: {\\k12}palabra {\\k20}otra."""
    partes = []
    for texto, centesimas in silabas:
        if mayusculas:
            texto = texto.upper()
        partes.append("{\\k%d}%s" % (centesimas, texto))
    return " ".join(partes)


def generar_subtitulos_ass(segmentos: list[dict], inicio_clip: float,
                           fin_clip: float, ruta_salida: str,
                           estilo: str = ESTILO_DEFECTO,
                           margen_vertical: int | None = None) -> str:
    """Genera un archivo .ass con los subtítulos del clip.

    Tiempos relativos al inicio del clip. `estilo` es un preset de
    PRESETS_SUBTITULOS ("Shorts clásico" por defecto; un nombre
    desconocido usa el defecto). `margen_vertical` anula el MarginV
    del preset (zona segura de TikTok); con None se usa el del preset.
    Los presets con karaoke pintan cada palabra con tags \\k según
    sus timestamps.
    """
    preset = PRESETS_SUBTITULOS.get(estilo,
                                    PRESETS_SUBTITULOS[ESTILO_DEFECTO])
    frases = _frases_de_segmentos(segmentos)
    lineas = []
    for frase in frases:
        if frase["end"] <= inicio_clip or frase["start"] >= fin_clip:
            continue
        if preset["karaoke"]:
            fragmentos = _fragmentos_karaoke(frase)
            if not fragmentos:
                # Sin timestamps por palabra: fragmentos normales.
                fragmentos = [(i, f, [(t, 0)])
                              for i, f, t in _fragmentos_subtitulo(frase)]
                for inicio, fin, silabas in fragmentos:
                    inicio_rel = max(0.0, inicio - inicio_clip)
                    fin_rel = min(fin_clip - inicio_clip, fin - inicio_clip)
                    if fin_rel - inicio_rel < 0.15:
                        continue
                    texto = silabas[0][0].replace("{", "").replace("}", "")
                    if preset["mayusculas"]:
                        texto = texto.upper()
                    lineas.append(
                        "Dialogue: 0,%s,%s,Default,,0,0,0,,%s"
                        % (formato_ass(inicio_rel), formato_ass(fin_rel),
                           texto))
                continue
            for inicio, fin, silabas in fragmentos:
                inicio_rel = max(0.0, inicio - inicio_clip)
                fin_rel = min(fin_clip - inicio_clip, fin - inicio_clip)
                if fin_rel - inicio_rel < 0.15:
                    continue
                lineas.append(
                    "Dialogue: 0,%s,%s,Default,,0,0,0,,%s"
                    % (formato_ass(inicio_rel), formato_ass(fin_rel),
                       _texto_karaoke(silabas, preset["mayusculas"])))
        else:
            for inicio, fin, texto in _fragmentos_subtitulo(frase):
                inicio_rel = max(0.0, inicio - inicio_clip)
                fin_rel = min(fin_clip - inicio_clip, fin - inicio_clip)
                if fin_rel - inicio_rel < 0.15:
                    continue
                texto = texto.replace("{", "").replace("}", "")
                if preset["mayusculas"]:
                    texto = texto.upper()
                lineas.append(
                    "Dialogue: 0,%s,%s,Default,,0,0,0,,%s"
                    % (formato_ass(inicio_rel), formato_ass(fin_rel), texto)
                )
    contenido = _plantilla_ass(preset, margen_vertical).format(
        eventos="\n".join(lineas))
    with open(ruta_salida, "w", encoding="utf-8") as archivo:
        archivo.write(contenido)
    return ruta_salida
