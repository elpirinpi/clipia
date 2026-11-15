"""Detección de los mejores momentos para clips cortos (30-90 s)."""
import re

# Palabras que suelen marcar un momento con gancho en español.
PALABRAS_GANCHO: set[str] = {
    "mira", "miran", "escucha", "escuchen", "atención", "atencion", "ojo",
    "importante", "secreto", "secretos", "gratis", "nadie", "nunca",
    "siempre", "verdad", "increíble", "increible", "cuidado", "mejor",
    "peor", "dinero", "ganar", "gana", "error", "errores", "truco",
    "trucos", "clave", "claves", "descubre", "descubrí", "descubri",
    "imagina", "imagínate", "imaginate", "recuerda", "sabes", "créeme",
    "creeme", "te", "voy", "contar", "pasa", "resulta", "fíjate", "fijate",
    "alerta", "urgente", "exclusivo", "nuevo", "primero", "último",
    "ultimo", "ahora", "sucedió", "sucedio", "pasó", "paso",
    "misterio", "revelo", "reveló", "confieso", "todos",
    "ninguno", "jamás", "jamas", "imposible", "locura", "brutal",
}

# Duraciones de ventana que se prueban (segundos).
DURACIONES_VENTANA: tuple[int, ...] = (30, 45, 60, 75, 90)


def _frases_de_segmentos(segmentos: list[dict]) -> list[dict]:
    """Agrupa las palabras en frases (por puntuación o pausa larga).

    Devuelve [{"start": float, "end": float, "text": str, "words": [...]}].
    """
    palabras = []
    for seg in segmentos:
        palabras.extend(seg.get("words") or [])
    if not palabras:
        # Sin timestamps por palabra: usar los segmentos tal cual.
        return [{"start": s["start"], "end": s["end"], "text": s["text"],
                 "words": []} for s in segmentos if s["text"]]

    frases = []
    actual = []
    for palabra in palabras:
        if actual:
            pausa = palabra["start"] - actual[-1]["end"]
            texto_previo = "".join(p["word"] for p in actual)
            if pausa > 0.9 or texto_previo.rstrip().endswith((".", "?", "!")):
                frases.append(actual)
                actual = []
        actual.append(palabra)
    if actual:
        frases.append(actual)

    return [{
        "start": f[0]["start"],
        "end": f[-1]["end"],
        "text": "".join(p["word"] for p in f).strip(),
        "words": f,
    } for f in frases if "".join(p["word"] for p in f).strip()]


def _puntuar_ventana(frases: list[dict], inicio: float, fin: float) -> float:
    """Puntúa una ventana [inicio, fin] de 0 a 1.

    Combina densidad de habla, exclamaciones/preguntas y palabras gancho.
    """
    en_ventana = [f for f in frases if f["start"] >= inicio - 0.5
                  and f["start"] < fin]
    if not en_ventana:
        return 0.0
    duracion = max(1.0, fin - inicio)
    texto = " ".join(f["text"] for f in en_ventana)
    num_palabras = len(texto.split())

    # Densidad de habla (palabras por segundo, tope ~3).
    densidad = min(1.0, (num_palabras / duracion) / 3.0)
    # Exclamaciones y preguntas.
    signos = texto.count("!") + texto.count("?")
    signos_puntos = min(1.0, signos / 3.0)
    # Palabras gancho.
    tokens = re.findall(r"[a-záéíóúñü]+", texto.lower())
    ganchos = sum(1 for t in tokens if t in PALABRAS_GANCHO)
    gancho_puntos = min(1.0, ganchos / 4.0)

    return 0.45 * densidad + 0.30 * gancho_puntos + 0.25 * signos_puntos


def _traslapan(a_inicio: float, a_fin: float, b_inicio: float, b_fin: float,
               umbral: float = 0.5) -> bool:
    """True si el traslape entre dos ventanas supera el umbral."""
    traslape = max(0.0, min(a_fin, b_fin) - max(a_inicio, b_inicio))
    menor = min(a_fin - a_inicio, b_fin - b_inicio)
    return menor > 0 and traslape / menor > umbral


def detectar_momentos(segmentos: list[dict], duracion_video: float,
                      cantidad: int = 10) -> list[dict]:
    """Detecta los mejores momentos para clips cortos.

    Devuelve hasta `cantidad` candidatos ordenados por puntuación:
      [{"start": float, "end": float, "score": float, "text": str}]
    """
    frases = _frases_de_segmentos(segmentos)
    if not frases or duracion_video <= 0:
        return []

    # Video muy corto: un solo clip con todo el video.
    if duracion_video < 30:
        texto = " ".join(f["text"] for f in frases)
        return [{"start": 0.0, "end": float(duracion_video),
                 "score": 1.0, "text": texto}]

    candidatos = []
    vistos = set()
    for frase in frases:
        inicio = frase["start"]
        for dur in DURACIONES_VENTANA:
            fin = min(duracion_video, inicio + dur)
            if fin - inicio < 25:
                continue
            clave = (round(inicio, 1), round(fin, 1))
            if clave in vistos:
                continue
            vistos.add(clave)
            puntos = _puntuar_ventana(frases, inicio, fin)
            if puntos <= 0:
                continue
            texto = " ".join(f["text"] for f in frases
                             if f["start"] >= inicio - 0.5
                             and f["start"] < fin)
            candidatos.append({"start": inicio, "end": fin,
                               "score": puntos, "text": texto})

    # Elegir los mejores sin traslapes grandes entre ellos.
    candidatos.sort(key=lambda c: c["score"], reverse=True)
    elegidos = []
    for cand in candidatos:
        if len(elegidos) >= cantidad:
            break
        if any(_traslapan(cand["start"], cand["end"], e["start"], e["end"])
               for e in elegidos):
            continue
        elegidos.append(cand)
    return elegidos
