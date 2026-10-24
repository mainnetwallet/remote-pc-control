#define MyAppName "Remote PC Control"
#define MyAppVersion "0.1.0"
[Setup]
AppId={{A2C7E5B3-0A54-4B62-9F24-7F5A6D8C1001}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
DefaultDirName={autopf}\RemotePCControl
DefaultGroupName=Remote PC Control
DisableProgramGroupPage=yes
SetupIconFile=..\assets\app.ico
PrivilegesRequired=admin
CloseApplications=no
SetupLogging=yes
UninstallDisplayIcon={app}\RemotePCControl.exe
OutputDir=..\dist-installer
OutputBaseFilename=RemotePCControl-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64
[Files]
Source: "..\dist\RemotePCControl.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\dist\tsbridge.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\INSTALL_WINDOWS.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\assets\app.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\scripts\register-installed-task.ps1"; DestDir: "{app}"; Flags: ignoreversion
[Icons]
Name: "{autoprograms}\Remote PC Control"; Filename: "{app}\RemotePCControl.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\Remote PC Control"; Filename: "{app}\RemotePCControl.exe"; WorkingDir: "{app}"
[InstallDelete]
Type: filesandordirs; Name: "{autoprograms}\Remote PC Control"
Type: filesandordirs; Name: "{userprograms}\Remote PC Control"
Type: files; Name: "{userdesktop}\Remote PC Control.lnk"
[Run]
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\register-installed-task.ps1"" -Exe ""{app}\RemotePCControl.exe"""; WorkingDir: "{app}"; Flags: runhidden waituntilterminated; StatusMsg: "Setting up autostart, administrator rights and firewall..."
; shellexec: the exe needs administrator rights (UAC); starting it with CreateProcess fails with error 740
Filename: "{app}\RemotePCControl.exe"; Description: "Open Remote PC Control now"; WorkingDir: "{app}"; Flags: nowait postinstall skipifsilent shellexec
[UninstallRun]
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\register-installed-task.ps1"" -Remove"; Flags: runhidden waituntilterminated; RunOnceId: "RemovePCTask"
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\register-installed-task.ps1"" -Kind lock -Remove"; Flags: runhidden waituntilterminated; RunOnceId: "RemoveLockTask"
Filename: "taskkill.exe"; Parameters: "/F /IM RemotePCControl.exe"; Flags: runhidden; RunOnceId: "KillPC"
Filename: "taskkill.exe"; Parameters: "/F /IM tsbridge.exe"; Flags: runhidden; RunOnceId: "KillTsBridge"

[Code]
// An installed Remote PC Control keeps running (agent, PIN lock screen) and its scheduled tasks start it again when it
// is ended, which blocks replacing RemotePCControl.exe. So before anything is copied: switch the tasks off, end the
// program, and after the copy switch the tasks on again.
procedure Quiet(const Exe, Params: String);
var Code: Integer;
begin
  Exec(Exe, Params, '', SW_HIDE, ewWaitUntilTerminated, Code);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var Tasks: String;
begin
  Result := '';
  Tasks := ExpandConstant('{sys}\schtasks.exe');
  Quiet(Tasks, '/Change /TN "RemotePCControl" /DISABLE');
  Quiet(Tasks, '/Change /TN "RemotePCControlLock" /DISABLE');
  Quiet(Tasks, '/End /TN "RemotePCControl"');
  Quiet(Tasks, '/End /TN "RemotePCControlLock"');
  Quiet(ExpandConstant('{sys}\taskkill.exe'), '/F /T /IM RemotePCControl.exe');
  Quiet(ExpandConstant('{sys}\taskkill.exe'), '/F /T /IM tsbridge.exe');
  Sleep(2000);
  Quiet(ExpandConstant('{sys}\taskkill.exe'), '/F /T /IM RemotePCControl.exe');   // a second pass for a copy that was just restarted
  Sleep(500);
end;

procedure CurStepChanged(CurStep: TSetupStep);
var Tasks: String;
begin
  if CurStep = ssPostInstall then
  begin
    Tasks := ExpandConstant('{sys}\schtasks.exe');
    Quiet(Tasks, '/Change /TN "RemotePCControl" /ENABLE');       // the setup script registers it again as well
    Quiet(Tasks, '/Change /TN "RemotePCControlLock" /ENABLE');   // only exists when the user turned the lock screen on
  end;
end;
