# PowerShell script to create Desktop Shortcut for SBpy
$ProjectRoot = $PSScriptRoot
$ExePath = Join-Path $ProjectRoot "dist\sbpy.exe"
$IcoPath = Join-Path $ProjectRoot "assets\icon.ico"

if (-not (Test-Path $ExePath)) {
    Write-Host "[!] dist\sbpy.exe not found. Please run build.bat first." -ForegroundColor Red
    exit 1
}

# Resolve desktop path
$userprofile = $env:USERPROFILE
$desktop = Join-Path $userprofile "Desktop"
$onedrive = Join-Path $userprofile "OneDrive - PCMASTER\Desktop"
if (Test-Path $onedrive) {
    $desktop = $onedrive
}

$ShortcutPath = Join-Path $desktop "SBpy.lnk"

$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = $ExePath
$Shortcut.WorkingDirectory = $ProjectRoot
if (Test-Path $IcoPath) {
    $Shortcut.IconLocation = $IcoPath
}
$Shortcut.Description = "SBpy - Python AI Debugger, Error Fixer & Optimizer"
$Shortcut.Save()

Write-Host "[+] Shortcut created on Desktop: $ShortcutPath" -ForegroundColor Green
