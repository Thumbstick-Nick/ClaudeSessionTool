; Inno Setup script for Claude Usage Monitor
; Build with: ISCC.exe installer.iss   (or `py build.py`)

#define AppName        "Claude Usage Monitor"
#define AppVersion     "1.0.0"
#define AppPublisher   "Eagle Point Software"
#define AppExeName     "ClaudeUsageMonitor.exe"
#define SourceDir      "dist\ClaudeUsageMonitor"

[Setup]
AppId={{B4A12B5E-7C1F-4C91-9F3C-9F2C8F3D6E11}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL=
DefaultDirName={autopf}\ClaudeUsageMonitor
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir=dist-installer
OutputBaseFilename=ClaudeUsageMonitor-Setup-{#AppVersion}
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\{#AppExeName}
Compression=lzma2/ultra
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked
Name: "startupicon"; Description: "Launch &when I sign in to Windows"; GroupDescription: "Auto-start:"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{userdesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon
Name: "{userstartup}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: startupicon

[Run]
; Launch the app at the end of install so the first-run prompt can ask
; about Claude Code integration in its own UI.
Filename: "{app}\{#AppExeName}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; Best-effort: clean our SessionStart hook out of ~/.claude/settings.json
; on uninstall. Runs hidden; failure is non-fatal.
Filename: "{app}\{#AppExeName}"; Parameters: "--uninstall-hook"; Flags: runhidden

[Code]
function InitializeUninstall(): Boolean;
begin
  Result := True;
end;
