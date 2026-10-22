param(
    [string]$GeneratedDir = "$PSScriptRoot/../out/delivery/demo/src-gen",
    [string]$BuildDir = "$PSScriptRoot/../out/build/windows",
    [switch]$Demo
)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path "$PSScriptRoot/..").Path
$vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
$vs = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (-not $vs) { throw 'Visual Studio 2022 C++ Build Tools required' }
$cmake = "$vs\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe"
$ninja = "$vs\Common7\IDE\CommonExtensions\Microsoft\CMake\Ninja\ninja.exe"
$GeneratedDir = (Resolve-Path $GeneratedDir).Path
New-Item -ItemType Directory -Force $BuildDir | Out-Null
$BuildDir = (Resolve-Path $BuildDir).Path
$demoFlag = if ($Demo) { 'ON' } else { 'OFF' }
# Invoke only paths supplied by the local developer, with cmd metacharacters rejected.
foreach ($p in @($root,$vs,$cmake,$ninja,$GeneratedDir,$BuildDir)) {
    if ($p -match '["%\r\n!&|<>^]') { throw "Unsupported cmd metacharacter in path: $p" }
}
$command = @"
@echo off
call "$vs\VC\Auxiliary\Build\vcvars64.bat"
if errorlevel 1 exit /b 1
"$cmake" -S "$root" -B "$BuildDir" -G Ninja -DCMAKE_MAKE_PROGRAM="$ninja" -DCMAKE_BUILD_TYPE=Release -DAMW_GENERATED_DIR="$GeneratedDir" -DAMW_BUILD_DEMO=$demoFlag
if errorlevel 1 exit /b 1
"$cmake" --build "$BuildDir" --parallel 4
if errorlevel 1 exit /b 1
set "PATH=$GeneratedDir\dependencies\windows-x64\bin;%PATH%"
"$vs\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\ctest.exe" --test-dir "$BuildDir" --output-on-failure
exit /b %ERRORLEVEL%
"@
$file = Join-Path $BuildDir 'build.cmd'
[IO.File]::WriteAllText($file,$command,[Text.Encoding]::Default)
& cmd.exe /d /c $file
if ($LASTEXITCODE -ne 0) { throw "Windows build/test failed: $LASTEXITCODE" }
