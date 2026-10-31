import { api } from "./api.js";

window.addEventListener("error", (event) => {
  window.__zcLastError = String(event.message || event.error || "script error");
});
window.addEventListener("unhandledrejection", (event) => {
  const reason = event.reason;
  window.__zcLastError = String(reason?.message || reason || "unhandled rejection");
});

const TARGET_LABELS = { zh: "中文", ja: "日语", en: "英语" };
const root = document.getElementById("zc-overlay");
const langEl = document.getElementById("zc-overlay-lang");
const sourceEl = document.getElementById("zc-overlay-source");
const statusEl = document.getElementById("zc-overlay-status");
const targetEl = document.getElementById("zc-overlay-target");
const copyButton = document.getElementById("zc-overlay-copy");
const closeButton = document.getElementById("zc-overlay-close");

const state = {
  version: 0,
  controller: null,
  text: "",
  target: "zh",
  blocks: new Map(),
  hideTimer: 0,
  measureTimer: 0,
  renderTimer: 0,
  renderStreaming: false,
  lastSize: "",
  lastMeasureAt: 0,
  bridge: null,
};

function bridge() {
  if (!state.bridge) {
    state.bridge = window.pywebview?.api || null;
  }
  return state.bridge;
}

function applyTheme(theme) {
  document.documentElement.dataset.theme = theme || "system";
}

function targetLabel(code) {
  return TARGET_LABELS[code] || code || "译文";
}

function setLanguage(source, target) {
  const left = source ? source.toUpperCase() : "自动";
  langEl.textContent = `${left} → ${targetLabel(target)}`;
}

function setStatus(text) {
  statusEl.textContent = String(text || "");
  statusEl.classList.toggle("hidden", !text);
  scheduleMeasure();
}

function renderTarget(streaming) {
  const value = [...state.blocks.entries()]
    .sort((a, b) => a[0] - b[0])
    .map(([, text]) => text)
    .join("\n\n");
  targetEl.textContent = value;
  targetEl.classList.toggle("streaming", Boolean(streaming));
  scheduleMeasure();
}

function cancelScheduledRender() {
  if (state.renderTimer) {
    window.clearTimeout(state.renderTimer);
    state.renderTimer = 0;
  }
  state.renderStreaming = false;
}

function flushRender(streaming) {
  cancelScheduledRender();
  renderTarget(streaming);
}

function scheduleRender(streaming) {
  // Long selections can stream thousands of deltas.  Coalesce them so the
  // hidden WebView and the native resize bridge are not called per token.
  state.renderStreaming = state.renderStreaming || Boolean(streaming);
  if (state.renderTimer) return;
  state.renderTimer = window.setTimeout(() => {
    state.renderTimer = 0;
    const value = state.renderStreaming;
    state.renderStreaming = false;
    renderTarget(value);
  }, 50);
}

function measureNow() {
  if (root.classList.contains("hidden")) return;
  const rect = root.getBoundingClientRect();
  const maxHeight = Math.max(96, Number(root.style.maxHeight.replace("px", "")) || 360);
  // scrollHeight keeps growing even while the native window is still at the
  // previous height.  Using it here makes every streamed delta resize the card
  // immediately instead of waiting for the final done event.
  const contentHeight = Math.max(rect.height, root.scrollHeight);
  const width = Math.max(220, Math.ceil(rect.width || root.scrollWidth));
  const height = Math.max(56, Math.min(maxHeight, Math.ceil(contentHeight)));
  state.lastMeasureAt = performance.now();
  const size = `${width}x${height}`;
  if (size === state.lastSize) return;
  state.lastSize = size;
  const app = bridge();
  if (app && typeof app.overlay_resize === "function") {
    Promise.resolve(app.overlay_resize(width, height)).catch(() => {});
  }
}

function scheduleMeasure(immediate = false) {
  if (root.classList.contains("hidden")) return;
  const now = performance.now();
  if (immediate || now - state.lastMeasureAt >= 32) {
    window.clearTimeout(state.measureTimer);
    state.measureTimer = 0;
    measureNow();
    return;
  }
  if (state.measureTimer) return;
  state.measureTimer = window.setTimeout(() => {
    state.measureTimer = 0;
    measureNow();
  }, 16);
}

function scheduleHide(delay) {
  window.clearTimeout(state.hideTimer);
  state.hideTimer = window.setTimeout(() => hideOverlay(), delay);
}

function hideOverlay() {
  const app = bridge();
  if (app && typeof app.overlay_hide === "function") {
    Promise.resolve(app.overlay_hide()).catch(() => {});
  }
  cancel();
}

function cancel() {
  state.version += 1;
  window.clearTimeout(state.hideTimer);
  window.clearTimeout(state.measureTimer);
  cancelScheduledRender();
  if (state.controller) {
    try {
      state.controller.abort();
    } catch {
      /* ignore */
    }
    state.controller = null;
  }
  state.blocks.clear();
  state.lastSize = "";
  root.classList.add("hidden");
  sourceEl.textContent = "";
  targetEl.textContent = "";
  targetEl.classList.remove("streaming");
  langEl.textContent = "";
  setStatus("");
  copyButton.textContent = "复制";
}

async function copyResult() {
  const text = targetEl.textContent || "";
  if (!text) return;
  let ok = false;
  const app = bridge();
  if (app && typeof app.copy_text === "function") {
    try {
      ok = Boolean(await app.copy_text(text));
    } catch {
      ok = false;
    }
  }
  if (!ok) {
    try {
      await navigator.clipboard.writeText(text);
      ok = true;
    } catch {
      ok = false;
    }
  }
  copyButton.textContent = ok ? "已复制" : "复制失败";
  window.setTimeout(() => { copyButton.textContent = "复制"; }, 1200);
}

async function show(payload) {
  const text = typeof payload?.text === "string" ? payload.text.trim() : "";
  if (!text) {
    hideOverlay();
    return;
  }
  const version = ++state.version;
  window.clearTimeout(state.hideTimer);
  window.clearTimeout(state.measureTimer);
  if (state.controller) {
    try {
      state.controller.abort();
    } catch {
      /* ignore */
    }
  }
  state.controller = null;
  state.text = text;
  state.blocks = new Map();
  cancelScheduledRender();
  state.lastSize = "";
  state.target = "zh";
  root.classList.remove("hidden");
  root.style.maxHeight = `${Math.max(96, Number(payload?.maxHeight) || 360)}px`;
  sourceEl.textContent = text.length > 240 ? `${text.slice(0, 240)}…` : text;
  setLanguage("", state.target);
  setStatus("正在翻译…");
  targetEl.textContent = "";
  scheduleMeasure(true);

  let settings;
  try {
    settings = await api.get("/api/settings");
  } catch (error) {
    if (version !== state.version) return;
    setStatus(error?.message || "无法读取设置");
    scheduleMeasure();
    return;
  }
  if (version !== state.version) return;
  applyTheme(settings.theme);
  if (!settings.selection_translate) {
    hideOverlay();
    return;
  }
  state.target = settings.target_lang || "zh";
  setLanguage("", state.target);
  scheduleMeasure();

  const controller = new AbortController();
  state.controller = controller;
  const request = {
    text,
    source_lang: "auto",
    target_lang: state.target,
    profile_id: settings.profile_id || null,
    device: settings.device || "auto",
    glossary_id: settings.glossary_id || null,
    style: settings.style || "default",
    use_tm: settings.use_tm !== false,
    use_context: false,
    refine: false,
    split_mode: "auto",
  };

  try {
    await api.translateStream(request, {
      status: (data) => {
        if (version !== state.version) return;
        if (data.message) setStatus(data.message);
      },
      meta: (data) => {
        if (version !== state.version) return;
        setLanguage(data.detected_lang || data.src_lang || "", state.target);
        state.blocks = new Map();
        for (const block of data.blocks || []) state.blocks.set(block.id, "");
        setStatus("翻译中…");
        scheduleMeasure();
      },
      block_start: (data) => {
        if (version !== state.version) return;
        if (!state.blocks.has(data.block_id)) state.blocks.set(data.block_id, "");
        setStatus("翻译中…");
        scheduleRender(true);
      },
      block_reset: (data) => {
        if (version !== state.version) return;
        state.blocks.set(data.block_id, "");
        setStatus(data.reason || "正在重试…");
        scheduleRender(true);
      },
      delta: (data) => {
        if (version !== state.version) return;
        state.blocks.set(
          data.block_id,
          `${state.blocks.get(data.block_id) || ""}${data.text || ""}`,
        );
        scheduleRender(true);
      },
      block_done: (data) => {
        if (version !== state.version) return;
        state.blocks.set(data.block_id, data.text || "");
        flushRender(false);
        setStatus((data.warnings || []).length ? "完成（有提示，建议复核）" : "完成");
        scheduleMeasure(true);
      },
      done: (data) => {
        if (version !== state.version) return;
        cancelScheduledRender();
        const finalText = data.text || [...state.blocks.values()].join("\n\n");
        if (finalText) {
          targetEl.textContent = finalText;
          targetEl.classList.remove("streaming");
        }
        setStatus(data.warnings?.length ? "完成（有提示，建议复核）" : "完成");
        state.controller = null;
        scheduleMeasure(true);
      },
      error: (data) => {
        if (version !== state.version) return;
        state.controller = null;
        const message = data.message || "翻译失败";
        if (data.code === "SAME_LANGUAGE") {
          setStatus(message || "原文已是目标语言");
          targetEl.textContent = "";
          scheduleHide(1800);
        } else {
          setStatus(message);
        }
        scheduleMeasure();
      },
    }, controller.signal);
  } catch (error) {
    if (version !== state.version) return;
    if (error?.name === "AbortError") return;
    setStatus(error?.message || "翻译失败");
    scheduleMeasure();
  }
}

copyButton.addEventListener("click", copyResult);
closeButton.addEventListener("click", hideOverlay);
window.addEventListener("keydown", (event) => {
  if (event.key === "Escape") hideOverlay();
});
window.addEventListener("pywebviewready", () => {
  state.bridge = window.pywebview?.api || null;
  scheduleMeasure();
});

try {
  state.bridge = window.pywebview?.api || null;
} catch {
  state.bridge = null;
}

new ResizeObserver(() => scheduleMeasure()).observe(root);
window.zcOverlay = { show, cancel, hide: hideOverlay, refreshSize: scheduleMeasure };

api.get("/api/settings").then((settings) => applyTheme(settings.theme)).catch(() => {});
