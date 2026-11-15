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
3. **Clips** — Revisa la lista con una miniatura vertical de cada
   momento, marca los que quieres, usa «Seleccionar todo» o crea un
   clip manual con hora de inicio y fin. Cada clip tiene un botón
   «▶ Vista previa» que genera una versión rápida (540x960) y la abre
   en tu reproductor para verla antes de exportar.
4. **Exportar** — «Descargar clips» exporta los seleccionados en
   vertical 1080x1920, con subtítulos quemados estilo Shorts (negrita,
   blanco con borde negro, abajo al centro), H.264 + AAC. Con la
   opción «Seguir rostros» activada, el recorte vertical sigue la
   cara del hablante en vez de centrarse siempre en la imagen; si no
   se detecta ninguna cara, usa el centro como antes.

## Requisitos

- Windows 10/11 (64 bits)
- Conexión a internet solo para la instalación y para descargar videos
  de YouTube. La transcripción y la exportación son locales.
- ~1.2 GB de espacio libre (dependencias + modelo de voz de ~150 MB).

## Instalación

1. Descarga o copia la carpeta `clipia` a tu PC (por ejemplo,
   `C:\ClipIA`).
2. Haz doble clic en **`setup.bat`**. El instalador:
   - instala Python 3.12 (python.org) con winget si no lo tienes
     (si tu `python` es de MSYS2, setup.bat instala el de python.org
     porque MSYS2 no trae pip);
   - instala ffmpeg con winget si no lo tienes;
   - instala Deno con winget si no lo tienes (lo usa yt-dlp para
     descargar de YouTube sin errores);
   - crea el entorno virtual `.venv` y instala las dependencias
     dentro de él (`pip install -r requirements.txt`). La app usa
     siempre su propio entorno, sin tocar el Python global.
3. Si Python se instaló en ese momento, cierra la ventana y vuelve a
   ejecutar `setup.bat` para terminar (Windows necesita refrescar el
   PATH).

## Cómo usarla

1. Haz doble clic en **`run.bat`**.
2. Elige un video con «Examinar…» o pega una URL de YouTube.
3. Pulsa **«Analizar video»**. La primera vez descarga el modelo de
   voz (~150 MB, unos segundos con buena conexión).
4. Marca los clips que quieres (puedes previsualizar cada uno con
   «▶ Vista previa») y pulsa **«Descargar clips»**. Si el video es
   una persona hablando, deja activado «Seguir rostros» para que el
   recorte siga su cara.
5. Los clips quedan en `Videos\ClipIA` (puedes cambiar la carpeta
   antes de exportar).

## Rendimiento

Medido en la prueba de punta a punta (video de 2:57, 1920x1080, voz en
español, CPU de 4 núcleos, modelo Whisper base, 13-11-2026):

| Fase | Tiempo medido |
|---|---|
| Transcripción (2:57 de audio) | ~26 s (unas 6.8 veces más rápido que tiempo real) |
| Detección de momentos | menos de 1 s |
| Detección de rostros (clip de 60 s, sin caras) | ~10 s |
| Vista previa (clip de 60 s, 540x960) | ~24 s |
| Exportar un clip de 60 s | ~50 s |
| Exportar un clip de 30 s | ~27 s |

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
| `clipia/` | Núcleo dividido en módulos: `transcripcion`, `momentos`, `subtitulos`, `rostros`, `exportacion`, `descarga`, `utilidades`, `config`, `logs` |
| `clipia_core.py` | Fachada compatible: re-exporta la API del paquete |
| `test_pipeline.py` | Prueba de punta a punta sin interfaz gráfica |
| `tests/` | Suite pytest (unitarios, GUI, e2e con video sintético) |
| `requirements.txt` | Dependencias con versiones fijadas |
| `requirements-dev.txt` | Dependencias de desarrollo (pytest, ruff) |
| `pyproject.toml` | Configuración de ruff y pytest |
| `.github/workflows/ci.yml` | CI en Windows (ruff + pytest) |
| `setup.bat` | Instalador para Windows |
| `run.bat` | Lanzador de la app |
| `diagnostico.bat` | Diagnóstico de la instalación |
| `LICENSE` | Licencia MIT |
| `CHANGELOG.md` | Historial de cambios |

## Desarrollo

```bat
REM Instalar las dependencias de desarrollo (dentro del venv):
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt

REM Lint:
.venv\Scripts\python.exe -m ruff check main.py clipia_core.py clipia/ test_pipeline.py tests/

REM Tests:
.venv\Scripts\python.exe -m pytest tests/ -q

REM Prueba de punta a punta:
.venv\Scripts\python.exe test_pipeline.py --video video_prueba.mp4 --salida ./salida_prueba
```

Cada push a `main` corre ruff y la suite en GitHub Actions
(`windows-latest`).

## Solución de problemas

- **La ventana se cierra sin abrir la app**: ejecuta
  `diagnostico.bat` y revisa qué línea falla (Python, customtkinter,
  tkinter, faster-whisper, yt-dlp o ffmpeg). También puedes abrir
  `cmd` en la carpeta y ejecutar `python main.py` para ver el error
  completo.
- **«python no se reconoce»**: cierra la ventana y ejecuta `setup.bat`
  de nuevo; si sigue fallando, instala Python 3.12 desde
  python.org marcando «Add Python to PATH».
- **«No module named pip»**: tu `python` es de MSYS2 y no trae pip.
  Ejecuta `setup.bat` (instala Python 3.12 de python.org, que sí
  trae pip) o corre `python -m ensurepip --upgrade` en cmd.
- **La carpeta `Videos` está dañada o redirigida** (OneDrive, enlace
  roto): la app usa automáticamente `~/ClipIA` y si tampoco se
  puede, una carpeta `salida` junto a la app. La carpeta en uso se
  ve en el campo «Carpeta de salida».
- **«ffmpeg no se reconoce»**: ejecuta `setup.bat` de nuevo o instala
  ffmpeg con `winget install Gyan.FFmpeg`.
- **«No se detectó habla en el video»**: el video no tiene voz clara
  en español, o el audio está muy bajo. Prueba con otro video.
- **La barra de progreso se congela al exportar o previsualizar**:
  en la v1.1.2 y anteriores, ffmpeg escribía sus mensajes en un tubo
  aparte que nadie leía; en Windows ese tubo se llena y ffmpeg se
  queda esperando para siempre. Desde la v1.1.3 sus mensajes van por
  el mismo tubo del avance, así que la barra se mueve y la
  exportación termina.
- **Se queda en «Detectando rostros»**: en la v1.1.0 y v1.1.1 la
  detección leía el video con OpenCV y eso se congela con algunos
  MP4 en Windows. Desde la v1.1.2 los fotogramas se extraen con
  ffmpeg (el mismo programa que ya usa la app para exportar) y
  OpenCV solo detecta la cara en cada foto; además, la detección
  tiene un límite de 60 segundos por clip: si un video se resiste,
  la app sigue con el recorte centrado en vez de quedarse congelada.
  Si pasa de todos modos, desmarca «Seguir rostros» y exporta con
  el recorte centrado de siempre.
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

## v2.0 (en desarrollo)

La v2.0 se está construyendo por fases: Fase 0 (cimientos: corrección
de errores, paquete `clipia/`, logging, configuración, tests y CI),
Fase 1 (rendimiento: encoder por hardware, caché, cola de exportación),
Fase 2 (calidad de clips: cortes en frases completas, subtítulos
karaoke, normalización de audio), Fase 3 (editor de clips y mejoras de
interfaz) y Fase 4 (instalador). Los detalles están en `CHANGELOG.md`.
