[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$SecretDir = Join-Path $ProjectDir '.secrets'
$SecretPath = Join-Path $SecretDir 'zotero_key.dpapi'
$OpenAlexSecretPath = Join-Path $SecretDir 'openalex_key.dpapi'

Write-Host '请在 Zotero 网站创建一个只允许访问“个人文库”、具有读写权限的专用 API Key。'
Write-Host '密钥不会显示，也不会写入配置文件；它将用 Windows 当前用户 DPAPI 加密。'
$SecureKey = Read-Host '请粘贴 Zotero API Key' -AsSecureString
if ($SecureKey.Length -eq 0) {
    throw '没有输入 API Key。'
}

New-Item -ItemType Directory -Path $SecretDir -Force | Out-Null
$Encrypted = ConvertFrom-SecureString $SecureKey
Set-Content -LiteralPath $SecretPath -Value $Encrypted -Encoding UTF8 -NoNewline
Write-Host "密钥已加密保存到 $SecretPath"

Write-Host 'OpenAlex 用于检索论文。免费 API Key 可从 openalex.org/settings/api 获取。'
$OpenAlexSecureKey = Read-Host '请粘贴 OpenAlex API Key' -AsSecureString
if ($OpenAlexSecureKey.Length -eq 0) {
    throw '没有输入 OpenAlex API Key。'
}
$OpenAlexEncrypted = ConvertFrom-SecureString $OpenAlexSecureKey
Set-Content -LiteralPath $OpenAlexSecretPath -Value $OpenAlexEncrypted -Encoding UTF8 -NoNewline
Write-Host "OpenAlex 密钥已加密保存到 $OpenAlexSecretPath"
Write-Host '下一步运行：.\run.ps1 -Initial -VerboseOutput'
