"""Caché en disco de ClipIA (transcripciones y rostros).

Cada entrada se identifica por un hash de la identidad del archivo
(ruta absoluta + tamaño + fecha de modificación) más los parámetros
que afectan al resultado (modelo, idioma, intervalo...). Si el video
cambia, la clave cambia y la entrada vieja deja de usarse.

Vive en %LOCALAPPDATA%/ClipIA/cache en Windows (en otros sistemas,
~/.local/share/ClipIA/cache). Con un límite de tamaño: al superarlo
se borran las entradas más antiguas.
"""
import hashlib
import json
import os

NOMBRE_APP = "ClipIA"
LIMITE_MB = 500


def carpeta_cache() -> str:
    """Carpeta de la caché según el sistema."""
    base = os.environ.get("LOCALAPPDATA")
    if base:
        return os.path.join(base, NOMBRE_APP, "cache")
    return os.path.join(os.path.expanduser("~"), ".local", "share",
                        NOMBRE_APP, "cache")


def clave_archivo(ruta_video: str, **parametros) -> str:
    """Hash de la identidad del archivo más los parámetros dados.

    Dos llamadas con el mismo archivo sin modificar y los mismos
    parámetros devuelven la misma clave; cualquier cambio (tamaño,
    fecha de modificación, parámetros) da una clave distinta.
    """
    ruta = os.path.abspath(ruta_video)
    info = os.stat(ruta)  # FileNotFoundError si no existe
    datos = {"ruta": ruta, "tamano": info.st_size, "mtime": info.st_mtime}
    datos.update(parametros)
    texto = json.dumps(datos, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()[:32]


def _ruta_entrada(tipo: str, clave: str) -> str:
    return os.path.join(carpeta_cache(), tipo, clave + ".json")


def leer_cache(tipo: str, clave: str):
    """Devuelve el valor guardado o None si no existe o está corrupto."""
    try:
        with open(_ruta_entrada(tipo, clave), encoding="utf-8") as archivo:
            return json.load(archivo)
    except (OSError, ValueError):
        return None


def escribir_cache(tipo: str, clave: str, valor) -> None:
    """Guarda un valor (escritura atómica). Nunca rompe al llamador:
    si no se puede escribir, se ignora en silencio."""
    try:
        carpeta = os.path.join(carpeta_cache(), tipo)
        os.makedirs(carpeta, exist_ok=True)
        ruta = _ruta_entrada(tipo, clave)
        tmp = ruta + ".tmp"
        with open(tmp, "w", encoding="utf-8") as archivo:
            json.dump(valor, archivo, ensure_ascii=False)
        os.replace(tmp, ruta)
    except OSError:
        return
    _podar()


def _podar(limite_mb: int = LIMITE_MB) -> None:
    """Borra las entradas más antiguas hasta quedar bajo el límite."""
    try:
        base = carpeta_cache()
        if not os.path.isdir(base):
            return
        entradas = []
        total = 0
        for raiz, _dirs, nombres in os.walk(base):
            for nombre in nombres:
                if not nombre.endswith(".json"):
                    continue
                ruta = os.path.join(raiz, nombre)
                try:
                    info = os.stat(ruta)
                except OSError:
                    continue
                entradas.append((info.st_mtime, info.st_size, ruta))
                total += info.st_size
        limite = limite_mb * 1024 * 1024
        entradas.sort()
        for _mtime, tamano, ruta in entradas:
            if total <= limite:
                break
            try:
                os.remove(ruta)
            except OSError:
                continue
            total -= tamano
    except OSError:
        pass
