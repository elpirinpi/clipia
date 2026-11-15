"""Detección de los mejores momentos para clips cortos (30-90 s)."""
import math
import re

# Palabras que suelen marcar un momento con gancho en español.
# Fase 2: fuera las genéricas ("te", "voy", "pasa", "paso", "todos",
# "ahora", "nuevo") — aparecían en casi cualquier ventana y no
# distinguían nada — y los duplicados del literal original.
PALABRAS_GANCHO: set[str] = {
    "mira", "miran", "escucha", "escuchen", "atención", "atencion", "ojo",
    "importante", "secreto", "secretos", "gratis", "nadie", "nunca",
    "siempre", "verdad", "increíble", "increible", "cuidado", "mejor",
    "peor", "dinero", "ganar", "gana", "error", "errores", "truco",
    "trucos", "clave", "claves", "descubre", "descubrí", "descubri",
    "imagina", "imagínate", "imaginate", "recuerda", "sabes", "créeme",
    "creeme", "contar", "resulta", "fíjate", "fijate",
    "alerta", "urgente", "exclusivo", "primero", "último",
    "ultimo", "sucedió", "sucedio", "pasó",
    "misterio", "revelo", "reveló", "confieso",
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


def _idf_ganchos(frases: list[dict]) -> dict[str, float]:
    """Rareza (idf) de cada palabra gancho sobre las frases del video.

    idf(t) = ln((N+1)/(df+1)) + 1, con N = número de frases y df =
    frases que contienen t. Una palabra en casi todas las frases vale
    ~1; una que aparece una sola vez vale ~ln(N)+1. Así "dinero" en un
    video sobre dinero pesa menos que "secreto" dicho una sola vez.
    """
    total = len(frases)
    df: dict[str, int] = {}
    for frase in frases:
        tokens = set(re.findall(r"[a-záéíóúñü]+", frase["text"].lower()))
        for token in tokens & PALABRAS_GANCHO:
            df[token] = df.get(token, 0) + 1
    return {t: math.log((total + 1) / (n + 1)) + 1.0
            for t, n in df.items()}


def _puntuar_ventana(frases: list[dict], inicio: float, fin: float,
                     idf: dict[str, float] | None = None) -> float:
    """Puntúa una ventana [inicio, fin] de 0 a 1.

    Combina densidad de habla, exclamaciones/preguntas y palabras gancho.
    Con `idf` (ver _idf_ganchos) las palabras gancho raras pesan más
    que las comunes; sin `idf` cada gancho vale lo mismo que antes.
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
    # Palabras gancho (con rareza si se pasa el idf: 4 ganchos muy
    # raros ~1.0; 4 ganchos comunes ~0.4).
    tokens = re.findall(r"[a-záéíóúñü]+", texto.lower())
    if idf is None:
        ganchos = sum(1 for t in tokens if t in PALABRAS_GANCHO)
        gancho_puntos = min(1.0, ganchos / 4.0)
    else:
        peso = sum(idf.get(t, 1.0) for t in tokens
                   if t in PALABRAS_GANCHO)
        gancho_puntos = min(1.0, peso / 12.0)

    return 0.45 * densidad + 0.30 * gancho_puntos + 0.25 * signos_puntos


def _snap_fin(frases: list[dict], inicio: float, fin_deseado: float,
              duracion_video: float, minimo: float = 25.0) -> float:
    """Ajusta `fin_deseado` a una frontera de frase.

    Devuelve el fin de la última frase que termina dentro de la
    ventana, para no cortar a media frase. Si eso deja el clip por
    debajo de `minimo` segundos, lo alarga hasta la siguiente frontera
    de frase. Si una sola frase cubre toda la ventana, el fin es el
    fin de esa frase. El fin del video siempre es una frontera válida.
    """
    if fin_deseado >= duracion_video:
        return float(duracion_video)
    fines = sorted({f["end"] for f in frases
                    if f["start"] < fin_deseado and f["end"] > inicio})
    if not fines:
        # Sin frases en la ventana: no hay nada que cortar.
        return float(fin_deseado)
    dentro = [f for f in fines if f <= fin_deseado]
    if dentro:
        fin = dentro[-1]
        if fin - inicio >= minimo:
            return fin
        # Quedó corto: alargar a la siguiente frontera de frase.
        siguientes = [f for f in fines if f > fin_deseado]
        if siguientes:
            return min(siguientes[0], duracion_video)
        return fin
    # Ninguna frase termina dentro: la primera que termina después
    # (una frase larga cubre la ventana).
    return min(fines[0], duracion_video)


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
    idf = _idf_ganchos(frases)
    for frase in frases:
        # El inicio ya es frontera de frase (empieza en una frase); el
        # fin se ajusta a la frontera de frase más cercana para no
        # cortar a media palabra.
        inicio = frase["start"]
        for dur in DURACIONES_VENTANA:
            fin = _snap_fin(frases, inicio, inicio + dur, duracion_video)
            if fin - inicio < 25:
                continue
            clave = (round(inicio, 1), round(fin, 1))
            if clave in vistos:
                continue
            vistos.add(clave)
            puntos = _puntuar_ventana(frases, inicio, fin, idf=idf)
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
