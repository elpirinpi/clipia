"""
Prueba de punta a punta de ClipIA (sin interfaz gráfica).

Uso:
    python test_pipeline.py --video video_prueba.mp4 --salida ./salida_prueba

Pasos: transcribir -> detectar momentos -> detectar rostros y vista
previa -> exportar clips -> verificar con ffprobe que los clips son
MP4 verticales 1080x1920 válidos, con la duración pedida (±0.5 s),
audio AAC y subtítulos realmente quemados (eventos ASS + píxeles de
texto en el fotograma). Imprime los tiempos medidos de cada fase.
"""

import argparse
import json
import os
import subprocess
import sys
import threading
import time

import numpy as np
from PIL import Image

import clipia_core as core

# Tolerancia de duración pedida vs real (segundos).
TOLERANCIA_DURACION = 0.5
# Mínimo de píxeles casi blancos en la banda de subtítulos para dar
# por quemado el texto (una línea a 64 px tiene miles).
MIN_PIXELES_SUBTITULO = 500
# Límite de la detección de rostros (igual que en la GUI).
TIMEOUT_ROSTROS = 60


def verificar_clip(ruta: str) -> dict:
    """Verifica con ffprobe que el clip es un MP4 vertical válido."""
    resultado = subprocess.run(
        ["ffprobe", "-v", "error",
         "-show_entries", "stream=width,height,codec_name,codec_type",
         "-show_entries", "format=duration",
         "-of", "json", ruta],
        capture_output=True, text=True, timeout=60,
    )
    if resultado.returncode != 0:
        raise RuntimeError("ffprobe falló en %s: %s"
                           % (ruta, resultado.stderr.strip()))
    info = json.loads(resultado.stdout)
    video = next(f for f in info["streams"]
                 if f["codec_type"] == "video")
    audios = [f for f in info["streams"] if f["codec_type"] == "audio"]
    return {
        "ancho": video["width"],
        "alto": video["height"],
        "codec": video["codec_name"],
        "audio": audios[0]["codec_name"] if audios else None,
        "duracion": float(info["format"]["duration"]),
        "tamano_kb": os.path.getsize(ruta) // 1024,
    }


def extraer_fotograma(ruta_video: str, segundo: float,
                      ruta_salida: str) -> str:
    """Extrae un fotograma en el segundo indicado (para revisar subtítulos)."""
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-ss", "%.2f" % segundo,
         "-i", ruta_video, "-frames:v", "1", ruta_salida],
        check=True, timeout=60,
    )
    return ruta_salida


def eventos_ass(ruta_ass: str) -> list[float]:
    """Inicios (en segundos) de los eventos Dialogue de un .ass."""
    inicios = []
    with open(ruta_ass, encoding="utf-8") as archivo:
        for linea in archivo:
            if not linea.startswith("Dialogue:"):
                continue
            campos = linea.rstrip("\n").split(",", 9)
            partes = campos[1].split(":")
            segundos = (int(partes[0]) * 3600 + int(partes[1]) * 60
                        + float(partes[2]))
            inicios.append(segundos)
    return inicios


def contar_pixeles_subtitulo(ruta_fotograma: str) -> int:
    """Píxeles casi blancos en la banda inferior del fotograma.

    Los subtítulos son texto blanco con borde negro, centrados abajo
    (MarginV 300 en un lienzo de 1920 px). Si el texto está quemado,
    la banda tiene miles de píxeles casi blancos.
    """
    imagen = np.asarray(Image.open(ruta_fotograma).convert("RGB"))
    alto = imagen.shape[0]
    banda = imagen[int(alto * 0.75):int(alto * 0.95)]
    blancos = (banda[:, :, 0] > 240) & (banda[:, :, 1] > 240) \
        & (banda[:, :, 2] > 240)
    return int(blancos.sum())


def detectar_rostros_con_limite(ruta_video: str, inicio: float, fin: float,
                                timeout: int = TIMEOUT_ROSTROS
                                ) -> tuple[list, bool]:
    """Detecta rostros con límite de tiempo (devuelve muestras y si
    se completó a tiempo)."""
    resultado: list = []

    def trabajo():
        try:
            resultado.extend(core.detectar_rostros(
                ruta_video, inicio, fin))
        except Exception:
            pass

    hilo = threading.Thread(target=trabajo, daemon=True)
    hilo.start()
    hilo.join(timeout)
    return resultado, not hilo.is_alive()


def main() -> int:
    parser = argparse.ArgumentParser(description="Prueba de ClipIA")
    parser.add_argument("--video", required=True, help="Video de entrada")
    parser.add_argument("--salida", required=True,
                        help="Carpeta donde se guardan los clips")
    parser.add_argument("--modelo", default="base",
                        help="Modelo Whisper (base por defecto)")
    parser.add_argument("--clips", type=int, default=2,
                        help="Cuántos clips exportar (2 por defecto)")
    args = parser.parse_args()

    os.makedirs(args.salida, exist_ok=True)
    tiempos = {}

    print("== ClipIA: prueba de punta a punta ==")
    print("Video:", args.video)
    duracion = core.obtener_duracion(args.video)
    print("Duración del video: %.1f s (%s)"
          % (duracion, core.formato_hora(duracion)))

    # 1. Transcripción
    t0 = time.time()
    print("\n[1/5] Transcribiendo con faster-whisper (%s)..." % args.modelo)
    segmentos = core.transcribir(args.video, modelo=args.modelo)
    tiempos["transcripcion"] = time.time() - t0
    palabras = sum(len(s["text"].split()) for s in segmentos)
    print("      Segmentos: %d · Palabras: %d · Tiempo: %.1f s"
          % (len(segmentos), palabras, tiempos["transcripcion"]))
    if segmentos:
        print("      Ejemplo: %r" % segmentos[0]["text"][:120])

    # 2. Detección de momentos
    t0 = time.time()
    print("\n[2/5] Detectando momentos...")
    candidatos = core.detectar_momentos(segmentos, duracion, cantidad=10)
    tiempos["momentos"] = time.time() - t0
    print("      Candidatos: %d · Tiempo: %.2f s"
          % (len(candidatos), tiempos["momentos"]))
    for i, c in enumerate(candidatos[:10], 1):
        print("      %2d. %s-%s (%s) puntos=%.2f  %r"
              % (i, core.formato_hora(c["start"]), core.formato_hora(c["end"]),
                 core.formato_hora(c["end"] - c["start"]), c["score"],
                 c["text"][:70]))

    if not candidatos:
        print("\nFALLO: no se detectaron momentos (¿el video tiene habla?).")
        return 1

    primer_clip = candidatos[0]

    # 3. Rostros + vista previa del primer clip
    t0 = time.time()
    print("\n[3/5] Detectando rostros en el primer clip...")
    rostros, a_tiempo = detectar_rostros_con_limite(
        args.video, primer_clip["start"], primer_clip["end"])
    tiempos["rostros"] = time.time() - t0
    if not a_tiempo:
        print("      AVISO: la detección superó %d s; se sigue con el "
              "recorte centrado." % TIMEOUT_ROSTROS)
        rostros = []
    print("      Muestras: %d · Tiempo: %.1f s"
          % (len(rostros), tiempos["rostros"]))

    t0 = time.time()
    print("      Generando vista previa del primer clip...")
    ruta_preview = os.path.join(args.salida, "preview_clip01.mp4")
    core.generar_vista_previa(args.video, primer_clip["start"],
                              primer_clip["end"], ruta_preview,
                              rostros=rostros or None)
    tiempos["vista_previa"] = time.time() - t0
    info_preview = verificar_clip(ruta_preview)
    preview_ok = (info_preview["ancho"] == 540
                  and info_preview["alto"] == 960)
    print("      Vista previa: %dx%d, %.1f s -> %s"
          % (info_preview["ancho"], info_preview["alto"],
             tiempos["vista_previa"], "VÁLIDA" if preview_ok else "INVÁLIDA"))

    # 4. Exportación
    print("\n[4/5] Exportando %d clip(s)..."
          % min(args.clips, len(candidatos)))
    t0 = time.time()
    exportados = []
    for i, clip in enumerate(candidatos[:args.clips], 1):
        ruta_ass = os.path.join(args.salida, "clip%02d.ass" % i)
        ruta_clip = os.path.join(args.salida, "clip%02d.mp4" % i)
        core.generar_subtitulos_ass(segmentos, clip["start"], clip["end"],
                                    ruta_ass)
        t_clip = time.time()
        # El primer clip se exporta siguiendo los rostros detectados.
        core.exportar_clip(args.video, clip["start"], clip["end"],
                           ruta_ass, ruta_clip,
                           rostros=rostros if i == 1 else None)
        exportados.append((ruta_clip, clip, ruta_ass))
        print("      Clip %d exportado en %.1f s -> %s"
              % (i, time.time() - t_clip, os.path.basename(ruta_clip)))
    tiempos["exportacion"] = time.time() - t0

    # 5. Verificación
    print("\n[5/5] Verificando clips con ffprobe...")
    ok = preview_ok
    for ruta_clip, clip, ruta_ass in exportados:
        info = verificar_clip(ruta_clip)
        pedida = clip["end"] - clip["start"]
        dif_duracion = abs(info["duracion"] - pedida)
        valido = (info["ancho"] == 1080 and info["alto"] == 1920
                  and info["codec"] == "h264"
                  and dif_duracion <= TOLERANCIA_DURACION)
        audio_ok = info["audio"] is None or info["audio"] == "aac"
        valido = valido and audio_ok
        ok = ok and valido
        print("      %s: %dx%d %s, audio %s, %.1f s (pedida %.1f s, "
              "dif %.2f s), %d KB -> %s"
              % (os.path.basename(ruta_clip), info["ancho"], info["alto"],
                 info["codec"], info["audio"] or "sin audio",
                 info["duracion"], pedida, dif_duracion,
                 info["tamano_kb"], "VÁLIDO" if valido else "INVÁLIDO"))

        # Subtítulos: eventos ASS + píxeles de texto en el fotograma.
        inicios = eventos_ass(ruta_ass)
        tiene_palabras = any(
            s["start"] < clip["end"] and s["end"] > clip["start"]
            for s in segmentos)
        if tiene_palabras and not inicios:
            print("      FALLO: el clip tiene palabras pero el .ass no "
                  "tiene eventos Dialogue.")
            ok = False
        elif inicios:
            print("      Subtítulos: %d eventos ASS" % len(inicios))
            # Fotograma en el primer evento: ahí seguro hay texto.
            fotograma = ruta_clip.replace(".mp4", "_subtitulo.png")
            extraer_fotograma(ruta_clip, inicios[0] + 0.1, fotograma)
            pixeles = contar_pixeles_subtitulo(fotograma)
            print("      Píxeles de subtítulo en el fotograma: %d"
                  % pixeles)
            if pixeles < MIN_PIXELES_SUBTITULO:
                print("      FALLO: no se detectó texto quemado en el "
                      "fotograma.")
                ok = False
        # Fotograma a mitad del clip para revisión visual.
        medio = info["duracion"] / 2
        fotograma = ruta_clip.replace(".mp4", "_fotograma.png")
        extraer_fotograma(ruta_clip, medio, fotograma)
        print("      Fotograma guardado en: %s" % fotograma)

    print("\n== Resumen de tiempos ==")
    for fase, segundos in tiempos.items():
        print("  %-14s %6.1f s" % (fase, segundos))
    print("  %-14s %6.1f s" % ("TOTAL", sum(tiempos.values())))
    print("\nRESULTADO:", "PRUEBA SUPERADA" if ok else "PRUEBA CON FALLOS")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
