# ClipIA — Estudio de clips

App de escritorio para Windows que convierte videos largos o directos en
**clips cortos verticales con subtítulos**, listos para TikTok, Reels y
YouTube Shorts. Todo corre **100% local y gratis**: sin APIs de pago,
sin claves, sin subir tus videos a ningún servidor.

Inspirada en la plataforma de clipping automático con IA del reel de
Instagram de [@varonsandro1](https://www.instagram.com/reel/DfnzxnFR-1u/).

## Qué hace

1. **Cargar** — Elige un archivo de video (mp4, mkv, mov, webm) o pega
   una URL de YouTube (se descarga en MP4, máximo 1080p).
2. **Analizar** — Transcribe el audio con faster-whisper (español,
   timestamps por palabra) y detecta los 10 mejores momentos para clips
   de 30 a 90 segundos, puntuados por densidad de habla, exclamaciones,
   preguntas y palabras gancho.
3. **Clips** — Revisa la lista, marca los que quieres, usa
   «Seleccionar todo» o crea un clip manual con hora de inicio y fin.
4. **Exportar** — «Descargar clips» exporta los seleccionados en
   vertical 1080x1920, con subtítulos quemados estilo Shorts (negrita,
   blanco con borde negro, abajo al centro), H.264 + AAC.

## Requisitos

- Windows 10/11 (64 bits)
- Conexión a internet solo para la instalación y para descargar videos
  de YouTube. La transcripción y la exportación son locales.
- ~1 GB de espacio libre (dependencias + modelo de voz de ~150 MB).

## Instalación

1. Descarga o copia la carpeta `clipia` a tu PC (por ejemplo,
   `C:\ClipIA`).
2. Haz doble clic en **`setup.bat`**. El instalador:
   - instala Python 3.11 con winget si no lo tienes;
   - instala ffmpeg con winget si no lo tienes;
   - instala Deno con winget si no lo tienes (lo usa yt-dlp para
     descargar de YouTube sin errores);
   - instala las dependencias (`pip install -r requirements.txt`).
3. Si Python se instaló en ese momento, cierra la ventana y vuelve a
   ejecutar `setup.bat` para terminar (Windows necesita refrescar el
   PATH).

## Cómo usarla

1. Haz doble clic en **`run.bat`**.
2. Elige un video con «Examinar…» o pega una URL de YouTube.
3. Pulsa **«Analizar video»**. La primera vez descarga el modelo de
   voz (~150 MB, unos segundos con buena conexión).
4. Marca los clips que quieres y pulsa **«Descargar clips»**.
5. Los clips quedan en `Videos\ClipIA` (puedes cambiar la carpeta
   antes de exportar).

## Rendimiento

Medido en la prueba de punta a punta (video de 2:57, 1920x1080, voz en
español, CPU de 4 núcleos, modelo Whisper base):

| Fase | Tiempo medido |
|---|---|
| Transcripción (2:57 de audio) | ~38 s (unas 4.6 veces más rápido que tiempo real) |
| Detección de momentos | menos de 1 s |
| Exportar un clip de 60 s | ~57 s |
| Exportar un clip de 30 s | ~30 s |

En el PC de destino (Xeon E5-2680 v4 de 14 núcleos, 24 GB RAM) la
transcripción y la exportación deberían ser más rápidas. Con una GPU
compatible con CUDA la transcripción es mucho más rápida todavía (la
app usa la GPU automáticamente si está disponible; si no, usa la CPU).

La primera vez que se analiza un video, la app descarga el modelo de
voz base (~150 MB).

## Archivos del proyecto

| Archivo | Descripción |
|---|---|
| `main.py` | Interfaz gráfica (CustomTkinter, tema oscuro) |
| `clipia_core.py` | Transcripción, detección de momentos, subtítulos, exportación, descarga |
| `test_pipeline.py` | Prueba de punta a punta sin interfaz gráfica |
| `requirements.txt` | Dependencias con versiones fijadas |
| `setup.bat` | Instalador para Windows |
| `run.bat` | Lanzador de la app |

## Solución de problemas

- **«python no se reconoce»**: cierra la ventana y ejecuta `setup.bat`
  de nuevo; si sigue fallando, instala Python 3.11 desde
  python.org marcando «Add Python to PATH».
- **«ffmpeg no se reconoce»**: ejecuta `setup.bat` de nuevo o instala
  ffmpeg con `winget install Gyan.FFmpeg`.
- **«No se detectó habla en el video»**: el video no tiene voz clara
  en español, o el audio está muy bajo. Prueba con otro video.
- **La transcripción es lenta**: es normal en CPU. Con una GPU
  compatible con CUDA es mucho más rápida.
- **Los subtítulos no se ven**: el ffmpeg instalado debe incluir
  libass (el de `Gyan.FFmpeg` vía winget lo incluye).
- **YouTube pide verificar que no eres un bot**: YouTube a veces
  bloquea las descargas automáticas. En ese caso, descarga el video
  con tu navegador (o con otra herramienta) y usa el archivo local
  con «Examinar…». La descarga directa con yt-dlp no pudo probarse
  desde el servidor donde se desarrolló la app porque YouTube
  bloquea esa red; en una conexión casera normalmente funciona.

## Ideas para la v2

- Puntuación de momentos con un LLM local (vía Ollama): elegir los
  clips por contenido y no solo por densidad de habla y palabras gancho.
- Recorte vertical con seguimiento de rostros (centrar al hablante en
  vez de centrar la imagen).
- Subtítulos con resaltado palabra por palabra (estilo karaoke).
- Vista previa de cada clip antes de exportar.
- Exportación en lote con cola y cancelación.
- Descarga de YouTube con cookies del navegador (para cuando YouTube
  pide verificar que no eres un bot).
