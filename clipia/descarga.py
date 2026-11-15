"""Descarga de YouTube con yt-dlp (máximo 1080p)."""
import os
from collections.abc import Callable


def descargar_youtube(url: str, carpeta_destino: str,
                      progreso: Callable[[float], None] | None = None
                      ) -> str:
    """Descarga un video de YouTube en MP4, máximo 1080p.

    Devuelve la ruta del archivo descargado.
    """
    import yt_dlp

    os.makedirs(carpeta_destino, exist_ok=True)

    def gancho_estado(info):
        if progreso and info.get("status") == "downloading":
            total = info.get("total_bytes") or info.get("total_bytes_estimate")
            descargado = info.get("downloaded_bytes", 0)
            if total:
                progreso(min(1.0, descargado / total))

    opciones = {
        "format": ("bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/"
                   "bestvideo[height<=1080]+bestaudio/"
                   "best[height<=1080]/best"),
        "merge_output_format": "mp4",
        "noplaylist": True,
        "restrictfilenames": True,
        "outtmpl": os.path.join(carpeta_destino, "%(title)s.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "progress_hooks": [gancho_estado],
    }
    with yt_dlp.YoutubeDL(opciones) as ydl:
        info = ydl.extract_info(url, download=True)
        # B1: tras el merge (p. ej. webm->mp4), prepare_filename()
        # devuelve la ruta previa al merge (un .webm que ya no existe).
        # requested_downloads trae la ruta del archivo final real.
        descargas = info.get("requested_downloads") or []
        if descargas and descargas[0].get("filepath"):
            ruta = descargas[0]["filepath"]
        else:
            ruta = ydl.prepare_filename(info)
    if progreso:
        progreso(1.0)
    return ruta
