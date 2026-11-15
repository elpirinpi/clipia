"""Detección de rostros (OpenCV) — para que el recorte siga la cara.

Los fotogramas se extraen con ffmpeg (v1.1.2): nunca usar
cv2.VideoCapture, que se congela con algunos MP4 en Windows.
Solo mide dónde está la cara en cada momento; no identifica a nadie.

Fase 2: el detector por defecto es YuNet (cv2.FaceDetectorYN, ONNX
~230 KB, detecta perfiles y caras parcialmente tapadas, donde Haar
falla). El modelo se descarga en el primer uso (con caché local y
verificación SHA-256); sin modelo o sin red, se usa Haar.
"""
import hashlib
import logging
import os
import shutil
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from collections.abc import Callable

from .cache import carpeta_cache, clave_archivo, escribir_cache, leer_cache
from .procesos import ejecutar

log = logging.getLogger("clipia.rostros")

# Modelo YuNet (OpenCV Zoo, licencia MIT). ~230 KB.
URL_MODELO_YUNET = (
    "https://github.com/opencv/opencv_zoo/raw/main/"
    "models/face_detection_yunet/face_detection_yunet_2023mar.onnx")
SHA256_MODELO_YUNET = (
    "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4")
NOMBRE_MODELO_YUNET = "face_detection_yunet_2023mar.onnx"

# Banda muerta: un movimiento de la cara menor del 5% del ancho no
# mueve el recorte (evita el tembleque por ruido de detección).
BANDA_MUERTA = 0.05
# Puntos de interpolación en la expresión del recorte (antes 12).
# crop no admite comandos sendcmd, así que se sube el tope: con 45
# muestras como mucho, la expresión cubre todas.
MAX_PUNTOS_EXPRESION = 45
# Puntuación mínima de YuNet para aceptar una cara.
UMBRAL_YUNET = 0.6


def ruta_modelo_yunet() -> str:
    """Ruta local del modelo YuNet (junto a la caché)."""
    return os.path.join(carpeta_cache(), NOMBRE_MODELO_YUNET)


def ruta_modelo_yunet_empaquetado() -> str | None:
    """Ruta del modelo YuNet empaquetado con el instalador, si
    existe y su SHA-256 coincide (junto al .exe; en one-file, en
    _MEIPASS). None si no está empaquetado: la app lo descarga en
    el primer uso."""
    if not getattr(sys, "frozen", False):
        return None
    candidatos = [os.path.join(os.path.dirname(sys.executable),
                               NOMBRE_MODELO_YUNET)]
    base = getattr(sys, "_MEIPASS", None)
    if base:
        candidatos.append(os.path.join(base, NOMBRE_MODELO_YUNET))
    for ruta in candidatos:
        if os.path.isfile(ruta):
            try:
                if _sha256_archivo(ruta) == SHA256_MODELO_YUNET:
                    return ruta
            except OSError:
                continue
    return None


def _sha256_archivo(ruta: str) -> str:
    suma = hashlib.sha256()
    with open(ruta, "rb") as archivo:
        for bloque in iter(lambda: archivo.read(65536), b""):
            suma.update(bloque)
    return suma.hexdigest()


def descargar_modelo_yunet(
        progreso: Callable[[float], None] | None = None,
        timeout: int = 120) -> str | None:
    """Descarga el modelo YuNet en el primer uso (con caché local).

    Devuelve la ruta del modelo, o None si no se pudo descargar
    (sin red, suma incorrecta...): el llamador usa Haar entonces.
    `progreso` recibe un valor 0.0-1.0 mientras descarga.
    """
    # Fase 4: el instalador empaqueta el modelo junto al .exe; si
    # está ahí, no hace falta descargarlo (ni conexión).
    empaquetado = ruta_modelo_yunet_empaquetado()
    if empaquetado:
        return empaquetado
    ruta = ruta_modelo_yunet()
    if os.path.isfile(ruta):
        try:
            if _sha256_archivo(ruta) == SHA256_MODELO_YUNET:
                return ruta
            log.warning("el modelo YuNet guardado está corrupto; "
                        "se vuelve a descargar")
            os.remove(ruta)
        except OSError:
            return None
    try:
        os.makedirs(os.path.dirname(ruta), exist_ok=True)
        tmp = ruta + ".tmp"
        peticion = urllib.request.Request(
            URL_MODELO_YUNET, headers={"User-Agent": "ClipIA"})
        with urllib.request.urlopen(peticion, timeout=timeout) as respuesta:
            total = int(respuesta.headers.get("Content-Length") or 0)
            descargado = 0
            with open(tmp, "wb") as archivo:
                while True:
                    bloque = respuesta.read(65536)
                    if not bloque:
                        break
                    archivo.write(bloque)
                    descargado += len(bloque)
                    if progreso and total:
                        progreso(min(1.0, descargado / total))
        if _sha256_archivo(tmp) != SHA256_MODELO_YUNET:
            os.remove(tmp)
            log.warning("el modelo YuNet descargado no coincide con "
                        "su suma SHA-256; se usa Haar")
            return None
        os.replace(tmp, ruta)
        if progreso:
            progreso(1.0)
        return ruta
    except (OSError, urllib.error.URLError, ValueError) as error:
        log.warning("no se pudo descargar el modelo YuNet (%s); "
                    "se usa Haar", error)
        try:
            os.remove(ruta + ".tmp")
        except OSError:
            pass
        return None


def _detector_yunet(ruta_modelo: str, ancho: int, alto: int):
    """Crea un FaceDetectorYN, o None si OpenCV no lo tiene."""
    try:
        import cv2
        return cv2.FaceDetectorYN.create(
            ruta_modelo, "", (ancho, alto),
            score_threshold=UMBRAL_YUNET, nms_threshold=0.3)
    except Exception as error:  # noqa: BLE001 - cualquier fallo -> Haar
        log.warning("no se pudo crear el detector YuNet (%s); se usa "
                    "Haar", error)
        return None


def _centro_yunet(detector, imagen):
    """Centro horizontal de la cara más grande (0.0-1.0), o None."""
    alto, ancho = imagen.shape[:2]
    try:
        if tuple(detector.getInputSize()) != (ancho, alto):
            detector.setInputSize((ancho, alto))
        _ok, caras = detector.detect(imagen)
    except Exception:  # noqa: BLE001 - un fotograma malo no aborta
        return None
    if caras is None or len(caras) == 0:
        return None
    x, _y, w, _h = max(caras, key=lambda c: c[2] * c[3])[:4]
    # float() explícito: YuNet devuelve float32 y json no lo serializa
    # (la caché de rostros guardaría TypeError).
    return float(min(1.0, max(0.0, (x + w / 2) / ancho)))


def _centro_haar(cascada, imagen):
    """Centro horizontal de la cara más grande con Haar, o None."""
    import cv2

    gris = cv2.cvtColor(imagen, cv2.COLOR_BGR2GRAY)
    caras = cascada.detectMultiScale(
        gris, scaleFactor=1.1, minNeighbors=5, minSize=(40, 40))
    if len(caras) == 0:
        return None
    x, _y, w, _h = max(caras, key=lambda c: c[2] * c[3])
    return float(min(1.0, max(0.0, (x + w / 2) / imagen.shape[1])))


def _suavizar_centros(muestras: list[tuple[float, float]],
                      banda_muerta: float = BANDA_MUERTA
                      ) -> list[tuple[float, float]]:
    """Suaviza la trayectoria de la cara.

    Primero media móvil de 3 (que el recorte no salte de lado a lado);
    después banda muerta: un movimiento menor de `banda_muerta`
    (fracción del ancho) no mueve el recorte, así el tembleque de la
    detección no se ve en el video.
    """
    if len(muestras) >= 3:
        suavizadas = []
        for i, (t, _x) in enumerate(muestras):
            vecinos = [muestras[j][1] for j in range(
                max(0, i - 1), min(len(muestras), i + 2))]
            suavizadas.append((t, sum(vecinos) / len(vecinos)))
    else:
        suavizadas = list(muestras)
    if not suavizadas:
        return suavizadas
    resultado = [suavizadas[0]]
    actual = suavizadas[0][1]
    for t, x in suavizadas[1:]:
        if abs(x - actual) >= banda_muerta:
            actual = x
        resultado.append((t, actual))
    return resultado


def detectar_rostros(ruta_video: str, inicio: float, fin: float,
                     intervalo: float = 2.0,
                     progreso: Callable[[float], None] | None = None,
                     usar_cache: bool = True
                     ) -> list[tuple[float, float]]:
    """Detecta la posición horizontal de la cara principal en un fragmento.

    Extrae fotogramas con ffmpeg (el mismo programa que ya usa la app
    para exportar, fiable en cualquier PC) y detecta la cara en cada
    foto con OpenCV (YuNet; Haar si el modelo no está disponible). No
    usa la lectura de video de OpenCV, que se congela con algunos MP4
    en Windows. Devuelve una lista de (t, x) donde t son segundos
    desde `inicio` y x la posición del centro de la cara como fracción
    del ancho (0.0-1.0). Devuelve [] si no se encuentra ninguna cara,
    si OpenCV no está instalado o si algo falla. `progreso` es una
    función opcional que recibe un valor 0.0-1.0. Con `usar_cache` se
    reutiliza la detección guardada si el video no cambió (así la
    vista previa y la exportación del mismo clip no detectan dos
    veces). La clave de caché incluye el detector: cambiar de Haar a
    YuNet invalida las detecciones viejas. Solo mide dónde está la
    cara en cada momento; no identifica a nadie.
    """
    duracion = max(0.1, fin - inicio)
    # Como mucho 45 muestras por clip, aunque el clip sea largo.
    intervalo = max(intervalo, duracion / 45)
    try:
        import cv2
    except ImportError:
        return []
    # Elegir el detector antes de mirar la caché: la clave incluye el
    # detector, así las detecciones de Haar no se reutilizan con YuNet.
    ruta_modelo = None
    if hasattr(cv2, "FaceDetectorYN"):
        if progreso:
            def _progreso_descarga(p):
                progreso(p * 0.1)
        else:
            _progreso_descarga = None
        ruta_modelo = descargar_modelo_yunet(_progreso_descarga)
    detector = "yunet" if ruta_modelo else "haar"
    clave = None
    if usar_cache:
        try:
            clave = clave_archivo(ruta_video, version=1,
                                  inicio=round(inicio, 3),
                                  fin=round(fin, 3),
                                  intervalo=round(intervalo, 3),
                                  detector=detector)
            guardado = leer_cache("rostros", clave)
        except OSError:
            guardado = None
        if isinstance(guardado, dict) and isinstance(
                guardado.get("muestras"), list):
            if progreso:
                progreso(1.0)
            return [(float(t), float(x))
                    for t, x in guardado["muestras"]]
    muestras = []
    error = False
    try:
        cascada = None
        detector_yunet = None
        if detector == "haar":
            cascada = cv2.CascadeClassifier(
                cv2.data.haarcascades
                + "haarcascade_frontalface_default.xml")
            if cascada.empty():
                return []
        tmp = tempfile.mkdtemp(prefix="clipia_rostros_")
        try:
            # Un fotograma cada `intervalo` segundos, reducido a 640 px.
            # ejecutar() registra el ffmpeg: si la app se cierra a
            # mitad, matar_todos() lo alcanza (no queda huérfano).
            patron = os.path.join(tmp, "f_%03d.jpg")
            ejecutar(
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
                centro = None
                if detector == "yunet":
                    if detector_yunet is None:
                        alto, ancho = imagen.shape[:2]
                        detector_yunet = _detector_yunet(
                            ruta_modelo, ancho, alto)
                        if detector_yunet is None:
                            # YuNet falló a mitad: se sigue con Haar
                            # y no se guarda la caché (la clave dice
                            # "yunet" pero las muestras son de Haar).
                            detector = "haar"
                            clave = None
                            cascada = cv2.CascadeClassifier(
                                cv2.data.haarcascades
                                + "haarcascade_frontalface_default.xml")
                    if detector_yunet is not None:
                        centro = _centro_yunet(detector_yunet, imagen)
                if centro is None and detector == "haar" and cascada:
                    centro = _centro_haar(cascada, imagen)
                if centro is not None:
                    muestras.append((t, centro))
                if progreso:
                    # El 10% inicial es la descarga del modelo.
                    base = 0.1 if ruta_modelo else 0.0
                    progreso(base + (1.0 - base)
                             * (i + 1) / max(1, len(archivos)))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    except Exception:
        error = True
    resultado = _suavizar_centros(muestras)
    if clave is not None and not error:
        escribir_cache("rostros", clave, {"muestras": resultado})
    return resultado


def detectar_rostros_con_limite(
    ruta_video: str, inicio: float, fin: float,
    progreso: Callable[[float], None] | None = None, timeout: int = 60,
) -> list[tuple[float, float]]:
    """Detecta rostros con un límite de tiempo.

    Si la detección tarda más de `timeout` segundos (por ejemplo, un
    video que se resiste), se abandona y se devuelve [] para que la
    exportación siga con el recorte centrado: la app nunca se queda
    congelada esperando.
    """
    resultado: list[tuple[float, float]] = []

    def trabajo() -> None:
        try:
            resultado.extend(detectar_rostros(
                ruta_video, inicio, fin, progreso=progreso))
        except Exception:
            pass

    hilo = threading.Thread(target=trabajo, daemon=True)
    hilo.start()
    hilo.join(timeout)
    if hilo.is_alive():
        log.warning("la detección de rostros tardó más de %d s; "
                    "se sigue con el recorte centrado", timeout)
    return resultado


def _expresion_rostros(muestras: list[tuple[float, float]],
                       ancho_salida: int) -> str | None:
    """Expresión ffmpeg para el x del recorte siguiendo las `muestras`.

    `muestras` es la lista de (t, x) de detectar_rostros (t en segundos
    desde el inicio del clip, x fracción del ancho). Devuelve None si
    no hay muestras. Interpola linealmente entre muestras para que el
    recorte se mueva de forma suave. Hasta 45 puntos (antes 12): con
    más puntos el recorte sigue mejor a una cara en movimiento.
    """
    if not muestras:
        return None
    if len(muestras) > MAX_PUNTOS_EXPRESION:
        paso = (len(muestras) - 1) / (MAX_PUNTOS_EXPRESION - 1)
        muestras = [muestras[int(round(k * paso))]
                    for k in range(MAX_PUNTOS_EXPRESION)]
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
