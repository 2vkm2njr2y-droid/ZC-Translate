function formatElapsed(ms) {
  const total = Math.max(0, Math.round(Number(ms || 0) / 1000));
  const minutes = Math.floor(total / 60).toString().padStart(2, "0");
  const seconds = (total % 60).toString().padStart(2, "0");
  return `${minutes}:${seconds}`;
}

function languageLabel(value) {
  return ({ zh: "中文", ja: "日语", en: "英语" })[value] || "自动";
}

export function createVoiceController(options) {
  const {
    api,
    store,
    toast,
    textArea,
    resultEl,
    resultTextEl,
    resultStatusEl,
    resultMetaEl,
    conversationButton,
    inputButton,
    downloadButton,
    stateEl,
    getSource,
    getTarget,
    getStyle,
    getGlossary,
    getSettings,
    showResult,
    updateCount,
    saveDraft,
    resetResult,
    setVoiceBusy,
    isTextBusy,
  } = options;

  let model = null;
  let sessionId = "";
  let mode = "";
  let since = 0;
  let pollTimer = 0;
  let stopping = false;
  let active = false;
  let translationChain = Promise.resolve();
  let inputPrefix = "";
  let partialRow = null;

  function renderInputTranscript(transcript, partial = "") {
    const committed = String(transcript || "").trim();
    const preview = String(partial || "").trim();
    const recognized = [committed, preview].filter(Boolean).join("\n");
    if (!recognized && !inputPrefix) return;
    const separator = inputPrefix && !inputPrefix.endsWith("\n") ? "\n" : "";
    textArea.value = recognized ? `${inputPrefix}${separator}${recognized}` : inputPrefix;
    updateCount();
    saveDraft();
  }

  function setState(text, kind = "") {
    stateEl.textContent = text;
    stateEl.className = `compact-voice-state ${kind}`;
  }

  function updateButtons() {
    const ready = Boolean(model?.ready);
    const downloading = model?.download?.state === "downloading";
    conversationButton.disabled = active ? mode !== "conversation" : !ready;
    inputButton.disabled = active ? mode !== "input" : !ready;
    downloadButton.classList.toggle("hidden", ready && !downloading);
    downloadButton.disabled = downloading;
    conversationButton.textContent = active && mode === "conversation" ? "结束对话" : "语音对话";
    inputButton.textContent = active && mode === "input" ? "停止录音" : "语音输入";
  }

  async function refreshModel() {
    try {
      model = await api.speechStatus();
      if (model.ready) {
        setState("语音已就绪 · 停顿约 2.5 秒分句", "ok");
      } else if (model.download?.state === "downloading") {
        setState(`${model.download.message || "正在下载语音模型…"} ${model.download.progress || 0}%`, "busy");
      } else if (!model.installed) {
        setState("首次使用请下载语音模型", "warn");
      } else {
        setState("语音依赖未安装", "warn");
      }
      updateButtons();
    } catch (error) {
      setState("无法检查语音模型", "error");
      toast(error.message, "error");
    }
    return model;
  }

  async function downloadModel() {
    if (model?.download?.state === "downloading") return;
    try {
      await api.speechDownload();
      setState("正在准备语音模型…", "busy");
      updateButtons();
      const poll = async () => {
        await refreshModel();
        if (model?.download?.state === "downloading") {
          window.setTimeout(poll, 700);
        } else if (model?.download?.state === "error") {
          toast(model.download.error || "语音模型下载失败", "error", 6000);
        }
      };
      window.setTimeout(poll, 400);
    } catch (error) {
      toast(error.message, "error", 6000);
    }
  }

  function appendConversationRow(segment) {
    partialRow?.remove();
    partialRow = null;
    showResult();
    const row = document.createElement("article");
    row.className = "voice-conversation-row";
    row.dataset.seq = String(segment.seq);
    const head = document.createElement("div");
    head.className = "voice-conversation-head";
    const time = document.createElement("span");
    time.textContent = segment.time || formatElapsed(segment.timestamp);
    const lang = document.createElement("span");
    lang.textContent = languageLabel(segment.lang);
    head.append(time, lang);
    const source = document.createElement("div");
    source.className = "voice-conversation-source";
    source.textContent = segment.text;
    const target = document.createElement("div");
    target.className = "voice-conversation-target";
    target.textContent = "翻译中…";
    row.append(head, source, target);
    resultTextEl.appendChild(row);
    resultTextEl.scrollTop = resultTextEl.scrollHeight;
    return target;
  }

  function renderConversationPartial(text) {
    const value = String(text || "").trim();
    if (!value) {
      partialRow?.remove();
      partialRow = null;
      return;
    }
    showResult();
    if (!partialRow) {
      partialRow = document.createElement("article");
      partialRow.className = "voice-conversation-row voice-conversation-partial";
      const source = document.createElement("div");
      source.className = "voice-conversation-source";
      partialRow.appendChild(source);
      resultTextEl.appendChild(partialRow);
    }
    partialRow.firstElementChild.textContent = value;
    resultTextEl.scrollTop = resultTextEl.scrollHeight;
  }

  function translateSegment(segment) {
    const targetEl = appendConversationRow(segment);
    translationChain = translationChain.then(async () => {
      try {
        const settings = getSettings() || {};
        const result = await api.post("/api/translate", {
          text: segment.text,
          source_lang: getSource() || "auto",
          target_lang: getTarget() || "zh",
          profile_id: settings.profile_id || "balanced",
          device: settings.device || "auto",
          glossary_id: getGlossary() || null,
          style: getStyle() || "default",
          use_tm: settings.use_tm !== false,
          use_context: false,
          split_mode: "auto",
        });
        targetEl.textContent = result.text || "（没有译文）";
        resultStatusEl.textContent = "对话翻译进行中";
      } catch (error) {
        targetEl.textContent = `翻译失败：${error.message}`;
        targetEl.classList.add("error");
      }
    });
  }

  function finish(data) {
    active = false;
    sessionId = "";
    mode = "";
    inputPrefix = "";
    partialRow?.remove();
    partialRow = null;
    since = 0;
    stopping = false;
    if (pollTimer) window.clearTimeout(pollTimer);
    pollTimer = 0;
    setVoiceBusy(false);
    updateButtons();
    if (data?.error) {
      setState(data.error, "error");
      toast(data.error, "error", 6000);
    } else if (data?.mode === "input") {
      setState("语音已转成文字，请点击翻译", "ok");
    } else {
      setState("对话已结束", "ok");
    }
  }

  async function pollSession() {
    if (!active || !sessionId) return;
    try {
      const data = await api.speechSessionStatus(sessionId, since);
      for (const segment of data.segments || []) {
        since = Math.max(since, Number(segment.seq || 0));
        if (mode === "conversation") translateSegment(segment);
      }
      if (mode === "input") renderInputTranscript(data.transcript, data.partial_text);
      else if (mode === "conversation") renderConversationPartial(data.partial_text);
      if (data.state === "error") {
        finish(data);
        return;
      }
      if (mode === "input") {
        if (data.state === "processing") setState("正在整理语音文字…", "busy");
        else if (data.state === "recording") {
          setState(
            data.partial_text || `录音中 ${formatElapsed(data.audio_seconds * 1000)} · 正在识别`,
            "busy",
          );
        }
        if (data.state === "done") {
          renderInputTranscript(data.transcript, data.partial_text);
          resetResult();
          finish(data);
          toast(data.transcript ? "语音已填入原文框，请点击翻译" : "没有识别到语音", data.transcript ? "success" : "warn", 4000);
          return;
        }
      } else if (data.state === "recording") {
        setState(data.partial_text || data.partial || "正在等待说话…", "busy");
      }
      if (data.state === "done" && mode === "conversation") {
        await translationChain;
        finish(data);
        return;
      }
      pollTimer = window.setTimeout(pollSession, 450);
    } catch (error) {
      finish({ error: error.message });
    }
  }

  async function startSession(nextMode) {
    if (active) {
      if (mode === nextMode) return stopSession();
      toast("请先结束当前语音模式", "warn");
      return;
    }
    if (!model?.ready) {
      toast("请先下载语音模型", "warn");
      return;
    }
    if (isTextBusy?.()) {
      toast("请先完成或停止当前文字翻译", "warn");
      return;
    }
    try {
      const data = await api.speechStart(nextMode);
      active = true;
      sessionId = data.session_id;
      mode = nextMode;
      since = 0;
      stopping = false;
      translationChain = Promise.resolve();
      setVoiceBusy(true);
      if (nextMode === "conversation") {
        resultTextEl.replaceChildren();
        resultMetaEl.textContent = "原文与译文会按时间顺序显示";
        resultStatusEl.textContent = "等待说话…";
        showResult();
        setState("对话已开始 · 停顿不会结束对话", "busy");
      } else {
        resultStatusEl.textContent = "识别到一句就会显示在原文框";
        inputPrefix = textArea.value.trimEnd();
        setState("录音中 · 停顿后实时显示", "busy");
      }
      updateButtons();
      pollSession();
    } catch (error) {
      toast(error.message, "error", 6000);
    }
  }

  async function stopSession() {
    if (!active || !sessionId || stopping) return;
    stopping = true;
    setState(mode === "input" ? "正在停止并识别…" : "正在结束最后一句…", "busy");
    try {
      await api.speechStop(sessionId);
    } catch (error) {
      finish({ error: error.message });
    }
  }

  function clearConversation() {
    if (resultTextEl.querySelector(".voice-conversation-row")) resultTextEl.replaceChildren();
  }

  conversationButton.addEventListener("click", () => startSession("conversation"));
  inputButton.addEventListener("click", () => startSession("input"));
  downloadButton.addEventListener("click", downloadModel);
  refreshModel();

  return {
    active: () => active,
    clearConversation,
    cleanup() {
      if (active) {
        api.speechStop(sessionId).catch(() => {});
      }
      if (pollTimer) window.clearTimeout(pollTimer);
    },
  };
}
