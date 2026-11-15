; ClipIA — instalador Inno Setup (Fase 4).
; Lo compila GitHub Actions (windows-latest) con ISCC tras el build
; de PyInstaller. La carpeta dist\ClipIA ya lleva ffmpeg.exe,
; ffprobe.exe y el modelo YuNet (los añade el workflow antes de
; compilar este script).
;
; Instalación por usuario (sin permisos de administrador): se
; instala en %LOCALAPPDATA%\Programs\ClipIA. El desinstalador lo
; quita todo (la carpeta de la app; la configuración y la caché de
; %APPDATA% y %LOCALAPPDATA% se conservan, como hacen la mayoría de
; apps, para no borrar el modelo de voz descargado).

#define AppVersion "2.0.0"

[Setup]
AppId={{6E4C0D58-E034-4BD7-B6B8-CFF9E2A8B1C6}
AppName=ClipIA
AppVersion={#AppVersion}
AppVerName=ClipIA {#AppVersion}
AppPublisher=ClipIA
AppPublisherURL=https://github.com/elpirinpi/clipia
AppSupportURL=https://github.com/elpirinpi/clipia/issues
DefaultDirName={localappdata}\Programs\ClipIA
DefaultGroupName=ClipIA
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
OutputDir=Output
OutputBaseFilename=ClipIA-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\ClipIA.exe

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\ClipIA\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\ClipIA"; Filename: "{app}\ClipIA.exe"
Name: "{autodesktop}\ClipIA"; Filename: "{app}\ClipIA.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\ClipIA.exe"; Description: "{cm:LaunchProgram,ClipIA}"; Flags: nowait postinstall skipifsilent
