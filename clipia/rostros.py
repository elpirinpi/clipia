# -*- coding: utf-8 -*-
"""Detección de rostros (OpenCV) — para que el recorte siga la cara.

Los fotogramas se extraen con ffmpeg (v1.1.2): nunca usar
cv2.VideoCapture, que se congela con algunos MP4 en Windows.
Solo mide dónde está la cara en cada momento; no identifica a nadie.
"""
import os
import shutil
import subprocess
import tempfile


def detectar_rostros(ruta_video, inicio, fin, intervalo=2.0, progreso=None):
    """Detecta la posición horizontal de la cara principal en un fragmento.

    Extrae fotogramas con ffmpeg (el mismo programa que ya usa la app
    para exportar, fiable en cualquier PC) y detecta la cara en cada
    foto con OpenCV. No usa la lectura de video de OpenCV, que se
    congela con algunos MP4 en Windows. Devuelve una lista de (t, x)
    donde t son segundos desde `inicio` y x la posición del centro de
    la cara como fracción del ancho (0.0-1.0). Devuelve [] si no se
    encuentra ninguna cara, si OpenCV no está instalado o si algo
    falla. `progreso` es una función opcional que recibe un valor
    0.0-1.0. Solo mide dónde está la cara en cada momento; no identifica
    a nadie.
    """
    try:
        import cv2
    except ImportError:
        return []
    muestras = []
    try:
        cascada = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        if cascada.empty():
            return []
        duracion = max(0.1, fin - inicio)
        # Como mucho 45 muestras por clip, aunque el clip sea largo.
        intervalo = max(intervalo, duracion / 45)
        tmp = tempfile.mkdtemp(prefix="clipia_rostros_")
        try:
            # Un fotograma cada `intervalo` segundos, reducido a 640 px.
            patron = os.path.join(tmp, "f_%03d.jpg")
            subprocess.run(
                ["ffmpeg", "-y", "-v", "error",
                 "-ss", "%.3f" % inicio, "-t", "%.3f" % duracion,
                 "-i", ruta_video,
                 "-vf", "fps=%.4f,scale=640:-1" % (1.0 / intervalo),
                 "-q:v", "5", patron],
                timeout=60, check=True)
            archivos = sorted(
                f for f in os.listdir(tmp) if f.endswith(".jpg"))
            for i, nombre in enumerate(archivos):
                t = min(duracion, i * intervalo)
                imagen = cv2.imread(os.path.join(tmp, nombre))
                if imagen is None:
                    continue
                gris = cv2.cvtColor(imagen, cv2.COLOR_BGR2GRAY)
                caras = cascada.detectMultiScale(
                    gris, scaleFactor=1.1, minNeighbors=5, minSize=(40, 40))
                if len(caras):
                    # La cara más grande (la principal)
                    x, _y, w, _h = max(caras, key=lambda c: c[2] * c[3])
                    centro = (x + w / 2) / imagen.shape[1]
                    muestras.append((t, min(1.0, max(0.0, centro))))
                if progreso:
                    progreso(min(1.0, (i + 1) / max(1, len(archivos))))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    except Exception:
        pass
    # Suavizar: media móvil de 3 para que el recorte no salte de lado a lado
    if len(muestras) >= 3:
        suavizadas = []
        for i, (t, _x) in enumerate(muestras):
            vecinos = [muestras[j][1] for j in range(
                max(0, i - 1), min(len(muestras), i + 2))]
            suavizadas.append((t, sum(vecinos) / len(vecinos)))
        return suavizadas
    return muestras


def _expresion_rostros(muestras, ancho_salida):
    """Expresión ffmpeg para el x del recorte siguiendo las `muestras`.

    `muestras` es la lista de (t, x) de detectar_rostros (t en segundos
    desde el inicio del clip, x fracción del ancho). Devuelve None si
    no hay muestras. Interpola linealmente entre muestras para que el
    recorte se mueva de forma suave.
    """
    if not muestras:
        return None
    # Como mucho 12 puntos en la expresión, para que el filtro sea corto.
    if len(muestras) > 12:
        paso = (len(muestras) - 1) / 11
        muestras = [muestras[int(round(k * paso))] for k in range(12)]
    if len(muestras) == 1:
        posicion = "%.4f" % muestras[0][1]
    else:
        posicion = "%.4f" % muestras[-1][1]
        for k in range(len(muestras) - 2, -1, -1):
            t0, x0 = muestras[k]
            t1, x1 = muestras[k + 1]
            interp = ("%.4f+(%.4f-%.4f)*(t-%.3f)/%.3f"
                      % (x0, x1, x0, t0, max(0.001, t1 - t0)))
            posicion = "if(lt(t,%.3f),%s,%s)" % (t1, interp, posicion)
    return ("clip((%s)*iw-%d,0,iw-%d)"
            % (posicion, ancho_salida // 2, ancho_salida))
