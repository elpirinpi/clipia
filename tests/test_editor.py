"""Tests del editor de clip (Fase 3): forma de onda, texto por tramo
y ajuste de límites. Sin interfaz gráfica."""
from conftest import video_sintetico

from clipia.editor import (
    ajustar_limites,
    extraer_muestras_audio,
    formato_tiempo,
    imagen_waveform,
    palabras_entre,
    texto_entre,
)

SEGMENTOS = [
    {"start": 0.0, "end": 5.0, "text": "Hola mundo, esto es una prueba.",
     "words": [
         {"word": "Hola", "start": 0.0, "end": 0.5},
         {"word": " mundo,", "start": 0.5, "end": 1.0},
         {"word": " esto", "start": 1.0, "end": 1.5},
         {"word": " es", "start": 1.5, "end": 2.0},
         {"word": " una", "start": 2.0, "end": 2.5},
         {"word": " prueba.", "start": 2.5, "end": 3.0},
     ]},
    {"start": 6.0, "end": 10.0, "text": "Segunda frase aquí.",
     "words": [
         {"word": "Segunda", "start": 6.0, "end": 6.5},
         {"word": " frase", "start": 6.5, "end": 7.0},
         {"word": " aquí.", "start": 7.0, "end": 7.5},
     ]},
]


def test_formato_tiempo():
    assert formato_tiempo(0) == "0:00.0"
    assert formato_tiempo(83.4) == "1:23.4"
    assert formato_tiempo(600.1) == "10:00.1"


def test_texto_entre_recorta_por_tramo():
    assert texto_entre(SEGMENTOS, 0.0, 5.0) == \
        "Hola mundo, esto es una prueba."
    assert texto_entre(SEGMENTOS, 6.0, 10.0) == "Segunda frase aquí."
    assert texto_entre(SEGMENTOS, 4.0, 4.5) == ""
    assert "Segunda" in texto_entre(SEGMENTOS, 5.5, 10.0)


def test_palabras_entre_con_margen():
    palabras = palabras_entre(SEGMENTOS, 1.0, 2.0)
    # "una" empieza justo en 2.0: es la primera palabra tras el tramo.
    assert [p["word"].strip() for p in palabras] == ["esto", "es"]
    con_margen = palabras_entre(SEGMENTOS, 1.0, 2.0, margen=1.0)
    assert "Hola" in [p["word"].strip() for p in con_margen]
    assert palabras_entre(SEGMENTOS, 4.0, 4.5) == []


def test_ajustar_limites_recalcula_texto_y_sujeta():
    clip = {"start": 0.0, "end": 5.0, "score": 1.0, "text": "viejo",
            "video": "v.mp4", "miniatura": "/tmp/antes.jpg"}
    nuevo = ajustar_limites(clip, SEGMENTOS, 6.0, 10.0, 120.0)
    assert nuevo["start"] == 6.0 and nuevo["end"] == 10.0
    assert nuevo["text"] == "Segunda frase aquí."
    assert nuevo["video"] == "v.mp4" and nuevo["score"] == 1.0
    assert nuevo["miniatura"] is None
    # El original no se toca.
    assert clip["start"] == 0.0 and clip["text"] == "viejo"


def test_ajustar_limites_fuera_de_rango_y_minimo():
    clip = {"start": 0.0, "end": 5.0, "score": 1.0, "text": "x"}
    nuevo = ajustar_limites(clip, SEGMENTOS, -10.0, 999.0, 60.0)
    assert nuevo["start"] == 0.0 and nuevo["end"] == 60.0
    nuevo = ajustar_limites(clip, SEGMENTOS, 10.0, 10.0, 60.0)
    assert nuevo["end"] - nuevo["start"] >= 1.0
    nuevo = ajustar_limites(clip, SEGMENTOS, 59.9, 60.0, 60.0)
    assert nuevo["start"] <= 59.0 and nuevo["end"] == 60.0


def test_ajustar_limites_sin_habla(tmp_path):
    clip = {"start": 0.0, "end": 5.0, "score": 1.0, "text": "x"}
    nuevo = ajustar_limites(clip, SEGMENTOS, 4.0, 4.5, 60.0)
    assert nuevo["text"] == "Sin habla en este tramo"


def test_extraer_muestras_audio(tmp_path):
    video = video_sintetico(tmp_path / "origen.mp4", duracion=10.0)
    muestras = extraer_muestras_audio(video, 2.0, 8.0, n_barras=60)
    assert len(muestras) == 60
    assert all(0.0 <= m <= 1.0 for m in muestras)
    # Tono constante: casi todas las barras cerca del máximo.
    assert sum(m > 0.9 for m in muestras) >= 50


def test_extraer_muestras_audio_sin_audio(tmp_path):
    video = video_sintetico(tmp_path / "silencio.mp4", duracion=5.0,
                            audio=False)
    assert extraer_muestras_audio(video, 0.0, 5.0) == []


def test_extraer_muestras_audio_ruta_inexistente():
    assert extraer_muestras_audio("/tmp/no_existe.mp4", 0.0, 5.0) == []


def test_imagen_waveform():
    imagen = imagen_waveform([0.0, 0.5, 1.0, 0.5, 0.0], 100, 40)
    assert imagen.size == (100, 40)
    assert imagen.mode == "RGB"
    # Con muestras hay píxeles de onda (no todo fondo).
    colores = imagen.getcolors(maxcolors=10000)
    assert len(colores) > 1


def test_imagen_waveform_seleccion_resalta():
    muestras = [1.0] * 10
    imagen = imagen_waveform(muestras, 100, 40,
                             color_onda="#0000FF",
                             color_seleccion="#FF0000",
                             seleccion=(0.2, 0.4))
    # Una barra dentro de la selección es roja, una fuera es azul.
    assert imagen.getpixel((25, 20)) == (255, 0, 0)
    assert imagen.getpixel((85, 20)) == (0, 0, 255)


def test_imagen_waveform_sin_muestras():
    imagen = imagen_waveform([], 100, 40, color_fondo="#010203")
    assert imagen.getpixel((50, 20)) == (1, 2, 3)
