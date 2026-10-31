import { h, clear, selectOption, spinner } from "../dom.js";
import { icon } from "../icons.js";

const SOURCES = [
  { value: "auto", label: "自动" },
  { value: "zh", label: "中文" },
  { value: "ja", label: "日语" },
  { value: "en", label: "英语" },
];
const TARGETS = [
  { value: "zh", label: "中文" },
  { value: "ja", label: "日语" },
  { value: "en", label: "英语" },
];
const MAX_LINES = 200;
const MIN_SCORE = 0.3;

function base64FromDataUrl(dataUrl) {
  return String(dataUrl || "").split(",", 2)[1] || "";
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function languageLabel(value) {
  return [...SOURCES, ...TARGETS].find((item) => item.value === value)?.label || value;
}

function waitForImage(image) {
  if (image.complete && image.naturalWidth) return Promise.resolve();
  return new Promise((resolve) => {
    image.addEventListener("load", resolve, { once: true });
    image.addEventListener("error", resolve, { once: true });
  });
}

export function render(ctx, capture, { onBack } = {}) {
  const settings = ctx.store.settings || {};
  let imageWidth = Number(capture?.width) || 0;
  let imageHeight = Number(capture?.height) || 0;
  let items = [];
  let targetTexts = [];
  let itemWarnings = [];
  let detectedLang = "";
  let mode = "translated";
  let zoom = "fit";
  let stageScale = 1;
  let selectedIndex = -1;
  let running = false;
  let destroyed = false;
  let translatedCount = 0;
  let aborter = null;
  let ocrAborter = null;
  let jobId = "";
  let fitFrame = 0;
  let panning = null;

  const cards = [];

  const sourceSelect = h("select", { class: "shot-select", attrs: { "aria-label": "截图源语言" } });
  for (const item of SOURCES) sourceSelect.appendChild(selectOption(item.value, item.label));
  sourceSelect.value = settings.source_lang || "auto";
  const targetSelect = h("select", { class: "shot-select", attrs: { "aria-label": "截图目标语言" } });
  for (const item of TARGETS) targetSelect.appendChild(selectOption(item.value, item.label));
  targetSelect.value = settings.target_lang || "zh";

  const statusEl = h("span", { class: "shot-status", attrs: { "aria-live": "polite" }, text: "准备截图" });
  const backButton = h("button", { class: "ghost small shot-back", attrs: { type: "button", title: "返回翻译" } }, [
    icon("back", 14), h("span", { text: "返回" }),
  ]);
  const originalButton = h("button", {
    class: "ghost small shot-mode",
    attrs: { type: "button", "aria-pressed": "false", title: "查看截图原文" },
  });
  const copyButton = h("button", { class: "ghost small", attrs: { type: "button", title: "复制全部译文" } }, [
    icon("copy", 14), h("span", { text: "复制" }),
  ]);
  const zoomOutButton = h("button", {
    class: "ghost small shot-icon", attrs: { type: "button", title: "缩小", "aria-label": "缩小" },
  }, [icon("zoomOut", 14)]);
  const zoomInButton = h("button", {
    class: "ghost small shot-icon", attrs: { type: "button", title: "放大", "aria-label": "放大" },
  }, [icon("zoomIn", 14)]);
  const fitButton = h("button", {
    class: "ghost small shot-icon", attrs: { type: "button", title: "适应窗口", "aria-label": "适应窗口" },
  }, [icon("fit", 14)]);
  const oneToOneButton = h("button", {
    class: "ghost small shot-one",
    attrs: { type: "button", title: "原始大小（100%）", "aria-label": "原始大小" },
    text: "1:1",
  });
  const zoomLabel = h("span", { class: "shot-zoom-label", text: "适应" });
  const cancelButton = h("button", {
    class: "ghost small shot-cancel hidden", attrs: { type: "button", text: "停止" },
  }, "停止");

  const progressFill = h("i", { style: "width:0%" });
  const progressBar = h("div", { class: "shot-progressbar", attrs: { role: "progressbar", "aria-valuemin": "0", "aria-valuemax": "100" } }, progressFill);
  const errorEl = h("div", { class: "shot-error hidden" });
  const image = h("img", { attrs: { alt: "截图", draggable: "false" } });
  image.src = capture?.data_url || "";
  const overlay = h("div", { class: "shot-overlay" });
  const canvas = h("div", { class: "shot-canvas" }, [image, overlay]);
  const loadingEl = h("div", { class: "shot-stage-note" }, spinner("正在识别文字…"));
  const emptyEl = h("div", { class: "shot-stage-note hidden" }, [h("strong", { text: "未识别到文字" }), h("span", { text: "可以切换“原文”查看截图，或返回重试。" })]);
  const stage = h("div", { class: "shot-stage" }, [canvas, loadingEl, emptyEl]);

  const detailSource = h("div", { class: "shot-detail-text" });
  const detailTarget = h("div", { class: "shot-detail-text" });
  const detailWarnings = h("div", { class: "shot-detail-warn hidden" });
  const detailClose = h("button", {
    class: "ghost small", attrs: { type: "button", "aria-label": "关闭对照" }, on: { click: () => clearSelection() },
  }, "关闭");
  const detailEl = h("div", { class: "shot-detail hidden" }, [
    h("div", { class: "shot-detail-head" }, [
      h("strong", { text: "原文 / 译文对照" }),
      h("span", { class: "hint", text: "悬停译文块可原位看原文；点击块可固定对照。" }),
      detailClose,
    ]),
    h("div", { class: "shot-detail-grid" }, [
      h("div", { class: "shot-detail-col" }, [h("label", { text: "识别原文" }), detailSource]),
      h("div", { class: "shot-detail-col" }, [h("label", { text: "译文" }), detailTarget]),
    ]),
    detailWarnings,
  ]);

  const backRow = h("div", { class: "shot-row" }, [
    backButton,
    h("div", { class: "shot-title" }, [h("strong", { text: "截图翻译" }), statusEl]),
    h("span", { class: "shot-spacer" }),
    originalButton,
    copyButton,
  ]);
  const controlRow = h("div", { class: "shot-row shot-controls" }, [
    h("label", { class: "shot-label", text: "源" }),
    sourceSelect,
    h("span", { class: "shot-arrow", text: "→" }),
    h("label", { class: "shot-label", text: "目标" }),
    targetSelect,
    h("span", { class: "shot-spacer" }),
    zoomOutButton,
    zoomLabel,
    zoomInButton,
    oneToOneButton,
    fitButton,
    cancelButton,
  ]);
  const el = h("div", { class: "screenshot-page", dataset: { mode } }, [
    backRow,
    controlRow,
    progressBar,
    errorEl,
    stage,
    detailEl,
  ]);

  function setStatus(text) {
    statusEl.textContent = text || "";
  }

  function updateOriginalButton() {
    clear(originalButton);
    originalButton.appendChild(icon(mode === "translated" ? "eye" : "eyeOff", 14));
    originalButton.appendChild(h("span", { text: mode === "translated" ? "原文" : "译文" }));
    originalButton.title = mode === "translated" ? "查看截图原文" : "回到译文覆盖";
    originalButton.setAttribute("aria-pressed", String(mode === "original"));
  }

  function setMode(next) {
    mode = next;
    el.dataset.mode = mode;
    updateOriginalButton();
    if (mode === "original") clearSelection();
  }

  function showError(message, { toastIt = false } = {}) {
    errorEl.textContent = message || "";
    errorEl.classList.toggle("hidden", !message);
    if (message && toastIt) ctx.toast(message, "error", 6000);
  }

  function hideError() {
    errorEl.textContent = "";
    errorEl.classList.add("hidden");
  }

  function showLoading(text) {
    clear(loadingEl);
    loadingEl.appendChild(spinner(text));
    loadingEl.classList.remove("hidden");
  }

  function hideLoading() {
    loadingEl.classList.add("hidden");
  }

  function updateProgress(done) {
    const total = items.length || 1;
    const percent = Math.round((done / total) * 100);
    progressFill.style.width = `${clamp(percent, 0, 100)}%`;
    progressBar.setAttribute("aria-valuenow", String(clamp(percent, 0, 100)));
  }

  function effectiveSource() {
    if (sourceSelect.value !== "auto") return sourceSelect.value;
    return detectedLang || "";
  }

  function sourceLabel() {
    const value = effectiveSource();
    return value ? languageLabel(value) : "未知";
  }

  function checkLanguage() {
    const source = effectiveSource();
    if (!source) return "无法判断原文语言，请手动选择源语言。";
    if (source === targetSelect.value) {
      return `原文已是${languageLabel(source)}，请选择其他目标语言。`;
    }
    return "";
  }

  function scheduleFitCards() {
    if (destroyed) return;
    if (fitFrame) cancelAnimationFrame(fitFrame);
    fitFrame = requestAnimationFrame(() => {
      fitFrame = 0;
      fitCards();
    });
  }

  function fitCards() {
    for (const card of cards) {
      if (!card || !card.isConnected) continue;
      const height = card.clientHeight;
      if (height <= 0) continue;
      let size = clamp(height * 0.66, 7, 28);
      card.style.fontSize = `${size}px`;
      let guard = 0;
      while ((card.scrollHeight > card.clientHeight + 1 || card.scrollWidth > card.clientWidth + 1)
        && size > 6 && guard < 18) {
        size -= 0.5;
        card.style.fontSize = `${size}px`;
        guard += 1;
      }
      card.classList.toggle("clipped", size <= 6.5
        && (card.scrollHeight > card.clientHeight + 1 || card.scrollWidth > card.clientWidth + 1));
    }
  }

  function sampleColors() {
    if (!imageWidth || !imageHeight || !items.length) return;
    let sample = null;
    try {
      const width = Math.min(320, imageWidth);
      const height = Math.max(1, Math.round(imageHeight * width / imageWidth));
      const canvasEl = document.createElement("canvas");
      canvasEl.width = width;
      canvasEl.height = height;
      const context = canvasEl.getContext("2d", { willReadFrequently: true });
      context.drawImage(image, 0, 0, width, height);
      sample = { data: context.getImageData(0, 0, width, height).data, width, height };
    } catch {
      sample = null;
    }
    const points = [[0, 0, 1, 1], [1, 0, -1, 1], [0, 1, 1, -1], [1, 1, -1, -1]];
    items.forEach((item, index) => {
      const card = cards[index];
      if (!card) return;
      let luminance = 0.65;
      if (sample) {
        const px = (item.bbox[0] + item.bbox[2]) / 2;
        const py = (item.bbox[1] + item.bbox[3]) / 2;
        let total = 0;
        for (const [fx, fy, dx, dy] of points) {
          const x = clamp(Math.round((px + (item.bbox[2] - item.bbox[0]) * (fx - 0.5) + dx) * sample.width / imageWidth), 0, sample.width - 1);
          const y = clamp(Math.round((py + (item.bbox[3] - item.bbox[1]) * (fy - 0.5) + dy) * sample.height / imageHeight), 0, sample.height - 1);
          const offset = (y * sample.width + x) * 4;
          const r = sample.data[offset] / 255;
          const g = sample.data[offset + 1] / 255;
          const b = sample.data[offset + 2] / 255;
          total += 0.2126 * r + 0.7152 * g + 0.0722 * b;
        }
        luminance = total / points.length;
      }
      if (luminance > 0.55) {
        card.style.setProperty("--shot-paper", "#ffffff");
        card.style.setProperty("--shot-ink", "#0f172a");
      } else {
        card.style.setProperty("--shot-paper", "#0f172a");
        card.style.setProperty("--shot-ink", "#f8fafc");
      }
    });
  }

  function cardText(index) {
    const card = cards[index];
    if (!card) return;
    const value = targetTexts[index] || "";
    if (running && !value) {
      card.textContent = "…";
      card.classList.add("pending");
    } else {
      card.textContent = value || items[index]?.text || "";
      card.classList.remove("pending");
    }
    card.classList.toggle("warn", Boolean(itemWarnings[index]?.length));
    scheduleFitCards();
  }

  function renderCards() {
    clear(overlay);
    cards.length = 0;
    items.forEach((item, index) => {
      const [x0, y0, x1, y1] = item.bbox;
      const left = (x0 / imageWidth) * 100;
      const top = (y0 / imageHeight) * 100;
      const width = ((x1 - x0) / imageWidth) * 100;
      const height = ((y1 - y0) / imageHeight) * 100;
      if (!(width > 0) || !(height > 0)) return;
      const card = h("button", {
        class: "shot-card pending",
        attrs: {
          type: "button",
          "aria-label": `第 ${index + 1} 段译文，悬停查看原文，点击查看对照`,
        },
        on: { click: (event) => { event.stopPropagation(); selectItem(index); } },
      }, "…");
      Object.assign(card.style, {
        left: `${left}%`, top: `${top}%`, width: `${width}%`, height: `${height}%`,
      });
      overlay.appendChild(card);
      cards[index] = card;
    });
    sampleColors();
    scheduleFitCards();
  }

  function updateDetail() {
    if (selectedIndex < 0 || !items[selectedIndex]) {
      detailEl.classList.add("hidden");
      return;
    }
    const item = items[selectedIndex];
    detailSource.textContent = item.text || "";
    detailTarget.textContent = targetTexts[selectedIndex] || (running ? "翻译中…" : "暂无译文");
    detailWarnings.textContent = (itemWarnings[selectedIndex] || []).join("；");
    detailWarnings.classList.toggle("hidden", !itemWarnings[selectedIndex]?.length);
    detailEl.classList.remove("hidden");
  }

  function selectItem(index) {
    if (!items[index]) return;
    selectedIndex = index;
    cards.forEach((card, cardIndex) => card?.classList.toggle("selected", cardIndex === index));
    updateDetail();
  }

  function clearSelection() {
    selectedIndex = -1;
    for (const card of cards) card?.classList.remove("selected");
    detailEl.classList.add("hidden");
  }

  function applyZoom() {
    if (destroyed || !imageWidth || !imageHeight) return;
    const availableWidth = Math.max(80, stage.clientWidth - 16);
    const availableHeight = Math.max(80, stage.clientHeight - 16);
    const fitScale = Math.max(0.05, Math.min(availableWidth / imageWidth, availableHeight / imageHeight, 1));
    const scale = zoom === "fit" ? fitScale : zoom;
    stageScale = scale;
    canvas.style.width = `${Math.round(imageWidth * scale)}px`;
    canvas.style.height = `${Math.round(imageHeight * scale)}px`;
    zoomLabel.textContent = zoom === "fit" ? "适应" : `${Math.round(scale * 100)}%`;
    scheduleFitCards();
  }

  function stepZoom(factor) {
    const current = stageScale || 1;
    const availableWidth = Math.max(80, stage.clientWidth - 16);
    const availableHeight = Math.max(80, stage.clientHeight - 16);
    const fitScale = Math.max(0.05, Math.min(availableWidth / imageWidth, availableHeight / imageHeight, 1));
    const next = clamp(current * factor, 0.1, 4);
    zoom = next <= fitScale * 1.01 ? "fit" : next;
    applyZoom();
  }

  function stopStream(showCancelled) {
    if (aborter) {
      try { aborter.abort(); } catch { /* ignore */ }
    }
    if (jobId) ctx.api.cancelJob(jobId);
    aborter = null;
    jobId = "";
    running = false;
    cancelButton.classList.add("hidden");
    if (showCancelled) setStatus("已取消");
  }

  function finaliseTranslation(statusText) {
    running = false;
    aborter = null;
    jobId = "";
    cancelButton.classList.add("hidden");
    setStatus(statusText);
    updateProgress(translatedCount);
  }

  async function startTranslation() {
    if (!items.length) return;
    stopStream(false);
    hideError();
    const languageProblem = checkLanguage();
    if (languageProblem) {
      showError(languageProblem);
      setStatus(languageProblem);
      if (sourceSelect.value === "auto" && !detectedLang) sourceSelect.focus();
      else targetSelect.focus();
      return;
    }

    targetTexts = items.map(() => "");
    itemWarnings = items.map(() => []);
    translatedCount = 0;
    updateProgress(0);
    clearSelection();
    cards.forEach((card) => { if (card) card.classList.add("pending"); });
    cards.forEach((_, index) => cardText(index));
    running = true;
    cancelButton.classList.remove("hidden");
    setStatus("正在翻译…");
    const controller = new AbortController();
    aborter = controller;
    jobId = "";
    const payload = {
      lines: items.map((item) => item.text),
      source_lang: sourceSelect.value,
      target_lang: targetSelect.value,
      profile_id: settings.profile_id || "balanced",
      device: settings.device || "auto",
      glossary_id: settings.glossary_id || null,
      style: settings.style || "default",
      use_tm: settings.use_tm !== false,
    };

    try {
      await ctx.api.screenshotStream(payload, {
        onOpen: (response) => {
          jobId = response.headers.get("X-Job-Id") || "";
          setStatus("排队 / 加载模型…");
        },
        status: (data) => {
          if (data.message) setStatus(data.message);
        },
        meta: (data) => {
          detectedLang = data.detected_lang || detectedLang;
          if (data.device_warning) ctx.toast(data.device_warning, "warn", 5000);
          setStatus(`${data.device || ""} · ${data.model || ""}`.trim() || "翻译中…");
          const problem = checkLanguage();
          if (problem) {
            showError(problem);
            stopStream(false);
            finaliseTranslation(problem);
          }
        },
        item_start: (data) => {
          targetTexts[data.index] = "";
          itemWarnings[data.index] = [];
          cardText(data.index);
          setStatus(`翻译 ${data.index + 1}/${items.length}`);
        },
        item_delta: (data) => {
          targetTexts[data.index] = `${targetTexts[data.index] || ""}${data.text || ""}`;
          cardText(data.index);
          if (selectedIndex === data.index) updateDetail();
        },
        item_reset: (data) => {
          targetTexts[data.index] = "";
          itemWarnings[data.index] = [];
          cardText(data.index);
          setStatus(data.reason || "正在重试…");
        },
        item_done: (data) => {
          targetTexts[data.index] = data.text || "";
          itemWarnings[data.index] = data.warnings || [];
          cardText(data.index);
          translatedCount += 1;
          updateProgress(translatedCount);
          if (selectedIndex === data.index) updateDetail();
          setStatus(`已翻译 ${translatedCount}/${items.length}`);
        },
        done: (data) => {
          if (Array.isArray(data.targets) && data.targets.length === items.length) {
            targetTexts = data.targets.slice();
          }
          cards.forEach((_, index) => cardText(index));
          translatedCount = items.length;
          updateProgress(translatedCount);
          if (data.cancelled) setStatus("已取消");
          else setStatus(`完成 · ${items.length} 段 · ${data.device || ""}`.trim());
          finaliseTranslation(data.cancelled ? "已取消" : `完成 · ${items.length} 段`);
          if (selectedIndex >= 0) updateDetail();
        },
        error: (data) => {
          showError(data.message || "翻译失败");
          ctx.toast(data.message || "翻译失败", "error", 6000);
          finaliseTranslation("失败");
        },
      }, controller.signal);
    } catch (error) {
      if (error.name === "AbortError") {
        if (!destroyed && aborter === controller) setStatus("已取消");
      } else if (aborter === controller) {
        showError(error.message || "翻译失败");
        ctx.toast(error.message || "翻译失败", "error", 6000);
        finaliseTranslation("失败");
      }
    } finally {
      if (aborter === controller) {
        aborter = null;
        running = false;
        cancelButton.classList.add("hidden");
      }
    }
  }

  async function runOcr() {
    if (!capture?.data_url) {
      showError("截图数据为空，请重新截图。");
      setStatus("截图失败");
      hideLoading();
      return;
    }
    hideError();
    showLoading("正在识别文字…");
    setStatus("正在识别文字…");
    emptyEl.classList.add("hidden");
    ocrAborter?.abort();
    const controller = new AbortController();
    ocrAborter = controller;
    try {
      const data = await ctx.api.post("/api/ocr/image", {
        file_name: "screenshot.png",
        content_base64: base64FromDataUrl(capture.data_url),
      }, { signal: controller.signal });
      if (destroyed) return;
      imageWidth = Number(data.width) || imageWidth || image.naturalWidth;
      imageHeight = Number(data.height) || imageHeight || image.naturalHeight;
      if (!imageWidth || !imageHeight) throw new Error("截图尺寸无效，请重新截图。");
      detectedLang = data.detected_lang || "";
      const rawItems = Array.isArray(data.items) ? data.items : [];
      const filtered = rawItems.filter((item) => item && item.text && (item.score === undefined || item.score >= MIN_SCORE));
      const chosen = (filtered.length ? filtered : rawItems.filter((item) => item?.text)).slice(0, MAX_LINES);
      items = chosen.map((item) => {
        const [x0, y0, x1, y1] = (item.bbox || [0, 0, 0, 0]).map(Number);
        const left = clamp(Math.min(x0, x1), 0, imageWidth);
        const top = clamp(Math.min(y0, y1), 0, imageHeight);
        const right = clamp(Math.max(x0, x1), 0, imageWidth);
        const bottom = clamp(Math.max(y0, y1), 0, imageHeight);
        return { ...item, bbox: [left, top, right, bottom] };
      }).filter((item) => item.bbox[2] > item.bbox[0] && item.bbox[3] > item.bbox[1]);
      targetTexts = items.map(() => "");
      itemWarnings = items.map(() => []);
      applyZoom();
      renderCards();
      hideLoading();
      if (!items.length) {
        emptyEl.classList.remove("hidden");
        setStatus("未识别到文字");
        return;
      }
      if (rawItems.length > MAX_LINES) ctx.toast(`文字较多，仅翻译前 ${MAX_LINES} 段`, "warn", 5000);
      setStatus(`识别到 ${items.length} 段 · ${sourceLabel()}`);
      const problem = checkLanguage();
      if (problem) {
        showError(problem);
        setStatus(problem);
        return;
      }
      await startTranslation();
    } catch (error) {
      if (error.name === "AbortError" || destroyed) return;
      hideLoading();
      showError(error.message || "OCR 识别失败");
      ctx.toast(error.message || "OCR 识别失败", "error", 6000);
      setStatus("识别失败");
    }
  }

  function toggleMode() {
    setMode(mode === "translated" ? "original" : "translated");
  }

  async function copyAll() {
    const text = items.map((item, index) => targetTexts[index] || item.text || "").join("\n");
    if (!text) {
      ctx.toast("没有可复制的译文", "warn");
      return;
    }
    try {
      await navigator.clipboard.writeText(text);
      ctx.toast("已复制全部译文", "success", 1800);
    } catch {
      const area = h("textarea", { style: "position:fixed;opacity:0" });
      area.value = text;
      document.body.appendChild(area);
      area.select();
      document.execCommand("copy");
      area.remove();
      ctx.toast("已复制全部译文", "success", 1800);
    }
  }

  async function persistLanguages() {
    try {
      const updated = await ctx.api.put("/api/settings", {
        source_lang: sourceSelect.value,
        target_lang: targetSelect.value,
      });
      ctx.store.set({ settings: updated });
    } catch (error) {
      ctx.toast(error.message, "error");
    }
  }

  async function languageChanged() {
    await persistLanguages();
    if (items.length) {
      await startTranslation();
    }
  }

  function onKeyDown(event) {
    if (event.key !== "Escape") return;
    if (!detailEl.classList.contains("hidden")) {
      event.preventDefault();
      clearSelection();
    } else if (running) {
      event.preventDefault();
      stopStream(true);
      finaliseTranslation("已取消");
    } else {
      event.preventDefault();
      onBack?.();
    }
  }

  function onStageClick(event) {
    if (!event.target.closest(".shot-card")) clearSelection();
  }

  function onStageWheel(event) {
    if (!event.ctrlKey) return;
    event.preventDefault();
    stepZoom(event.deltaY < 0 ? 1.15 : 0.87);
  }

  function onStageDoubleClick(event) {
    if (event.target.closest(".shot-card")) return;
    zoom = zoom === "fit" ? 1 : "fit";
    applyZoom();
  }

  function onStagePointerDown(event) {
    if (event.button !== 0 || event.target.closest(".shot-card")) return;
    if (stage.scrollWidth <= stage.clientWidth && stage.scrollHeight <= stage.clientHeight) return;
    panning = {
      x: event.clientX,
      y: event.clientY,
      left: stage.scrollLeft,
      top: stage.scrollTop,
    };
    stage.classList.add("panning");
    try { stage.setPointerCapture(event.pointerId); } catch { /* ignore */ }
  }

  function onStagePointerMove(event) {
    if (!panning) return;
    stage.scrollLeft = panning.left - (event.clientX - panning.x);
    stage.scrollTop = panning.top - (event.clientY - panning.y);
  }

  function onStagePointerUp(event) {
    if (!panning) return;
    panning = null;
    stage.classList.remove("panning");
    try { stage.releasePointerCapture(event.pointerId); } catch { /* ignore */ }
  }

  backButton.addEventListener("click", () => onBack?.());
  originalButton.addEventListener("click", toggleMode);
  copyButton.addEventListener("click", copyAll);
  zoomOutButton.addEventListener("click", () => stepZoom(0.8));
  zoomInButton.addEventListener("click", () => stepZoom(1.25));
  fitButton.addEventListener("click", () => { zoom = "fit"; applyZoom(); });
  oneToOneButton.addEventListener("click", () => { zoom = 1; applyZoom(); });
  cancelButton.addEventListener("click", () => { stopStream(true); finaliseTranslation("已取消"); });
  sourceSelect.addEventListener("change", languageChanged);
  targetSelect.addEventListener("change", languageChanged);
  stage.addEventListener("click", onStageClick);
  stage.addEventListener("wheel", onStageWheel, { passive: false });
  stage.addEventListener("dblclick", onStageDoubleClick);
  stage.addEventListener("pointerdown", onStagePointerDown);
  stage.addEventListener("pointermove", onStagePointerMove);
  stage.addEventListener("pointerup", onStagePointerUp);
  stage.addEventListener("pointercancel", onStagePointerUp);
  window.addEventListener("keydown", onKeyDown);

  let observer = null;
  try {
    observer = new ResizeObserver(() => {
      if (zoom === "fit") applyZoom();
      else scheduleFitCards();
    });
    observer.observe(stage);
  } catch {
    observer = null;
  }

  updateOriginalButton();
  showLoading("正在准备截图…");

  const view = {
    el,
    async start() {
      await waitForImage(image);
      if (destroyed) return;
      imageWidth = image.naturalWidth || imageWidth;
      imageHeight = image.naturalHeight || imageHeight;
      applyZoom();
      hideLoading();
      await runOcr();
    },
    cleanup() {
      destroyed = true;
      if (fitFrame) cancelAnimationFrame(fitFrame);
      ocrAborter?.abort();
      stopStream(false);
      observer?.disconnect();
      window.removeEventListener("keydown", onKeyDown);
      stage.removeEventListener("wheel", onStageWheel);
      stage.removeEventListener("dblclick", onStageDoubleClick);
      stage.removeEventListener("pointerdown", onStagePointerDown);
      stage.removeEventListener("pointermove", onStagePointerMove);
      stage.removeEventListener("pointerup", onStagePointerUp);
      stage.removeEventListener("pointercancel", onStagePointerUp);
    },
  };
  return view;
}
