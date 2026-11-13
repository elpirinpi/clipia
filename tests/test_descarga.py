# -*- coding: utf-8 -*-
"""Tests de descarga de YouTube (B1, B2). Sin red: yt-dlp va mockeado."""
from unittest import mock

import clipia_core as core


def test_descargar_youtube_devuelve_ruta_final_tras_merge(tmp_path):
    """B1: con merge webm->mp4, la ruta devuelta es la del mp4 final,
    no la .webm que prepare_filename() devuelve antes del merge."""
    info = {
        "requested_downloads": [
            {"filepath": str(tmp_path / "video_final.mp4")}
        ],
    }
    with mock.patch("yt_dlp.YoutubeDL") as mock_ydl_cls:
        instancia = mock_ydl_cls.return_value.__enter__.return_value
        instancia.extract_info.return_value = info
        instancia.prepare_filename.return_value = str(tmp_path / "video.webm")
        ruta = core.descargar_youtube("https://www.youtube.com/watch?v=abc",
                                      str(tmp_path))
    assert ruta == str(tmp_path / "video_final.mp4")


def test_descargar_youtube_sin_requested_downloads_usa_prepare_filename(
        tmp_path):
    """B1 (fallback): si info no trae requested_downloads, se usa
    prepare_filename() como antes."""
    with mock.patch("yt_dlp.YoutubeDL") as mock_ydl_cls:
        instancia = mock_ydl_cls.return_value.__enter__.return_value
        instancia.extract_info.return_value = {}
        instancia.prepare_filename.return_value = str(tmp_path / "video.mp4")
        ruta = core.descargar_youtube("https://www.youtube.com/watch?v=abc",
                                      str(tmp_path))
    assert ruta == str(tmp_path / "video.mp4")


def test_descargar_youtube_con_noplaylist(tmp_path):
    """B2: las opciones incluyen noplaylist (URLs con &list= no deben
    intentar descargar la lista entera)."""
    info = {"requested_downloads": [{"filepath": str(tmp_path / "v.mp4")}]}
    with mock.patch("yt_dlp.YoutubeDL") as mock_ydl_cls:
        instancia = mock_ydl_cls.return_value.__enter__.return_value
        instancia.extract_info.return_value = info
        core.descargar_youtube(
            "https://www.youtube.com/watch?v=abc&list=PL123", str(tmp_path))
    opciones = mock_ydl_cls.call_args.args[0]
    assert opciones.get("noplaylist") is True
