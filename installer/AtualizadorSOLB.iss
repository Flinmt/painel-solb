#define AppName "Atualizador SOLB"
#define AppVersion "0.3.0"
#define AppPublisher "SOLB"
#define AppExeName "Atualizador SOLB.exe"

[Setup]
AppId={{B4C4F17E-1E0E-4B0C-9DB7-2E8E0D5B9E6B}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\SOLB\Atualizador SOLB
DefaultGroupName={#AppName}
OutputDir=output
OutputBaseFilename=Atualizador-SOLB-Setup
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=admin
Uninstallable=yes
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na área de trabalho"; GroupDescription: "Atalhos:"; Flags: unchecked

[Files]
Source: "..\dist\Atualizador SOLB\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Abrir o {#AppName}"; Flags: nowait postinstall skipifsilent

[Code]
function InitializeSetup(): Boolean;
begin
  Result := RegKeyExists(HKEY_CLASSES_ROOT, 'Excel.Application\CLSID');
  if not Result then
    MsgBox('O Microsoft Excel não foi encontrado. Instale o Excel antes de usar o Atualizador SOLB.', mbError, MB_OK);
end;
