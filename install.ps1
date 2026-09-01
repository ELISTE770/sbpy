<#
.SYNOPSIS
    מתקין את SBpy בסביבה מבודדת ומוסיף פקודת `sbpy` גלובלית.

.DESCRIPTION
    יוצר venv נפרד ב-%LOCALAPPDATA%\SBpy\env כדי לא לגעת בפייתון הראשי,
    מתקין לתוכו את SBpy ואת google-genai, ויוצר shim בשם sbpy.cmd
    בתיקייה שמתווספת ל-PATH של המשתמש.

.EXAMPLE
    .\install.ps1
    .\install.ps1 -Dev          # התקנה editable, לפיתוח על הקוד עצמו
    .\install.ps1 -NoPath       # בלי לגעת ב-PATH
    .\install.ps1 -Uninstall
#>

[CmdletBinding()]
param(
    [switch]$Dev,
    [switch]$NoPath,
    [switch]$Uninstall,
    [switch]$NoGemini,
    [string]$Python = ""
)

$ErrorActionPreference = "Stop"
$env:PYTHONUTF8 = "1"

$ProjectRoot = $PSScriptRoot
$InstallRoot = Join-Path $env:LOCALAPPDATA "SBpy"
$EnvDir      = Join-Path $InstallRoot "env"
$BinDir      = Join-Path $InstallRoot "bin"
$VenvPython  = Join-Path $EnvDir "Scripts\python.exe"

# בלי מרכאות כפולות בפנים: PowerShell מוחק אותן כשהיא מעבירה ארגומנטים ל-exe חיצוני.
$VersionSnippet = 'import sys; print(sys.version.split()[0])'

function Write-Step([string]$Text) { Write-Host "  $Text" -ForegroundColor Cyan }
function Write-Ok([string]$Text)   { Write-Host "  $Text" -ForegroundColor Green }
function Write-Warn([string]$Text) { Write-Host "  $Text" -ForegroundColor Yellow }
function Write-Fail([string]$Text) { Write-Host "  $Text" -ForegroundColor Red }

function Get-UserPath {
    return [Environment]::GetEnvironmentVariable("Path", "User")
}

function Remove-FromUserPath([string]$Directory) {
    $current = Get-UserPath
    if (-not $current) { return }
    $kept = @()
    foreach ($part in $current.Split(";")) {
        if ($part -and ($part.TrimEnd("\") -ne $Directory.TrimEnd("\"))) { $kept += $part }
    }
    [Environment]::SetEnvironmentVariable("Path", ($kept -join ";"), "User")
}

function Add-ToUserPath([string]$Directory) {
    $current = Get-UserPath
    $parts = @()
    if ($current) {
        foreach ($part in $current.Split(";")) {
            if ($part) { $parts += $part }
        }
    }
    foreach ($part in $parts) {
        if ($part.TrimEnd("\") -eq $Directory.TrimEnd("\")) {
            Write-Ok "PATH כבר מכיל את $Directory"
            return $false
        }
    }
    $parts += $Directory
    [Environment]::SetEnvironmentVariable("Path", ($parts -join ";"), "User")
    return $true
}

# ----------------------------------------------------------------------
Write-Host ""
Write-Host "  SBpy installer" -ForegroundColor White

if ($Uninstall) {
    Write-Step "מסיר את SBpy..."
    Remove-FromUserPath $BinDir
    if (Test-Path $InstallRoot) {
        Remove-Item -Recurse -Force $InstallRoot
        Write-Ok "נמחק: $InstallRoot"
    }
    else {
        Write-Warn "לא נמצאה התקנה ב-$InstallRoot"
    }
    Write-Ok "הוסר. פתח טרמינל חדש כדי שה-PATH יתעדכן."
    Write-Host ""
    exit 0
}

# --- 1. איתור פייתון ---
$UsePyLauncher = $false
$Interpreter = $Python

if (-not $Interpreter) {
    $launcher = Get-Command "py" -ErrorAction SilentlyContinue
    if ($launcher) {
        $UsePyLauncher = $true
        $Interpreter = "py"
    }
    else {
        foreach ($candidate in @("python", "python3")) {
            $found = Get-Command $candidate -ErrorAction SilentlyContinue
            if ($found) { $Interpreter = $found.Source; break }
        }
    }
}

if (-not $Interpreter) {
    Write-Fail "לא נמצא פייתון. התקן מ-https://python.org ונסה שוב."
    exit 1
}

function Invoke-BasePython {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    if ($script:UsePyLauncher) {
        & py -3 @Arguments
    }
    else {
        & $script:Interpreter @Arguments
    }
}

$versionText = (Invoke-BasePython "-c" $VersionSnippet).Trim()
if (-not $versionText) {
    Write-Fail "לא הצלחתי להריץ את פייתון ($Interpreter)."
    exit 1
}
Write-Ok "פייתון $versionText"

$pieces = $versionText.Split(".")
$major = [int]$pieces[0]
$minor = [int]$pieces[1]
if (($major -lt 3) -or (($major -eq 3) -and ($minor -lt 10))) {
    Write-Fail "SBpy דורש Python 3.10 ומעלה (נמצא $versionText)."
    exit 1
}

# --- 2. סביבה מבודדת ---
if (Test-Path $VenvPython) {
    Write-Ok "סביבה קיימת: $EnvDir"
}
else {
    Write-Step "יוצר סביבה מבודדת ב-$EnvDir ..."
    New-Item -ItemType Directory -Force -Path $InstallRoot | Out-Null
    Invoke-BasePython "-m" "venv" $EnvDir
    if (-not (Test-Path $VenvPython)) {
        Write-Fail "יצירת ה-venv נכשלה."
        exit 1
    }
    Write-Ok "נוצרה."
}

# --- 3. התקנת החבילה ---
Write-Step "מתקין את SBpy..."
& $VenvPython -m pip install --quiet --disable-pip-version-check --upgrade pip

$spec = ".[gemini]"
if ($NoGemini) { $spec = "." }

Push-Location $ProjectRoot
try {
    if ($Dev) {
        & $VenvPython -m pip install --quiet --disable-pip-version-check -e $spec
    }
    else {
        & $VenvPython -m pip install --quiet --disable-pip-version-check $spec
    }
}
finally {
    Pop-Location
}

if ($LASTEXITCODE -ne 0) {
    Write-Fail "ההתקנה נכשלה."
    exit 1
}

if ($Dev) { Write-Ok "הותקן (editable)." } else { Write-Ok "הותקן." }

# --- 4. יצירת פקודת sbpy ---
New-Item -ItemType Directory -Force -Path $BinDir | Out-Null

$cmdShim = @"
@echo off
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
"$VenvPython" -m sbpy %*
"@
Set-Content -Path (Join-Path $BinDir "sbpy.cmd") -Value $cmdShim -Encoding ASCII

$ps1Shim = @"
`$env:PYTHONUTF8 = '1'
`$env:PYTHONIOENCODING = 'utf-8'
& '$VenvPython' -m sbpy `@args
exit `$LASTEXITCODE
"@
Set-Content -Path (Join-Path $BinDir "sbpy.ps1") -Value $ps1Shim -Encoding UTF8
Write-Ok "נוצרה פקודת sbpy ב-$BinDir"

# --- 5. PATH ---
if ($NoPath) {
    Write-Warn "לא נגעתי ב-PATH. הרצה ישירה: $BinDir\sbpy.cmd"
}
else {
    $added = Add-ToUserPath $BinDir
    if ($added) {
        Write-Ok "נוסף ל-PATH של המשתמש."
        $env:Path = "$env:Path;$BinDir"
    }
}

# --- 6. בדיקה ---
Write-Step "בודק..."
$check = (& $VenvPython -m sbpy --version 2>&1 | Out-String).Trim()
Write-Ok $check

Write-Host ""
Write-Host "  הכל מוכן." -ForegroundColor Green
Write-Host ""
Write-Host "    sbpy              " -ForegroundColor Yellow -NoNewline
Write-Host "פותח את הסביבה האינטראקטיבית"
Write-Host "    sbpy run app.py   " -ForegroundColor Yellow -NoNewline
Write-Host "מריץ קובץ עם אבחון"
Write-Host "    sbpy sfb app.py   " -ForegroundColor Yellow -NoNewline
Write-Host "מחפש באגים"
Write-Host "    sbpy doctor       " -ForegroundColor Yellow -NoNewline
Write-Host "בודק שהכל מחובר"
Write-Host ""

if (-not $env:GEMINI_API_KEY) {
    Write-Warn "אין GEMINI_API_KEY - SBpy יעבוד מקומית בלבד (וזה תקין)."
    Write-Host '    להפעלת ההסלמה:  setx GEMINI_API_KEY "your-key"' -ForegroundColor Gray
}
if (-not $NoPath) {
    Write-Warn "פתח טרמינל חדש כדי שהפקודה sbpy תיקלט."
}
Write-Host ""
