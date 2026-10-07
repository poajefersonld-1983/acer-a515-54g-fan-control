param([string]$Destination = (Join-Path ([Environment]::GetFolderPath('Desktop')) 'Acer Fan Control - Instalador'))
$ErrorActionPreference = 'Stop'
$compiler = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
$build = Join-Path $PSScriptRoot 'build'
New-Item -ItemType Directory -Path $build,$Destination -Force | Out-Null
$references = @('/reference:System.Windows.Forms.dll','/reference:System.Drawing.dll','/reference:System.Management.dll','/reference:System.ServiceProcess.dll','/reference:System.Web.Extensions.dll')
$app = Join-Path $build 'AcerFanControl.exe'
& $compiler /nologo /target:winexe /platform:x64 /optimize+ @references ('/win32manifest:' + (Join-Path $PSScriptRoot 'app.manifest')) ('/out:' + $app) (Join-Path $PSScriptRoot 'Core.cs') (Join-Path $PSScriptRoot 'App.cs')
if ($LASTEXITCODE -ne 0) { throw 'Compilação do aplicativo falhou.' }
$tests = Join-Path $build 'Tests.exe'
& $compiler /nologo /target:exe /platform:x64 @references ('/out:' + $tests) (Join-Path $PSScriptRoot 'Core.cs') (Join-Path $PSScriptRoot 'Tests.cs')
if ($LASTEXITCODE -ne 0) { throw 'Compilação dos testes falhou.' }
& $tests (Join-Path $build 'test-data')
if ($LASTEXITCODE -ne 0) { throw 'Testes falharam.' }
$source = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'Setup.cs') -Raw -Encoding UTF8
$source = $source.Replace('APP_HASH',(Get-FileHash -LiteralPath $app -Algorithm SHA256).Hash)
$generated = Join-Path $build 'Setup.generated.cs'
Set-Content -LiteralPath $generated -Value $source -Encoding UTF8
$setup = Join-Path $Destination 'Instalar.exe'
$arguments = @('/nologo','/target:winexe','/platform:x64','/optimize+','/reference:Microsoft.CSharp.dll') + $references + @(('/win32manifest:' + (Join-Path $PSScriptRoot 'app.manifest')),('/out:' + $setup))
$arguments += '/resource:' + $app + ',payload.AcerFanControl.exe'
foreach ($file in @('README.md','LICENSE','install-service.ps1','uninstall.ps1')) { $arguments += '/resource:' + (Join-Path $PSScriptRoot $file) + ',payload.' + $file }
$arguments += $generated
& $compiler @arguments
if ($LASTEXITCODE -ne 0) { throw 'Compilação do instalador falhou.' }
foreach ($file in @('LEIA-ME.txt','README.md','LICENSE')) { Copy-Item -LiteralPath (Join-Path $PSScriptRoot $file) -Destination $Destination -Force }
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'images') -Destination $Destination -Recurse -Force
Set-Content -LiteralPath (Join-Path $Destination 'SHA256.txt') -Value ((Get-FileHash -LiteralPath $setup -Algorithm SHA256).Hash + '  Instalar.exe') -Encoding ASCII
Write-Output ('Prévia criada: ' + $setup)

