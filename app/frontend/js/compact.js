import { api } from "./api.js";
import { store } from "./state.js";
import { h, clear, selectOption, debounce } from "./dom.js";
import { icon } from "./icons.js";
import * as documentView from "./views/document.js";
import * as glossaryView from "./views/glossary.js";
import * as historyView from "./views/history.js";
import * as screenshotView from "./views/screenshot.js";
import * as settingsView from "./views/settings.js";
import { createVoiceController } from "./voice.js";

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
  { value: "default", label: "通用领域" },
  { value: "formal", label: "正式" },
  { value: "casual", label: "口语" },
  { value: "technical", label: "技术" },
  { value: "literary", label: "文学" },
];
const VIEWS = {
  document: documentView,
  glossary: glossaryView,
  history: historyView,
  settings: settingsView,
};
const MAX_TEXT_CHARS = 100_000;
const FOLLOW_THRESHOLD = 12;

function shortModel(name) {
  return String(name || "Hy-MT2").replace(/^Hy-MT2\s*/, "Hy-MT2 ");
}

export function initCompact(ctx) {
  const shell = document.getElementById("compact-shell");
  if (!shell) return null;

  const sourceSelect = document.getElementById("compact-source");
  const targetSelect = document.getElementById("compact-target");
  const glossarySelect = document.getElementById("compact-glossary");
  const styleSelect = document.getElementById("compact-style");
  const textArea = document.getElementById("compact-text");
  const countEl = document.getElementById("compact-count");
  const translateButton = document.getElementById("compact-translate");
  const translateLabel = document.getElementById("compact-translate-label");
  const resultEl = document.getElementById("compact-result");
  const resultTextEl = document.getElementById("compact-result-text");
  const resultStatusEl = document.getElementById("compact-result-status");
  const resultMetaEl = document.getElementById("compact-result-meta");
  const engineEl = document.getElementById("compact-engine");
  const tmCheck = document.getElementById("compact-tm");
  const swapButton = document.getElementById("compact-swap");
  const importButton = document.getElementById("compact-import");
  const themeButton = document.getElementById("compact-theme");
  const settingsButton = document.getElementById("compact-settings");
  const translatePage = document.getElementById("compact-translate-page");
  const viewPage = document.getElementById("compact-view-page");

  let streaming = false;
  let aborter = null;
  let jobId = "";
  let sawError = false;
  let currentPage = "translate";
  let currentView = null;
  let currentViewRoute = "";
  let capturing = false;
  let voiceController = null;
  const blocks = new Map();
  let renderedText = "";
  let renderedBlockId = null;
  let renderedBlockStart = 0;

  // Decorate the static shell with the shared icon set.
  swapButton.appendChild(icon("swap", 15));
  translateButton.prepend(icon("spark", 14));
  if (settingsButton && !settingsButton.querySelector("svg")) {
    settingsButton.appendChild(icon("grid", 16));
  }
  const screenshotButton = document.getElementById("compact-screenshot");
  if (screenshotButton && !screenshotButton.querySelector("svg")) {
    screenshotButton.prepend(icon("camera", 14));
  }

  for (const item of LANGS) sourceSelect.appendChild(selectOption(item.value, item.label));
  for (const item of TARGETS) targetSelect.appendChild(selectOption(item.value, item.label));
  for (const item of STYLES) styleSelect.appendChild(selectOption(item.value, item.label));

  function settings() {
    return store.settings || {};
  }

  function currentSource() {
    return sourceSelect.value || "auto";
  }

  function currentTarget() {
    return targetSelect.value || "zh";
  }

  function applySettings() {
    const value = settings();
    sourceSelect.value = value.source_lang || "auto";
    targetSelect.value = value.target_lang || "zh";
    styleSelect.value = value.style || "default";
    tmCheck.checked = value.use_tm !== false;
    if (sourceSelect.value !== "auto" && sourceSelect.value === targetSelect.value) {
      targetSelect.value = sourceSelect.value === "zh" ? "ja" : "zh";
    }
  }

  function populateGlossaries() {
    const current = settings().glossary_id || "";
    clear(glossarySelect);
    glossarySelect.appendChild(selectOption("", "术语：无"));
    for (const glossary of store.glossaries) {
      glossarySelect.appendChild(selectOption(
        glossary.id,
        `${glossary.name} · ${glossary.src_lang}→${glossary.tgt_lang}`,
      ));
    }
    glossarySelect.value = current;
    if (glossarySelect.value !== current) glossarySelect.value = "";
    glossarySelect.title = glossarySelect.selectedOptions[0]?.textContent || "";
  }

  function updateCount() {
    const length = textArea.value.length;
    countEl.textContent = `${length} 字`;
    countEl.classList.toggle("over", length > MAX_TEXT_CHARS);
  }

  function saveDraft() {
    const text = textArea.value;
    const result = resultTextEl.textContent || "";
    if (!text && !result) return;
    store.draftText = text;
    store.draftTarget = result;
    localStorage.setItem("zc.draft.text", text);
    if (result) localStorage.setItem("zc.draft.target", result);
    else localStorage.removeItem("zc.draft.target");
  }

  function loadDrafts() {
    const text = store.draftText || localStorage.getItem("zc.draft.text") || "";
    textArea.value = text;
    const result = store.draftTarget || localStorage.getItem("zc.draft.target") || "";
    if (result) {
      resultTextEl.textContent = result;
      showResult();
    } else if (!streaming) {
      hideResult();
    }
    updateCount();
    applySettings();
  }

  const saveSettings = debounce(async (patch) => {
    try {
      store.settings = await api.put("/api/settings", patch);
    } catch (error) {
      ctx.toast(error.message, "error");
    }
  }, 260);

  function updateEngine() {
    const engine = store.engine || {};
    const ready = engine.state === "ready";
    const loading = engine.state === "loading";
    const failed = engine.state === "error";
    const installed = store.models.some((model) => model.installed);
    engineEl.className = `compact-engine ${ready ? "ok" : failed ? "error" : loading ? "warn" : ""}`;
    if (ready) engineEl.textContent = `${engine.device || "本机"} · ${shortModel(engine.model_name)}`;
    else if (loading) engineEl.textContent = "模型加载中…";
    else if (failed) engineEl.textContent = "模型异常";
    else if (!installed) engineEl.textContent = "未找到模型";
    else engineEl.textContent = "模型未加载";
    if (!streaming) translateButton.disabled = !ready;
    translateButton.title = ready ? "翻译（Ctrl+Enter）" : "模型尚未就绪";
  }

  function setBusy(value) {
    streaming = value;
    shell.classList.toggle("busy", value);
    translateLabel.textContent = value ? "停止" : "翻译";
    translateButton.classList.toggle("is-streaming", value);
    translateButton.disabled = false;
    sourceSelect.disabled = value;
    targetSelect.disabled = value;
    styleSelect.disabled = value;
    swapButton.disabled = value;
    importButton.disabled = value;
    tmCheck.disabled = value;
    textArea.readOnly = value;
    if (!value) updateEngine();
  }

  function showResult() {
    resultEl.classList.remove("hidden");
  }

  function hideResult() {
    resultEl.classList.add("hidden");
    resultTextEl.textContent = "";
    resultStatusEl.textContent = "";
    resultMetaEl.textContent = "";
  }

  function isOutputAtBottom() {
    // A hidden page has no client height; keep the reader's last position
    // instead of treating the output as "at the bottom".
    if (resultTextEl.clientHeight === 0) return false;
    return resultTextEl.scrollHeight - resultTextEl.scrollTop - resultTextEl.clientHeight
      <= FOLLOW_THRESHOLD;
  }

  function scrollOutputToBottom() {
    resultTextEl.scrollTop = resultTextEl.scrollHeight;
  }

  function setResultText(text, streamingText = false) {
    // Only auto-follow while the output is already at (or very near) the
    // bottom.  Replacing textContent can reset scrollTop, so restore the
    // previous offset when the reader has scrolled up.
    const previousTop = resultTextEl.scrollTop;
    const follow = isOutputAtBottom();
    resultTextEl.textContent = text;
    resultTextEl.classList.toggle("streaming", streamingText);
    if (follow) scrollOutputToBottom();
    else resultTextEl.scrollTop = previousTop;
  }

  function resetRenderedResult() {
    renderedText = "";
    renderedBlockId = null;
    renderedBlockStart = 0;
    resultTextEl.textContent = "";
  }

  function appendRenderedResult(text, streamingText = true) {
    if (!text) return;
    const previousTop = resultTextEl.scrollTop;
    const follow = isOutputAtBottom();
    renderedText += text;
    resultTextEl.appendChild(document.createTextNode(text));
    resultTextEl.classList.toggle("streaming", streamingText);
    if (follow) scrollOutputToBottom();
    else resultTextEl.scrollTop = previousTop;
  }

  function beginRenderedBlock(blockId) {
    if (renderedBlockId === blockId) return;
    if (renderedText) appendRenderedResult("\n\n", true);
    renderedBlockId = blockId;
    renderedBlockStart = renderedText.length;
  }

  function resetRenderedBlock(blockId) {
    blocks.set(blockId, "");
    renderedText = renderedText.slice(0, renderedBlockStart);
    resultTextEl.textContent = renderedText;
    resultTextEl.classList.add("streaming");
  }

  function finishRenderedBlock(blockId, text) {
    beginRenderedBlock(blockId);
    blocks.set(blockId, text || "");
    renderedText = `${renderedText.slice(0, renderedBlockStart)}${text || ""}`;
    setResultText(renderedText, false);
  }

  function finishTranslation() {
    resultTextEl.classList.remove("streaming");
    aborter = null;
    jobId = "";
    setBusy(false);
  }

  async function cancelTranslation() {
    if (!streaming) return;
    if (aborter) aborter.abort();
    await api.cancelJob(jobId);
    resultStatusEl.textContent = "已取消";
    finishTranslation();
  }

  async function translate() {
    if (voiceController?.active()) {
      ctx.toast("请先结束当前语音模式", "warn");
      return;
    }
    if (streaming) {
      await cancelTranslation();
      return;
    }
    const text = textArea.value.trim();
    if (!text) {
      ctx.toast("请先输入原文", "warn");
      textArea.focus();
      return;
    }
    if (!store.hasModel() || store.engine?.state !== "ready") {
      ctx.toast("模型尚未就绪，请到设置页检查模型", "warn");
      return;
    }
    if (currentSource() !== "auto" && currentSource() === currentTarget()) {
      ctx.toast("源语言与目标语言相同", "warn");
      return;
    }
    if (text.length > MAX_TEXT_CHARS) {
      ctx.toast(`文本超过 ${MAX_TEXT_CHARS} 字，请分段后再翻译`, "warn", 5000);
      return;
    }

    saveSettings({
      source_lang: currentSource(),
      target_lang: currentTarget(),
      style: styleSelect.value,
      use_tm: tmCheck.checked,
    });

    const payload = {
      text,
      source_lang: currentSource(),
      target_lang: currentTarget(),
      profile_id: settings().profile_id || "balanced",
      device: settings().device || "auto",
      glossary_id: glossarySelect.value || null,
      style: styleSelect.value,
      use_tm: tmCheck.checked,
      use_context: false,
      split_mode: "auto",
    };

    blocks.clear();
    resetRenderedResult();
    sawError = false;
    showResult();
    resultStatusEl.textContent = "正在连接模型…";
    resultMetaEl.textContent = "";
    setBusy(true);
    aborter = new AbortController();

    try {
      await api.translateStream(payload, {
        onOpen: (response) => {
          jobId = response.headers.get("X-Job-Id") || "";
        },
        status: (data) => {
          if (data.message) resultStatusEl.textContent = data.message;
        },
        meta: (data) => {
          blocks.clear();
          resetRenderedResult();
          for (const block of data.blocks || []) blocks.set(block.id, "");
          resultStatusEl.textContent = `${data.device || ""} · ${data.model || ""}`;
          store.engine = {
            ...(store.engine || {}),
            state: "ready",
            device: data.device,
            model_name: data.model,
          };
          updateEngine();
          if (data.device_warning) ctx.toast(data.device_warning, "warn", 5000);
        },
        block_start: (data) => {
          if (!blocks.has(data.block_id)) blocks.set(data.block_id, "");
          beginRenderedBlock(data.block_id);
          resultStatusEl.textContent = "翻译中…";
          resultTextEl.classList.add("streaming");
        },
        delta: (data) => {
          beginRenderedBlock(data.block_id);
          blocks.set(data.block_id, `${blocks.get(data.block_id) || ""}${data.text || ""}`);
          appendRenderedResult(data.text || "");
        },
        block_reset: (data) => {
          resetRenderedBlock(data.block_id);
          resultStatusEl.textContent = data.reason || "正在重试…";
        },
        block_done: (data) => {
          finishRenderedBlock(data.block_id, data.text || "");
          if (data.tok_s) resultMetaEl.textContent = `${data.tok_s} tok/s${data.ttft_ms ? ` · 首字 ${Math.round(data.ttft_ms)} ms` : ""}`;
          if ((data.warnings || []).length) resultStatusEl.textContent = "有提示，建议复核";
          else resultStatusEl.textContent = "完成";
        },
        done: (data) => {
          const finalText = data.text || [...blocks.values()].join("\n\n");
          renderedText = finalText;
          renderedBlockId = null;
          renderedBlockStart = 0;
          setResultText(finalText, false);
          resultStatusEl.textContent = data.cancelled ? "已取消" : "完成";
          resultMetaEl.textContent = `${data.device || ""} · ${data.elapsed_ms || 0} ms · ${data.tok_s || 0} tok/s`;
          store.draftTarget = finalText;
          try {
            localStorage.setItem("zc.draft.target", finalText);
          } catch {
            /* quota exceeded on very large results */
          }
          store.engine = {
            ...(store.engine || {}),
            state: "ready",
            device: data.device,
            model_name: data.model,
          };
          finishTranslation();
        },
        error: (data) => {
          sawError = true;
          resultStatusEl.textContent = "失败";
          renderedText = data.message || "翻译失败";
          renderedBlockId = null;
          setResultText(renderedText, false);
          ctx.toast(data.message || "翻译失败", "error", 5000);
          finishTranslation();
        },
      }, aborter.signal);
    } catch (error) {
      if (error.name === "AbortError") {
        resultStatusEl.textContent = "已取消";
      } else if (!sawError) {
        resultStatusEl.textContent = "失败";
        renderedText = error.message || String(error);
        renderedBlockId = null;
        setResultText(renderedText, false);
        ctx.toast(error.message || "翻译失败", "error", 5000);
      }
    } finally {
      if (streaming) finishTranslation();
    }
  }

  async function reloadStore(rerender = true) {
    try {
      const [settingsData, models, system, glossaries] = await Promise.all([
        api.get("/api/settings"),
        api.get("/api/models"),
        api.get("/api/system/info"),
        api.get("/api/glossaries"),
      ]);
      store.set({
        settings: settingsData,
        models: models.models,
        activeProfile: models.active_profile,
        engine: models.engine,
        system,
        glossaries: glossaries.items,
      });
      applySettings();
      updateCount();
      updateEngine();
      if (rerender && currentPage !== "translate") showPage(currentPage, true);
    } catch (error) {
      ctx.toast(error.message, "error");
    }
  }

  function disposeView() {
    if (currentView && typeof currentView.cleanup === "function") {
      try {
        currentView.cleanup();
      } catch (error) {
        console.error(error);
      }
    }
    currentView = null;
    currentViewRoute = "";
  }

  function renderView(route) {
    const module = VIEWS[route];
    if (!module) return;
    disposeView();
    clear(viewPage);
    const view = module.render(pageCtx);
    currentView = view;
    currentViewRoute = route;
    if (view && view.el instanceof Node) viewPage.appendChild(view.el);
    else if (view instanceof Node) viewPage.appendChild(view);
    viewPage.scrollTop = 0;
  }

  function setActiveTab(route) {
    for (const tab of shell.querySelectorAll(".compact-tab")) {
      tab.classList.toggle("active", tab.dataset.route === route);
    }
  }

  function animatePageIn(node) {
    if (!node) return;
    node.classList.remove("page-slide-in");
    // Reading offsetWidth forces the browser to restart the animation when
    // the same page is opened again.
    void node.offsetWidth;
    node.classList.add("page-slide-in");
  }

  function showPage(route, force = false) {
    if (route !== "screenshot") {
      shell.classList.remove("screenshot-mode");
      viewPage.classList.remove("screenshot-active");
    }
    if (route === "translate") {
      disposeView();
      viewPage.classList.add("hidden");
      translatePage.classList.remove("hidden");
      currentPage = "translate";
      setActiveTab("translate");
      animatePageIn(translatePage);
      if (!streaming) loadDrafts();
      textArea.focus();
      return;
    }
    if (!VIEWS[route]) return;
    translatePage.classList.add("hidden");
    viewPage.classList.remove("hidden");
    currentPage = route;
    setActiveTab(route);
    if (currentViewRoute !== route || force) renderView(route);
    else viewPage.scrollTop = 0;
    animatePageIn(viewPage);
  }

  const pageCtx = {
    store,
    api,
    toast: ctx.toast,
    navigate: (route) => showPage(route),
    openImageTranslation,
    reload: (rerender = true) => reloadStore(rerender),
    updateChrome: () => updateEngine(),
    setStatus: () => {},
  };

  function themeIsDark(theme) {
    return theme === "dark"
      || (theme === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);
  }

  function updateThemeButton() {
    if (!themeButton) return;
    const value = settings().theme || "system";
    clear(themeButton);
    themeButton.appendChild(icon(themeIsDark(value) ? "sun" : "moon", 15));
    themeButton.title = `主题：${value === "system" ? "跟随系统" : value === "dark" ? "深色" : "浅色"}`;
  }

  async function toggleTheme() {
    const order = ["system", "light", "dark"];
    const next = order[(order.indexOf(settings().theme || "system") + 1) % order.length];
    store.settings = { ...settings(), theme: next };
    document.documentElement.dataset.theme = next;
    window.zcSyncFrameColor?.();
    updateThemeButton();
    try {
      await api.put("/api/settings", { theme: next });
    } catch (error) {
      ctx.toast(error.message, "error");
    }
  }

  async function copyResult() {
    const text = resultTextEl.textContent || "";
    if (!text) {
      ctx.toast("没有可复制的译文", "warn");
      return;
    }
    try {
      await navigator.clipboard.writeText(text);
      ctx.toast("已复制译文", "success", 1800);
    } catch {
      const area = h("textarea", { style: "position:fixed;opacity:0" });
      area.value = text;
      document.body.appendChild(area);
      area.select();
      document.execCommand("copy");
      area.remove();
      ctx.toast("已复制译文", "success", 1800);
    }
  }

  function clearAll() {
    voiceController?.clearConversation();
    textArea.value = "";
    updateCount();
    hideResult();
    blocks.clear();
    store.draftText = "";
    store.draftTarget = "";
    localStorage.removeItem("zc.draft.text");
    localStorage.removeItem("zc.draft.target");
    textArea.focus();
  }

  function importFile() {
    const input = h("input", { type: "file", attrs: { accept: ".txt,.md,text/plain,text/markdown" } });
    input.addEventListener("change", () => {
      const file = input.files?.[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = () => {
        const raw = String(reader.result || "");
        textArea.value = raw;
        updateCount();
        saveDraft();
        if (raw.length > MAX_TEXT_CHARS) {
          ctx.toast(`已导入，但文本超过 ${MAX_TEXT_CHARS} 字，请分段后再翻译`, "warn", 5000);
        } else {
          ctx.toast(`已导入 ${file.name}`, "success", 2000);
        }
        textArea.focus();
      };
      reader.onerror = () => ctx.toast("文件读取失败", "error");
      reader.readAsText(file, "utf-8");
    });
    input.click();
  }

  async function captureNativeRegion() {
    const desktop = window.pywebview?.api;
    if (desktop && typeof desktop.capture_for_screenshot === "function") {
      return desktop.capture_for_screenshot();
    }
    return api.post("/api/screenshot/capture");
  }

  function openScreenshotView(capture, returnRoute = "translate") {
    saveDraft();
    disposeView();
    clear(viewPage);
    translatePage.classList.add("hidden");
    viewPage.classList.remove("hidden");
    viewPage.classList.add("screenshot-active");
    shell.classList.add("screenshot-mode");
    setActiveTab("");
    currentPage = "screenshot";
    viewPage.scrollTop = 0;
    const view = screenshotView.render(pageCtx, capture, {
      onBack: () => showPage(returnRoute),
    });
    currentView = view;
    currentViewRoute = "screenshot";
    if (view?.el instanceof Node) viewPage.appendChild(view.el);
    Promise.resolve(view?.start?.()).catch((error) => {
      ctx.toast(error?.message || "截图翻译失败", "error", 6000);
    });
  }

  function openImageTranslation(capture, returnRoute = "document") {
    if (!capture?.data_url) {
      ctx.toast("图片数据为空，请重新选择图片。", "error", 5000);
      return;
    }
    openScreenshotView(capture, returnRoute);
  }

  async function startScreenshotTranslation() {
    if (capturing) return;
    if (streaming) {
      ctx.toast("请先停止当前翻译，再截图。", "warn");
      return;
    }
    if (!store.hasModel()) {
      ctx.toast("未找到可用模型，请先在设置页检查模型。", "warn", 5000);
      return;
    }
    capturing = true;
    try {
      const capture = await captureNativeRegion();
      if (capture && capture.ok === false) {
        const error = new Error(capture.message || "截图失败");
        error.code = capture.code || "";
        error.cancelled = Boolean(capture.cancelled);
        throw error;
      }
      if (!capture?.data_url) throw new Error("截图返回为空，请重试。");
      openScreenshotView(capture, "translate");
    } catch (error) {
      if (error.code === "SCREENSHOT_CANCELLED") {
        ctx.toast(error.message || "已取消截图", "info", 6500);
      } else if (error.code === "SCREENSHOT_TIMEOUT") {
        ctx.toast(error.message || "等待截图超时，请重试。", "warn", 8000);
      } else {
        ctx.toast(error.message || "截图失败", "error", 8000);
      }
    } finally {
      capturing = false;
    }
  }

  // Initial state from the shared store / last draft.
  applySettings();
  populateGlossaries();
  const existingDraft = store.draftText || localStorage.getItem("zc.draft.text") || "";
  textArea.value = existingDraft;
  const existingTarget = store.draftTarget || localStorage.getItem("zc.draft.target") || "";
  if (existingTarget) {
    resultTextEl.textContent = existingTarget;
    showResult();
  }
  updateCount();
  updateEngine();
  updateThemeButton();

  // Window chrome.
  document.getElementById("compact-minimize")?.addEventListener("click", () => ctx.desktopCall("minimize"));
  const closeButton = document.getElementById("compact-close");
  if (closeButton) {
    closeButton.title = "关闭到托盘";
    closeButton.setAttribute("aria-label", "关闭到托盘");
    closeButton.addEventListener("click", () => ctx.desktopCall("close"));
  }
  document.getElementById("compact-screenshot")?.addEventListener("click", startScreenshotTranslation);
  document.getElementById("compact-settings")?.addEventListener("click", () => showPage("settings"));
  document.getElementById("compact-copy")?.addEventListener("click", copyResult);
  document.getElementById("compact-clear")?.addEventListener("click", clearAll);
  themeButton?.addEventListener("click", toggleTheme);
  translateButton.addEventListener("click", translate);
  importButton.addEventListener("click", importFile);
  swapButton.addEventListener("click", () => {
    const source = currentSource() === "auto" ? (store.lastDetected || "zh") : currentSource();
    let newSource = currentTarget();
    let newTarget = source;
    if (newSource === newTarget) newTarget = newSource === "zh" ? "en" : "zh";
    sourceSelect.value = newSource;
    targetSelect.value = newTarget;
    saveSettings({ source_lang: newSource, target_lang: newTarget });
    textArea.focus();
  });

  for (const tab of shell.querySelectorAll(".compact-tab")) {
    tab.addEventListener("click", () => showPage(tab.dataset.route || "translate"));
  }

  sourceSelect.addEventListener("change", () => {
    if (sourceSelect.value !== "auto" && sourceSelect.value === targetSelect.value) {
      targetSelect.value = sourceSelect.value === "zh" ? "ja" : "zh";
    }
    saveSettings({ source_lang: sourceSelect.value, target_lang: targetSelect.value });
  });
  targetSelect.addEventListener("change", () => {
    if (sourceSelect.value !== "auto" && targetSelect.value === sourceSelect.value) {
      ctx.toast("源语言与目标语言相同，请调整", "warn");
      targetSelect.value = settings().target_lang || "zh";
      return;
    }
    saveSettings({ target_lang: targetSelect.value });
  });
  glossarySelect.addEventListener("change", () => {
    glossarySelect.title = glossarySelect.selectedOptions[0]?.textContent || "";
    saveSettings({ glossary_id: glossarySelect.value });
  });
  styleSelect.addEventListener("change", () => saveSettings({ style: styleSelect.value }));
  tmCheck.addEventListener("change", () => saveSettings({ use_tm: tmCheck.checked }));
  textArea.addEventListener("input", () => {
    updateCount();
    saveDraft();
  });
  textArea.addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
      event.preventDefault();
      translate();
    } else if (event.key === "Escape" && streaming) {
      event.preventDefault();
      cancelTranslation();
    }
  });

  voiceController = createVoiceController({
    api,
    store,
    toast: ctx.toast,
    textArea,
    resultEl,
    resultTextEl,
    resultStatusEl,
    resultMetaEl,
    conversationButton: document.getElementById("compact-voice-conversation"),
    inputButton: document.getElementById("compact-voice-input"),
    downloadButton: document.getElementById("compact-voice-download"),
    stateEl: document.getElementById("compact-voice-state"),
    getSource: currentSource,
    getTarget: currentTarget,
    getStyle: () => styleSelect.value,
    getGlossary: () => glossarySelect.value,
    getSettings: settings,
    showResult,
    updateCount,
    saveDraft,
    resetResult: () => hideResult(),
    isTextBusy: () => streaming,
    setVoiceBusy: (value) => {
      shell.classList.toggle("voice-busy", value);
      if (!value) {
        sourceSelect.disabled = false;
        targetSelect.disabled = false;
        styleSelect.disabled = false;
        swapButton.disabled = false;
        importButton.disabled = false;
        tmCheck.disabled = false;
        textArea.readOnly = false;
      } else {
        sourceSelect.disabled = true;
        targetSelect.disabled = true;
        styleSelect.disabled = true;
        swapButton.disabled = true;
        importButton.disabled = true;
        tmCheck.disabled = true;
        textArea.readOnly = true;
      }
    },
  });

  const unsub = store.subscribe(() => {
    updateEngine();
    updateThemeButton();
    if (!streaming) tmCheck.checked = settings().use_tm !== false;
    if (document.activeElement !== glossarySelect) populateGlossaries();
  });

  const onThemeMedia = () => {
    if ((settings().theme || "system") === "system") updateThemeButton();
  };
  const onSettingsChanged = () => reloadStore(true);
  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", onThemeMedia);
  window.addEventListener("zc-screenshot", startScreenshotTranslation);
  window.addEventListener("zc-settings-changed", onSettingsChanged);

  return {
    cleanup() {
      unsub();
      voiceController?.cleanup();
      disposeView();
      window.removeEventListener("zc-screenshot", startScreenshotTranslation);
      window.removeEventListener("zc-settings-changed", onSettingsChanged);
      window.matchMedia("(prefers-color-scheme: dark)").removeEventListener("change", onThemeMedia);
    },
  };
}
