"""Tests del arrastrar y soltar (Fase 3, tkinterdnd2).

El gesto real del sistema operativo (Xdnd/OLE) lo hace tkinterdnd2
y no se puede simular de forma fiable bajo Xvfb; aquí se prueba la
integración (el mixin carga tkdnd en la app CustomTkinter) y la
lógica del manejador <<Drop>> con eventos sintéticos, que es como
tkdnd entrega los datos.
"""
from unittest import mock

import pytest

import main as app_mod


class Evento:
    def __init__(self, data):
        self.data = data


def _datos(app, *rutas):
    """Datos de drop como los entrega tkdnd: la lista Tcl canónica.

    En Windows las rutas llevan barras invertidas, que splitlist
    interpreta como escapes si van sin entrecomillar (las borra y
    convierte \\v en tabulador vertical): por eso la simulación debe
    entrecomillar como Tcl, no pasar la ruta cruda."""
    return app.tk.call("list", *rutas)


@pytest.mark.skipif(not getattr(app_mod, "_DND_DISPONIBLE", False),
                    reason="tkinterdnd2 no está instalado")
def test_dnd_activo_en_la_app(app):
    """La app carga tkdnd y se registra como destino de arrastre."""
    assert app._dnd_activo is True
    assert hasattr(app, "drop_target_register")
    assert hasattr(app, "dnd_bind")


def test_soltar_un_video_lo_pone_en_el_campo(app, tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"fake")
    app._al_soltar(Evento(_datos(app, str(video))))
    assert app.entrada_archivo.get() == str(video)
    assert app.entrada_url.get() == ""
    assert app.cola_videos == []


def test_soltar_varios_videos_los_pone_en_cola(app, tmp_path):
    uno = tmp_path / "mi video.mp4"
    dos = tmp_path / "otro.mkv"
    uno.write_bytes(b"fake")
    dos.write_bytes(b"fake")
    app._al_soltar(Evento(_datos(app, str(uno), str(dos))))
    assert [v["ruta"] for v in app.cola_videos] == [str(uno), str(dos)]
    assert all(v["estado"] == "pendiente" for v in app.cola_videos)


def test_soltar_un_video_con_cola_no_vacia_va_a_la_cola(app, tmp_path):
    app.cola_videos = [{"ruta": "C:/ya.mp4", "estado": "pendiente",
                        "error": None}]
    video = tmp_path / "nuevo.mp4"
    video.write_bytes(b"fake")
    app._al_soltar(Evento(_datos(app, str(video))))
    assert app.entrada_archivo.get() == ""
    assert [v["ruta"] for v in app.cola_videos] == ["C:/ya.mp4",
                                                    str(video)]


def test_soltar_texto_url_lo_pone_en_el_campo_url(app):
    url = "https://www.youtube.com/watch?v=abc123"
    app._al_soltar(Evento(url))
    assert app.entrada_url.get() == url
    assert app.entrada_archivo.get() == ""


def test_soltar_texto_sin_url_no_hace_nada(app):
    app._al_soltar(Evento("hola mundo, esto no es una url"))
    assert app.entrada_url.get() == ""
    assert app.entrada_archivo.get() == ""
    assert app.cola_videos == []


def test_soltar_archivo_no_video_avisa(app, tmp_path):
    texto = tmp_path / "notas.txt"
    texto.write_bytes(b"fake")
    with mock.patch.object(app_mod.messagebox, "showinfo") as info:
        app._al_soltar(Evento(_datos(app, str(texto))))
    info.assert_called_once()
    assert app.cola_videos == []
    assert app.entrada_archivo.get() == ""


def test_soltar_con_trabajo_en_curso_no_hace_nada(app, tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"fake")
    app._bloquear(True)
    try:
        app._al_soltar(Evento(str(video)))
    finally:
        app._bloquear(False)
    assert app.entrada_archivo.get() == ""
    assert app.cola_videos == []
