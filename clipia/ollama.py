"""Re-ranking opcional de candidatos con un LLM local (Ollama).

Totalmente opcional: si Ollama no está instalado, no tiene el modelo
o no responde, la app sigue con la heurística sin bloquearse nunca.
Solo usa la red local (http://127.0.0.1:11434); nada sale del PC.
"""
import json
import logging
import urllib.error
import urllib.request

log = logging.getLogger("clipia.ollama")

HOST_DEFECTO = "http://127.0.0.1:11434"
MODELO_DEFECTO = "qwen2.5:7b"
# Comprobar si Ollama está ahí debe ser instantáneo; generar la
# puntuación con qwen2.5:7b en CPU puede tardar un par de minutos.
TIMEOUT_CONEXION = 2.0
TIMEOUT_GENERACION = 180.0
# Como mucho, se reordenan los 25 mejores candidatos.
MAX_CANDIDATOS = 25

INSTRUCCIONES_INSTALACION = (
    "Para reordenar los clips con IA local necesitas Ollama:\n\n"
    "1. Descarga Ollama desde https://ollama.com y ejecútalo.\n"
    "2. En una ventana de comandos (cmd), escribe:\n"
    "   ollama pull qwen2.5:7b\n"
    "   (descarga el modelo, unos 4.7 GB, solo la primera vez)\n"
    "3. Vuelve a pulsar «Reordenar con IA local».\n\n"
    "Todo corre en tu PC: ningún video ni texto sale a internet."
)

INSTRUCCIONES_MODELO = (
    "Ollama está corriendo, pero no tiene el modelo %s.\n\n"
    "En una ventana de comandos (cmd), escribe:\n"
    "   ollama pull %s\n"
    "y vuelve a pulsar «Reordenar con IA local»."
)

_PLANTILLA_PROMPT = """Eres un editor de clips virales para TikTok,
Reels y Shorts. Puntúa cada candidato de 0 a 10 en tres aspectos:
- "gancho": ¿engancha en los primeros 3 segundos?
- "coherencia": ¿la idea se entiende completa?
- "remate": ¿termina con fuerza, sin quedarse a medias?
Responde SOLO con este JSON, sin texto adicional:
{{"puntuaciones": [{{"indice": 0, "gancho": 8,
"coherencia": 7, "remate": 9}}]}}
Candidatos:
{candidatos}
"""


def _pedir(url: str, datos: dict | None = None,
           timeout: float = TIMEOUT_CONEXION) -> dict | None:
    """GET (sin datos) o POST JSON a Ollama. None si algo falla."""
    cuerpo = None
    cabeceras = {"Content-Type": "application/json"}
    if datos is not None:
        cuerpo = json.dumps(datos).encode("utf-8")
    peticion = urllib.request.Request(url, data=cuerpo,
                                      headers=cabeceras, method="POST"
                                      if datos is not None else "GET")
    try:
        with urllib.request.urlopen(peticion, timeout=timeout) as respuesta:
            return json.loads(respuesta.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError, TimeoutError):
        return None


def ollama_disponible(host: str = HOST_DEFECTO,
                      timeout: float = TIMEOUT_CONEXION) -> bool:
    """True si Ollama responde en `host` (sin bloquear más de
    `timeout` segundos)."""
    return _pedir(host + "/api/tags", timeout=timeout) is not None


def modelo_disponible(modelo: str = MODELO_DEFECTO,
                      host: str = HOST_DEFECTO,
                      timeout: float = TIMEOUT_CONEXION) -> bool:
    """True si Ollama tiene descargado `modelo`."""
    respuesta = _pedir(host + "/api/tags", timeout=timeout)
    if not isinstance(respuesta, dict):
        return False
    modelos = respuesta.get("models") or []
    nombres = {m.get("name") for m in modelos if isinstance(m, dict)}
    return modelo in nombres or (modelo + ":latest") in nombres


def _extraer_json(texto: str) -> dict | None:
    """Extrae el primer objeto JSON de `texto` (tolera cercas de
    markdown y texto alrededor)."""
    inicio = texto.find("{")
    fin = texto.rfind("}")
    if inicio < 0 or fin <= inicio:
        return None
    try:
        valor = json.loads(texto[inicio:fin + 1])
    except ValueError:
        return None
    return valor if isinstance(valor, dict) else None


def _pedir_puntuaciones(candidatos: list[dict], modelo: str, host: str,
                        timeout: float) -> dict[int, float] | None:
    """Pide a Ollama la puntuación de cada candidato.

    Devuelve {índice: nota 0.0-1.0} o None si Ollama no responde o
    la respuesta no se entiende.
    """
    lineas = []
    for i, c in enumerate(candidatos):
        texto = c.get("text", "")[:400].replace("\n", " ")
        lineas.append("[%d] %s - %s — %s"
                      % (i, c.get("start", 0), c.get("end", 0), texto))
    prompt = _PLANTILLA_PROMPT.format(candidatos="\n".join(lineas))
    respuesta = _pedir(host + "/api/generate",
                       {"model": modelo, "prompt": prompt,
                        "format": "json", "stream": False},
                       timeout=timeout)
    if not isinstance(respuesta, dict):
        return None
    puntuaciones = _extraer_json(respuesta.get("response", ""))
    if not puntuaciones or not isinstance(
            puntuaciones.get("puntuaciones"), list):
        return None
    notas = {}
    for entrada in puntuaciones["puntuaciones"]:
        if not isinstance(entrada, dict):
            continue
        try:
            indice = int(entrada["indice"])
            gancho = float(entrada["gancho"])
            coherencia = float(entrada["coherencia"])
            remate = float(entrada["remate"])
        except (KeyError, TypeError, ValueError):
            continue
        if 0 <= indice < len(candidatos):
            notas[indice] = ((gancho + coherencia + remate) / 30.0)
    return notas or None


def rerank_ollama(candidatos: list[dict], modelo: str = MODELO_DEFECTO,
                  host: str = HOST_DEFECTO,
                  timeout: float = TIMEOUT_GENERACION,
                  max_candidatos: int = MAX_CANDIDATOS
                  ) -> list[dict] | None:
    """Reordena los candidatos con un LLM local.

    Devuelve una lista nueva (los ~`max_candidatos` mejores reordenados
    por la nota del LLM mezclada con la heurística, y el resto detrás
    en su orden original) o None si Ollama no responde o la respuesta
    no sirve. Nunca lanza excepciones: cualquier fallo devuelve None
    para que la app siga con la heurística.
    """
    if not candidatos:
        return None
    try:
        primeros = candidatos[:max_candidatos]
        notas = _pedir_puntuaciones(primeros, modelo, host, timeout)
        if notas is None:
            log.warning("Ollama no devolvió puntuaciones útiles")
            return None
        # Exigir al menos la mitad puntuada: si el LLM solo puntuó
        # uno o dos, el reorden no es de fiar.
        if len(notas) * 2 < len(primeros):
            log.warning("Ollama puntuó %d de %d candidatos; se ignora",
                        len(notas), len(primeros))
            return None
        reordenados = []
        for i, c in enumerate(primeros):
            copia = dict(c)
            copia["score_heuristica"] = c.get("score", 0.0)
            nota_llm = notas.get(i)
            if nota_llm is None:
                copia["score_llm"] = None
                copia["score"] = copia["score_heuristica"]
            else:
                copia["score_llm"] = round(nota_llm, 3)
                copia["score"] = round(
                    0.6 * nota_llm + 0.4 * copia["score_heuristica"], 3)
            reordenados.append(copia)
        reordenados.sort(key=lambda c: c["score"], reverse=True)
        return reordenados + list(candidatos[max_candidatos:])
    except Exception:
        log.exception("fallo al reordenar con Ollama")
        return None
