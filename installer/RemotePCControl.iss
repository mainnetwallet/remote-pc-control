#define MyAppName "Remote PC Control"
#define MyAppVersion "0.1.0"
[Setup]
AppId={{A2C7E5B3-0A54-4B62-9F24-7F5A6D8C1001}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
DefaultDirName={localappdata}\Programs\RemotePCControl
DefaultGroupName=Remote PC Control
PrivilegesRequired=lowest
OutputDir=..\dist-installer
OutputBaseFilename=RemotePCControl-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64
[Files]
Source: "..\dist\RemotePCControl.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\INSTALL_WINDOWS.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\scripts\configure-installed.ps1"; DestDir: "{app}"; Flags: ignoreversion
[Icons]
Name: "{group}\Remote PC Control"; Filename: "{app}\RemotePCControl.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\Remote PC Control"; Filename: "{app}\RemotePCControl.exe"; WorkingDir: "{app}"
[Run]
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\configure-installed.ps1"""; WorkingDir: "{app}"; Flags: postinstall
