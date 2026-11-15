# Historial de cambios de KellyAiClip

Todos los cambios importantes de cada versión. El formato sigue
[Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/).

## [2.0.1] - 15-11-2026

- **Corregida la columna izquierda invisible en la app instalada**:
  el panel de origen del video salía vacío (sin «Examinar…», sin
  «Pegar URL», sin «Analizar video») porque un
  `pack_propagate(False)` sobre el marco desplazable colapsaba su
  layout interno a 1x1. Se quitó esa línea; la columna usa su
  ancho fijo de 360 px como estaba previsto. Nuevo test de
  regresión: los botones y campos de la columna deben medir más
  de 1 px de ancho tras arrancar la app.
- **Renombre a KellyAiClip**: título de la ventana, encabezado,
  instalador (`KellyAiClip-Setup-2.0.1.exe`, en
  `%LOCALAPPDATA%\Programs\KellyAiClip`), ejecutable
  (`KellyAiClip.exe`) y `--version` (`KellyAiClip 2.0.1`). Las
  carpetas internas (`%APPDATA%/ClipIA`, `%LOCALAPPDATA%/ClipIA`,
  `Videos\ClipIA`) no cambian, así las instalaciones existentes
  conservan su configuración, caché y modelo de voz.
- **Créditos en la interfaz**: el pie de la ventana principal
  muestra «Desarrollado por Kelly Benjamin de la Cruz».

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

### Fase 4: distribución (13-11-2026)

- **Instalador de Windows**: PyInstaller one-folder (`clipia.spec`,
  solo CPU, sin librerías CUDA) + Inno Setup
  (`instalador/clipia.iss`): un único `ClipIA-Setup-2.0.0.exe` que
  instala la app por usuario (sin permisos de administrador) en
  `%LOCALAPPDATA%\Programs\ClipIA`, con acceso directo en el menú
  Inicio y desinstalador. El usuario final ya NO instala Python,
  winget ni ffmpeg a mano: ffmpeg y ffprobe van embebidos junto al
  `.exe` (la app añade su carpeta al PATH al arrancar) y el modelo
  YuNet va empaquetado (si está junto al `.exe`, no se descarga).
- **Build en GitHub Actions** (`.github/workflows/build.yml`): en
  cada push de un tag `v*` (o al lanzarlo a mano) compila el
  instalador en `windows-latest` (PyInstaller 6.22.3, ffmpeg de
  Gyan.dev, YuNet con verificación SHA-256, prueba de humo
  `ClipIA.exe --version`) y lo sube como artefacto del workflow.
  El build no se puede probar en el servidor de desarrollo (Linux):
  la primera corrida del workflow es la prueba real.
- **YouTube más robusto**: opción de cookies del navegador en
  Ajustes (Chrome, Edge o Firefox) para el anti-bot de YouTube; si
  las cookies fallan, la descarga se reintenta una vez sin ellas.
  Los errores de yt-dlp se traducen a mensajes accionables en
  español (qué hacer en cada caso: iniciar sesión, actualizar
  yt-dlp, revisar la conexión...). Botón «Actualizar yt-dlp» en
  Ajustes: en modo dev actualiza con pip; en el instalador descarga
  o auto-actualiza el binario standalone oficial `yt-dlp.exe`
  (~23 MB), que la app prefiere sobre la librería empaquetada
  cuando existe (la librería empaquetada no se puede actualizar
  con pip).
- **Modelo de voz con progreso visible**: en el primer uso, la
  descarga del modelo Whisper muestra su avance real en la barra de
  estado («Descargando modelo de voz…»); sin red, el error dice
  qué hacer en vez del error técnico de faster-whisper.
- Flag `--version` (`ClipIA.exe --version` imprime la versión y
  sale sin abrir ventana; lo usa la prueba de humo del build).
- La suite pytest crece a 351 tests (cookies y errores de descarga,
  binario externo y actualización de yt-dlp, progreso del modelo,
  validación del spec/ISS/workflow, YuNet empaquetado).
- Métricas finales (video 2:57, CPU, modelo base): transcribir
  ~21 s en frío (0.1 s desde caché), vista previa de 60 s con
  subtítulos ~22 s, export de 60 s ~50 s (el objetivo de 30 s en
  CPU sigue sin alcanzarse; el camino es NVENC en GPU, sin medir
  en este servidor), 0 clips cortados a media frase.

### Fase 3: UX de producto (13-11-2026)

- **Editor de clip** (`clipia/editor.py`): cada tarjeta tiene un
  botón «✎ Editar» que abre una ventana con sliders de inicio/fin,
  la forma de onda del tramo (con el clip resaltado) y la
  transcripción clicable: un clic en una palabra (o en la onda)
  fija el límite activo (inicio o fin). Al guardar, el clip
  actualiza sus tiempos y su texto y se conserva la selección; la
  miniatura se regenera con el nuevo punto medio.
- **Vista previa con subtítulos y recorte final**: la vista previa
  reutiliza la ruta de exportación a 540x960 con los mismos
  subtítulos (estilo y margen actuales de los ajustes) y el mismo
  recorte que el clip final (libass escala el .ass de 1080x1920 al
  marco de 540x960). Verificado con píxeles de texto en el
  fotograma.
- **Cola multi-video**: la columna izquierda tiene una sección
  «Cola de videos» para añadir varios videos y analizarlos uno
  tras otro; un video con error no tumba los demás. Cada clip
  recuerda de qué video viene y las tarjetas muestran su origen
  cuando hay varios videos.
- **Pegar URL del portapapeles**: el botón «Pegar URL» copia una
  URL de YouTube desde el portapapeles (avisa si no hay texto o no
  es una URL).
- **Arrastrar y soltar** (`tkinterdnd2`): soltar un video sobre la
  ventana lo carga; soltar varios los añade a la cola; soltar una
  URL la pone en el campo de URL. La integración usa la API oficial
  `require()` para CustomTkinter (prototipo R3: tkdnd 2.10.3 carga
  limpio) y el import es opcional: sin la librería la app funciona
  sin DnD.
- **Guardar/cargar proyecto** (`clipia/proyecto.py`): los botones
  «Guardar proyecto» / «Abrir proyecto» guardan un archivo
  `.clipia` (JSON) con los videos analizados (ruta, duración y
  transcripción), los clips (con los tiempos editados), la
  selección y la carpeta de salida. Al abrir, los videos que ya no
  están en su ruta se ofrecen para localizarlos. Las miniaturas se
  regeneran al abrir.
- **Ajustes ampliados**: el diálogo de Ajustes tiene dos secciones
  nuevas — el modelo de Ollama para el reordenado con IA local
  (por defecto `qwen2.5:7b`) y el lote de transcripción
  (Automático/4/8/16) — y el contenido se desplaza para que quepa
  en pantallas bajas; el botón Guardar queda fijo abajo.
- **Resumen de exportación**: al terminar, un diálogo lista cada
  clip con ✓/✗/⊘ (y el motivo del fallo) y un botón «Abrir
  carpeta» que abre la carpeta de salida. Si todo se canceló, no
  se muestra el diálogo.
- La suite pytest crece a 280 tests (editor, vista previa con
  subtítulos quemados, cola multi-video, pegar URL, proyecto,
  ajustes persistidos, resultado de exportación, arrastrar y
  soltar).

### Fase 2: calidad de clips (13-11-2026)

- **Cortes en frases completas** (`clipia/momentos.py`): el fin de
  cada clip se ajusta a la frontera de frase más cercana con los
  timestamps por palabra (antes `fin = inicio + duración` cortaba a
  media palabra). Los clips duran como mínimo 25 s; si una sola
  frase cubre toda la ventana, el clip termina al final de esa
  frase. Verificado: 0 cortes a media frase en el video de prueba.
- **Palabras gancho limpias y ponderadas por rareza**: fuera «te»,
  «voy», «pasa», «paso», «todos», «ahora» y «nuevo» (y los
  duplicados); cada palabra gancho se pondera con un idf simple
  sobre el propio video, así una palabra rara («secreto») pesa más
  que una que se repite en todo el video.
- **Reordenar con IA local, opcional** (`clipia/ollama.py`): el
  botón «✨ Reordenar con IA local» envía los ~25 mejores candidatos
  a un LLM local vía Ollama (`qwen2.5:7b` por defecto) que puntúa
  gancho, coherencia y remate de cada uno; la puntuación final
  mezcla un 60% de la IA con un 40% de la heurística. Sin Ollama
  instalado, el botón muestra las instrucciones de instalación y la
  app sigue con la heurística de siempre; si Ollama no responde, no
  bloquea (timeout de 2 s para conectar, 180 s para generar) y se
  conserva el orden heurístico. La selección de clips se conserva
  al reordenar.
- **Subtítulos karaoke y presets** (`clipia/subtitulos.py`): cuatro
  estilos — «Shorts clásico» (el de siempre), «Hormozi» (palabra
  activa amarilla, MAYÚSCULAS, karaoke), «Minimal» (letra más
  pequeña, sin negrita) y «Neón» (cian/magenta, karaoke). Los
  estilos karaoke pintan cada palabra al pronunciarse (tags `\k`
  de ASS con los timestamps por palabra). El **margen vertical** es
  configurable en Ajustes (300 px por defecto; súbelo si los
  botones de TikTok tapan los subtítulos). El estilo y el margen se
  guardan en la configuración.
- **Audio normalizado a -14 LUFS**: cada clip exportado pasa por
  `loudnorm` en una sola pasada con ganancia lineal (sin bombeo
  dinámico en la voz), el nivel de TikTok/Reels/Shorts. Solo se
  aplica si el video tiene audio. Coste: ~1 s por clip de 60 s.
- **Detección de rostros con YuNet** (`clipia/rostros.py`):
  `cv2.FaceDetectorYN` en vez de Haar: detecta perfiles y caras
  parcialmente tapadas, donde Haar fallaba. El modelo ONNX (~230 KB)
  se descarga en el primer uso (con verificación SHA-256 y caché
  local); sin red o sin modelo, se usa Haar como antes. La
  trayectoria se suaviza con media móvil de 3 y **banda muerta**:
  un movimiento menor del 5% del ancho no mueve el recorte, así el
  tembleque de la detección no se ve en el video. El recorte usa
  hasta **45 puntos de interpolación** (antes 12): `crop` no admite
  comandos sendcmd, así que se subió el tope de la expresión. La
  clave de caché de rostros incluye el detector, así las detecciones
  de Haar no se reutilizan con YuNet. Se conservan el timeout de
  60 s con recorte centrado y la extracción de fotogramas vía ffmpeg.
- La suite pytest crece a 208 tests (snap a frontera de frase,
  ponderación idf, re-ranking con Ollama ausente y simulado,
  karaoke y cada preset, loudnorm medido a -14 LUFS, YuNet con cara
  en movimiento, banda muerta y fallback a Haar).
- El test de miniaturas en paralelo ya no exige un tiempo total
  menor de 1.5 s (frágil en máquinas cargadas: se midió 29 s en una
  corrida de la suite completa en el servidor de desarrollo); la
  prueba de paralelismo es la concurrencia observada y el tiempo
  solo acota un posible cuelgue.

### Fase 1: rendimiento (13-11-2026)

- **Encoder por hardware autodetectado** (`clipia/encoder.py`): al
  arrancar, la app prueba con un video de 1 s los codificadores
  `h264_nvenc` → `h264_qsv` → `h264_amf` y usa el primero que
  funcione; si ninguno funciona o el elegido falla, vuelve a
  `libx264` (CPU). El pie de la ventana muestra cuál se está usando
  y en **Ajustes** se puede elegir uno a mano (se guarda en la
  configuración). En un PC sin GPU compatible no cambia nada: sigue
  usando la CPU como antes.
- **Transcripción más rápida** (`clipia/transcripcion.py`): usa
  `BatchedInferencePipeline` de faster-whisper (lotes de 8 en CPU,
  16 en GPU) y el modelo queda cacheado en memoria (singleton, hasta
  2 modelos): analizar un segundo video ya no recarga el modelo. En
  **Ajustes** se elige el modelo (tiny/base/small/medium/large-v3,
  con aviso si el equipo no tiene RAM suficiente) y el idioma del
  audio (español, inglés, portugués, francés, italiano, alemán o
  autodetectar; por defecto español).
- **Caché en disco** (`clipia/cache.py`): la transcripción y la
  detección de rostros se guardan en `%LOCALAPPDATA%/ClipIA/cache`
  con una clave por archivo (ruta + tamaño + fecha de modificación)
  y parámetros. Reanalizar el mismo video es casi instantáneo y los
  rostros ya no se detectan dos veces (vista previa y exportación).
  Límite de 500 MB con poda automática de las entradas más antiguas.
- **Cola de exportación** (`clipia/cola.py`): los clips se exportan
  con workers configurables (automático: 1 con CPU, 2 con
  codificador por hardware; ajustable a 1–3 en Ajustes). La barra
  muestra el avance global, el clip en curso y el tiempo estimado
  restante. El botón **Cancelar** detiene el lote: mata el ffmpeg
  en curso en menos de 2 s, borra el archivo parcial y no empieza
  los clips pendientes. Un clip que falla se reintenta una vez sin
  tumbar el lote; al final se informa cuáles fallaron y por qué.
- **Miniaturas en paralelo**: las miniaturas de la lista de clips se
  generan con 4 workers a la vez en vez de una tras otra.
- **Al cerrar la app no quedan ffmpeg huérfanos**
  (`clipia/procesos.py`): cada ffmpeg de larga duración (exportación,
  detección de rostros, extracción de audio) se registra al arrancar;
  al cerrar, la app cancela la exportación en curso y termina todos
  los procesos registrados.
- La suite pytest crece a 144 tests (encoder con fallback, caché de
  transcripción y rostros, cancelación que mata el proceso y borra
  el parcial, reintento por clip, cierre sin huérfanos, miniaturas
  en paralelo, workers de la cola).
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
