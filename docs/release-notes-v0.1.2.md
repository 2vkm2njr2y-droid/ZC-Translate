# ZC 离线翻译 v0.1.2 / ZC Translate v0.1.2

文档与合规版本（Windows 11 x64）。没有功能变更，翻译、OCR、语音和文档处理逻辑与 v0.1.1 相同。

## 简体中文

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
