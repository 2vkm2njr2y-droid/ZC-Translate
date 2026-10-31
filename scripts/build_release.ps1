param(
    [string]$Version = "",
    [switch]$Clean,
    [switch]$SkipBuild,
    [switch]$SkipZip,
    [switch]$SkipInstaller
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$NsisZipUrl = "https://sourceforge.net/projects/nsis/files/NSIS%203/3.11/nsis-3.11.zip/download"

function Write-Step([string]$text) {
    Write-Host "`n== $text ==" -ForegroundColor Cyan
}

function Assert-Exit([string]$what) {
    if ($LASTEXITCODE -ne 0) {
        throw "$what 失败，退出码：$LASTEXITCODE"
    }
}

# ---------------------------------------------------------------- version
if (-not $Version) {
    $match = Select-String -Path "app\backend\config.py" `
        -Pattern 'APP_VERSION\s*=\s*"([^"]+)"' | Select-Object -First 1
    if ($match) { $Version = $match.Matches[0].Groups[1].Value }
}
if (-not $Version) { throw "无法从 app\backend\config.py 读取 APP_VERSION，请用 -Version 指定。" }

$outDir = Join-Path $Root "dist\release\v$Version"
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
Write-Host "版本：$Version" -ForegroundColor Green
Write-Host "输出：$outDir"

# ---------------------------------------------------------------- portable build
$dist = Join-Path $Root "dist\ZCTranslate"
if (-not $SkipBuild) {
    Write-Step "构建便携目录版（-Release：去掉本机路径与 data\）"
    $buildArgs = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "scripts\build_portable.ps1", "-Release")
    if ($Clean) { $buildArgs += "-Clean" }
    & powershell @buildArgs
    Assert-Exit "build_portable.ps1"
} else {
    Write-Step "跳过 exe 构建，复用现有 dist"
}

$exe = Join-Path $dist "ZCTranslate.exe"
if (-not (Test-Path $exe)) { throw "未找到 $exe。请去掉 -SkipBuild 重新构建。" }

# ---------------------------------------------------------------- 发布前自检
Write-Step "发布前自检"
$problems = @()
if (Test-Path (Join-Path $dist "data")) { $problems += "发行目录仍包含 data\" }
if (Test-Path (Join-Path $dist "models")) { $problems += "发行目录仍包含 models\" }
if (-not (Test-Path (Join-Path $dist "portable.flag"))) { $problems += "缺少 portable.flag（便携版需要）" }

$licensePath = Join-Path $dist "LICENSE"
if (-not (Test-Path $licensePath)) {
    $problems += "缺少 LICENSE"
} elseif (-not (Select-String -Path $licensePath -Pattern "GNU AFFERO GENERAL PUBLIC LICENSE" -SimpleMatch -Quiet)) {
    $problems += "LICENSE 不是 AGPL-3.0 原文"
}

$textFiles = @(
    (Join-Path $dist "models-path.txt"),
    (Join-Path $dist "使用说明.txt"),
    (Join-Path $dist "启动翻译器.bat"),
    (Join-Path $dist "Start-ZCTranslate.bat")
) | Where-Object { Test-Path $_ }
foreach ($file in $textFiles) {
    if (Select-String -Path $file -Pattern ([regex]::Escape($Root)) -SimpleMatch -Quiet) {
        $problems += "$([System.IO.Path]::GetFileName($file)) 仍包含构建机路径 $Root"
    }
}
foreach ($name in @("README.md", "README.en.md", "README.ja.md", "README.ko.md", "README.es.md",
                    "THIRD_PARTY_NOTICES.md", "LICENSING.md")) {
    if (-not (Test-Path (Join-Path $dist $name))) { $problems += "缺少 $name" }
}
if ($problems.Count -gt 0) {
    throw ("发布自检未通过：`n - " + ($problems -join "`n - "))
}
Write-Host "自检通过：无 data/models，无本机路径，LICENSE 为 AGPL。" -ForegroundColor Green

# ---------------------------------------------------------------- ZIP
$zipPath = Join-Path $outDir "ZCTranslate-$Version-win64-portable.zip"
if (-not $SkipZip) {
    Write-Step "生成便携版 ZIP"
    if (Test-Path $zipPath) { Remove-Item -LiteralPath $zipPath -Force }
    & tar.exe -a -c -f $zipPath -C (Join-Path $Root "dist") "ZCTranslate"
    Assert-Exit "tar 打包"
    $entries = & tar.exe -tf $zipPath
    Assert-Exit "ZIP 校验"
    foreach ($expected in @("ZCTranslate/ZCTranslate.exe", "ZCTranslate/LICENSE",
                            "ZCTranslate/Start-ZCTranslate.bat", "ZCTranslate/README.md")) {
        if (-not ($entries -contains $expected)) { throw "ZIP 缺少 $expected" }
    }
    Write-Host ("ZIP：{0}（{1:N1} MB）" -f $zipPath, ((Get-Item $zipPath).Length / 1MB)) -ForegroundColor Green
}

# ---------------------------------------------------------------- NSIS
$setupPath = Join-Path $outDir "ZCTranslate-$Version-win64-setup.exe"
if (-not $SkipInstaller) {
    Write-Step "准备 NSIS 3.11（便携工具，不安装到系统）"
    $toolsDir = Join-Path $Root ".tools"
    $nsisDir = Join-Path $toolsDir "nsis"
    $makensis = Join-Path $nsisDir "nsis-3.11\makensis.exe"
    if (-not (Test-Path $makensis)) {
        New-Item -ItemType Directory -Force -Path $nsisDir | Out-Null
        $nsisZip = Join-Path $toolsDir "nsis-3.11.zip"
        $downloaded = $false
        for ($attempt = 1; $attempt -le 2 -and -not $downloaded; $attempt++) {
            try {
                Write-Host "下载 NSIS（第 $attempt 次）…"
                Invoke-WebRequest -Uri $NsisZipUrl -OutFile $nsisZip -UseBasicParsing -TimeoutSec 300
                $downloaded = $true
            } catch {
                Write-Host "下载失败：$($_.Exception.Message)" -ForegroundColor Yellow
                Start-Sleep -Seconds 3
            }
        }
        if (-not $downloaded) { throw "无法下载 NSIS：$NsisZipUrl（可手动解压到 $nsisDir\nsis-3.11）" }
        Expand-Archive -Path $nsisZip -DestinationPath $nsisDir -Force
        Remove-Item -LiteralPath $nsisZip -Force
    }
    if (-not (Test-Path $makensis)) {
        throw "未找到 makensis.exe，请检查 $nsisDir\nsis-3.11"
    }

    Write-Step "生成 NSIS 安装包（LZMA，约 5–15 分钟）"
    if (Test-Path $setupPath) { Remove-Item -LiteralPath $setupPath -Force }
    & $makensis "/DAPPVERSION=$Version" "/DOUTDIR=$outDir" "/DDIST=$dist" "scripts\installer.nsi"
    Assert-Exit "makensis"
    Write-Host ("安装包：{0}（{1:N1} MB）" -f $setupPath, ((Get-Item $setupPath).Length / 1MB)) -ForegroundColor Green
}

# ---------------------------------------------------------------- 校验和
Write-Step "生成 SHA256SUMS.txt"
$assets = @($zipPath, $setupPath) | Where-Object { Test-Path $_ }
$lines = foreach ($asset in $assets) {
    $hash = (Get-FileHash -LiteralPath $asset -Algorithm SHA256).Hash
    "$hash  $(Split-Path -Leaf $asset)"
}
$sumsPath = Join-Path $outDir "SHA256SUMS.txt"
Set-Content -LiteralPath $sumsPath -Value $lines -Encoding ASCII
$lines | ForEach-Object { Write-Host "  $_" }

Write-Step "完成"
Write-Host "输出目录：$outDir" -ForegroundColor Green
Get-ChildItem $outDir | ForEach-Object {
    Write-Host ("  {0}  {1:N1} MB" -f $_.Name, ($_.Length / 1MB))
}
Write-Host "`n下一步（推送源码后）：" -ForegroundColor Cyan
Write-Host "  git tag -a v$Version -m `"ZC 离线翻译 v$Version`""
Write-Host "  git push origin v$Version"
Write-Host "  gh release create v$Version --draft --verify-tag --title `"ZC 离线翻译 v$Version`" --notes-file docs\release-notes-v$Version.md"
Write-Host "  gh release upload v$Version `"$zipPath`" `"$setupPath`" `"$sumsPath`" --clobber"
