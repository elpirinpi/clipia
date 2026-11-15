# -*- mode: python ; coding: utf-8 -*-
"""Spec de PyInstaller para KellyAiClip (Fase 4).

One-folder, solo CPU: el .exe queda en dist/KellyAiClip/KellyAiClip.exe junto
a sus DLLs y datos. El instalador Inno Setup empaqueta esa carpeta
(más ffmpeg.exe, ffprobe.exe y el modelo YuNet, que el workflow de
GitHub Actions añade después del build).

NO ejecutar en Linux: el build es en GitHub Actions (windows-latest)
con `pyinstaller clipia.spec`. El tamaño esperado del instalador es
de unos 300-400 MB (sin librerías CUDA: el wheel de ctranslate2 para
Windows solo trae cudnn64_9.dll, 19.5 MB en total).
"""
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=[
        # Datos de CustomTkinter (temas, fuentes).
        *collect_data_files("customtkinter"),
        # Binarios tkdnd de tkinterdnd2 (win-x64 entre ellos): sin
        # ellos el arrastrar y soltar no funciona en el instalador.
        *collect_data_files("tkinterdnd2"),
        # Certificados TLS (los usa huggingface_hub al descargar el
        # modelo de voz).
        *collect_data_files("certifi"),
        # Modelo ONNX de detección de voz (VAD) de faster-whisper
        # (assets/silero_vad_v6.onnx): sin él, toda transcripción
        # desde la app instalada falla con ONNXRuntimeError
        # NO_SUCHFILE (en desarrollo funciona porque el archivo está
        # en site-packages).
        *collect_data_files("faster_whisper"),
    ],
    hiddenimports=[
        # yt-dlp carga sus extractores de forma dinámica: sin esto
        # el binario no sabe descargar de YouTube.
        *collect_submodules("yt_dlp"),
        "faster_whisper",
        "ctranslate2",
        "huggingface_hub",
        "tqdm",
        "tokenizers",
        "PIL",
        "cv2",
        "numpy",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="KellyAiClip",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    # UPX desactivado: comprime las DLLs y a veces rompe las de
    # OpenCV/ctranslate2; el instalador ya comprime con lzma2.
    upx=False,
    # App de ventana (sin consola): los errores van al log de
    # %LOCALAPPDATA%/ClipIA/logs/clipia.log, no a una consola.
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="KellyAiClip",
)
