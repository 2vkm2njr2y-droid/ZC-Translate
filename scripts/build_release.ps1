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
# build_portable.ps1 -Release 会把中立发行目录写到 build\release\ZCTranslate，
# 本机日常使用的 dist\ZCTranslate 保持不变（模型指针、data\ 都不动）。
$dist = Join-Path $Root "build\release\ZCTranslate"
if (-not $SkipBuild) {
    Write-Step "构建便携目录版并生成中立发行目录"
    $buildArgs = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "scripts\build_portable.ps1", "-Release")
    if ($Clean) { $buildArgs += "-Clean" }
    & powershell @buildArgs
    Assert-Exit "build_portable.ps1"
} else {
    Write-Step "跳过 exe 构建，复用 build\release\ZCTranslate"
}

$exe = Join-Path $dist "ZCTranslate.exe"
if (-not (Test-Path $exe)) {
    throw "未找到 $exe。请去掉 -SkipBuild，先运行 scripts\build_portable.ps1 -Release。"
}

# ---------------------------------------------------------------- 发布前自检
Write-Step "发布前自检"
$problems = @()

# 运行打包版做验收测试时可能生成 data（日志/数据库），发布前清掉。
$dataDir = Join-Path $dist "data"
if (Test-Path $dataDir) {
    $resolvedDistForData = (Resolve-Path $dist).Path
    $resolvedData = (Resolve-Path $dataDir).Path
    if ($resolvedData -ne (Join-Path $resolvedDistForData "data")) {
        throw "拒绝删除：$resolvedData 不是预期的数据目录"
    }
    Remove-Item -LiteralPath $resolvedData -Recurse -Force
    Write-Host "已删除残留 data（验收测试产生）：$resolvedData" -ForegroundColor Yellow
}

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
                    "NOTICE", "THIRD_PARTY_NOTICES.md", "LICENSING.md")) {
    if (-not (Test-Path (Join-Path $dist $name))) { $problems += "缺少 $name" }
}
if (-not (Test-Path (Join-Path $dist "licenses"))) { $problems += "缺少 licenses（第三方许可证原文）" }
if ($problems.Count -gt 0) {
    throw ("发布自检未通过：`n - " + ($problems -join "`n - "))
}
Write-Host "自检通过：无 data/models，无本机路径，LICENSE 为 AGPL。" -ForegroundColor Green

# ---------------------------------------------------------------- ZIP
$zipPath = Join-Path $outDir "ZCTranslate-$Version-win64-portable.zip"
if (-not $SkipZip) {
    Write-Step "生成便携版 ZIP"
    if (Test-Path $zipPath) { Remove-Item -LiteralPath $zipPath -Force }
    & tar.exe -a -c -f $zipPath -C (Join-Path $Root "build\release") "ZCTranslate"
    Assert-Exit "tar 打包"
    $entries = & tar.exe -tf $zipPath
    Assert-Exit "ZIP 校验"
    foreach ($expected in @("ZCTranslate/ZCTranslate.exe", "ZCTranslate/LICENSE",
                            "ZCTranslate/NOTICE", "ZCTranslate/THIRD_PARTY_NOTICES.md",
                            "ZCTranslate/Start-ZCTranslate.bat", "ZCTranslate/README.md")) {
        if (-not ($entries -contains $expected)) { throw "ZIP 缺少 $expected" }
    }
    if (-not ($entries | Where-Object { $_ -like "ZCTranslate/licenses/*" })) {
        throw "ZIP 缺少 licenses 目录"
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
        for ($attempt = 1; $attempt -le 3 -and -not $downloaded; $attempt++) {
            Write-Host "下载 NSIS（第 $attempt 次）…"
            if (Test-Path $nsisZip) { Remove-Item -LiteralPath $nsisZip -Force }
            # SourceForge 会先返回 HTML 中转页，必须用 curl 跟随重定向拿到真正的 zip。
            & curl.exe -sSL --fail --retry 2 --max-time 300 -o $nsisZip $NsisZipUrl
            if ($LASTEXITCODE -eq 0 -and (Test-Path $nsisZip)) {
                $magic = [System.IO.File]::ReadAllBytes($nsisZip)[0..1]
                if ($magic[0] -eq 0x50 -and $magic[1] -eq 0x4B) {
                    $downloaded = $true
                } else {
                    Write-Host "下载内容不是 ZIP（可能是 SourceForge 中转页）。" -ForegroundColor Yellow
                }
            }
            if (-not $downloaded) { Start-Sleep -Seconds 3 }
        }
        if (-not $downloaded) { throw "无法下载 NSIS：$NsisZipUrl（可手动解压到 $nsisDir\nsis-3.11）" }
        Expand-Archive -Path $nsisZip -DestinationPath $nsisDir -Force
        Remove-Item -LiteralPath $nsisZip -Force
    }
    if (-not (Test-Path $makensis)) {
        throw "未找到 makensis.exe，请检查 $nsisDir\nsis-3.11"
    }

    Write-Step "生成 NSIS 安装包（LZMA，约 5–15 分钟）"
    # 两个环境相关的坑（本机实测）：
    # 1) makensis 在 C:\Users\...\Temp 下创建 mmap 会失败（杀软/受控文件夹），
    #    把 TEMP/TMP 指到仓库内 .tools\tmp 后再编译；
    # 2) 输出直接写到发布目录偶尔报 "Can't open output file"，
    #    先输出到 .tools\nsis-out，再复制到发布目录并重试。
    $stagingDir = Join-Path $Root ".tools\nsis-out"
    New-Item -ItemType Directory -Force -Path $stagingDir | Out-Null
    $built = Join-Path $stagingDir "ZCTranslate-$Version-win64-setup.exe"
    $nsisTemp = Join-Path $Root ".tools\tmp"
    New-Item -ItemType Directory -Force -Path $nsisTemp | Out-Null
    Get-ChildItem $stagingDir -Filter "ZCTranslate-*-win64-setup.exe" -ErrorAction SilentlyContinue |
        Remove-Item -Force -ErrorAction SilentlyContinue

    $savedTemp = $env:TEMP
    $savedTmp = $env:TMP
    $env:TEMP = $nsisTemp
    $env:TMP = $nsisTemp
    $compiled = $false
    try {
        for ($attempt = 1; $attempt -le 2 -and -not $compiled; $attempt++) {
            if (Test-Path $built) { Remove-Item -LiteralPath $built -Force -ErrorAction SilentlyContinue }
            # 注意：脚本里的变量名带下划线（APP_VERSION），/D 必须同名。
            & $makensis "/DAPP_VERSION=$Version" "/DOUTDIR=$stagingDir" "/DDIST=$dist" "scripts\installer.nsi"
            if ($LASTEXITCODE -eq 0 -and (Test-Path $built)) {
                $compiled = $true
            } else {
                Write-Host "makensis 第 $attempt 次失败（退出码 $LASTEXITCODE），准备重试…" -ForegroundColor Yellow
                Start-Sleep -Seconds 3
            }
        }
    } finally {
        $env:TEMP = $savedTemp
        $env:TMP = $savedTmp
    }
    if (-not $compiled) { throw "makensis 编译失败；若已有旧安装包可检查 $stagingDir" }

    if (-not (Test-Path $built)) { throw "makensis 未生成 $built" }
    if (Test-Path $setupPath) { Remove-Item -LiteralPath $setupPath -Force -ErrorAction SilentlyContinue }
    $copied = $false
    for ($i = 1; $i -le 5 -and -not $copied; $i++) {
        try {
            Copy-Item -LiteralPath $built -Destination $setupPath -Force
            $copied = $true
        } catch {
            Write-Host "复制安装包失败（第 $i 次）：$($_.Exception.Message)" -ForegroundColor Yellow
            Start-Sleep -Seconds 2
        }
    }
    if (-not $copied) { throw "无法写入 $setupPath，安装包保留在 $built" }
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
