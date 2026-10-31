import { h, spinner, toast } from "../dom.js";
import { icon } from "../icons.js";

function toBase64(fileOrBlob) {
  if (fileOrBlob?.contentBase64) return Promise.resolve(fileOrBlob.contentBase64);
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(",", 2)[1] || "");
    reader.onerror = () => reject(reader.error || new Error("读取文件失败"));
    reader.readAsDataURL(fileOrBlob);
  });
}

function saveBase64(name, encoded) {
  const bytes = Uint8Array.from(atob(encoded), (char) => char.charCodeAt(0));
  const suffix = String(name || "").toLowerCase().split(".").pop();
  const mime = suffix === "pdf" ? "application/pdf"
    : suffix === "docx" ? "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
      : "text/plain;charset=utf-8";
  const blob = new Blob([bytes], { type: mime });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url; link.download = name; document.body.appendChild(link); link.click(); link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function languageSelect(value = "zh") {
  const select = h("select", { class: "doc-select" });
  [["zh", "中文"], ["ja", "日语"], ["en", "英语"]].forEach(([id, label]) => {
    const option = h("option", { value: id, text: label });
    option.selected = id === value;
    select.appendChild(option);
  });
  return select;
}

function formatDuration(ms) {
  const total = Math.max(0, Math.round((Number(ms) || 0) / 1000));
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

const IMAGE_EXTENSIONS = ["png", "jpg", "jpeg", "bmp", "webp", "gif"];
const DOCUMENT_EXTENSIONS = ["txt", "md", "pdf", "docx"];
const LONG_DOC_CHARS = 100_000;

export function render(ctx) {
  const { api } = ctx;
  const fileInput = h("input", { type: "file", attrs: { accept: "image/*,.pdf,.txt,.md,.docx" } });
  fileInput.className = "hidden";
  const result = h("pre", { class: "ocr-result scroll-thin", text: "识别后的文字会显示在这里。" });
  const nameEl = h("div", { class: "doc-file-name", text: "尚未选择文件" });
  const progress = h("div", { class: "doc-progress hint", text: "" });
  const progressFill = h("i");
  const progressBar = h("div", { class: "doc-progressbar hidden" }, progressFill);
  const target = languageSelect(ctx.store.settings.target_lang || "zh");
  const selectButton = h("button", { class: "secondary", on: { click: () => chooseFile() } }, [icon("folder", 15), " 选择文件"]);
  const imageTranslateButton = h("button", { class: "primary", disabled: true, on: { click: () => translateImage() } }, [icon("camera", 15), " 图片翻译"]);
  const ocrButton = h("button", { class: "secondary", disabled: true, on: { click: () => runOCR() } }, [icon("spark", 15), " OCR 识别"]);
  const translateButton = h("button", { class: "primary", disabled: true, on: { click: () => translateDocument() } }, [icon("translate", 15), " 翻译并生成文件"]);
  const cancelButton = h("button", {
    class: "secondary hidden",
    attrs: { type: "button" },
    on: { click: () => cancelTranslation() },
  }, [icon("x", 14), " 取消翻译"]);
  let selectedFile = null;
  let running = false;
  let aborter = null;
  let jobId = "";

  function extension() {
    return String(selectedFile?.name || "").toLowerCase().split(".").pop();
  }

  function isImage() {
    return Boolean(selectedFile && (selectedFile.type || "").startsWith("image/"))
      || IMAGE_EXTENSIONS.includes(extension());
  }

  function imageMime() {
    if (selectedFile?.type) return selectedFile.type;
    const ext = extension();
    return ext === "jpg" || ext === "jpeg" ? "image/jpeg" : `image/${ext || "png"}`;
  }

  function updateButtons() {
    const image = isImage();
    const document = DOCUMENT_EXTENSIONS.includes(extension());
    imageTranslateButton.disabled = !image || running;
    ocrButton.disabled = !image || running;
    translateButton.disabled = !document || running;
    selectButton.disabled = running;
    target.disabled = running;
  }

  function currentPayload(contentBase64) {
    return {
      file_name: selectedFile.name,
      source_path: selectedFile.path || "",
      content_base64: contentBase64,
      source_lang: ctx.store.settings.source_lang || "auto",
      target_lang: target.value,
      profile_id: ctx.store.settings.profile_id || "balanced",
      device: ctx.store.settings.device || "auto",
      glossary_id: ctx.store.settings.glossary_id || null,
      style: ctx.store.settings.style || "default",
      use_tm: ctx.store.settings.use_tm !== false,
    };
  }

  async function chooseFile() {
    if (running) return;
    if (window.pywebview?.api?.choose_document) {
      try {
        const picked = await window.pywebview.api.choose_document();
        if (picked) {
          selectedFile = { name: picked.name, path: picked.path, contentBase64: picked.content_base64 };
          nameEl.textContent = selectedFile.name;
          updateButtons();
          progress.textContent = "文件已就绪，可开始处理。";
        }
        return;
      } catch (error) { toast(error.message || "无法打开文件选择器", "error"); }
    }
    fileInput.click();
  }

  async function runOCR() {
    if (!selectedFile || !isImage() || running) return;
    progress.replaceChildren(spinner("正在本地 OCR…"));
    try {
      const data = await api.post("/api/ocr/image", {
        file_name: selectedFile.name,
        content_base64: await toBase64(selectedFile),
      });
      result.textContent = data.text || "未识别到文字";
      progress.textContent = `识别完成：${data.items?.length || 0} 个文字区域`;
    } catch (error) {
      progress.textContent = error.message;
      toast(error.message, "error");
    }
  }

  async function translateImage() {
    if (!selectedFile || !isImage() || running) return;
    if (typeof ctx.openImageTranslation !== "function") {
      toast("图片翻译页面暂不可用，请重启应用后重试。", "error");
      return;
    }
    try {
      progress.replaceChildren(spinner("正在打开图片翻译…"));
      const encoded = await toBase64(selectedFile);
      ctx.openImageTranslation({
        data_url: `data:${imageMime()};base64,${encoded}`,
        width: 0,
        height: 0,
      }, "document");
    } catch (error) {
      progress.textContent = error.message;
      toast(error.message, "error");
    }
  }

  function cancelTranslation() {
    if (!running) return;
    cancelButton.disabled = true;
    progress.textContent = "正在取消…";
    if (aborter) {
      try { aborter.abort(); } catch { /* ignore */ }
    }
    if (jobId) api.cancelJob(jobId);
  }

  async function translateDocxStream() {
    running = true;
    updateButtons();
    cancelButton.classList.remove("hidden");
    cancelButton.disabled = false;
    progressBar.classList.remove("hidden");
    progressFill.style.width = "0%";
    progress.replaceChildren();
    progress.textContent = "正在读取文档…";
    const controller = new AbortController();
    aborter = controller;
    jobId = "";
    let finished = false;

    try {
      const payload = currentPayload(await toBase64(selectedFile));
      await api.documentStream(payload, {
        onOpen: (response) => { jobId = response.headers.get("X-Job-Id") || ""; },
        status: (data) => {
          if (aborter === controller && data.message) progress.textContent = data.message;
        },
        meta: (data) => {
          if (aborter !== controller) return;
          const total = Number(data.total) || 0;
          progressBar.classList.remove("hidden");
          progressFill.style.width = "0%";
          progress.textContent = `已翻译 0/${total} 段（0%）· 已用 00:00`;
          const profile = ctx.store.settings.profile_id || "balanced";
          if (Number(data.chars) > LONG_DOC_CHARS && profile === "quality") {
            toast("本文档较长，7B 可能需要较长时间；可取消后改用 1.8B。", "warn", 6000);
          }
        },
        progress: (data) => {
          if (aborter !== controller) return;
          const total = Number(data.total) || 0;
          const done = Number(data.done) || 0;
          const percent = total ? Math.round((done / total) * 100) : 0;
          progressFill.style.width = `${percent}%`;
          progress.textContent = `已翻译 ${done}/${total} 段（${percent}%）· 已用 ${formatDuration(data.elapsed_ms)}`;
        },
        done: (data) => {
          if (aborter !== controller) return;
          finished = true;
          if (data.cancelled) {
            progressBar.classList.add("hidden");
            progress.textContent = `已取消：已完成 ${data.segments || 0}/${data.total || 0} 段，未生成文件；重试会跳过已完成段落。`;
            toast("已取消文档翻译", "info");
            return;
          }
          progressFill.style.width = "100%";
          if (data.saved_path) {
            progress.textContent = `已保存：${data.saved_path}`;
            toast("文档翻译完成", "success");
          } else if (data.content_base64) {
            saveBase64(data.file_name, data.content_base64);
            progress.textContent = `已生成并下载：${data.file_name}`;
            toast("文档翻译完成", "success");
          } else {
            progress.textContent = "文档翻译完成，但没有收到文件内容。";
            toast("没有收到文件内容", "error");
          }
        },
        error: (data) => {
          if (aborter !== controller) return;
          finished = true;
          progressBar.classList.add("hidden");
          progress.textContent = data.message || "文档翻译失败";
          toast(data.message || "文档翻译失败", "error", 6000);
        },
      }, controller.signal);
      if (!finished && aborter === controller) {
        progressBar.classList.add("hidden");
        progress.textContent = "连接中断，请重试。";
        toast("连接中断，请重试", "error", 6000);
      }
    } catch (error) {
      if (error.name === "AbortError") {
        if (aborter === controller) {
          progressBar.classList.add("hidden");
          progress.textContent = "已取消";
        }
      } else if (aborter === controller) {
        progressBar.classList.add("hidden");
        progress.textContent = error.message || "文档翻译失败";
        toast(error.message || "文档翻译失败", "error", 6000);
      }
    } finally {
      if (aborter === controller) {
        aborter = null;
        jobId = "";
        running = false;
        cancelButton.classList.add("hidden");
        cancelButton.disabled = false;
        updateButtons();
      }
    }
  }

  async function translateOtherDocument() {
    running = true;
    updateButtons();
    progressBar.classList.add("hidden");
    progress.replaceChildren(spinner("正在翻译并生成文件…"));
    try {
      const data = await api.post("/api/document/translate", currentPayload(await toBase64(selectedFile)));
      if (!data.saved_path) saveBase64(data.file_name, data.content_base64);
      progress.textContent = data.saved_path ? `已保存：${data.saved_path}` : `已生成并下载：${data.file_name}`;
      toast("文档翻译完成", "success");
    } catch (error) {
      progress.textContent = error.message;
      toast(error.message, "error");
    } finally {
      running = false;
      updateButtons();
    }
  }

  async function translateDocument() {
    if (!selectedFile || !DOCUMENT_EXTENSIONS.includes(extension()) || running) return;
    if (extension() === "docx") {
      await translateDocxStream();
      return;
    }
    await translateOtherDocument();
  }

  fileInput.addEventListener("change", () => {
    if (running) return;
    selectedFile = fileInput.files?.[0] || null;
    nameEl.textContent = selectedFile ? selectedFile.name : "尚未选择文件";
    updateButtons();
    progress.textContent = selectedFile ? "文件已就绪，可开始处理。" : "";
  });

  const el = h("div", { class: "document-page" }, [
    h("div", { class: "document-hero" }, [
      h("div", { class: "hero-icon" }, icon("file", 24)),
      h("div", {}, [h("h2", { text: "图片与文档翻译" }), h("p", { class: "hint", text: "图片会在原图上覆盖译文；纯文本、PDF、Word 会在原文件夹生成“原文件名_翻译”。" })]),
    ]),
    h("div", { class: "document-toolbar" }, [
      selectButton, imageTranslateButton, ocrButton, translateButton, cancelButton,
      h("span", { class: "toolbar-label", text: "目标语言" }), target,
    ]),
    h("div", { class: "document-file-card" }, [icon("file", 18), nameEl, h("span", { class: "hint", text: "支持图片 / TXT / MD / PDF / DOCX" })]),
    h("div", { class: "hint", text: "长文档（DOCX）会显示进度，可随时取消；1.8B 更快，7B 更准但更慢。" }),
    progressBar,
    progress,
    h("div", { class: "ocr-panel" }, [h("div", { class: "panel-title", text: "识别文本预览" }), result]),
    fileInput,
  ]);
  return { el };
}
