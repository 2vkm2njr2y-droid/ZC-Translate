# ZC 离线翻译 v0.1.1 / ZC Translate v0.1.1

修复版（Windows 11 x64）。功能与 v0.1.0 相同，重点修复模型定位与托盘恢复窗口尺寸。

## 简体中文

### 修复

1. **打包版找不到模型（桌面快捷方式启动）**
   - 原因：发布构建会就地改写可运行目录里的 `models-path.txt`（写成相对路径 `models`），通过桌面快捷方式直接启动 `ZCTranslate.exe` 时便找不到工作区模型。
   - 修复：发布构建改为在 `build\release\ZCTranslate` 生成一份中立发行目录，ZIP 与安装包从该目录产出；本机 `dist\ZCTranslate` 的模型指针、`data\` 与日志不再被改动。
   - 本机已恢复：`dist\ZCTranslate\models-path.txt` 指回工作区 `models`。

2. **关闭主窗口后再从托盘显示，窗口会变大**
   - 原因：WinForms 在窗口重新显示时会按 DPI 重新套用一次尺寸，每次托盘往返都可能放大一点。
   - 修复：隐藏前记录窗口的物理尺寸与 DPI；显示后立刻恢复，并在 80 ms / 300 ms 再校正一次；更换显示器导致 DPI 变化时按比例换算，保持相同的逻辑尺寸。

### 升级

- 便携版：用新 ZIP 覆盖旧目录即可，`data\` 与 `models` 不动。
- 安装版：直接安装覆盖；`%LOCALAPPDATA%\ZCTranslate` 保留。

### 下载与校验

| 资产 | 说明 |
|---|---|
| `ZCTranslate-0.1.1-win64-setup.exe` | NSIS 安装包（按用户安装，免 UAC，含开始菜单与卸载） |
| `ZCTranslate-0.1.1-win64-portable.zip` | 便携版，解压即用 |
| `SHA256SUMS.txt` | 两个包的 SHA-256 |

```powershell
Get-FileHash .\ZCTranslate-0.1.1-win64-portable.zip -Algorithm SHA256
```

### 说明

- 两个包都**不含翻译模型**，请按 README 的“模型”一节准备。
- 安装包未做代码签名，SmartScreen 提示“更多信息 → 仍要运行”。
- 许可证：AGPL-3.0-only；对应源码即本仓库 `v0.1.1` tag。

---

## English

### Fixes

1. **Packaged build could not find models when started from a desktop shortcut**
   - Cause: the release build rewrote `models-path.txt` inside the runnable folder to the relative path `models`, so launching `ZCTranslate.exe` directly lost the workspace models.
   - Fix: release packaging now stages a neutral copy under `build\release\ZCTranslate` and builds ZIP/installer from there; the local `dist\ZCTranslate` keeps its model pointer, `data\` and logs untouched.
   - Already restored locally: `dist\ZCTranslate\models-path.txt` points at the workspace `models` folder again.

2. **Main window grew after closing to tray and showing again**
   - Cause: WinForms re-applies DPI scaling when the form is shown again, so every tray round-trip could enlarge the window slightly.
   - Fix: capture the physical window size and DPI before hiding; restore immediately on show and re-apply after 80 ms / 300 ms; when the monitor DPI changes, scale proportionally so the logical size stays the same.

### Upgrade

- Portable: overwrite the old folder with the new ZIP; `data\` and `models` are untouched.
- Installed: install over the existing version; `%LOCALAPPDATA%\ZCTranslate` is preserved.

### Downloads

| Asset | Description |
|---|---|
| `ZCTranslate-0.1.1-win64-setup.exe` | NSIS installer (per-user, no UAC, Start Menu + uninstaller) |
| `ZCTranslate-0.1.1-win64-portable.zip` | Portable, unzip and run |
| `SHA256SUMS.txt` | SHA-256 checksums |

### Notes

- **No translation models are bundled**; see the “Models” section of the README.
- The installer is unsigned; SmartScreen will ask for “More info → Run anyway”.
- License: AGPL-3.0-only; the corresponding source is the `v0.1.1` tag of this repository.
