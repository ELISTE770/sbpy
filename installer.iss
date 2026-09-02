; Inno Setup Script for SBpy
; Built by Smart Binary (https://smartbinary.org)
; GitHub Repository: https://github.com/ELISTE770/sbpy

#define MyAppName "SBpy"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "Smart Binary"
#define MyAppURL "https://smartbinary.org"
#define MyAppGitHub "https://github.com/ELISTE770/sbpy"
#define MyAppExeName "sbpy.exe"

[Setup]
AppId={{D37F869F-4BCB-4B76-B817-6B1C568A91EE}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppGitHub}
AppUpdatesURL={#MyAppGitHub}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
OutputDir=dist
OutputBaseFilename=SBpy_Setup
SetupIconFile=assets\icon.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ChangesEnvironment=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "hebrew"; MessagesFile: "compiler:Languages\Hebrew.isl"

[CustomMessages]
english.AddPathPrompt=Add SBpy to system PATH (Recommended)
hebrew.AddPathPrompt=הוסף את SBpy למשתנה הסביבה PATH (מומלץ)

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "envPath"; Description: "{cm:AddPathPrompt}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "assets\*"; DestDir: "{app}\assets"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\assets\icon.ico"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon; WorkingDir: "{app}"; IconFilename: "{app}\assets\icon.ico"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent shellexec

[Code]
const
    EnvironmentKey = 'Environment';

procedure AddToPath();
var
    Paths: string;
    AppDir: string;
begin
    AppDir := ExpandConstant('{app}');
    if not RegQueryStringValue(HKEY_CURRENT_USER, EnvironmentKey, 'Path', Paths) then
        Paths := '';

    if Pos(';' + Uppercase(AppDir) + ';', ';' + Uppercase(Paths) + ';') = 0 then
    begin
        if (Length(Paths) > 0) and (Paths[Length(Paths)] <> ';') then
            Paths := Paths + ';';
        Paths := Paths + AppDir;
        RegWriteStringValue(HKEY_CURRENT_USER, EnvironmentKey, 'Path', Paths);
    end;
end;

procedure RemoveFromPath();
var
    Paths, AppDir: string;
    P, L: Integer;
begin
    AppDir := ExpandConstant('{app}');
    if RegQueryStringValue(HKEY_CURRENT_USER, EnvironmentKey, 'Path', Paths) then
    begin
        P := Pos(';' + Uppercase(AppDir) + ';', ';' + Uppercase(Paths) + ';');
        if P > 0 then
        begin
            L := Length(AppDir);
            if P = 1 then
                Delete(Paths, 1, L + 1)
            else if P + L > Length(Paths) then
                Delete(Paths, P, L + 1)
            else
                Delete(Paths, P, L + 1);
            RegWriteStringValue(HKEY_CURRENT_USER, EnvironmentKey, 'Path', Paths);
        end;
    end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
    if (CurStep = ssPostInstall) and WizardIsTaskSelected('envPath') then
    begin
        AddToPath();
    end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
    if CurUninstallStep = usPostUninstall then
    begin
        RemoveFromPath();
    end;
end;
