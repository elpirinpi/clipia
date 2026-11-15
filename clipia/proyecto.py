"""Guardar/cargar proyectos (.clipia).

Un proyecto es un JSON con los videos analizados (ruta, duración y
transcripción), los clips candidatos (con los tiempos editados), la
selección y la carpeta de salida. Guardar es atómico (temporal +
replace), como en config.py. Al cargar se valida la estructura y se
devuelve el proyecto normalizado; la GUI reubica los videos que ya
no están en su ruta. Las miniaturas NO se guardan (son temporales):
se regeneran al abrir el proyecto.
"""
import json
import os

VERSION_PROYECTO = 1
EXTENSION = ".clipia"


def guardar_proyecto(ruta: str, proyecto: dict) -> str:
    """Guarda el proyecto en `ruta` (escritura atómica)."""
    datos = dict(proyecto)
    datos["version"] = VERSION_PROYECTO
    ruta_tmp = ruta + ".tmp"
    with open(ruta_tmp, "w", encoding="utf-8") as archivo:
        json.dump(datos, archivo, ensure_ascii=False)
    os.replace(ruta_tmp, ruta)
    return ruta


def _es_numero(valor) -> bool:
    return isinstance(valor, (int, float)) and not isinstance(valor, bool)


def cargar_proyecto(ruta: str) -> dict:
    """Lee y valida un proyecto. Devuelve el dict normalizado.

    Lanza ValueError si el archivo no existe, no es JSON válido o no
    tiene la estructura de un proyecto KellyAiClip.
    """
    try:
        with open(ruta, encoding="utf-8") as archivo:
            datos = json.load(archivo)
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("No se pudo leer el proyecto: %s" % error) \
            from error
    if not isinstance(datos, dict):
        raise ValueError("El archivo no es un proyecto KellyAiClip válido.")
    if datos.get("version") != VERSION_PROYECTO:
        raise ValueError(
            "El proyecto es de otra versión (versión %s; esta app "
            "lee la versión %s)."
            % (datos.get("version"), VERSION_PROYECTO))
    videos = datos.get("videos")
    if not isinstance(videos, list):
        raise ValueError("El proyecto no trae la lista de videos.")
    for video in videos:
        if not isinstance(video, dict) \
                or not isinstance(video.get("ruta"), str) \
                or not _es_numero(video.get("duracion")) \
                or not isinstance(video.get("segmentos"), list):
            raise ValueError(
                "Un video del proyecto está incompleto (falta ruta, "
                "duración o transcripción).")
    candidatos = datos.get("candidatos")
    if not isinstance(candidatos, list):
        raise ValueError("El proyecto no trae la lista de clips.")
    for clip in candidatos:
        if not isinstance(clip, dict) \
                or not _es_numero(clip.get("start")) \
                or not _es_numero(clip.get("end")):
            raise ValueError("Un clip del proyecto no tiene inicio/fin.")
    seleccion = datos.get("seleccion", [])
    if not isinstance(seleccion, list):
        raise ValueError("La selección del proyecto no es una lista.")
    # Tolerante: si la selección no cubre todos los clips, los que
    # falten quedan marcados (y si sobra, se recorta).
    seleccion = [bool(v) for v in seleccion[:len(candidatos)]]
    seleccion += [True] * (len(candidatos) - len(seleccion))
    carpeta = datos.get("carpeta_salida", "")
    if not isinstance(carpeta, str):
        carpeta = ""
    return {
        "version": VERSION_PROYECTO,
        "videos": [{"ruta": v["ruta"], "duracion": float(v["duracion"]),
                    "segmentos": v["segmentos"]} for v in videos],
        "candidatos": [{
            "start": float(c["start"]), "end": float(c["end"]),
            "score": float(c["score"]) if _es_numero(c.get("score"))
            else 0.0,
            "text": c.get("text", "") if isinstance(c.get("text"), str)
            else "",
            "video": c.get("video") if isinstance(c.get("video"), str)
            else None,
        } for c in candidatos],
        "seleccion": seleccion,
        "carpeta_salida": carpeta,
    }
