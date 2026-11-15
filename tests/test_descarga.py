"""Tests de descarga de YouTube (B1, B2). Sin red: yt-dlp va mockeado."""
from unittest import mock

import pytest
import yt_dlp

import clipia_core as core
from clipia.descarga import (
    ErrorDescarga,
    clasificar_error_descarga,
    mensaje_error_descarga,
)


def _info_ok(tmp_path):
    return {"requested_downloads": [{"filepath": str(tmp_path / "v.mp4")}]}


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


# --- Fase 4: cookies y errores accionables -------------------------------

def test_descargar_youtube_con_cookies_pasa_la_tupla(tmp_path):
    """Con navegador=chrome, yt-dlp recibe cookiesfrombrowser."""
    with mock.patch("yt_dlp.YoutubeDL") as mock_ydl_cls:
        instancia = mock_ydl_cls.return_value.__enter__.return_value
        instancia.extract_info.return_value = _info_ok(tmp_path)
        core.descargar_youtube("https://www.youtube.com/watch?v=abc",
                               str(tmp_path), navegador="chrome")
    opciones = mock_ydl_cls.call_args.args[0]
    assert opciones.get("cookiesfrombrowser") == ("chrome",)


@pytest.mark.parametrize("navegador", [None, "ninguno", "", "safari",
                                       "CHROME"])
def test_descargar_youtube_sin_cookies_validas_no_pasa_opcion(
        tmp_path, navegador):
    """Sin navegador válido no se pasa cookiesfrombrowser."""
    with mock.patch("yt_dlp.YoutubeDL") as mock_ydl_cls:
        instancia = mock_ydl_cls.return_value.__enter__.return_value
        instancia.extract_info.return_value = _info_ok(tmp_path)
        core.descargar_youtube("https://www.youtube.com/watch?v=abc",
                               str(tmp_path), navegador=navegador)
    opciones = mock_ydl_cls.call_args.args[0]
    assert "cookiesfrombrowser" not in opciones


def test_descargar_youtube_reintenta_sin_cookies_si_fallan(tmp_path):
    """Si las cookies fallan, se reintenta una vez sin ellas."""
    error_cookies = yt_dlp.utils.DownloadError(
        "ERROR: Could not get cookies from browser Chrome: "
        "the browser is locked")
    with mock.patch("yt_dlp.YoutubeDL") as mock_ydl_cls:
        instancia = mock_ydl_cls.return_value.__enter__.return_value
        instancia.extract_info.side_effect = [error_cookies,
                                              _info_ok(tmp_path)]
        ruta = core.descargar_youtube(
            "https://www.youtube.com/watch?v=abc", str(tmp_path),
            navegador="chrome")
    assert ruta == str(tmp_path / "v.mp4")
    assert mock_ydl_cls.call_count == 2
    primera = mock_ydl_cls.call_args_list[0].args[0]
    segunda = mock_ydl_cls.call_args_list[1].args[0]
    assert primera.get("cookiesfrombrowser") == ("chrome",)
    assert "cookiesfrombrowser" not in segunda


def test_descargar_youtube_no_reintenta_errores_que_no_son_cookies(
        tmp_path):
    """Un error de anti-bot con cookies NO se reintenta sin ellas:
    el segundo intento fallaría igual y solo pierde tiempo."""
    error_bot = yt_dlp.utils.DownloadError(
        "ERROR: Sign in to confirm you're not a bot")
    with mock.patch("yt_dlp.YoutubeDL") as mock_ydl_cls:
        instancia = mock_ydl_cls.return_value.__enter__.return_value
        instancia.extract_info.side_effect = error_bot
        with pytest.raises(ErrorDescarga):
            core.descargar_youtube(
                "https://www.youtube.com/watch?v=abc", str(tmp_path),
                navegador="chrome")
    assert mock_ydl_cls.call_count == 1


@pytest.mark.parametrize("texto,codigo", [
    ("Sign in to confirm you're not a bot", "bot"),
    ("Please sign in to confirm you are not a bot", "bot"),
    ("Could not get cookies from browser", "cookies"),
    ("ERROR: no cookies found for youtube.com", "cookies"),
    ("Unable to extract uploader id", "obsoleto"),
    ("Failed to extract any player response", "obsoleto"),
    ("regex not matched", "obsoleto"),
    ("ERROR: Video unavailable", "no_disponible"),
    ("This video is private", "no_disponible"),
    ("HTTP Error 404: Not Found", "no_disponible"),
    ("Unsupported URL: https://ejemplo.com/x", "url"),
    ("HTTP Error 403: Forbidden", "prohibido"),
    ("Connection timed out", "red"),
    ("Name or service not known", "red"),
    ("Failed to establish a new connection", "red"),
    ("No space left on device", "espacio"),
    ("Permission denied", "permisos"),
    ("algo raro sin clasificar", "otro"),
])
def test_clasificar_error_descarga(texto, codigo):
    assert clasificar_error_descarga(texto) == codigo


def test_mensaje_error_descarga_es_accionable():
    """Cada código produce un mensaje en español que dice qué hacer."""
    assert "Ajustes" in mensaje_error_descarga(
        yt_dlp.utils.DownloadError("Sign in to confirm you're not a bot"))
    assert "Actualizar yt-dlp" in mensaje_error_descarga(
        yt_dlp.utils.DownloadError("Unable to extract uploader id"))
    assert "conexión" in mensaje_error_descarga(
        yt_dlp.utils.DownloadError("Connection timed out"))
    otro = mensaje_error_descarga(
        yt_dlp.utils.DownloadError("algo raro sin clasificar"))
    assert "algo raro sin clasificar" in otro


def test_descargar_youtube_envuelve_el_error_en_error_descarga(tmp_path):
    """El fallo sube como ErrorDescarga (mensaje accionable + código),
    no como el DownloadError crudo de yt-dlp."""
    with mock.patch("yt_dlp.YoutubeDL") as mock_ydl_cls:
        instancia = mock_ydl_cls.return_value.__enter__.return_value
        instancia.extract_info.side_effect = yt_dlp.utils.DownloadError(
            "HTTP Error 403: Forbidden")
        with pytest.raises(ErrorDescarga) as excinfo:
            core.descargar_youtube("https://www.youtube.com/watch?v=abc",
                                   str(tmp_path))
    assert excinfo.value.codigo == "prohibido"
    assert "403" in str(excinfo.value)
