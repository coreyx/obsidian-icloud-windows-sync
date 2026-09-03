; Inno Setup script for obsidian-sync + obsidian-sync-tray.
;
; Per-user install (no admin required, Requirement 9.4) under
; {localappdata}\Programs\obsidian-sync. Assumes both PyInstaller onedir
; builds already exist at ..\dist\obsidian-sync-tray and ..\dist\obsidian-sync
; (build both specs first -- see installer\build.ps1).
;
; Install layout:
;   {app}\obsidian-sync-tray.exe   + {app}\_internal\...        (tray bundle)
;   {app}\daemon\obsidian-sync.exe + {app}\daemon\_internal\... (daemon bundle)
; Kept in separate subfolders rather than flattened together because each
; PyInstaller onedir bundle has its own same-named _internal\ dependency
; tree -- merging them into one directory would collide those. process_manager.py's
; frozen-mode daemon-exe lookup expects exactly this layout.

#define MyAppName "obsidian-sync"
#define MyAppVersion "1.3.0"
#define MyAppPublisher "obsidian-sync"
#define MyAppExeName "obsidian-sync-tray.exe"
#define MyDaemonExeName "obsidian-sync.exe"
#define MyRunKeyPath "Software\Microsoft\Windows\CurrentVersion\Run"
#define MyRunValueName "obsidian-sync-tray"

[Setup]
AppId={{6B7C9F2E-6C0C-4E3E-9C7A-6D3E0B1E9F3D}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist-installer
OutputBaseFilename=obsidian-sync-setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}
DisableWelcomePage=no

; No code-signing certificate: expect an "Unknown Publisher" SmartScreen
; prompt on first run (specs/tray-app/design.md -- Error Handling; out of
; scope for this feature).

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "startuplaunch"; Description: "Start {#MyAppName} automatically when you log in"; GroupDescription: "Additional options:"; Flags: unchecked
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"; Flags: unchecked

[Files]
Source: "..\dist\obsidian-sync-tray\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\dist\obsidian-sync\*"; DestDir: "{app}\daemon"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

; The startup-at-login registration is the SAME HKCU Run value the tray
; app's own "Start on Windows startup" menu item manages at runtime
; (obsidian_sync_tray/autostart.py) -- this just gives it an install-time
; opt-in. Deliberately no `uninsdeletevalue` flag here: since the tray app
; can also write/toggle this same value independently of what the
; installer did, only removing it unconditionally in [Code] below (not
; conditioned on this Task) correctly satisfies Requirement 10.2 either way.
[Registry]
Root: HKCU; Subkey: "{#MyRunKeyPath}"; ValueType: string; ValueName: "{#MyRunValueName}"; ValueData: """{app}\{#MyAppExeName}"""; Tasks: startuplaunch

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName} now"; Flags: nowait postinstall skipifsilent

[Code]
procedure KillRunningProcesses;
var
  ResultCode: Integer;
  TaskKillPath: String;
begin
  // Best-effort hard stop of both processes before touching files, at both
  // install (covers reinstall/upgrade over a running instance) and
  // uninstall (Requirement 10.1). A hard kill rather than the tray's own
  // graceful stop-file protocol is a deliberate simplification for the
  // installer context -- worst case the daemon re-hashes unchanged files
  // on its next run, which it already does safely.
  TaskKillPath := ExpandConstant('{sys}\taskkill.exe');
  Exec(TaskKillPath, '/IM {#MyAppExeName} /F', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Exec(TaskKillPath, '/IM {#MyDaemonExeName} /F', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;

function InitializeSetup(): Boolean;
begin
  KillRunningProcesses;
  Result := True;
end;

function InitializeUninstall(): Boolean;
begin
  KillRunningProcesses;
  Result := True;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DaemonDataDir, TrayDataDir: String;
begin
  if CurUninstallStep = usUninstall then
  begin
    KillRunningProcesses;
    // Unconditional: removes this value whether the installer's Task set
    // it or the tray app's own runtime toggle did (Requirement 10.2).
    RegDeleteValue(HKCU, '{#MyRunKeyPath}', '{#MyRunValueName}');
  end;

  if CurUninstallStep = usPostUninstall then
  begin
    // Config/logs/sync-state cache live outside {app}, in the user's
    // AppData, and are left in place by default (Requirement 10.3) --
    // ask explicitly before removing them (Requirement 10.4).
    // /SUPPRESSMSGBOXES only silences Setup's own built-in dialogs, not
    // custom MsgBox calls -- a fully silent/scripted uninstall would
    // otherwise hang here waiting for input. Skip the prompt and default
    // to the safe choice (leave the data in place) when running silently.
    if not WizardSilent() then
    begin
      DaemonDataDir := ExpandConstant('{userappdata}\obsidian-sync');
      TrayDataDir := ExpandConstant('{userappdata}\obsidian-sync-tray');
      if DirExists(DaemonDataDir) or DirExists(TrayDataDir) then
      begin
        if MsgBox('Also remove your saved configuration, logs, and sync history? This cannot be undone.',
                  mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
        begin
          DelTree(DaemonDataDir, True, True, True);
          DelTree(TrayDataDir, True, True, True);
        end;
      end;
    end;
  end;
end;
