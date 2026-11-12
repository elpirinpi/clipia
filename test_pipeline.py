# -*- coding: utf-8 -*-
"""
Prueba de punta a punta de ClipIA (sin interfaz gráfica).

Uso:
    python test_pipeline.py --video video_prueba.mp4 --salida ./salida_prueba

Pasos: transcribir -> detectar momentos -> exportar clips -> verificar
con ffprobe que los clips son MP4 verticales 1080x1920 válidos.
Imprime los tiempos medidos de cada fase.
"""

import argparse
import json
import os
import subprocess
import sys
import time

import clipia_core as core


def verificar_clip(ruta):
    """Verifica con ffprobe que el clip es un MP4 vertical válido."""
    resultado = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height,codec_name,duration",
         "-show_entries", "format=duration",
         "-of", "json", ruta],
        capture_output=True, text=True, timeout=60,
    )
    if resultado.returncode != 0:
        raise RuntimeError("ffprobe falló en %s: %s"
                           % (ruta, resultado.stderr.strip()))
    info = json.loads(resultado.stdout)
    video = info["streams"][0]
    return {
        "ancho": video["width"],
        "alto": video["height"],
        "codec": video["codec_name"],
        "duracion": float(info["format"]["duration"]),
        "tamano_kb": os.path.getsize(ruta) // 1024,
    }


def extraer_fotograma(ruta_video, segundo, ruta_salida):
    """Extrae un fotograma en el segundo indicado (para revisar subtítulos)."""
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-ss", "%.2f" % segundo,
         "-i", ruta_video, "-frames:v", "1", ruta_salida],
        check=True, timeout=60,
    )
    return ruta_salida


def main():
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
    print("\n[1/4] Transcribiendo con faster-whisper (%s)..." % args.modelo)
    segmentos = core.transcribir(args.video, modelo=args.modelo)
    tiempos["transcripcion"] = time.time() - t0
    palabras = sum(len(s["text"].split()) for s in segmentos)
    print("      Segmentos: %d · Palabras: %d · Tiempo: %.1f s"
          % (len(segmentos), palabras, tiempos["transcripcion"]))
    if segmentos:
        print("      Ejemplo: %r" % segmentos[0]["text"][:120])

    # 2. Detección de momentos
    t0 = time.time()
    print("\n[2/4] Detectando momentos...")
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

    # 3. Exportación
    print("\n[3/4] Exportando %d clip(s)..." % min(args.clips, len(candidatos)))
    t0 = time.time()
    exportados = []
    for i, clip in enumerate(candidatos[:args.clips], 1):
        ruta_ass = os.path.join(args.salida, "clip%02d.ass" % i)
        ruta_clip = os.path.join(args.salida, "clip%02d.mp4" % i)
        core.generar_subtitulos_ass(segmentos, clip["start"], clip["end"],
                                    ruta_ass)
        t_clip = time.time()
        core.exportar_clip(args.video, clip["start"], clip["end"],
                           ruta_ass, ruta_clip)
        exportados.append(ruta_clip)
        print("      Clip %d exportado en %.1f s -> %s"
              % (i, time.time() - t_clip, os.path.basename(ruta_clip)))
    tiempos["exportacion"] = time.time() - t0

    # 4. Verificación
    print("\n[4/4] Verificando clips con ffprobe...")
    ok = True
    for ruta_clip in exportados:
        info = verificar_clip(ruta_clip)
        valido = (info["ancho"] == 1080 and info["alto"] == 1920
                  and info["codec"] == "h264")
        ok = ok and valido
        print("      %s: %dx%d %s, %.1f s, %d KB -> %s"
              % (os.path.basename(ruta_clip), info["ancho"], info["alto"],
                 info["codec"], info["duracion"], info["tamano_kb"],
                 "VÁLIDO" if valido else "INVÁLIDO"))
        # Fotograma a mitad del clip para revisar los subtítulos quemados.
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
