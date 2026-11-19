#define MyAppName "SS Serial Generator"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "SS Serial Generator"
#define MyAppExeName "SS_Serial_Generator.exe"

[Setup]
AppId={{4F53B6CB-21BE-44AF-92E5-1D4BDDE7428F}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\SS Serial Generator
DefaultGroupName={#MyAppName}
PrivilegesRequired=lowest
OutputDir=dist\installer
OutputBaseFilename=SS_Serial_Generator_Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional icons:"

[Files]
Source: "dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent
