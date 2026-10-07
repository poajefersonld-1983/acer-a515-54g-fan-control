$ErrorActionPreference = 'Stop'
$expected = Join-Path ([Environment]::GetFolderPath('ProgramFiles')) 'AcerFanControl'
$resolved = (Resolve-Path -LiteralPath $PSScriptRoot).ProviderPath
if ($resolved -ne $expected) { throw 'Execute na pasta instalada.' }
$service = Get-Service AcerFanControl -ErrorAction SilentlyContinue
if ($service) { Stop-Service AcerFanControl -ErrorAction Stop; & sc.exe delete AcerFanControl; if ($LASTEXITCODE -ne 0) { throw 'Falha ao remover o serviço.' } }
Unregister-ScheduledTask -TaskName AcerFanControlInterface -Confirm:$false -ErrorAction SilentlyContinue
$exe = Join-Path $resolved 'AcerFanControl.exe'
if (Get-Process AcerFanControl -ErrorAction SilentlyContinue) { throw 'O serviço foi parado. Saia da interface pelo menu da bandeja e execute novamente.' }
foreach ($folder in @([Environment]::GetFolderPath('Desktop'),[Environment]::GetFolderPath('Programs'))) {
    $shortcut = Join-Path $folder 'Acer Fan Control.lnk'
    if (Test-Path -LiteralPath $shortcut) { Remove-Item -LiteralPath $shortcut -Force }
}
Remove-Item -LiteralPath 'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\AcerFanControl' -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $resolved -Recurse -Force

