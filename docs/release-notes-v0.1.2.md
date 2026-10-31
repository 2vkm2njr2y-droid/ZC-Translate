# ZC 离线翻译 v0.1.2 / ZC Translate v0.1.2

文档、合规与稳定性版本（Windows 11 x64）。没有新增翻译功能；重点修复长文本翻译时卡顿、长时间无响应甚至闪退的问题。

## 简体中文

### 修复

- 长文本按行切分时，原来每一行都会单独调用一次模型。几万字的字幕、日志或分行文档会排成几百上千次推理，界面长时间无响应。现在会合并相邻短行，把上千个块压到几十个，速度、内存和界面都更稳定。
- 流式输出改为增量追加，不再每收到一个 token 就重建整段译文，避免长文本把 WebView2 拖死。
- 设置页“关于”中的版权与许可证声明现在会随程序一起显示。

### 变更

- 重写五种语言的 README（简体中文、English、日本語、한국어、Español），改成项目介绍，删掉了许可证选择过程的解释性段落。
- 补充 AGPL 合规材料：
  - 新增 `NOTICE`，写明版权、AGPL-3.0-only、无担保和对应源码地址。
  - 设置页“关于”增加版权、许可证、担保和源码声明。
  - 发行包新增 `licenses/`，收录运行时依赖的许可证原文。
  - 发布自检会检查 `NOTICE`、`licenses/` 和 ZIP 内容。
- 修复 PowerShell 构建脚本在 Windows PowerShell 5.1 下因 UTF-8 无 BOM 导致中文解析失败的问题。
- 更新 GitHub 仓库简介。

### 升级

- 便携版：用新 ZIP 覆盖旧目录即可，`data\` 与 `models` 不动。
- 安装版：直接安装覆盖；`%LOCALAPPDATA%\ZCTranslate` 保留。

### 下载与校验

| 资产 | 说明 |
|---|---|
| `ZCTranslate-0.1.2-win64-setup.exe` | NSIS 安装包（按用户安装，免 UAC，含开始菜单与卸载） |
| `ZCTranslate-0.1.2-win64-portable.zip` | 便携版，解压即用 |
| `SHA256SUMS.txt` | 两个包的 SHA-256 |

```powershell
Get-FileHash .\ZCTranslate-0.1.2-win64-portable.zip -Algorithm SHA256
```

### 说明

- 两个包都**不含翻译模型**，请按 README 的“准备模型”一节准备。
- 安装包未做代码签名，SmartScreen 提示“更多信息 → 仍要运行”。
- 许可证：AGPL-3.0-only；对应源码即本仓库 `v0.1.2` tag。

---

## English

### Fixes

- Line-based splitting used to call the model once per line. A long subtitle file or log with thousands of lines became hundreds or thousands of sequential inferences, leaving the window unresponsive for a long time. Adjacent short lines are now coalesced, reducing thousands of blocks to dozens, which keeps speed, memory and the UI stable.
- Streaming output is appended incrementally instead of rebuilding the whole result text on every token, so long translations no longer overload WebView2.
- The copyright and license notice in Settings → About is now shipped with the app.

### Changes

- Rewrote all five READMEs (Simplified Chinese, English, Japanese, Korean, Spanish) as project introductions and removed the commentary about the license choice.
- Added AGPL compliance material:
  - New `NOTICE` with copyright, AGPL-3.0-only, no warranty and the corresponding source URL.
  - The About section in Settings now shows copyright, license, warranty and source notices.
  - Release packages now include `licenses/` with the license texts of runtime dependencies.
  - The release self-check now verifies `NOTICE`, `licenses/` and the ZIP contents.
- Fixed PowerShell build scripts failing under Windows PowerShell 5.1 because their UTF-8 files had no BOM.
- Updated the GitHub repository description.

### Upgrade

- Portable: overwrite the old folder with the new ZIP; `data\` and `models` are untouched.
- Installed: install over the existing version; `%LOCALAPPDATA%\ZCTranslate` is preserved.

### Downloads

| Asset | Description |
|---|---|
| `ZCTranslate-0.1.2-win64-setup.exe` | NSIS installer (per-user, no UAC, Start Menu + uninstaller) |
| `ZCTranslate-0.1.2-win64-portable.zip` | Portable, unzip and run |
| `SHA256SUMS.txt` | SHA-256 checksums |

### Notes

- **No translation models are bundled**; see the “Preparing a model” section of the README.
- The installer is unsigned; SmartScreen will ask for “More info → Run anyway”.
- License: AGPL-3.0-only; the corresponding source is the `v0.1.2` tag of this repository.
