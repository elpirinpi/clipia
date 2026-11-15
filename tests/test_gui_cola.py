"""Tests de la cola multi-video y de pegar URL (Fase 3)."""
import tkinter as tk
from unittest import mock

from test_gui_exportar import SEGMENTOS, ColaFalsa, _con_cola_falsa

import main as app_mod

URL = "https://www.youtube.com/watch?v=abc123"


def test_pegar_url_copia_url_del_portapapeles(app):
    app.entrada_archivo.insert(0, "video.mp4")
    with mock.patch.object(app, "clipboard_get", return_value=URL):
        app._pegar_url()
    assert app.entrada_url.get() == URL
    assert app.entrada_archivo.get() == ""


def test_pegar_url_rechaza_texto_sin_url(app):
    with mock.patch.object(app, "clipboard_get",
                           return_value="esto no es una url"), \
            mock.patch.object(app_mod.messagebox, "showinfo") as info:
        app._pegar_url()
    assert app.entrada_url.get() == ""
    info.assert_called_once()


def test_pegar_url_portapapeles_vacio_no_revienta(app):
    with mock.patch.object(app, "clipboard_get",
                           side_effect=tk.TclError("vacío")), \
            mock.patch.object(app_mod.messagebox, "showinfo") as info:
        app._pegar_url()
    assert app.entrada_url.get() == ""
    info.assert_called_once()


def test_mostrar_cola_vacia(app):
    app._mostrar_cola()
    textos = [w.cget("text") for w in app.marco_cola.winfo_children()]
    assert textos == ["Sin videos en cola"]


def test_agregar_videos_cola_sin_duplicados(app):
    rutas = ("C:/videos/uno.mp4", "C:/videos/dos.mp4")
    with mock.patch.object(app_mod.filedialog, "askopenfilenames",
                           return_value=rutas):
        app._agregar_videos_cola()
        app._agregar_videos_cola()
    assert [v["ruta"] for v in app.cola_videos] == list(rutas)
    assert all(v["estado"] == "pendiente" for v in app.cola_videos)
    textos = [w.cget("text") for w in app.marco_cola.winfo_children()]
    assert textos == ["uno.mp4 — pendiente", "dos.mp4 — pendiente"]


def test_bloquear_deshabilita_cola_y_pegar(app):
    widgets = (app.boton_pegar_url, app.boton_agregar_cola,
               app.boton_analizar_cola)
    app._bloquear(True)
    for w in widgets:
        assert str(w.cget("state")) == "disabled", w
    app._bloquear(False)
    for w in widgets:
        assert str(w.cget("state")) == "normal", w


def test_analizar_video_devuelve_resultado(app, tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"fake")
    clips = [{"start": 0.0, "end": 5.0, "score": 1.0, "text": "uno"}]
    avisos = []
    with mock.patch.object(app_mod.core, "obtener_duracion",
                           return_value=120.0), \
            mock.patch.object(app_mod.core, "transcribir",
                              return_value=list(SEGMENTOS)), \
            mock.patch.object(app_mod.core, "detectar_momentos",
                              return_value=[dict(c) for c in clips]):
        resultado = app._analizar_video(str(video), "",
                                        lambda t, v: avisos.append((t, v)))
    assert resultado["ruta_video"] == str(video)
    assert resultado["duracion"] == 120.0
    assert resultado["segmentos"] == SEGMENTOS
    assert resultado["candidatos"][0]["video"] == str(video)
    assert any("Transcribiendo" in t for t, _v in avisos)


def test_analizar_video_sin_habla_lanza_error(app, tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"fake")
    with mock.patch.object(app_mod.core, "obtener_duracion",
                           return_value=120.0), \
            mock.patch.object(app_mod.core, "transcribir",
                              return_value=[]):
        try:
            app._analizar_video(str(video), "", lambda t, v: None)
        except RuntimeError as error:
            assert "habla" in str(error)
        else:
            raise AssertionError("no lanzó RuntimeError")


def test_hilo_cola_procesa_varios_y_marca_error(app, tmp_path):
    video_a = str(tmp_path / "a.mp4")
    video_b = str(tmp_path / "b.mp4")
    app.cola_videos = [{"ruta": video_a, "estado": "pendiente",
                        "error": None},
                       {"ruta": video_b, "estado": "pendiente",
                        "error": None}]

    def falso_analizar(ruta, url, al_progreso):
        if ruta == video_b:
            raise RuntimeError("video roto")
        return {"ruta_video": ruta, "duracion": 60.0,
                "segmentos": list(SEGMENTOS),
                "candidatos": [{"start": 0.0, "end": 5.0, "score": 1.0,
                                "text": "uno", "video": ruta}]}

    with mock.patch.object(app, "_analizar_video",
                           side_effect=falso_analizar), \
            mock.patch.object(app, "_generar_miniaturas"):
        app._hilo_cola()
        app._procesar_cola()
    assert app.cola_videos[0]["estado"] == "listo"
    assert app.cola_videos[1]["estado"] == "error"
    assert "video roto" in app.cola_videos[1]["error"]
    assert len(app.candidatos) == 1
    assert app.candidatos[0]["video"] == video_a
    assert app.segmentos_por_video[video_a] == SEGMENTOS
    assert "1 de 2 video(s)" in app.etiqueta_estado.cget("text")


def _textos_tarjetas(app):
    """Textos de los checkboxes de las tarjetas de clips."""

    def recorrer(widget):
        textos = []
        for hijo in widget.winfo_children():
            if isinstance(hijo, tk.Checkbutton) or (
                    hijo.__class__.__name__ == "CTkCheckBox"):
                textos.append(hijo.cget("text"))
            textos.extend(recorrer(hijo))
        return textos

    return recorrer(app.lista_clips)


def test_mostrar_clips_muestra_origen_con_varios_videos(app):
    app.duracion_video = 120.0
    app.candidatos = [
        {"start": 0.0, "end": 30.0, "score": 1.0, "text": "uno",
         "video": "C:/videos/uno.mp4"},
        {"start": 0.0, "end": 30.0, "score": 1.0, "text": "dos",
         "video": "C:/videos/dos.mp4"},
    ]
    app._mostrar_clips()
    textos = _textos_tarjetas(app)
    assert any("uno.mp4" in t for t in textos)
    assert any("dos.mp4" in t for t in textos)


def test_mostrar_clips_sin_varios_videos_no_muestra_origen(app):
    app.duracion_video = 120.0
    app.candidatos = [
        {"start": 0.0, "end": 30.0, "score": 1.0, "text": "uno",
         "video": "C:/videos/uno.mp4"},
    ]
    app._mostrar_clips()
    textos = _textos_tarjetas(app)
    assert len(textos) == 1
    assert "uno.mp4" not in textos[0]


def test_hilo_exportar_usa_video_de_cada_clip(app, tmp_path):
    """Cada trabajo sale de su propio video, con sus segmentos y el
    nombre base de ese video."""
    ColaFalsa.instancias.clear()
    app.carpeta_salida = str(tmp_path)
    clips = [{"start": 0.0, "end": 5.0, "score": 1.0, "text": "uno",
              "video": "C:/videos/uno.mp4"},
             {"start": 0.0, "end": 5.0, "score": 1.0, "text": "dos",
              "video": "C:/videos/dos.mp4"}]
    segmentos_dos = [{"start": 0.0, "end": 10.0, "text": "otro",
                      "words": []}]
    por_video = {"C:/videos/uno.mp4": list(SEGMENTOS),
                 "C:/videos/dos.mp4": segmentos_dos}
    with _con_cola_falsa(), mock.patch.object(
            app_mod.messagebox, "showinfo"):
        app._hilo_exportar(clips, "C:/videos/uno.mp4", SEGMENTOS, False,
                           por_video)
    trabajos = ColaFalsa.instancias[-1].trabajos
    assert [t.ruta_video for t in trabajos] == ["C:/videos/uno.mp4",
                                                "C:/videos/dos.mp4"]
    assert trabajos[0].segmentos == SEGMENTOS
    assert trabajos[1].segmentos == segmentos_dos
    assert [t.nombre for t in trabajos] == ["uno_clip01_000-005.mp4",
                                            "dos_clip02_000-005.mp4"]


def test_generar_miniaturas_no_regenera_existentes(app, tmp_path):
    existente = tmp_path / "ya.jpg"
    existente.write_bytes(b"fake")
    app.ruta_video = "video.mp4"
    app.candidatos = [
        {"start": 0.0, "end": 5.0, "score": 1.0, "text": "ya",
         "miniatura": str(existente)},
        {"start": 5.0, "end": 10.0, "score": 1.0, "text": "nuevo"},
    ]
    llamadas = []

    def falso_generar(ruta_video, instante, ruta_salida, **kwargs):
        llamadas.append(instante)
        with open(ruta_salida, "wb") as archivo:
            archivo.write(b"fake")
        return ruta_salida

    with mock.patch.object(app_mod.core, "generar_miniatura",
                           side_effect=falso_generar):
        app._generar_miniaturas()
    assert llamadas == [7.5]
    assert app.candidatos[0]["miniatura"] == str(existente)
    assert app.candidatos[1]["miniatura"]
