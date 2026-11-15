"""Editor de clip: forma de onda y ajuste de límites.

Todo es código sin interfaz (probable sin pantalla): la ventana del
editor (main.py) usa estas funciones. La forma de onda se extrae con
ffmpeg (WAV temporal) y se dibuja con numpy + PIL; los límites se
ajustan sobre la transcripción con timestamps por palabra.
"""
import os
import tempfile
import wave

import numpy as np
from PIL import Image, ImageDraw

from .momentos import _frases_de_segmentos
from .procesos import ejecutar

# Barras de la forma de onda y contexto (segundos) que el editor
# muestra alrededor del clip para poder ampliarlo con un clic.
BARRAS_DEFECTO = 160
MARGEN_CONTEXTO = 5.0
# Duración mínima de un clip al ajustar límites.
DURACION_MINIMA_CLIP = 1.0


def formato_tiempo(segundos: float) -> str:
    """Convierte segundos a 'M:SS.d' (ej. 83.4 -> '1:23.4')."""
    segundos = max(0.0, float(segundos))
    minutos = int(segundos // 60)
    resto = segundos - minutos * 60
    return "%d:%04.1f" % (minutos, resto)


def _leer_wav_muestras(ruta_wav: str) -> np.ndarray:
    """Lee un WAV PCM 16 bits a un arreglo float32 normalizado."""
    with wave.open(ruta_wav, "rb") as archivo:
        datos = archivo.readframes(archivo.getnframes())
    return np.frombuffer(datos, dtype=np.int16).astype(np.float32) / 32768.0


def extraer_muestras_audio(ruta_video: str, inicio: float, fin: float,
                           n_barras: int = BARRAS_DEFECTO
                           ) -> list[float]:
    """Amplitud de pico por barra (0.0-1.0) del tramo [inicio, fin].

    Extrae el audio del tramo con ffmpeg (8 kHz mono, suficiente para
    dibujar) y normaliza por el pico del tramo, así la onda siempre
    llena la altura. Devuelve [] si el video no tiene audio o algo
    falla: el editor muestra entonces «sin audio» en vez de reventar.
    """
    if fin <= inicio or n_barras <= 0:
        return []
    try:
        with tempfile.TemporaryDirectory(prefix="clipia_onda_") as carpeta:
            ruta_wav = os.path.join(carpeta, "tramo.wav")
            ejecutar(
                ["ffmpeg", "-y", "-v", "error",
                 "-ss", "%.3f" % max(0.0, inicio),
                 "-t", "%.3f" % (fin - inicio),
                 "-i", ruta_video,
                 "-vn", "-ac", "1", "-ar", "8000",
                 "-c:a", "pcm_s16le", ruta_wav],
                check=True,
            )
            audio = _leer_wav_muestras(ruta_wav)
    except Exception:
        return []
    if audio.size == 0:
        return []
    # Pico por barra (el máximo absoluto del tramo de cada barra).
    trozos = np.array_split(np.abs(audio), n_barras)
    picos = np.array([t.max() if t.size else 0.0 for t in trozos])
    maximo = picos.max()
    if maximo <= 0:
        return [0.0] * n_barras
    return [round(float(p / maximo), 3) for p in picos]


def imagen_waveform(muestras: list[float], ancho: int, alto: int,
                    color_fondo: str = "#171B22",
                    color_onda: str = "#3B82F6",
                    color_seleccion: str = "#E5484D",
                    seleccion: tuple[float, float] | None = None
                    ) -> Image.Image:
    """Dibuja la forma de onda como imagen PIL.

    `seleccion` es (fracción_inicio, fracción_fin) en 0.0-1.0: las
    barras dentro se pintan en `color_seleccion` y las de fuera en
    `color_onda`. Sin muestras devuelve el fondo vacío.
    """
    imagen = Image.new("RGB", (max(1, ancho), max(1, alto)), color_fondo)
    if not muestras:
        return imagen
    dibujo = ImageDraw.Draw(imagen)
    n = len(muestras)
    ancho_barra = max(1, ancho // n)
    for i, valor in enumerate(muestras):
        x0 = i * ancho_barra
        x1 = min(ancho - 1, x0 + max(1, ancho_barra - 1))
        altura_barra = max(1, int(valor * (alto - 4)))
        y0 = (alto - altura_barra) // 2
        y1 = y0 + altura_barra
        dentro = False
        if seleccion is not None:
            frac = (i + 0.5) / n
            dentro = seleccion[0] <= frac <= seleccion[1]
        dibujo.rectangle([x0, y0, x1, y1],
                         fill=color_seleccion if dentro else color_onda)
    return imagen


def palabras_entre(segmentos: list[dict], inicio: float, fin: float,
                   margen: float = 0.0) -> list[dict]:
    """Palabras con timestamp en [inicio - margen, fin + margen].

    Devuelve [{"start", "end", "word"}] en orden. Sin timestamps por
    palabra devuelve [] (el editor muestra entonces el texto por
    frases, sin clic por palabra).
    """
    palabras = []
    for seg in segmentos:
        for palabra in (seg.get("words") or []):
            if (palabra["end"] > inicio - margen
                    and palabra["start"] < fin + margen):
                palabras.append({"start": float(palabra["start"]),
                                 "end": float(palabra["end"]),
                                 "word": palabra["word"]})
    return palabras


def texto_entre(segmentos: list[dict], inicio: float, fin: float) -> str:
    """Texto hablado en el tramo [inicio, fin]."""
    frases = _frases_de_segmentos(segmentos)
    partes = [f["text"] for f in frases
              if f["end"] > inicio and f["start"] < fin]
    return " ".join(partes).strip()


def ajustar_limites(clip: dict, segmentos: list[dict],
                    inicio: float, fin: float,
                    duracion: float) -> dict:
    """Devuelve una copia del clip con los límites ajustados.

    Sujeta los tiempos a [0, duración] y a una duración mínima de 1 s,
    recalcula el texto con la transcripción del tramo y descarta la
    miniatura (era del punto medio anterior: hay que regenerarla).
    """
    duracion = max(DURACION_MINIMA_CLIP, float(duracion))
    inicio = min(max(0.0, float(inicio)), duracion - DURACION_MINIMA_CLIP)
    fin = min(max(float(fin), inicio + DURACION_MINIMA_CLIP), duracion)
    if fin - inicio < DURACION_MINIMA_CLIP:
        fin = min(duracion, inicio + DURACION_MINIMA_CLIP)
    nuevo = dict(clip)
    nuevo["start"] = round(inicio, 1)
    nuevo["end"] = round(fin, 1)
    texto = texto_entre(segmentos, inicio, fin)
    nuevo["text"] = texto if texto else "Sin habla en este tramo"
    nuevo["miniatura"] = None
    return nuevo
