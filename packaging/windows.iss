#ifndef AppVersion
  #error AppVersion must be provided by build_windows.ps1
#endif
[Setup]
AppId={{B4C4B1A6-F1CD-4211-8149-AF13D8FDDC74}
AppName=codebone
AppVersion={#AppVersion}
AppPublisher=codebone
AppPublisherURL=https://github.com/palusc/codebone
DefaultDirName={localappdata}\Programs\codebone
DefaultGroupName=codebone
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename=codebone-windows-x64-setup
SetupIconFile=..\build\codebone.ico
UninstallDisplayIcon={app}\codebone.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
CloseApplicationsFilter=codebone.exe,cbone.exe
RestartApplications=no

[Tasks]
Name: desktopicon; Description: "Create a desktop shortcut"; Flags: unchecked
Name: startup; Description: "Start codebone when I sign in"; Flags: unchecked

[Files]
Source: "..\dist\codebone\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\codebone"; Filename: "{app}\codebone.exe"
Name: "{group}\Uninstall codebone"; Filename: "{uninstallexe}"
Name: "{autodesktop}\codebone"; Filename: "{app}\codebone.exe"; Tasks: desktopicon
Name: "{userstartup}\codebone"; Filename: "{app}\codebone.exe"; Tasks: startup

[Run]
Filename: "{app}\codebone.exe"; Description: "Launch codebone"; Flags: nowait postinstall skipifsilent

; Uninstall removes installed files and owned shortcuts, retaining user data and projects.
