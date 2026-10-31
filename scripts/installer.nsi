; ZC 离线翻译 / ZC Translate — NSIS 安装脚本
; 由 scripts/build_release.ps1 调用：
;   makensis /DAPPVERSION=0.1.0 /DOUTDIR=<输出目录> /DDIST=<dist\ZCTranslate> scripts\installer.nsi
; 按当前用户安装（免 UAC），数据目录沿用应用的 %LOCALAPPDATA%\ZCTranslate。

Unicode true
!include "MUI2.nsh"
!include "FileFunc.nsh"

!ifndef APP_VERSION
  !define APP_VERSION "0.1.0"
!endif
!ifndef DIST
  !define DIST "..\dist\ZCTranslate"
!endif
!ifndef OUTDIR
  !define OUTDIR "..\dist\release"
!endif

!define APP_NAME "ZC 离线翻译"
!define APP_EXE "ZCTranslate.exe"
!define APP_PUBLISHER "ZC Translate contributors"
!define APP_ID "ZCTranslate"
!define UNINST_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_ID}"

Name "${APP_NAME}"
OutFile "${OUTDIR}\ZCTranslate-${APP_VERSION}-win64-setup.exe"
InstallDir "$LOCALAPPDATA\Programs\ZCTranslate"
InstallDirRegKey HKCU "Software\ZCTranslate" "InstallDir"
RequestExecutionLevel user
; 安装包约 670 MB：不能用 /SOLID（32 位 makensis 会耗尽地址空间报 mmap 错误），
; 逐文件 LZMA 压缩内存占用低得多，体积略大。
SetCompressor lzma
SetCompressorDictSize 16
ShowInstDetails show
ShowUninstDetails show
BrandingText "${APP_NAME} ${APP_VERSION}"

VIProductVersion "${APP_VERSION}.0"
VIAddVersionKey "ProductName" "${APP_NAME}"
VIAddVersionKey "ProductVersion" "${APP_VERSION}"
VIAddVersionKey "FileVersion" "${APP_VERSION}"
VIAddVersionKey "CompanyName" "${APP_PUBLISHER}"
VIAddVersionKey "LegalCopyright" "Copyright (C) 2026 ZC Translate contributors. AGPL-3.0-only."
VIAddVersionKey "FileDescription" "${APP_NAME} 安装程序"

!define MUI_ABORTWARNING
!define MUI_ICON "${DIST}\zc-translate.ico"
!define MUI_UNICON "${DIST}\zc-translate.ico"
!define MUI_WELCOMEPAGE_TITLE "安装 ${APP_NAME} ${APP_VERSION}"
!define MUI_WELCOMEPAGE_TEXT "本安装包不包含翻译模型。安装完成后请按 README 的“模型”一节准备 Hy-MT2，否则程序可以启动但无法翻译。$\r$\n$\r$\n安装到当前用户目录（$LOCALAPPDATA\Programs\ZCTranslate），不需要管理员权限；设置、历史与模型放在 $LOCALAPPDATA\ZCTranslate。"
!define MUI_LICENSEPAGE_TEXT_TOP "本程序以 GNU Affero General Public License v3.0（AGPL-3.0-only）发布。继续安装表示你接受该许可证。"
!define MUI_FINISHPAGE_RUN "$INSTDIR\${APP_EXE}"
!define MUI_FINISHPAGE_RUN_TEXT "立即运行 ${APP_NAME}（需要已准备模型）"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "${DIST}\LICENSE"
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "SimpChinese"
!insertmacro MUI_LANGUAGE "English"

; ------------------------------------------------------------------ 安装
Section "ZC 离线翻译（必需）" SecMain
  SectionIn RO
  SetOutPath "$INSTDIR"
  File /r /x "data" /x "portable.flag" "${DIST}\*.*"

  ; 安装版没有 portable.flag，数据落在 %LOCALAPPDATA%\ZCTranslate。
  CreateDirectory "$LOCALAPPDATA\ZCTranslate\models"
  FileOpen $0 "$INSTDIR\models-path.txt" w
  FileWrite $0 "# Models prepared by the user. Relative paths resolve against this folder.$\r$\n"
  FileWrite $0 "$LOCALAPPDATA\ZCTranslate\models$\r$\n"
  FileClose $0

  WriteUninstaller "$INSTDIR\uninstall.exe"

  CreateDirectory "$SMPROGRAMS\ZC 离线翻译"
  CreateShortcut "$SMPROGRAMS\ZC 离线翻译\ZC 离线翻译.lnk" "$INSTDIR\${APP_EXE}"
  CreateShortcut "$SMPROGRAMS\ZC 离线翻译\使用说明.lnk" "$INSTDIR\使用说明.txt"
  CreateShortcut "$SMPROGRAMS\ZC 离线翻译\卸载 ZC 离线翻译.lnk" "$INSTDIR\uninstall.exe"

  WriteRegStr HKCU "Software\ZCTranslate" "InstallDir" "$INSTDIR"
  WriteRegStr HKCU "${UNINST_KEY}" "DisplayName" "${APP_NAME}"
  WriteRegStr HKCU "${UNINST_KEY}" "DisplayVersion" "${APP_VERSION}"
  WriteRegStr HKCU "${UNINST_KEY}" "Publisher" "${APP_PUBLISHER}"
  WriteRegStr HKCU "${UNINST_KEY}" "DisplayIcon" "$INSTDIR\${APP_EXE}"
  WriteRegStr HKCU "${UNINST_KEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "${UNINST_KEY}" "UninstallString" "$\"$INSTDIR\uninstall.exe$\""
  WriteRegStr HKCU "${UNINST_KEY}" "QuietUninstallString" "$\"$INSTDIR\uninstall.exe$\" /S"
  WriteRegDWORD HKCU "${UNINST_KEY}" "NoModify" 1
  WriteRegDWORD HKCU "${UNINST_KEY}" "NoRepair" 1
  ${GetSize} "$INSTDIR" "/S=0K" $0 $1 $2
  IntFmt $0 "0x%08X" $0
  WriteRegDWORD HKCU "${UNINST_KEY}" "EstimatedSize" "$0"
SectionEnd

Section /o "桌面快捷方式" SecDesktop
  CreateShortcut "$DESKTOP\ZC 离线翻译.lnk" "$INSTDIR\${APP_EXE}"
SectionEnd

!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
  !insertmacro MUI_DESCRIPTION_TEXT ${SecMain} "程序本体、许可证、说明文档与卸载程序（必需）。"
  !insertmacro MUI_DESCRIPTION_TEXT ${SecDesktop} "在桌面创建快捷方式。"
!insertmacro MUI_FUNCTION_DESCRIPTION_END

; ------------------------------------------------------------------ 卸载
Section "Uninstall"
  Delete "$SMPROGRAMS\ZC 离线翻译\ZC 离线翻译.lnk"
  Delete "$SMPROGRAMS\ZC 离线翻译\使用说明.lnk"
  Delete "$SMPROGRAMS\ZC 离线翻译\卸载 ZC 离线翻译.lnk"
  RMDir "$SMPROGRAMS\ZC 离线翻译"
  Delete "$DESKTOP\ZC 离线翻译.lnk"

  RMDir /r "$INSTDIR"

  DeleteRegKey HKCU "${UNINST_KEY}"
  DeleteRegKey HKCU "Software\ZCTranslate"

  ; 用户数据目录（%LOCALAPPDATA%\ZCTranslate：设置、历史、术语库、翻译记忆、
  ; 编译缓存与模型）在卸载时一律保留，避免误删模型与历史；需要彻底清理请手动删除。
SectionEnd
