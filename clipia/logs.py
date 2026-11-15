"""Logging rotativo de ClipIA.

El log vive en %LOCALAPPDATA%/ClipIA/logs/clipia.log en Windows
(en otros sistemas, ~/.local/share/ClipIA/logs/). Rota a 1 MB con
5 copias. También escribe en consola.
"""
import logging
import os
from logging.handlers import RotatingFileHandler

NOMBRE_APP = "ClipIA"
MAX_BYTES = 1024 * 1024
COPIAS = 5


def carpeta_logs() -> str:
    """Carpeta donde van los logs según el sistema."""
    base = os.environ.get("LOCALAPPDATA")
    if base:
        return os.path.join(base, NOMBRE_APP, "logs")
    return os.path.join(os.path.expanduser("~"), ".local", "share",
                        NOMBRE_APP, "logs")


def configurar_logging(nivel: int = logging.INFO,
                       nombre: str = "clipia") -> logging.Logger:
    """Configura el logger: archivo rotativo + consola. Idempotente."""
    logger = logging.getLogger(nombre)
    if logger.handlers:
        return logger
    logger.setLevel(nivel)
    formato = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S")
    consola = logging.StreamHandler()
    consola.setFormatter(formato)
    logger.addHandler(consola)
    try:
        carpeta = carpeta_logs()
        os.makedirs(carpeta, exist_ok=True)
        archivo = RotatingFileHandler(
            os.path.join(carpeta, "clipia.log"),
            maxBytes=MAX_BYTES, backupCount=COPIAS, encoding="utf-8")
        archivo.setFormatter(formato)
        logger.addHandler(archivo)
    except OSError:
        logger.warning("no se pudo crear el archivo de log", exc_info=True)
    return logger


def obtener_log(nombre: str | None = None) -> logging.Logger:
    """Logger hijo de 'clipia' (o el raíz si no se da nombre)."""
    if nombre:
        return logging.getLogger("clipia." + nombre)
    return logging.getLogger("clipia")
