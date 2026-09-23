[CmdletBinding()]
param(
    [switch]$Initial,
    [switch]$DryRun,
    [switch]$VerboseOutput
)

$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$SecretPath = Join-Path $ProjectDir '.secrets\zotero_key.dpapi'
$OpenAlexSecretPath = Join-Path $ProjectDir '.secrets\openalex_key.dpapi'

if (-not $DryRun -and -not (Test-Path -LiteralPath $SecretPath)) {
    throw "Zotero 密钥尚未配置。请先运行 setup.ps1。"
}

$PythonCommand = Get-Command py.exe -ErrorAction SilentlyContinue
$PythonArgs = @('-3', (Join-Path $ProjectDir 'digital_twin_zotero.py'))
if (-not $PythonCommand) {
    $PythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
    $PythonArgs = @((Join-Path $ProjectDir 'digital_twin_zotero.py'))
}
if (-not $PythonCommand) {
    throw '未找到 Python 3。请安装 Python 3，并重新打开 PowerShell。'
}

if ($Initial) { $PythonArgs += '--initial' }
if ($DryRun) { $PythonArgs += '--dry-run' }
if ($VerboseOutput) { $PythonArgs += '--verbose' }

$Bstr = [IntPtr]::Zero
$OpenAlexBstr = [IntPtr]::Zero
try {
    if (-not $DryRun) {
        $Encrypted = Get-Content -Raw -LiteralPath $SecretPath
        $SecureKey = ConvertTo-SecureString $Encrypted
        $Bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecureKey)
        $env:ZOTERO_API_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($Bstr)
    }
    if (Test-Path -LiteralPath $OpenAlexSecretPath) {
        $OpenAlexEncrypted = Get-Content -Raw -LiteralPath $OpenAlexSecretPath
        $OpenAlexSecureKey = ConvertTo-SecureString $OpenAlexEncrypted
        $OpenAlexBstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($OpenAlexSecureKey)
        $env:OPENALEX_API_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($OpenAlexBstr)
    }
    & $PythonCommand.Source @PythonArgs
    exit $LASTEXITCODE
}
finally {
    Remove-Item Env:ZOTERO_API_KEY -ErrorAction SilentlyContinue
    Remove-Item Env:OPENALEX_API_KEY -ErrorAction SilentlyContinue
    if ($Bstr -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($Bstr)
    }
    if ($OpenAlexBstr -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($OpenAlexBstr)
    }
}
