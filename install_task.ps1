[CmdletBinding()]
param(
    [string]$At = '08:30'
)

$ErrorActionPreference = 'Stop'
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Runner = Join-Path $ProjectDir 'run.ps1'
$SecretPath = Join-Path $ProjectDir '.secrets\zotero_key.dpapi'
$TaskName = '数字孪生文献每日追踪'
$LegacyTaskName = '车辆数字孪生文献每日追踪'

if (-not (Test-Path -LiteralPath $SecretPath)) {
    throw '请先运行 setup.ps1 配置 Zotero API Key，并完成一次首次导入测试。'
}

$ParsedTime = [DateTime]::ParseExact($At, 'HH:mm', [Globalization.CultureInfo]::InvariantCulture)
$Argument = "-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$Runner`""
$Action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $Argument
$Trigger = New-ScheduledTaskTrigger -Daily -At $ParsedTime
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
$CurrentUser = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$Principal = New-ScheduledTaskPrincipal -UserId $CurrentUser -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Principal $Principal -Description '每天筛选数字孪生论文并写入 Zotero' -Force | Out-Null
if ($LegacyTaskName -ne $TaskName -and (Get-ScheduledTask -TaskName $LegacyTaskName -ErrorAction SilentlyContinue)) {
    Unregister-ScheduledTask -TaskName $LegacyTaskName -Confirm:$false
}
Write-Host "已创建计划任务：$TaskName（每天 $At，本机登录状态下运行）"
