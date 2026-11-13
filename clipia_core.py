# -*- coding: utf-8 -*-
"""
ClipIA - núcleo (sin interfaz gráfica).

Funciones:
  - Transcribir un video con faster-whisper (español, timestamps por palabra).
  - Detectar los mejores momentos para clips cortos (30-90 s).
  - Generar subtítulos ASS estilo Shorts.
  - Exportar clips verticales 1080x1920 con ffmpeg.
  - Seguir la cara del hablante para centrar el recorte vertical.
  - Descargar videos de YouTube con yt-dlp (máximo 1080p).

Todo corre 100% local, sin APIs de pago ni claves.
"""

import json
import os
import re
import subprocess
import sys
import tempfile

# Silencia el aviso de huggingface_hub sobre symlinks en Windows: el caché
# funciona igual sin ellos, el aviso solo confunde.
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def formato_hora(segundos):
    """Convierte segundos a 'M:SS' (ej. 52 -> '0:52')."""
    segundos = max(0, int(round(segundos)))
    return "%d:%02d" % (segundos // 60, segundos % 60)


def formato_ass(segundos):
    """Convierte segundos a formato de tiempo ASS 'H:MM:SS.cc'."""
    segundos = max(0.0, float(segundos))
    h = int(segundos // 3600)
    m = int((segundos % 3600) // 60)
    s = int(segundos % 60)
    cs = int(round((segundos - int(segundos)) * 100))
    if cs == 100:
        s += 1
        cs = 0
    return "%d:%02d:%02d.%02d" % (h, m, s, cs)


def obtener_duracion(ruta_video):
    """Duración en segundos de un video, usando ffprobe."""
    resultado = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", ruta_video],
        capture_output=True, text=True, timeout=60,
    )
    if resultado.returncode != 0:
        raise RuntimeError("ffprobe no pudo leer el video: %s"
                           % resultado.stderr.strip())
    return float(resultado.stdout.strip())


def _escapar_ruta_subtitulos(ruta):
    """Escapa una ruta para el filtro subtitles de ffmpeg.

    En Windows las rutas con unidad (C:\\...) rompen el filtro si no se
    escapan los dos puntos y se usan barras normales.
    """
    ruta = ruta.replace("\\", "/")
    ruta = ruta.replace(":", "\\:")
    ruta = ruta.replace("'", "\\'")
    return ruta


# ---------------------------------------------------------------------------
# Transcripción (faster-whisper)
# ---------------------------------------------------------------------------

def _elegir_dispositivo():
    """Usa la GPU (CUDA) si está disponible; si no, CPU con int8."""
    try:
        from ctranslate2 import get_cuda_device_count
        if get_cuda_device_count() > 0:
            return "cuda", "float16"
    except Exception:
        pass
    return "cpu", "int8"


def _extraer_audio_wav(ruta_video, ruta_wav):
    """Extrae el audio a WAV PCM 16 kHz mono con ffmpeg (lo que Whisper usa)."""
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", ruta_video,
         "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", ruta_wav],
        check=True,
    )


def _leer_wav_numpy(ruta_wav):
    """Lee un WAV PCM 16 bits a un arreglo float32 normalizado [-1, 1]."""
    import wave

    import numpy as np

    with wave.open(ruta_wav, "rb") as archivo:
        datos = archivo.readframes(archivo.getnframes())
    return np.frombuffer(datos, dtype=np.int16).astype(np.float32) / 32768.0


def transcribir(ruta_video, modelo="base", idioma="es", progreso=None):
    """Transcribe el audio de un video.

    Devuelve una lista de segmentos:
      [{"start": float, "end": float, "text": str,
        "words": [{"start": float, "end": float, "word": str}]}]

    `progreso` es una función opcional que recibe un valor 0.0-1.0.
    """
    from faster_whisper import WhisperModel

    duracion = obtener_duracion(ruta_video)
    dispositivo, tipo_calculo = _elegir_dispositivo()
    try:
        whisper = WhisperModel(modelo, device=dispositivo,
                               compute_type=tipo_calculo)
    except Exception:
        # Si la GPU falla por cualquier motivo, reintentar en CPU.
        if dispositivo != "cpu":
            whisper = WhisperModel(modelo, device="cpu",
                                   compute_type="int8")
        else:
            raise

    # Se extrae el audio con ffmpeg y se pasa como arreglo numpy: así no
    # se depende del decodificador interno de faster-whisper (PyAV), que
    # cambia de API entre versiones y puede fallar según la versión instalada.
    with tempfile.TemporaryDirectory(prefix="clipia_audio_") as carpeta_tmp:
        ruta_wav = os.path.join(carpeta_tmp, "audio.wav")
        _extraer_audio_wav(ruta_video, ruta_wav)
        audio = _leer_wav_numpy(ruta_wav)

        segmentos, _info = whisper.transcribe(
            audio,
            language=idioma,
            word_timestamps=True,
            vad_filter=True,          # ignora silencios largos
            vad_parameters={"min_silence_duration_ms": 500},
        )

        resultado = []
        for seg in segmentos:
            palabras = []
            for palabra in (seg.words or []):
                palabras.append({
                    "start": float(palabra.start),
                    "end": float(palabra.end),
                    "word": palabra.word,
                })
            resultado.append({
                "start": float(seg.start),
                "end": float(seg.end),
                "text": seg.text.strip(),
                "words": palabras,
            })
            if progreso and duracion > 0:
                progreso(min(1.0, float(seg.end) / duracion))
    if progreso:
        progreso(1.0)
    return resultado


# ---------------------------------------------------------------------------
# Detección de momentos
# ---------------------------------------------------------------------------

# Palabras que suelen marcar un momento con gancho en español.
PALABRAS_GANCHO = {
    "mira", "miran", "escucha", "escuchen", "atención", "atencion", "ojo",
    "importante", "secreto", "secretos", "gratis", "nadie", "nunca",
    "siempre", "verdad", "increíble", "increible", "cuidado", "mejor",
    "peor", "dinero", "ganar", "gana", "error", "errores", "truco",
    "trucos", "clave", "claves", "descubre", "descubrí", "descubri",
    "imagina", "imagínate", "imaginate", "recuerda", "sabes", "créeme",
    "creeme", "te", "voy", "contar", "pasa", "resulta", "fíjate", "fijate",
    "alerta", "urgente", "exclusivo", "nuevo", "primero", "último",
    "ultimo", "ahora", "resulta", "sucedió", "sucedio", "pasó", "paso",
    "misterio", "revelo", "reveló", "confieso", "nadie", "todos",
    "ninguno", "jamás", "jamas", "imposible", "locura", "brutal",
}

# Duraciones de ventana que se prueban (segundos).
DURACIONES_VENTANA = (30, 45, 60, 75, 90)


def _frases_de_segmentos(segmentos):
    """Agrupa las palabras en frases (por puntuación o pausa larga).

    Devuelve [{"start": float, "end": float, "text": str, "words": [...]}].
    """
    palabras = []
    for seg in segmentos:
        palabras.extend(seg.get("words") or [])
    if not palabras:
        # Sin timestamps por palabra: usar los segmentos tal cual.
        return [{"start": s["start"], "end": s["end"], "text": s["text"],
                 "words": []} for s in segmentos if s["text"]]

    frases = []
    actual = []
    for palabra in palabras:
        if actual:
            pausa = palabra["start"] - actual[-1]["end"]
            texto_previo = "".join(p["word"] for p in actual)
            if pausa > 0.9 or texto_previo.rstrip().endswith((".", "?", "!")):
                frases.append(actual)
                actual = []
        actual.append(palabra)
    if actual:
        frases.append(actual)

    return [{
        "start": f[0]["start"],
        "end": f[-1]["end"],
        "text": "".join(p["word"] for p in f).strip(),
        "words": f,
    } for f in frases if "".join(p["word"] for p in f).strip()]


def _puntuar_ventana(frases, inicio, fin):
    """Puntúa una ventana [inicio, fin] de 0 a 1.

    Combina densidad de habla, exclamaciones/preguntas y palabras gancho.
    """
    en_ventana = [f for f in frases if f["start"] >= inicio - 0.5
                  and f["start"] < fin]
    if not en_ventana:
        return 0.0
    duracion = max(1.0, fin - inicio)
    texto = " ".join(f["text"] for f in en_ventana)
    num_palabras = len(texto.split())

    # Densidad de habla (palabras por segundo, tope ~3).
    densidad = min(1.0, (num_palabras / duracion) / 3.0)
    # Exclamaciones y preguntas.
    signos = texto.count("!") + texto.count("?")
    signos_puntos = min(1.0, signos / 3.0)
    # Palabras gancho.
    tokens = re.findall(r"[a-záéíóúñü]+", texto.lower())
    ganchos = sum(1 for t in tokens if t in PALABRAS_GANCHO)
    gancho_puntos = min(1.0, ganchos / 4.0)

    return 0.45 * densidad + 0.30 * gancho_puntos + 0.25 * signos_puntos


def _traslapan(a_inicio, a_fin, b_inicio, b_fin, umbral=0.5):
    """True si el traslape entre dos ventanas supera el umbral."""
    traslape = max(0.0, min(a_fin, b_fin) - max(a_inicio, b_inicio))
    menor = min(a_fin - a_inicio, b_fin - b_inicio)
    return menor > 0 and traslape / menor > umbral


def detectar_momentos(segmentos, duracion_video, cantidad=10):
    """Detecta los mejores momentos para clips cortos.

    Devuelve hasta `cantidad` candidatos ordenados por puntuación:
      [{"start": float, "end": float, "score": float, "text": str}]
    """
    frases = _frases_de_segmentos(segmentos)
    if not frases or duracion_video <= 0:
        return []

    # Video muy corto: un solo clip con todo el video.
    if duracion_video < 30:
        texto = " ".join(f["text"] for f in frases)
        return [{"start": 0.0, "end": float(duracion_video),
                 "score": 1.0, "text": texto}]

    candidatos = []
    vistos = set()
    for frase in frases:
        inicio = frase["start"]
        for dur in DURACIONES_VENTANA:
            fin = min(duracion_video, inicio + dur)
            if fin - inicio < 25:
                continue
            clave = (round(inicio, 1), round(fin, 1))
            if clave in vistos:
                continue
            vistos.add(clave)
            puntos = _puntuar_ventana(frases, inicio, fin)
            if puntos <= 0:
                continue
            texto = " ".join(f["text"] for f in frases
                             if f["start"] >= inicio - 0.5
                             and f["start"] < fin)
            candidatos.append({"start": inicio, "end": fin,
                               "score": puntos, "text": texto})

    # Elegir los mejores sin traslapes grandes entre ellos.
    candidatos.sort(key=lambda c: c["score"], reverse=True)
    elegidos = []
    for cand in candidatos:
        if len(elegidos) >= cantidad:
            break
        if any(_traslapan(cand["start"], cand["end"], e["start"], e["end"])
               for e in elegidos):
            continue
        elegidos.append(cand)
    return elegidos


# ---------------------------------------------------------------------------
# Subtítulos ASS estilo Shorts
# ---------------------------------------------------------------------------

PLANTILLA_ASS = """[Script Info]
Title: ClipIA
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,64,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,3,0,2,60,60,300,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
{eventos}
"""


def _fragmentos_subtitulo(frase, max_palabras=7):
    """Divide una frase en fragmentos cortos para subtítulos legibles."""
    palabras = frase.get("words") or []
    if not palabras:
        return [(frase["start"], frase["end"], frase["text"])]
    fragmentos = []
    for i in range(0, len(palabras), max_palabras):
        grupo = palabras[i:i + max_palabras]
        texto = "".join(p["word"] for p in grupo).strip()
        if texto:
            fragmentos.append((grupo[0]["start"], grupo[-1]["end"], texto))
    return fragmentos


def generar_subtitulos_ass(segmentos, inicio_clip, fin_clip, ruta_salida):
    """Genera un archivo .ass con los subtítulos del clip.

    Tiempos relativos al inicio del clip. Estilo Shorts: negrita, blanco
    con borde negro, abajo al centro.
    """
    frases = _frases_de_segmentos(segmentos)
    lineas = []
    for frase in frases:
        if frase["end"] <= inicio_clip or frase["start"] >= fin_clip:
            continue
        for inicio, fin, texto in _fragmentos_subtitulo(frase):
            inicio_rel = max(0.0, inicio - inicio_clip)
            fin_rel = min(fin_clip - inicio_clip, fin - inicio_clip)
            if fin_rel - inicio_rel < 0.15:
                continue
            texto = texto.replace("{", "").replace("}", "")
            lineas.append(
                "Dialogue: 0,%s,%s,Default,,0,0,0,,%s"
                % (formato_ass(inicio_rel), formato_ass(fin_rel), texto)
            )
    contenido = PLANTILLA_ASS.format(eventos="\n".join(lineas))
    with open(ruta_salida, "w", encoding="utf-8") as archivo:
        archivo.write(contenido)
    return ruta_salida


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Detección de rostros (OpenCV) — para que el recorte siga la cara
# ---------------------------------------------------------------------------

def detectar_rostros(ruta_video, inicio, fin, intervalo=2.0):
    """Detecta la posición horizontal de la cara principal en un fragmento.

    Muestrea un fotograma cada `intervalo` segundos y devuelve una lista
    de (t, x) donde t son segundos desde `inicio` y x la posición del
    centro de la cara como fracción del ancho (0.0-1.0). Devuelve []
    si no se encuentra ninguna cara o si OpenCV no está instalado.
    Solo mide dónde está la cara en cada momento; no identifica a nadie.
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
        captura = cv2.VideoCapture(ruta_video)
        if not captura.isOpened():
            return []
        t = inicio
        while t <= fin:
            captura.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
            ok, cuadro = captura.read()
            if not ok or cuadro is None:
                t += intervalo
                continue
            alto, ancho = cuadro.shape[:2]
            escala = 640 / max(1, ancho)
            pequeno = cv2.resize(cuadro, (640, max(1, int(alto * escala))))
            gris = cv2.cvtColor(pequeno, cv2.COLOR_BGR2GRAY)
            caras = cascada.detectMultiScale(
                gris, scaleFactor=1.1, minNeighbors=5, minSize=(40, 40))
            if len(caras):
                # La cara más grande (la principal)
                x, _y, w, _h = max(caras, key=lambda c: c[2] * c[3])
                centro = (x + w / 2) / pequeno.shape[1]
                muestras.append((t - inicio, min(1.0, max(0.0, centro))))
            t += intervalo
        captura.release()
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


# Exportación con ffmpeg
# ---------------------------------------------------------------------------

def exportar_clip(ruta_video, inicio, fin, ruta_ass, ruta_salida,
                  progreso=None, rostros=None, ancho=1080, alto=1920,
                  con_subtitulos=True):
    """Exporta un clip vertical con subtítulos quemados.

    `progreso` es una función opcional que recibe un valor 0.0-1.0.
    `rostros` es la lista de (t, x) de detectar_rostros: si se da, el
    recorte vertical sigue la cara en vez de centrarse. `ancho`/`alto`
    son el tamaño de salida (1080x1920 por defecto). Devuelve la ruta
    del clip exportado.
    """
    duracion = max(0.1, fin - inicio)
    expresion = _expresion_rostros(rostros, ancho) if rostros else None
    if expresion:
        recorte = "crop=%d:%d:x='%s'" % (ancho, alto, expresion)
    else:
        recorte = "crop=%d:%d" % (ancho, alto)
    filtro = ("scale=%d:%d:force_original_aspect_ratio=increase,%s"
              % (ancho, alto, recorte))
    if con_subtitulos and ruta_ass:
        filtro += ",subtitles='%s'" % _escapar_ruta_subtitulos(ruta_ass)
    comando = [
        "ffmpeg", "-y",
        "-ss", "%.3f" % inicio,
        "-t", "%.3f" % duracion,
        "-i", ruta_video,
        "-vf", filtro,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        "-progress", "pipe:1", "-nostats",
        ruta_salida,
    ]
    proceso = subprocess.Popen(
        comando, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    error = ""
    if proceso.stdout is not None:
        for linea in proceso.stdout:
            linea = linea.strip()
            if linea.startswith("out_time_ms="):
                try:
                    ms = int(linea.split("=", 1)[1])
                    if progreso:
                        progreso(min(1.0, (ms / 1_000_000) / duracion))
                except ValueError:
                    pass
            elif linea.startswith("progress=end") and progreso:
                progreso(1.0)
    _salida, error = proceso.communicate()
    if proceso.returncode != 0:
        raise RuntimeError("ffmpeg falló al exportar el clip:\n%s"
                           % (error or "").strip()[-2000:])
    if progreso:
        progreso(1.0)
    return ruta_salida


def generar_miniatura(ruta_video, instante, ruta_salida,
                      ancho=135, alto=240):
    """Guarda un fotograma vertical (9:16) del `instante` como imagen."""
    filtro = ("scale=1080:1920:force_original_aspect_ratio=increase,"
              "crop=1080:1920,scale=%d:%d" % (ancho, alto))
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-ss", "%.3f" % instante,
         "-i", ruta_video, "-frames:v", "1", "-vf", filtro, ruta_salida],
        check=True)
    return ruta_salida


def generar_vista_previa(ruta_video, inicio, fin, ruta_salida,
                         rostros=None, progreso=None):
    """Genera una vista previa rápida (540x960, sin subtítulos)."""
    return exportar_clip(ruta_video, inicio, fin, None, ruta_salida,
                         progreso=progreso, rostros=rostros,
                         ancho=540, alto=960, con_subtitulos=False)


# ---------------------------------------------------------------------------
# Descarga de YouTube (yt-dlp)
# ---------------------------------------------------------------------------

def descargar_youtube(url, carpeta_destino, progreso=None):
    """Descarga un video de YouTube en MP4, máximo 1080p.

    Devuelve la ruta del archivo descargado.
    """
    import yt_dlp

    os.makedirs(carpeta_destino, exist_ok=True)

    def gancho_estado(info):
        if progreso and info.get("status") == "downloading":
            total = info.get("total_bytes") or info.get("total_bytes_estimate")
            descargado = info.get("downloaded_bytes", 0)
            if total:
                progreso(min(1.0, descargado / total))

    opciones = {
        "format": ("bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/"
                   "bestvideo[height<=1080]+bestaudio/"
                   "best[height<=1080]/best"),
        "merge_output_format": "mp4",
        "restrictfilenames": True,
        "outtmpl": os.path.join(carpeta_destino, "%(title)s.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "progress_hooks": [gancho_estado],
    }
    with yt_dlp.YoutubeDL(opciones) as ydl:
        info = ydl.extract_info(url, download=True)
        ruta = ydl.prepare_filename(info)
    if progreso:
        progreso(1.0)
    return ruta
