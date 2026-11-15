# Historial de cambios de ClipIA

Todos los cambios importantes de cada versión. El formato sigue
[Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/).

## [2.0.0] - en desarrollo

### Fase 0: cimientos (13-11-2026)

#### Corrección de errores (B1–B10)

- **B1**: `descargar_youtube` usa la ruta real del archivo descargado
  (`requested_downloads`) en vez de adivinar la extensión: al fusionar
  webm a mp4 ya no devuelve una ruta `.webm` inexistente.
- **B2**: `descargar_youtube` ya no descarga listas de reproducción
  enteras (`noplaylist`).
- **B3**: cada clip exportado usa su propio archivo `.ass` temporal
  (antes todos compartían `clip_tmp.ass`).
- **B4**: `setup.bat` se detiene tras instalar Python con winget y pide
  volver a ejecutarlo (el PATH no se refresca en la misma sesión);
  las instalaciones de ffmpeg y Deno comprueban su `errorlevel`.
- **B5**: `run.bat` verifica todas las dependencias (customtkinter,
  faster_whisper, cv2, PIL, numpy, yt_dlp), no solo customtkinter.
- **B6**: `diagnostico.bat` usa el mismo intérprete que `run.bat` y
  comprueba cv2, PIL, numpy, ctranslate2, ffprobe y deno; vuelca todo
  a `diagnostico.log`.
- **B7**: `requirements.txt` declara numpy y ctranslate2.
- **B8**: `obtener_duracion` no revienta con `float("N/A")` en MKV/WebM;
  usa la duración del flujo de video como respaldo.
- **B9**: `exportar_clip` mapea explícitamente el primer video y el
  primer audio (`-map 0:v:0 -map 0:a:0?`) y el `.ass` se copia a un
  directorio temporal con nombre simple (sin escapes frágiles).
- **B10**: al arrancar se limpian los temporales de vistas previas y al
  cerrar las miniaturas; mientras la app trabaja se bloquean también
  «Crear clip», «Examinar…», «Cambiar carpeta», los campos y la casilla
  de rostros; al agregar un clip manual se conserva la selección.

#### Cimientos

- El núcleo se dividió en el paquete `clipia/` (`transcripcion`,
  `momentos`, `subtitulos`, `rostros`, `exportacion`, `descarga`,
  `utilidades`, `config`, `logs`); `clipia_core.py` sigue existiendo
  como fachada compatible.
- Type hints en todo el código y lint con ruff (`pyproject.toml`).
- Logging rotativo en `%LOCALAPPDATA%/ClipIA/logs/clipia.log`
  (1 MB x 5 copias) y en consola; los errores de los hilos quedan
  registrados con su traza.
- Configuración JSON en `%APPDATA%/ClipIA/config.json` (modelo,
  idioma, carpeta de salida, estilo de subtítulos, encoder, seguir
  rostros). La app recuerda la carpeta de salida y la opción de
  rostros entre sesiones.
- Suite pytest en `tests/` (74 tests): unitarios de formatos,
  puntuación de ventanas, fragmentos de subtítulo, traslapes,
  expresión de rostros y parseo de tiempos; tests de GUI, de los
  `.bat`, de la configuración, del logging y del repositorio; y una
  prueba e2e con video sintético de ffmpeg.
- `setup.bat` crea un entorno virtual `.venv` e instala las
  dependencias dentro; `run.bat` y `diagnostico.bat` prefieren el
  venv y caen al Python global si no existe.
- CI en GitHub Actions (`windows-latest`): ruff + pytest en cada push.
- `.gitignore` y licencia MIT.
- `test_pipeline.py` ampliado: detecta rostros en el primer clip,
  genera su vista previa (540x960), verifica la duración pedida vs
  real (±0.5 s), el stream de audio AAC y la presencia real de
  subtítulos (eventos ASS + píxeles de texto en el fotograma).

## [1.1.3] - 13-11-2026

- Corregido el congelamiento de la barra de progreso al exportar o
  previsualizar: el stderr de ffmpeg iba por un tubo aparte que nadie
  leía; en Windows ese tubo se llena y ffmpeg se queda esperando para
  siempre. Ahora el stderr va unido al tubo de progreso (`-v error`).

## [1.1.2] - 13-11-2026

- Detección de rostros reescrita: los fotogramas se extraen con ffmpeg
  (sin `cv2.VideoCapture`), con límite de 60 s por clip y recorte
  centrado si se agota, y un máximo de 12 puntos en la expresión de
  seguimiento.

## [1.1.1] - 13-11-2026

- Detección de rostros secuencial con `CAP_FFMPEG` y porcentaje de
  avance.

## [1.1.0] - 12-11-2026

- Seguimiento de rostros (OpenCV Haar): el recorte vertical sigue la
  cara del hablante.
- Vista previa por clip (540x960, sin subtítulos).
- Corregido el botón de exportar que quedaba deshabilitado al terminar.

## [1.0.5] - 12-11-2026

- Primera versión que funcionó de punta a punta en el PC de destino.

## [1.0.4] - 12-11-2026

- Carpeta de salida con respaldo `Videos` → `~/ClipIA` → `./salida`
  (la carpeta `Videos` del PC de destino está dañada).

## [1.0.3] - 12-11-2026

- Correcciones de lanzamiento (dependencias y arranque).

## [1.0.2] - 12-11-2026

- Correcciones de lanzamiento (dependencias y arranque).

## [1.0.1] - 12-11-2026

- Correcciones de lanzamiento (dependencias y arranque).

## [1.0.0] - 12-11-2026

- Primera versión: cargar video o URL de YouTube, transcribir con
  faster-whisper, detectar momentos, exportar clips verticales
  1080x1920 con subtítulos quemados estilo Shorts.
