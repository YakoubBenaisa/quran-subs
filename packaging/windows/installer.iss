; Inno Setup script for Quran Companion (built by packaging/build.py, which passes the /D values).
; Installs for the current user (no admin prompt), adds Start menu / optional desktop shortcuts.
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef SourceDir
  #define SourceDir "..\..\dist\QuranCompanion"
#endif
#ifndef OutputDir
  #define OutputDir "..\..\dist"
#endif
#ifndef IconFile
  #define IconFile "..\..\build\logo.ico"
#endif
#ifndef OutputName
  #define OutputName "QuranCompanion-setup"
#endif

[Setup]
AppId={{6E0B8F5C-3B3E-4C8E-9C7A-51A3D0F1C0AB}
AppName=Quran Companion
AppVerName=Quran Companion {#AppVersion}
AppVersion={#AppVersion}
AppPublisher=Quran Companion
DefaultDirName={localappdata}\Programs\Quran Companion
DefaultGroupName=Quran Companion
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir={#OutputDir}
OutputBaseFilename={#OutputName}
SetupIconFile={#IconFile}
UninstallDisplayIcon={app}\QuranCompanion.exe
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Quran Companion"; Filename: "{app}\QuranCompanion.exe"; Parameters: "ui"
Name: "{autodesktop}\Quran Companion"; Filename: "{app}\QuranCompanion.exe"; Parameters: "ui"; Tasks: desktopicon

[Run]
Filename: "{app}\QuranCompanion.exe"; Parameters: "ui"; Description: "{cm:LaunchProgram,Quran Companion}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; the on-screen verses run as a second QuranCompanion.exe: stop it before removing the files
Filename: "{cmd}"; Parameters: "/C taskkill /IM QuranCompanion.exe /F"; Flags: runhidden; RunOnceId: "StopApp"
