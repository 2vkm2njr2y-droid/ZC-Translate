# 架构

## 组件

```
pywebview (Edge WebView2)
   ├─ 主窗口（620×460，关闭后隐藏到托盘）
   └─ 隐藏的划译浮层（/overlay，无焦点置顶显示）
   │ 同源 HTTP + SSE，127.0.0.1 随机端口，一次性 token
FastAPI
   ├─ /overlay                划译悬浮卡片页面（token 校验）
   ├─ /api/translate/stream   文本翻译任务（SSE）
   ├─ /api/screenshot/capture  Windows 原生截图（读剪贴板）
   ├─ /api/screenshot/translate/stream  截图 OCR 行翻译（SSE）
   ├─ /api/ocr/image          图片 OCR（返回 bbox 与检测语言）
   ├─ /api/document/translate/stream  DOCX 文档翻译任务（SSE，后台队列）
   ├─ /api/speech/*          本地麦克风、VAD 分句、SenseVoice 语音识别
   ├─ /api/models /settings /glossaries /history /system
   ├─ JobQueue                 单推理 worker，串行
   └─ StaticFiles              原生 HTML/CSS/JS，无 CDN
翻译流水线
   ├─ 语言检测 / 分段 / 占位符 / 术语 / 官方提示词
   └─ 后处理 / 校验 / 重试 / 翻译记忆
OpenVINO GenAI LLMPipeline
   ├─ NPU: ov-int4-npu（对称 INT4，per-channel）
   ├─ GPU: ov-int4（非对称 INT4，group 128）
   └─ CPU: ov-int4
SQLite（settings/glossaries/terms/tm/history）
Windows 桌面壳
   ├─ 主窗口：不透明 WebView2 + DWM 原生圆角
   ├─ WH_MOUSE_LL 全局鼠标钩子 → UI Automation 读取选区
   ├─ 隐藏浮层：无焦点显示、按选区与显示器 DPI 定位
   ├─ Shell_NotifyIcon 托盘：打开窗口 / 开关划译 / 退出
   └─ 命名事件单实例：再次启动时唤起已有窗口
```

## 一次翻译

1. 前端 POST `/api/translate/stream`，带 `X-ZC-Token`。
2. 后端进入 `JobQueue`；模型未加载时先 `ensure_loaded`（自动选择设备并回退）。
3. `split_blocks` 按段落/行分段，保留分隔符。
4. 每段：占位符保护 → 术语匹配 → 查 TM → 组装官方提示词 → tokenizer `apply_chat_template` → `LLMPipeline.generate`。
5. 生成回调把 token 推到 `asyncio.Queue`，经 SSE 发给前端；前端逐段渲染。
6. 完成后：清理模型前缀/标点、还原占位符、检查数字/URL/术语、必要时重试一次；写 TM 与历史。

## 一次截图翻译

1. 前端点击“截图翻译”或收到 PrintScreen 事件，调用 pywebview 的 `capture_for_screenshot()`；桌面壳隐藏主窗口。
2. 后端用 `SendInput` 模拟 Win+Shift+S 打开 Windows 自带截图工具；记录剪贴板序号，轮询新图片；检测截图工具全屏窗口的出现/消失以识别取消。窗口在 `finally` 中恢复。
3. 截图像素通过剪贴板读入内存，按最长边 4096 缩放后返回 data URL，不写磁盘。
4. 前端把图片提交 `/api/ocr/image`，获得 `items[].bbox/text` 和 `detected_lang`。
5. 前端逐行提交 `/api/screenshot/translate/stream`；JobQueue 串行翻译，SSE 推送 `item_start/item_delta/item_done`。
6. 结果页按 bbox 百分比把译文卡片覆盖在原图文字位置；悬停卡片透出原图，工具栏切换原文/译文，点击查看对照。
7. 每次截图翻译写一条 `kind="screenshot"` 历史；图片本身不落盘，TM 仍按用户设置生效。

## 一次文档翻译（DOCX）

1. 文档页把 DOCX 以 base64 提交 `/api/document/translate/stream`。
2. 后端提交 `"document"` 任务到现有 `JobQueue`，与文本、截图、漫画翻译共用单 worker。
3. `translate_docx` 收集正文和表格中的非空段落；本次文档内相同原文只调用一次模型。
4. 每段仍走 `TranslationService.run`，TM、术语、校验和重试与普通翻译一致；每段完成推送 `meta` / `progress` SSE。
5. 取消或 SSE 断开时停止任务，不生成文件；已完成段落保留在 TM，同一档位重试会跳过。
6. 完成后保存原文件旁的 `原文件名_翻译.docx`，原文件不改。

## 一次划译

1. 主窗口关闭只隐藏（不销毁），Uvicorn、数据库和模型继续运行，托盘图标常驻。
2. 全局 `WH_MOUSE_LL` 钩子记录鼠标按下/移动/抬起；拖选、双击或 Shift+点击后做 140ms 去抖。
3. 选择服务读取 `selection_translate`；若开启，用 `AutomationElement.FocusedElement` + `TextPattern.GetSelection()` 读取选中文字与屏幕矩形（不模拟 Ctrl+C、不读写剪贴板）。
4. 按 UI Automation 矩形（异常时退回鼠标轨迹）计算锚点，取锚点所在显示器的 `rcWork` 与 DPI；卡片默认在选区上方 8px，空间不足时放下方。
5. 隐藏的划译 WebView 执行 `window.zcOverlay.show(...)`；原生窗口用 `ShowWindow(SW_SHOWNOACTIVATE)` 和 `WS_EX_NOACTIVATE` 显示，不抢当前应用焦点。
6. 浮层读取设置中的 `target_lang`，走现有 `/api/translate/stream`；模型档位/设备取当前设置，复用同一 EngineManager 和 JobQueue，因此不会启动第二个模型。
7. 流式内容通过 `ResizeObserver` 通知原生窗口调整高度；点击外部、滚轮、新选区、打开主窗口或退出时隐藏并取消请求。
8. 划译记录与普通翻译一样进入历史和翻译记忆；托盘/设置页可随时关闭划译。

## 一次语音翻译

1. 前端调用 `/api/speech/session/start`，选择“conversation”或“input”。
2. `SpeechService` 使用 `sounddevice` 读取本机麦克风的 16 kHz 单声道音频。
3. `sherpa-onnx` 的 SenseVoice 模型识别中文、日语和英语；Silero VAD 按约 2.5 秒静音分出一句话。
4. 对话模式把识别出的句子按序返回前端，前端逐句调用现有 `/api/translate`，因此翻译仍由 Hy-MT2 完成。
5. 语音输入模式只在手动停止后合并识别文字，填入原文框，不自动触发翻译。
6. 语音模型由用户点击按钮后下载到 `models/speech`；运行期不自动联网。

## 关键设计

- **单 worker**：NPU/GPU 无法有效并行，所有生成串行；队列最多 3 个任务。
- **模型变体**：1.8B 有 `ov-int4`（GPU/CPU）与 `ov-int4-npu`（对称量化）两个 IR；NPU 必须使用后者。
- **自动回退**：`auto` 先 NPU，再 GPU、CPU；显式选 NPU 不静默回退。加载失败写日志并提示。
- **提示词**：严格按模型卡；没有 system prompt；中文涉及源/目标时用中文提示词，否则英文。
- **占位符**：`⟦0⟧` 形式；代码块/URL/HTML/模板变量不送模型。
- **翻译记忆**：精确匹配，key 含模型档位、提示词版本、术语库 hash，避免旧缓存污染。
- **离线**：翻译、OCR 和已安装的语音识别都在本机完成；网络请求只发生在用户主动准备翻译模型或下载语音模型时。
- **截图**：未打包应用无法可靠使用新版 `ms-screenclip:` 回调协议，因此走 Win+Shift+S + 剪贴板；截图工具窗口用于取消检测，README/用户手册说明需开启“自动复制到剪贴板”。
- **划译**：选区读取走系统 UI Automation，不模拟复制，避免覆盖剪贴板或误复制文件；不支持 UIA 的应用会静默跳过。浮层是第二个隐藏 WebView，显示时必须走 `SW_SHOWNOACTIVATE`，不能调用 pywebview 的 `show()`（它会激活窗口）。
- **托盘/关闭**：关闭是隐藏而不是销毁；托盘菜单才提供“退出”。托盘不可用时关闭恢复为直接退出，避免留下无法唤回的后台进程。重复启动通过命名事件唤起已有窗口。

## 安全

- 只绑定 `127.0.0.1`；每次启动生成随机 token；API 校验 `X-ZC-Token`。
- CSP `default-src 'self'`，无内联脚本、无外部资源。
- 所有用户文本用 `textContent` 渲染，不用 `innerHTML`。
- SQLite 参数化查询；日志不记录原文/译文。
- 历史与 TM 只存本机，可一键清空。
- 截图只在本机内存中处理，不写临时图片、不上传；截图翻译的 OCR 文本会按普通翻译规则写入历史/TM。
- 划译只读取 UI Automation 暴露的选区文字，不模拟键盘、不修改剪贴板；选区文字只发送到本地 127.0.0.1 服务，并按普通翻译写入本地历史/TM。日志不记录选中正文。

## 数据表

见 `app/backend/storage/db.py`：`settings`、`glossaries`、`terms`、`tm`、`history`，`PRAGMA user_version=1`。
