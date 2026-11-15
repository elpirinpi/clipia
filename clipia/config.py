"""Configuración persistida de ClipIA (JSON).

Vive en %APPDATA%/ClipIA/config.json en Windows (en otros sistemas,
~/.config/ClipIA/config.json). Los valores que falten se rellenan con
los defectos; un JSON corrupto se ignora y se usan los defectos.
"""
import json
import os

NOMBRE_APP = "ClipIA"

VALORES_DEFECTO: dict = {
    "modelo": "base",
    "idioma": "es",
    "carpeta_salida": "",
    "estilo_subtitulos": "Shorts clásico",
    # Margen vertical de los subtítulos (px desde abajo; zona segura
    # de TikTok). 300 es el del preset clásico.
    "margen_vertical": 300,
    "encoder": "auto",
    "seguir_rostros": True,
    # Workers de exportación: 0 = automático (1 con libx264, 2 con
    # codificador por hardware).
    "workers_exportacion": 0,
}


def ruta_config() -> str:
    """Ruta del archivo de configuración según el sistema."""
    base = os.environ.get("APPDATA")
    if base:
        return os.path.join(base, NOMBRE_APP, "config.json")
    return os.path.join(os.path.expanduser("~"), ".config",
                        NOMBRE_APP, "config.json")


def cargar_config(ruta: str | None = None) -> dict:
    """Lee la configuración (defectos + lo guardado)."""
    valores = dict(VALORES_DEFECTO)
    ruta = ruta or ruta_config()
    try:
        with open(ruta, encoding="utf-8") as archivo:
            guardado = json.load(archivo)
    except (OSError, ValueError):
        return valores
    if isinstance(guardado, dict):
        for clave in VALORES_DEFECTO:
            if clave in guardado:
                valores[clave] = guardado[clave]
    return valores


def guardar_config(valores: dict, ruta: str | None = None) -> str:
    """Guarda la configuración (escritura atómica). Devuelve la ruta."""
    ruta = ruta or ruta_config()
    carpeta = os.path.dirname(ruta)
    if carpeta:
        os.makedirs(carpeta, exist_ok=True)
    solo_conocidos = {c: valores.get(c, VALORES_DEFECTO[c])
                      for c in VALORES_DEFECTO}
    tmp = ruta + ".tmp"
    with open(tmp, "w", encoding="utf-8") as archivo:
        json.dump(solo_conocidos, archivo, indent=2, ensure_ascii=False)
        archivo.write("\n")
    os.replace(tmp, ruta)
    return ruta
