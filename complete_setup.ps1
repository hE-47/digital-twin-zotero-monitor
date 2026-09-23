[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host '步骤 1/3：安全保存 Zotero 与 OpenAlex 密钥' -ForegroundColor Cyan
& (Join-Path $ProjectDir 'setup.ps1')

Write-Host '步骤 2/3：首次检索近 8 个月并导入最多 6 篇' -ForegroundColor Cyan
& (Join-Path $ProjectDir 'run.ps1') -Initial -VerboseOutput
if ($LASTEXITCODE -ne 0) {
    throw '首次导入失败，尚未创建每日计划任务。请查看 logs 目录。'
}

Write-Host '步骤 3/3：创建每天 08:30 的 Windows 计划任务' -ForegroundColor Cyan
& (Join-Path $ProjectDir 'install_task.ps1') -At '08:30'
Write-Host '全部完成。请打开 Zotero 并同步，查看“数字孪生_每日追踪”目录。' -ForegroundColor Green
