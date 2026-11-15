"""Tests de GUI de guardar/cargar proyecto (Fase 3)."""
import time
from unittest import mock

from test_editor import SEGMENTOS

import main as app_mod
from clipia.proyecto import cargar_proyecto, guardar_proyecto


def _estado_con_clips(app, video):
    app.ruta_video = video
    app.duracion_video = 120.0
    app.segmentos = list(SEGMENTOS)
    app.segmentos_por_video = {video: list(SEGMENTOS)}
    app.duracion_por_video = {video: 120.0}
    app.candidatos = [
        {"start": 0.0, "end": 5.0, "score": 1.0, "text": "uno",
         "video": video, "miniatura": "/tmp/temporal.jpg"},
        {"start": 6.0, "end": 10.0, "score": 0.9, "text": "dos",
         "video": video},
    ]
    app._mostrar_clips()
    app.seleccion[0].set(False)


def test_guardar_proyecto_escribe_archivo(app, tmp_path):
    video = str(tmp_path / "video.mp4")
    _estado_con_clips(app, video)
    # Un video obsoleto (analizado antes, sin clips actuales) no se
    # guarda: solo los videos de los clips actuales.
    app.segmentos_por_video["C:/viejo.mp4"] = list(SEGMENTOS)
    ruta_proyecto = str(tmp_path / "proyecto.clipia")
    with mock.patch.object(app_mod.filedialog, "asksaveasfilename",
                           return_value=ruta_proyecto):
        app._guardar_proyecto()
    cargado = cargar_proyecto(ruta_proyecto)
    assert [v["ruta"] for v in cargado["videos"]] == [video]
    assert cargado["candidatos"][0]["start"] == 0.0
    assert "miniatura" not in cargado["candidatos"][0]
    assert cargado["seleccion"] == [False, True]
    assert cargado["carpeta_salida"] == app.carpeta_salida


def test_guardar_proyecto_sin_clips_avisa(app):
    with mock.patch.object(app_mod.messagebox, "showinfo") as info, \
            mock.patch.object(app_mod.filedialog,
                              "asksaveasfilename") as guardar:
        app._guardar_proyecto()
    info.assert_called_once()
    guardar.assert_not_called()


def _proyecto_en_disco(tmp_path, video, seleccion=(True, False)):
    ruta = str(tmp_path / "proyecto.clipia")
    guardar_proyecto(ruta, {
        "videos": [{"ruta": video, "duracion": 120.0,
                    "segmentos": SEGMENTOS}],
        "candidatos": [
            {"start": 0.0, "end": 5.0, "score": 1.0, "text": "uno",
             "video": video},
            {"start": 6.0, "end": 10.0, "score": 0.9, "text": "dos",
             "video": video}],
        "seleccion": list(seleccion),
        "carpeta_salida": str(tmp_path / "salida"),
    })
    return ruta


def _esperar_miniaturas(app, generar, segundos=5):
    limite = time.time() + segundos
    while not generar.called and time.time() < limite:
        time.sleep(0.05)
    app._procesar_cola()


def test_abrir_proyecto_restaura_estado(app, tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"fake")
    ruta_proyecto = _proyecto_en_disco(tmp_path, str(video))
    with mock.patch.object(app_mod.filedialog, "askopenfilename",
                           return_value=ruta_proyecto), \
            mock.patch.object(app, "_generar_miniaturas") as generar:
        app._abrir_proyecto()
        _esperar_miniaturas(app, generar)
    assert len(app.candidatos) == 2
    assert app.candidatos[0]["text"] == "uno"
    assert app.segmentos_por_video[str(video)] == SEGMENTOS
    assert app.duracion_por_video[str(video)] == 120.0
    assert app.ruta_video == str(video)
    assert [v.get() for v in app.seleccion] == [True, False]
    assert "video.mp4" in app.etiqueta_video.cget("text")
    generar.assert_called()


def test_abrir_proyecto_reubica_video_faltante(app, tmp_path):
    nuevo = tmp_path / "nuevo.mp4"
    nuevo.write_bytes(b"fake")
    ruta_proyecto = _proyecto_en_disco(tmp_path, "C:/ya_no_existe.mp4")
    with mock.patch.object(app_mod.filedialog, "askopenfilename",
                           side_effect=[ruta_proyecto, str(nuevo)]), \
            mock.patch.object(app_mod.messagebox, "askyesno",
                              return_value=True), \
            mock.patch.object(app, "_generar_miniaturas") as generar:
        app._abrir_proyecto()
        _esperar_miniaturas(app, generar)
    assert all(c["video"] == str(nuevo) for c in app.candidatos)
    assert str(nuevo) in app.segmentos_por_video
    assert app.ruta_video == str(nuevo)


def test_abrir_proyecto_sin_reubicar_mantiene_ruta(app, tmp_path):
    ruta_proyecto = _proyecto_en_disco(tmp_path, "C:/ya_no_existe.mp4")
    with mock.patch.object(app_mod.filedialog, "askopenfilename",
                           return_value=ruta_proyecto), \
            mock.patch.object(app_mod.messagebox, "askyesno",
                              return_value=False), \
            mock.patch.object(app, "_generar_miniaturas") as generar:
        app._abrir_proyecto()
        _esperar_miniaturas(app, generar)
    assert app.candidatos[0]["video"] == "C:/ya_no_existe.mp4"
    assert "sin localizar" in app.etiqueta_estado.cget("text")


def test_abrir_proyecto_corrupto_muestra_error(app, tmp_path):
    ruta = tmp_path / "roto.clipia"
    ruta.write_text("{no es json", encoding="utf-8")
    with mock.patch.object(app_mod.filedialog, "askopenfilename",
                           return_value=str(ruta)), \
            mock.patch.object(app_mod.messagebox, "showerror") as error:
        app._abrir_proyecto()
    error.assert_called_once()
    assert app.candidatos == []
