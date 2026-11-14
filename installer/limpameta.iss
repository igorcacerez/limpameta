; Instalador do LimpaMeta (Inno Setup 6) — gerado por build.ps1
#ifndef AppVersion
  #define AppVersion "2.0.0"
#endif
#ifndef DistDir
  #define DistDir "..\dist\LimpaMeta"
#endif

[Setup]
AppId={{6D3B1C52-8E0A-4C1F-9F4B-2B7C5E0A9D11}
AppName=LimpaMeta
AppVersion={#AppVersion}
AppVerName=LimpaMeta {#AppVersion}
AppPublisher=igorcacerez
AppPublisherURL=https://github.com/igorcacerez/limpameta
AppSupportURL=https://github.com/igorcacerez/limpameta/issues
DefaultDirName={localappdata}\Programs\LimpaMeta
DefaultGroupName=LimpaMeta
DisableProgramGroupPage=yes
DisableDirPage=auto
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=LimpaMeta-Setup-{#AppVersion}
SetupIconFile=..\src\limpameta\assets\icon.ico
UninstallDisplayIcon={app}\LimpaMeta.exe
UninstallDisplayName=LimpaMeta
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64compatible
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "pt"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na Área de Trabalho"; GroupDescription: "Atalhos:"
Name: "sendto"; Description: "Adicionar ao menu ""Enviar para"" do Explorador de Arquivos"; GroupDescription: "Atalhos:"

[Files]
Source: "{#DistDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\LimpaMeta"; Filename: "{app}\LimpaMeta.exe"; Comment: "Veja e remova metadados de fotos e vídeos"
Name: "{autodesktop}\LimpaMeta"; Filename: "{app}\LimpaMeta.exe"; Tasks: desktopicon; Comment: "Veja e remova metadados de fotos e vídeos"
Name: "{userappdata}\Microsoft\Windows\SendTo\LimpaMeta"; Filename: "{app}\LimpaMeta.exe"; Tasks: sendto

[Run]
Filename: "{app}\LimpaMeta.exe"; Description: "Abrir o LimpaMeta agora"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
