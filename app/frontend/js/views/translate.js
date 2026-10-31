import { api } from "../api.js";
import { h, clear, selectOption, toast, downloadText, debounce } from "../dom.js";
import { icon } from "../icons.js";

const LANGS = [
  { value: "auto", label: "自动检测" },
  { value: "zh", label: "中文" },
  { value: "ja", label: "日语" },
  { value: "en", label: "英语" },
];
const TARGETS = [
  { value: "zh", label: "中文" },
  { value: "ja", label: "日语" },
  { value: "en", label: "英语" },
];
const STYLES = [
  { value: "default", label: "通用" },
  { value: "formal", label: "正式" },
  { value: "casual", label: "口语" },
  { value: "technical", label: "技术" },
  { value: "literary", label: "文学" },
];
const DEVICES = [
  { value: "auto", label: "设备：自动" },
  { value: "NPU", label: "设备：NPU" },
  { value: "GPU", label: "设备：GPU" },
  { value: "CPU", label: "设备：CPU" },
];

function langLabel(value) {
  return [...LANGS, ...TARGETS].find((item) => item.value === value)?.label || value;
}

export function render(ctx) {
  const { store } = ctx;
  const settings = store.settings || {};
  let aborter = null;
  let destroyed = false;
  let jobId = "";
  const blockEls = new Map();
  let selectedGlossary = settings.glossary_id || "";
  let currentRatio = Number(localStorage.getItem("zc.split") || "0.5");
  if (!Number.isFinite(currentRatio) || currentRatio < 0.25 || currentRatio > 0.75) currentRatio = 0.5;

  const initialText = store.draftText || localStorage.getItem("zc.draft.text") || "";
  const initialTarget = store.draftTarget || "";

  const saveSettings = debounce(async (patch) => {
    try {
      const updated = await api.put("/api/settings", patch);
      store.settings = updated;
    } catch (error) {
      toast(error.message, "error");
    }
  }, 300);

  const sourceSelect = h("select", { attrs: { "aria-label": "源语言" } });
  for (const item of LANGS) sourceSelect.appendChild(selectOption(item.value, item.label));
  sourceSelect.value = settings.source_lang || "auto";

  const targetSelect = h("select", { attrs: { "aria-label": "目标语言" } });
  for (const item of TARGETS) targetSelect.appendChild(selectOption(item.value, item.label));
  targetSelect.value = settings.target_lang || "zh";
  if (targetSelect.value === sourceSelect.value) targetSelect.value = "en";

  const profileSelect = h("select", { attrs: { "aria-label": "模型档位" } });
  const models = store.models.length ? store.models : [
    { profile_id: "balanced", name: "Hy-MT2 1.8B", installed: false },
    { profile_id: "quality", name: "Hy-MT2 7B", installed: false },
  ];
  for (const model of models) {
    profileSelect.appendChild(selectOption(
      model.profile_id,
      `${model.name}${model.installed ? "" : "（未安装）"}`,
    ));
  }
  profileSelect.value = settings.profile_id || "balanced";

  const deviceSelect = h("select", { attrs: { "aria-label": "推理设备" } });
  for (const item of DEVICES) deviceSelect.appendChild(selectOption(item.value, item.label));
  deviceSelect.value = settings.device || "auto";

  const glossarySelect = h("select", { attrs: { "aria-label": "术语库" } });
  glossarySelect.appendChild(selectOption("", "术语库：不使用"));
  for (const glossary of store.glossaries) {
    glossarySelect.appendChild(selectOption(
      glossary.id,
      `${glossary.name} · ${langLabel(glossary.src_lang)}→${langLabel(glossary.tgt_lang)}`,
    ));
  }
  glossarySelect.value = selectedGlossary;
  if (glossarySelect.value !== selectedGlossary) glossarySelect.value = "";

  const styleSelect = h("select", { attrs: { "aria-label": "翻译风格" } });
  for (const item of STYLES) styleSelect.appendChild(selectOption(item.value, `风格：${item.label}`));
  styleSelect.value = settings.style || "default";

  const tmCheck = h("input", { type: "checkbox", checked: settings.use_tm !== false });
  const contextCheck = h("input", { type: "checkbox", checked: Boolean(settings.use_context) });

  const sourceText = h("textarea", {
    id: "source-text",
    spellcheck: "false",
    attrs: { placeholder: "输入中文、日语或英语…", "aria-label": "原文" },
  });
  sourceText.value = initialText;

  const charCount = h("span", { class: "count", text: `${sourceText.value.length} 字` });
  const targetStatus = h("span", { class: "hint", text: "" });
  const translateButton = h("button", { class: "primary", on: { click: () => translate() } }, [
    icon("spark", 15),
    h("span", { text: "翻译" }),
    h("kbd", { text: "Ctrl ↵" }),
  ]);
  const cancelButton = h("button", {
    class: "secondary hidden",
    on: { click: () => cancel() },
  }, "取消");

  const targetContent = h("div", { id: "target-content", class: "target-content scroll-thin" });
  const emptyState = () => h("div", { class: "target-empty" }, [
    icon("translate", 34),
    h("div", { text: "译文会显示在这里" }),
    h("div", { class: "hint", text: "支持中文、日语、英语互译；模型在本机运行。" }),
  ]);
  targetContent.appendChild(emptyState());

  if (initialTarget) {
    clear(targetContent);
    const block = h("div", { class: "tblock" }, h("div", { class: "ttext", text: initialTarget }));
    targetContent.appendChild(block);
  }

  const banner = h("div", { class: "hidden" });
  const modelReady = store.hasModel();
  if (!modelReady) {
    banner.className = "warn-tip";
    banner.appendChild(h("strong", { text: "未找到可用模型。 " }));
    banner.appendChild(document.createTextNode(
      "首次使用请运行“准备模型.bat”（需要联网一次），或把 models 文件夹复制到应用目录。",
    ));
    banner.appendChild(h("button", {
      class: "ghost small",
      style: "margin-left:8px",
      text: "打开设置",
      on: { click: () => ctx.navigate("settings") },
    }));
  }
  if (store.engine?.state === "error") {
    banner.className = "error-box";
    clear(banner);
    banner.appendChild(h("strong", { text: "模型加载失败：" }));
    banner.appendChild(document.createTextNode(store.engine.last_error || "请到设置查看诊断。"));
    banner.appendChild(h("button", {
      class: "ghost small",
      style: "margin-left:8px",
      text: "查看设置",
      on: { click: () => ctx.navigate("settings") },
    }));
  }

  const panes = h("div", { class: "panes" });

  function paneHead(title, extra = []) {
    return h("div", { class: "pane-head" }, h("strong", { text: title }), ...extra);
  }

  const sourcePane = h("section", { class: "pane source" }, [
    paneHead("原文", [
      charCount,
      h("span", { class: "spacer" }),
      h("button", {
        class: "ghost small",
        text: "导入",
        on: { click: () => importFile() },
      }),
      h("button", {
        class: "ghost small",
        text: "清空",
        on: { click: () => clearAll() },
      }),
    ]),
    sourceText,
  ]);

  const targetHead = paneHead("译文", [
    targetStatus,
    h("span", { class: "spacer" }),
    cancelButton,
    h("button", {
      class: "ghost small",
      text: "复制",
      on: { click: () => copyResult() },
    }),
    h("button", {
      class: "ghost small",
      text: "导出",
      on: { click: () => exportResult() },
    }),
  ]);

  const targetPane = h("section", { class: "pane target" }, [targetHead, targetContent]);
  const divider = h("div", { class: "divider", attrs: { role: "separator", "aria-label": "调整分栏" } });
  panes.append(sourcePane, divider, targetPane);
  panes.style.gridTemplateColumns = `${currentRatio}fr 6px ${1 - currentRatio}fr`;

  const swapButton = h("button", {
    class: "swap-button",
    attrs: { "aria-label": "交换语言", title: "交换语言（Ctrl+Shift+S）" },
    on: { click: () => swapLanguages() },
    html: "",
  });
  swapButton.appendChild(icon("swap", 16));

  const langbar = h("div", { class: "langbar" }, [
    h("div", { class: "lang-selects" }, [sourceSelect, swapButton, targetSelect]),
    h("div", { class: "translate-actions" }, [translateButton]),
  ]);

  const optionsbar = h("div", { class: "optionsbar" }, [
    profileSelect,
    deviceSelect,
    glossarySelect,
    styleSelect,
    h("label", { class: "check" }, tmCheck, "记忆库"),
    h("label", { class: "check" }, contextCheck, "上下文"),
    h("span", { class: "spacer", style: "flex:1" }),
    h("span", { class: "hint", text: "首次加载 NPU 需要编译，之后会走缓存" }),
  ]);

  const el = h("div", { class: "translate-page" }, [banner, langbar, optionsbar, panes]);
  if (banner.classList.contains("hidden")) banner.remove();

  function updateCount() {
    charCount.textContent = `${sourceText.value.length} 字`;
    ctx.setStatus("就绪", `${sourceText.value.length} 字`);
    localStorage.setItem("zc.draft.text", sourceText.value);
    store.draftText = sourceText.value;
  }

  function currentTargetText() {
    if (store.draftTarget) return store.draftTarget;
    return [...blockEls.values()]
      .map((block) => block.textEl.textContent || "")
      .filter(Boolean)
      .join("\n\n");
  }

  function showTargetError(message) {
    clear(targetContent);
    targetContent.appendChild(h("div", { class: "error-box", text: message }));
  }

  function resetTarget(blocks = []) {
    clear(targetContent);
    blockEls.clear();
    if (!blocks.length) {
      targetContent.appendChild(emptyState());
      return;
    }
    for (const block of blocks) {
      const textEl = h("div", { class: "ttext" });
      if (!block.translate) textEl.textContent = block.text;
      const metaEl = h("div", { class: "tmeta" });
      const node = h("div", {
        class: "tblock",
        dataset: { id: String(block.id) },
      }, [
        h("div", { class: "tsource", title: block.text, text: block.text }),
        textEl,
        metaEl,
      ]);
      if (block.translate === false) node.classList.add("code-block");
      blockEls.set(block.id, { node, textEl, metaEl, source: block.text, streamNode: null });
      targetContent.appendChild(node);
    }
  }

  function ensureBlock(blockId, sourceTextValue = "") {
    let item = blockEls.get(blockId);
    if (item) return item;
    const textEl = h("div", { class: "ttext" });
    const metaEl = h("div", { class: "tmeta" });
    const node = h("div", { class: "tblock", dataset: { id: String(blockId) } }, [
      h("div", { class: "tsource", title: sourceTextValue, text: sourceTextValue }),
      textEl,
      metaEl,
    ]);
    item = { node, textEl, metaEl, source: sourceTextValue, streamNode: null };
    blockEls.set(blockId, item);
    targetContent.appendChild(node);
    return item;
  }

  function renderBlockMeta(item, data) {
    clear(item.metaEl);
    if (data.tm_hit) item.metaEl.appendChild(h("span", { class: "tm-chip", text: "记忆库" }));
    if (data.glossary_hits) {
      item.metaEl.appendChild(h("span", { class: "tm-chip", text: `术语 ${data.glossary_hits}` }));
    }
    if (data.tok_s) item.metaEl.appendChild(h("span", { class: "mono", text: `${data.tok_s} tok/s` }));
    if (data.ttft_ms) item.metaEl.appendChild(h("span", { text: `首字 ${Math.round(data.ttft_ms)} ms` }));
    const warnings = data.warnings || [];
    for (const warning of warnings.slice(0, 3)) {
      item.metaEl.appendChild(h("span", { class: "warn-chip", title: warning, text: "需复核" }));
    }
    if (warnings.length > 3) {
      item.metaEl.appendChild(h("span", { class: "warn-chip", text: `+${warnings.length - 3}` }));
    }
  }

  function setStreaming(value) {
    store.streaming = value;
    if (value) {
      store.system = { ...(store.system || {}), queue: { active: 1, pending: 0 } };
    }
    translateButton.disabled = value;
    translateButton.classList.toggle("hidden", value);
    cancelButton.classList.toggle("hidden", !value);
    sourceSelect.disabled = value;
    targetSelect.disabled = value;
    profileSelect.disabled = value;
    deviceSelect.disabled = value;
    glossarySelect.disabled = value;
    styleSelect.disabled = value;
    ctx.updateChrome();
  }

  function finishStreaming() {
    store.streaming = false;
    store.system = { ...(store.system || {}), queue: { active: 0, pending: 0 } };
    ctx.updateChrome();
  }

  async function translate() {
    const text = sourceText.value.trim();
    if (!text) {
      toast("请先输入原文", "warn");
      sourceText.focus();
      return;
    }
    if (!store.hasModel()) {
      toast("未找到模型，请先在设置中检查模型目录", "warn");
      ctx.navigate("settings");
      return;
    }
    if (sourceSelect.value !== "auto" && sourceSelect.value === targetSelect.value) {
      toast("源语言与目标语言相同", "warn");
      return;
    }
    if (text.length > 100000) {
      toast("文本过长，请分段翻译（上限 100,000 字符）", "warn");
      return;
    }

    store.draftTarget = "";
    store.lastMeta = null;
    localStorage.removeItem("zc.draft.target");
    resetTarget([]);
    setStreaming(true);
    targetStatus.textContent = "正在连接模型…";
    ctx.setStatus("正在翻译", `${text.length} 字`);
    aborter = new AbortController();
    jobId = "";
    let sawError = false;

    const payload = {
      text,
      source_lang: sourceSelect.value,
      target_lang: targetSelect.value,
      profile_id: profileSelect.value,
      device: deviceSelect.value,
      glossary_id: glossarySelect.value || null,
      style: styleSelect.value,
      use_tm: tmCheck.checked,
      use_context: contextCheck.checked,
      split_mode: "auto",
    };
    saveSettings({
      source_lang: payload.source_lang,
      target_lang: payload.target_lang,
      profile_id: payload.profile_id,
      device: payload.device,
      glossary_id: payload.glossary_id || "",
      style: payload.style,
      use_tm: payload.use_tm,
      use_context: payload.use_context,
    });

    try {
      await api.translateStream(payload, {
        onOpen: (response) => {
          jobId = response.headers.get("X-Job-Id") || "";
          store.jobId = jobId;
        },
        status: (data) => {
          if (data.message) targetStatus.textContent = data.message;
        },
        meta: (data) => {
          store.lastMeta = data;
          store.lastDetected = data.detected_lang || "";
          store.engine = {
            ...(store.engine || {}),
            state: "ready",
            device: data.device,
            model_name: data.model,
          };
          resetTarget(data.blocks || []);
          targetStatus.textContent = `${data.device} · ${data.model}`;
          ctx.updateChrome();
          if (data.device_warning) toast(data.device_warning, "warn", 5200);
          if (data.detected_lang && sourceSelect.value === "auto") {
            ctx.setStatus(`检测到${langLabel(data.detected_lang)}`, `${text.length} 字`);
          }
        },
        block_start: (data) => {
          const item = ensureBlock(data.block_id, data.source);
          item.node.classList.add("active");
          if (data.kind === "code") item.textEl.textContent = data.source;
          else item.textEl.classList.add("stream-caret");
          targetStatus.textContent = `正在翻译第 ${data.block_id + 1} 段…`;
        },
        delta: (data) => {
          const item = blockEls.get(data.block_id);
          if (!item) return;
          if (!item.streamNode) {
            item.textEl.textContent = "";
            item.streamNode = document.createTextNode("");
            item.textEl.appendChild(item.streamNode);
          }
          item.streamNode.appendData(data.text || "");
          item.textEl.classList.add("stream-caret");
        },
        block_reset: (data) => {
          const item = blockEls.get(data.block_id);
          if (!item) return;
          item.textEl.textContent = "";
          item.streamNode = null;
          clear(item.metaEl);
          item.metaEl.appendChild(h("span", { class: "hint", text: data.reason || "正在重试…" }));
        },
        block_done: (data) => {
          const item = ensureBlock(data.block_id, "");
          item.node.classList.remove("active");
          item.textEl.classList.remove("stream-caret");
          item.streamNode = null;
          item.textEl.textContent = data.text || "";
          renderBlockMeta(item, data);
        },
        done: (data) => {
          store.draftTarget = data.text || currentTargetText();
          localStorage.setItem("zc.draft.target", store.draftTarget);
          targetStatus.textContent = `${data.device} · ${data.elapsed_ms} ms`;
          ctx.setStatus(
            data.tm_hits ? "完成（记忆库）" : (data.cancelled ? "已取消" : "完成"),
            data.tm_hits
              ? `${data.tm_hits} 段命中 · ${data.elapsed_ms} ms`
              : `${data.tok_s || 0} tok/s · ${data.elapsed_ms} ms`,
          );
          store.engine = {
            ...(store.engine || {}),
            state: "ready",
            device: data.device,
            model_name: data.model,
          };
          finishStreaming();
          if (!data.cancelled) {
            const warningCount = (data.warnings || []).length;
            if (data.tm_hits) {
              toast(`命中翻译记忆（${data.tm_hits} 段）`, "success", 2400);
            } else {
              toast(
                warningCount
                  ? `翻译完成，有 ${warningCount} 条提示可复核`
                  : `翻译完成（${data.device}，${data.tok_s || 0} tok/s）`,
                warningCount ? "warn" : "success",
              );
            }
          }
        },
        error: (data) => {
          sawError = true;
          showTargetError(data.message || "翻译失败");
          targetStatus.textContent = "失败";
          ctx.setStatus("翻译失败", `${text.length} 字`);
          toast(data.message || "翻译失败", "error", 5200);
        },
      }, aborter.signal);
    } catch (error) {
      if (error.name === "AbortError") {
        targetStatus.textContent = "已取消";
        ctx.setStatus("已取消", `${text.length} 字`);
      } else if (!sawError) {
        showTargetError(error.message || String(error));
        toast(error.message || "翻译失败", "error", 5200);
      }
    } finally {
      setStreaming(false);
      finishStreaming();
      for (const item of blockEls.values()) item.textEl.classList.remove("stream-caret");
      if (!destroyed) sourceText.focus();
    }
  }

  async function cancel() {
    if (!store.streaming) return;
    if (aborter) aborter.abort();
    await api.cancelJob(jobId);
    targetStatus.textContent = "已取消";
    toast("已取消", "info", 2000);
  }

  function swapLanguages() {
    const currentSource = sourceSelect.value === "auto"
      ? (store.lastDetected || "zh")
      : sourceSelect.value;
    let newSource = targetSelect.value;
    let newTarget = currentSource;
    if (newSource === newTarget) newTarget = newSource === "zh" ? "en" : "zh";
    sourceSelect.value = newSource;
    targetSelect.value = newTarget;
    saveSettings({ source_lang: newSource, target_lang: newTarget });
  }

  function clearAll() {
    sourceText.value = "";
    store.draftText = "";
    store.draftTarget = "";
    localStorage.removeItem("zc.draft.text");
    localStorage.removeItem("zc.draft.target");
    resetTarget([]);
    targetStatus.textContent = "";
    updateCount();
    sourceText.focus();
  }

  async function copyResult() {
    const text = currentTargetText();
    if (!text) {
      toast("没有可复制的译文", "warn");
      return;
    }
    try {
      await navigator.clipboard.writeText(text);
      toast("已复制译文", "success", 1800);
    } catch {
      const area = h("textarea", { style: "position:fixed;opacity:0" });
      area.value = text;
      document.body.appendChild(area);
      area.select();
      document.execCommand("copy");
      area.remove();
      toast("已复制译文", "success", 1800);
    }
  }

  function exportResult() {
    const text = currentTargetText();
    if (!text) {
      toast("没有可导出的译文", "warn");
      return;
    }
    downloadText("translation.txt", text);
  }

  function importFile() {
    const input = h("input", { type: "file", attrs: { accept: ".txt,.md,text/plain,text/markdown" } });
    input.addEventListener("change", () => {
      const file = input.files?.[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = () => {
        sourceText.value = String(reader.result || "");
        updateCount();
        toast(`已导入 ${file.name}`, "success", 2000);
      };
      reader.onerror = () => toast("文件读取失败", "error");
      reader.readAsText(file, "utf-8");
    });
    input.click();
  }

  function updateDeviceOptions() {
    const isQuality = profileSelect.value === "quality";
    for (const option of deviceSelect.options) {
      if (option.value === "NPU") option.disabled = isQuality;
    }
    if (isQuality && deviceSelect.value === "NPU") deviceSelect.value = "auto";
  }

  sourceSelect.addEventListener("change", () => {
    if (sourceSelect.value !== "auto" && sourceSelect.value === targetSelect.value) {
      targetSelect.value = sourceSelect.value === "zh" ? "ja" : "zh";
    }
    saveSettings({ source_lang: sourceSelect.value, target_lang: targetSelect.value });
  });
  targetSelect.addEventListener("change", () => {
    if (sourceSelect.value !== "auto" && sourceSelect.value === targetSelect.value) {
      toast("源语言与目标语言相同，请调整", "warn");
      targetSelect.value = store.settings.target_lang || "zh";
      return;
    }
    saveSettings({ target_lang: targetSelect.value });
  });
  profileSelect.addEventListener("change", () => {
    const model = store.models.find((item) => item.profile_id === profileSelect.value);
    if (model && !model.installed) {
      toast(`${model.name} 尚未安装，请到设置查看模型准备说明`, "warn", 5000);
      profileSelect.value = store.settings.profile_id || "balanced";
      return;
    }
    updateDeviceOptions();
    store.settings = {
      ...store.settings,
      profile_id: profileSelect.value,
      device: deviceSelect.value,
    };
    ctx.updateChrome();
    saveSettings({ profile_id: profileSelect.value, device: deviceSelect.value });
  });
  deviceSelect.addEventListener("change", () => {
    store.settings = { ...store.settings, device: deviceSelect.value };
    ctx.updateChrome();
    saveSettings({ device: deviceSelect.value });
  });
  glossarySelect.addEventListener("change", () => saveSettings({ glossary_id: glossarySelect.value }));
  styleSelect.addEventListener("change", () => saveSettings({ style: styleSelect.value }));
  tmCheck.addEventListener("change", () => saveSettings({ use_tm: tmCheck.checked }));
  contextCheck.addEventListener("change", () => saveSettings({ use_context: contextCheck.checked }));
  sourceText.addEventListener("input", updateCount);
  sourceText.addEventListener("keydown", (event) => {
    if (event.key === "Tab") {
      event.preventDefault();
      const start = sourceText.selectionStart;
      sourceText.value = `${sourceText.value.slice(0, start)}  ${sourceText.value.slice(sourceText.selectionEnd)}`;
      sourceText.selectionStart = sourceText.selectionEnd = start + 2;
      updateCount();
    }
  });

  function onKeyDown(event) {
    const mod = event.ctrlKey || event.metaKey;
    if (mod && event.key === "Enter") {
      event.preventDefault();
      if (!store.streaming) translate();
    } else if (mod && event.shiftKey && event.key.toLowerCase() === "s") {
      event.preventDefault();
      swapLanguages();
    } else if (event.key === "Escape" && store.streaming) {
      event.preventDefault();
      cancel();
    }
  }
  document.addEventListener("keydown", onKeyDown);

  // Resizable split.
  let dragging = false;
  const onPointerMove = (event) => {
    if (!dragging) return;
    const rect = panes.getBoundingClientRect();
    const ratio = (event.clientX - rect.left) / rect.width;
    const clamped = Math.min(0.75, Math.max(0.25, ratio));
    panes.style.gridTemplateColumns = `${clamped}fr 6px ${1 - clamped}fr`;
    currentRatio = clamped;
  };
  const onPointerUp = () => {
    if (!dragging) return;
    dragging = false;
    document.body.style.cursor = "";
    localStorage.setItem("zc.split", String(currentRatio));
    document.removeEventListener("pointermove", onPointerMove);
    document.removeEventListener("pointerup", onPointerUp);
  };
  divider.addEventListener("pointerdown", (event) => {
    dragging = true;
    event.preventDefault();
    document.body.style.cursor = "col-resize";
    document.addEventListener("pointermove", onPointerMove);
    document.addEventListener("pointerup", onPointerUp);
  });

  updateDeviceOptions();
  updateCount();
  if (initialTarget) {
    ctx.setStatus("已载入历史译文", `${sourceText.value.length} 字`);
  }
  if (!modelReady) {
    translateButton.disabled = true;
  }
  window.setTimeout(() => sourceText.focus(), 30);

  return {
    el,
    cleanup() {
      destroyed = true;
      document.removeEventListener("keydown", onKeyDown);
      document.removeEventListener("pointermove", onPointerMove);
      document.removeEventListener("pointerup", onPointerUp);
      if (aborter) aborter.abort();
    },
  };
}
