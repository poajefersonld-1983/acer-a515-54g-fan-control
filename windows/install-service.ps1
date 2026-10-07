param([bool]$Startup = $true)
$ErrorActionPreference = 'Stop'
$expected = Join-Path ([Environment]::GetFolderPath('ProgramFiles')) 'AcerFanControl'
if ([IO.Path]::GetFullPath($PSScriptRoot) -ne $expected) { throw 'Execute na pasta instalada.' }
$exe = Join-Path $expected 'AcerFanControl.exe'
$profile = Join-Path ([Environment]::GetFolderPath('CommonApplicationData')) 'AcerFanControl'
New-Item -ItemType Directory -Path $profile -Force | Out-Null
& "$env:SystemRoot\System32\icacls.exe" $profile /inheritance:r /grant:r '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Falha ao proteger o perfil.' }
$binary = '"' + $exe + '" --service'
$existing = Get-Service -Name AcerFanControl -ErrorAction SilentlyContinue
if ($existing) {
    Set-Service -Name AcerFanControl -StartupType Automatic
} else {
    New-Service -Name AcerFanControl -DisplayName 'Acer Fan Control — Prévia Windows' -BinaryPathName $binary -StartupType Automatic -Description 'Controle limitado ao Aspire A515-54G / Doc_WC / BIOS V1.24. Módulo assinado e validação Windows pendentes.' | Out-Null
}
& sc.exe failure AcerFanControl reset= 86400 actions= restart/10000/restart/30000/restart/60000
if ($LASTEXITCODE -ne 0) { throw 'Falha ao configurar recuperação.' }
if ($Startup) {
    $action = New-ScheduledTaskAction -Execute $exe -Argument '--minimized'
    $user = [Security.Principal.WindowsIdentity]::GetCurrent().Name
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $user
    $principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Highest
    $settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
    Register-ScheduledTask -TaskName 'AcerFanControlInterface' -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
} else {
    Unregister-ScheduledTask -TaskName 'AcerFanControlInterface' -Confirm:$false -ErrorAction SilentlyContinue
}
Start-Service AcerFanControl

