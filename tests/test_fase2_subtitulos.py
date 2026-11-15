"""Fase 2: subtítulos karaoke + presets + MarginV configurable."""
import pytest

from clipia.cola import ColaExportacion, TrabajoExportacion
from clipia.config import cargar_config, guardar_config
from clipia.subtitulos import (
    PLANTILLA_ASS,
    PRESETS_SUBTITULOS,
    _fragmentos_karaoke,
    generar_subtitulos_ass,
)


def _segmentos():
    palabras = []
    for i, texto in enumerate(["hola", "mundo", "esto", "es", "una",
                               "prueba", "de", "karaoke"]):
        palabras.append({"word": " " + texto, "start": i * 0.5,
                         "end": i * 0.5 + 0.4})
    palabras[-1]["word"] += "."
    return [{"start": 0.0, "end": 4.0,
             "text": " ".join(p["word"] for p in palabras),
             "words": palabras}]


def _leer_ass(tmp_path, estilo="Shorts clásico", margen_vertical=None):
    ruta = str(tmp_path / "salida.ass")
    generar_subtitulos_ass(_segmentos(), 0.0, 4.0, ruta, estilo,
                           margen_vertical)
    with open(ruta, encoding="utf-8") as archivo:
        return archivo.read()


def _linea_estilo(contenido):
    for linea in contenido.splitlines():
        if linea.startswith("Style:"):
            return linea
    raise AssertionError("sin línea Style")


def _dialogues(contenido):
    return [linea for linea in contenido.splitlines()
            if linea.startswith("Dialogue:")]


def test_presets_existentes():
    assert set(PRESETS_SUBTITULOS) == {
        "Shorts clásico", "Hormozi", "Minimal", "Neón"}


def test_clasico_sin_karaoke_y_igual_que_antes(tmp_path):
    contenido = _leer_ass(tmp_path)
    assert "\\k" not in contenido
    assert _linea_estilo(contenido) == _linea_estilo(PLANTILLA_ASS)
    assert _dialogues(contenido)


def test_hormozi_karaoke_mayusculas_y_amarillo(tmp_path):
    contenido = _leer_ass(tmp_path, "Hormozi")
    estilo = _linea_estilo(contenido)
    assert ",72," in estilo  # tamaño 72
    assert "&H0000FFFF" in estilo  # palabra activa amarilla
    dialogos = _dialogues(contenido)
    assert dialogos
    assert "\\k" in dialogos[0]
    assert "HOLA" in dialogos[0]
    assert "hola" not in dialogos[0].split(",,")[-1]


def test_neon_karaoke_cian_magenta(tmp_path):
    contenido = _leer_ass(tmp_path, "Neón")
    estilo = _linea_estilo(contenido)
    assert "&H00FFFF00" in estilo  # cian (activa)
    assert "&H00FF00FF" in estilo  # magenta (pendiente)
    assert "\\k" in _dialogues(contenido)[0]


def test_minimal_sin_karaoke_y_mas_pequeno(tmp_path):
    contenido = _leer_ass(tmp_path, "Minimal")
    estilo = _linea_estilo(contenido)
    assert ",48," in estilo
    assert "\\k" not in contenido
    # No negrita: Bold 0 (el campo 8 de la línea Style).
    assert estilo.split(",")[7] == "0"


def test_karaoke_duraciones_por_palabra():
    # Palabra de 0.5 s -> \k50; de 0.25 s -> \k25.
    palabras = [{"word": " larga", "start": 0.0, "end": 0.5},
                {"word": " corta", "start": 0.5, "end": 0.75}]
    frase = {"start": 0.0, "end": 0.75, "text": "", "words": palabras}
    fragmentos = _fragmentos_karaoke(frase)
    assert len(fragmentos) == 1
    assert fragmentos[0][2] == [("larga", 50), ("corta", 25)]


def test_karaoke_sin_timestamps_no_revienta(tmp_path):
    segmentos = [{"start": 0.0, "end": 4.0, "text": "hola mundo",
                  "words": []}]
    ruta = str(tmp_path / "salida.ass")
    generar_subtitulos_ass(segmentos, 0.0, 4.0, ruta, "Hormozi", None)
    with open(ruta, encoding="utf-8") as archivo:
        contenido = archivo.read()
    assert "\\k" not in contenido  # sin timestamps no hay karaoke
    assert "HOLA MUNDO" in contenido


def test_margen_vertical_personalizado(tmp_path):
    contenido = _leer_ass(tmp_path, "Shorts clásico", 150)
    # MarginV es el campo 21 de la línea Style.
    assert _linea_estilo(contenido).split(",")[21] == "150"


def test_margen_vertical_por_defecto_del_preset(tmp_path):
    contenido = _leer_ass(tmp_path, "Minimal", None)
    assert _linea_estilo(contenido).split(",")[21] == "200"


def test_estilo_desconocido_usa_clasico(tmp_path):
    contenido = _leer_ass(tmp_path, "Inexistente", None)
    assert _linea_estilo(contenido) == _linea_estilo(PLANTILLA_ASS)


def test_config_margen_vertical(tmp_path):
    ruta = str(tmp_path / "config.json")
    config = cargar_config(ruta)
    assert config["margen_vertical"] == 300
    assert config["estilo_subtitulos"] == "Shorts clásico"
    guardar_config({**config, "estilo_subtitulos": "Hormozi",
                    "margen_vertical": 150}, ruta)
    config2 = cargar_config(ruta)
    assert config2["estilo_subtitulos"] == "Hormozi"
    assert config2["margen_vertical"] == 150


def test_cola_pasa_estilo_y_margen(tmp_path):
    llamadas = []

    def falso_ass(*args):
        llamadas.append(args)

    def falso_exportar(ruta_video, inicio, fin, ruta_ass, ruta_salida,
                       progreso=None, rostros=None, encoder=None,
                       cancelar=None):
        with open(ruta_salida, "wb") as archivo:
            archivo.write(b"fake")
        return ruta_salida

    trabajo = TrabajoExportacion(
        clip={"start": 0.0, "end": 5.0, "score": 1.0, "text": "t"},
        ruta_video="video.mp4", segmentos=[],
        carpeta_salida=str(tmp_path), nombre="clip.mp4",
        seguir_rostros=False, estilo="Neón", margen_vertical=150)
    cola = ColaExportacion(workers=1, exportar=falso_exportar,
                           generar_ass=falso_ass)
    resultados = cola.exportar([trabajo])
    assert resultados[0].ok
    assert len(llamadas) == 1
    assert llamadas[0][4] == "Neón"
    assert llamadas[0][5] == 150


# -- GUI: Ajustes ----------------------------------------------------------

def test_ajustes_muestran_estilo_y_margen(app, monkeypatch):
    from main import DialogoAjustes

    guardados = {}

    def al_guardar(valores):
        guardados.update(valores)

    dialogo = DialogoAjustes(app, app.config, al_guardar)
    try:
        assert dialogo.variable_estilo.get() == "Shorts clásico"
        assert dialogo.entrada_margen.get() == "300"
        dialogo.variable_estilo.set("Hormozi")
        dialogo.entrada_margen.delete(0, "end")
        dialogo.entrada_margen.insert(0, "150")
        dialogo._guardar()
    finally:
        try:
            dialogo.destroy()
        except Exception:
            pass
    assert guardados["estilo_subtitulos"] == "Hormozi"
    assert guardados["margen_vertical"] == 150


def test_ajustes_margen_invalido_usa_300(app):
    from main import DialogoAjustes

    guardados = {}
    dialogo = DialogoAjustes(app, app.config, guardados.update)
    try:
        dialogo.entrada_margen.delete(0, "end")
        dialogo.entrada_margen.insert(0, "no es un número")
        dialogo._guardar()
    finally:
        try:
            dialogo.destroy()
        except Exception:
            pass
    assert guardados["margen_vertical"] == 300


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
