import { api } from "../api.js";
import {
  h, clear, selectOption, toast, confirmDialog, formatBytes, debounce,
} from "../dom.js";
import { icon } from "../icons.js";

const DEVICES = [
  { value: "auto", label: "自动（推荐）" },
  { value: "NPU", label: "NPU（低功耗）" },
  { value: "GPU", label: "GPU（iGPU）" },
  { value: "CPU", label: "CPU" },
];
const SPLIT_MODES = [
  { value: "auto", label: "自动" },
  { value: "paragraph", label: "按段落" },
  { value: "line", label: "按行（UI 文案）" },
];
const TARGETS = [
  { value: "zh", label: "中文" },
  { value: "ja", label: "日语" },
  { value: "en", label: "英语" },
];

function statusIcon(status) {
  return icon(status === "ok" ? "check" : status === "warn" ? "alert" : "x", 16);
}

export function render(ctx) {
  const { store } = ctx;
  let models = [...store.models];
  let tmStats = { entries: 0, hits: 0 };
  let doctor = null;
  let doctorBusy = false;
  let loadingProfile = "";
  let saveTimer = 0;
  let statusTimer = 0;

  const modelList = h("div", { class: "page-stack", style: "gap:10px" });
  const doctorBox = h("div", { class: "check-list" });
  const systemBox = h("div", { class: "grid-2" });
  const tmLine = h("div", { class: "hint" });
  const saveHint = h("span", { class: "hint", text: "修改会自动保存" });

  const deviceSelect = h("select");
  for (const item of DEVICES) deviceSelect.appendChild(selectOption(item.value, item.label));
  deviceSelect.value = store.settings.device || "auto";

  const splitSelect = h("select");
  for (const item of SPLIT_MODES) splitSelect.appendChild(selectOption(item.value, item.label));
  splitSelect.value = store.settings.split_mode || "auto";

  const preloadCheck = h("input", { type: "checkbox", checked: store.settings.preload_model !== false });
  const selectionCheck = h("input", {
    type: "checkbox",
    checked: store.settings.selection_translate === true,
  });
  const selectionTarget = h("select");
  for (const item of TARGETS) selectionTarget.appendChild(selectOption(item.value, item.label));
  selectionTarget.value = store.settings.target_lang || "zh";
  const selectionStatus = h("div", { class: "hint", text: "正在检查桌面划译组件…" });

  const temperature = h("input", { type: "number", min: "0", max: "2", step: "0.1",
    value: String(store.settings.temperature ?? 0), style: "height:32px" });
  const topP = h("input", { type: "number", min: "0.05", max: "1", step: "0.05",
    value: String(store.settings.top_p ?? 1), style: "height:32px" });
  const topK = h("input", { type: "number", min: "0", max: "100", step: "1",
    value: String(store.settings.top_k ?? 0), style: "height:32px" });
  const repetition = h("input", { type: "number", min: "0.5", max: "2", step: "0.05",
    value: String(store.settings.repetition_penalty ?? 1.05), style: "height:32px" });
  const maxTokens = h("input", { type: "number", min: "64", max: "4096", step: "64",
    value: String(store.settings.max_new_tokens ?? 4096), style: "height:32px" });

  function setSaved(text = "已保存") {
    saveHint.textContent = text;
    window.clearTimeout(saveTimer);
    saveTimer = window.setTimeout(() => { saveHint.textContent = "修改会自动保存"; }, 2200);
  }

  const saveSettings = debounce(async (patch) => {
    try {
      const updated = await api.put("/api/settings", patch);
      store.settings = updated;
      setSaved();
    } catch (error) {
      toast(error.message, "error");
    }
  }, 220);

  function updateDeviceAvailability() {
    const active = models.find((item) => item.profile_id === (store.settings.profile_id || "balanced"));
    const quality = active?.profile_id === "quality";
    for (const option of deviceSelect.options) {
      option.disabled = quality && option.value === "NPU";
    }
    if (quality && deviceSelect.value === "NPU") deviceSelect.value = "auto";
  }

  function modelCard(model) {
    const active = model.profile_id === (store.settings.profile_id || "balanced");
    const loaded = model.loaded;
    const actions = h("div", { class: "model-actions" });
    if (model.installed) {
      if (!active) {
        actions.appendChild(h("button", {
          class: "secondary small",
          text: "设为当前",
          on: { click: () => activate(model) },
        }));
      }
      actions.appendChild(h("button", {
        class: loaded ? "ghost small" : "primary small",
        text: loaded ? "已加载" : (loadingProfile === model.profile_id ? "加载中…" : "加载测试"),
        disabled: loaded || loadingProfile === model.profile_id,
        on: { click: () => load(model) },
      }));
      actions.appendChild(h("button", {
        class: "ghost small",
        on: {
          click: async () => {
            try {
              await api.post(`/api/models/${model.profile_id}/open-folder`);
            } catch (error) {
              toast(error.message, "error");
            }
          },
        },
      }, [icon("folder", 14), h("span", { text: "目录" })]));
    } else {
      actions.appendChild(h("button", {
        class: "secondary small",
        text: "查看说明",
        on: {
          click: () => toast("请运行“准备模型.bat”，或把现成的模型文件夹复制到 models 目录后点“重新扫描”。", "info", 6500),
        },
      }));
    }

    const variants = Object.keys(model.variants || {});
    return h("div", { class: `model-card${active ? " active" : ""}` }, [
      h("div", {}, [
        h("h3", {}, [
          model.name,
          active ? h("span", { class: "badge ok", style: "margin-left:8px", text: "当前" }) : null,
        ]),
        h("p", { text: model.description || "" }),
        h("div", { class: "model-meta" }, [
          h("span", { class: `badge ${model.installed ? "ok" : "warn"}`, text: model.installed ? "已安装" : "未安装" }),
          h("span", { class: "badge", text: model.license || "Apache-2.0" }),
          model.size_bytes ? h("span", { class: "badge", text: formatBytes(model.size_bytes) }) : null,
          ...variants.map((variant) => h("span", { class: "badge", text: variant === "npu" ? "NPU 变体" : "GPU/CPU 变体" })),
          model.error && !model.installed && model.error !== "未安装"
            ? h("span", { class: "badge err", text: model.error }) : null,
        ]),
      ]),
      actions,
    ]);
  }

  function renderModels() {
    clear(modelList);
    for (const model of models) modelList.appendChild(modelCard(model));
    if (!models.length) {
      modelList.appendChild(h("div", { class: "warn-tip", text: "没有读取到模型配置，请检查 models 目录。" }));
    }
    modelList.appendChild(h("div", { class: "row between", style: "margin-top:2px" }, [
      h("span", { class: "hint", text: `模型目录：${store.system?.paths?.models || "models"}` }),
      h("button", {
        class: "ghost small",
        on: {
          click: async () => {
            try {
              await api.post("/api/models/scan");
              await ctx.reload(true);
              toast("已重新扫描模型目录", "success", 1800);
            } catch (error) {
              toast(error.message, "error");
            }
          },
        },
      }, [icon("refresh", 14), h("span", { text: "重新扫描" })]),
    ]));
  }

  async function activate(model) {
    try {
      await api.post(`/api/models/${model.profile_id}/activate`);
      toast(`已切换到 ${model.name}`, "success", 1800);
      await ctx.reload(true);
    } catch (error) {
      toast(error.message, "error");
    }
  }

  async function load(model) {
    if (loadingProfile) return;
    loadingProfile = model.profile_id;
    renderModels();
    try {
      const result = await api.post(
        `/api/models/${model.profile_id}/load?device=${encodeURIComponent(deviceSelect.value)}`,
      );
      toast(result.warning || `已加载到 ${result.device}`, result.warning ? "warn" : "success", 4200);
      await ctx.reload(true);
    } catch (error) {
      toast(error.message, "error", 6000);
    } finally {
      loadingProfile = "";
      if (document.body.contains(modelList)) renderModels();
    }
  }

  function renderSystem() {
    clear(systemBox);
    const system = store.system || {};
    const ov = system.openvino || {};
    const engine = store.engine || {};
    const items = [
      ["OpenVINO", ov.runtime || "未加载"],
      ["OpenVINO GenAI", ov.genai || "未加载"],
      ["NPU 驱动", ov.npu_driver || "未读取"],
      ["设备", (ov.devices || []).map((device) => `${device.id}: ${device.name}`).join(" · ") || "未检测"],
      ["数据目录", system.paths?.data || ""],
      ["模型目录", system.paths?.models || ""],
      ["WebView2", system.webview2 ? "已安装" : "未检测到（回退浏览器）"],
      ["数据库", system.db?.integrity === "ok" ? "完整" : (system.db?.integrity || "未知")],
      ["磁盘可用", system.disk_free_gb ? `${system.disk_free_gb} GB` : ""],
      ["引擎状态", engine.state === "ready"
        ? `${engine.device} · ${engine.model_name}`
        : (engine.last_error || engine.state || "idle")],
    ];
    for (const [name, value] of items) {
      systemBox.appendChild(h("div", { class: "field" }, [
        h("label", { text: name }),
        h("div", { class: "hint", style: "word-break:break-word", text: value || "—" }),
      ]));
    }
  }

  function renderDoctor(result) {
    clear(doctorBox);
    if (!result) {
      doctorBox.appendChild(h("div", { class: "hint", text: "运行诊断会检查 NPU 驱动、模型文件、数据库和磁盘。" }));
      return;
    }
    const overall = result.overall;
    doctorBox.appendChild(h("div", {
      class: overall === "ok" ? "tip" : overall === "warn" ? "warn-tip" : "error-box",
      text: overall === "ok" ? "所有关键项通过。" : overall === "warn" ? "有需要留意的项目。" : "存在阻塞项，请处理后再翻译。",
    }));
    for (const check of result.checks || []) {
      const row = h("div", { class: `check-row ${check.status}` });
      row.appendChild(h("span", { class: "ci" }, statusIcon(check.status)));
      row.appendChild(h("span", { class: "cn", text: check.name }));
      row.appendChild(h("span", { class: "cd", text: check.detail || "" }));
      doctorBox.appendChild(row);
    }
  }

  async function runDoctor() {
    if (doctorBusy) return;
    doctorBusy = true;
    clear(doctorBox);
    doctorBox.appendChild(h("div", { class: "loading-line" }, [h("span", { class: "spin" }), "正在检查…"]));
    try {
      doctor = await api.post("/api/system/doctor");
      renderDoctor(doctor);
      store.doctor = doctor;
    } catch (error) {
      clear(doctorBox);
      doctorBox.appendChild(h("div", { class: "error-box", text: error.message }));
    } finally {
      doctorBusy = false;
    }
  }

  async function loadTm() {
    try {
      tmStats = await api.get("/api/system/tm");
      tmLine.textContent = `翻译记忆：${tmStats.entries} 条，累计命中 ${tmStats.hits} 次。`;
    } catch {
      tmLine.textContent = "翻译记忆统计不可用。";
    }
  }

  const el = h("div", { class: "page-stack" }, [
    h("section", { class: "section-card" }, [
      h("div", { class: "card-head" }, [
        h("div", {}, [
          h("h2", { text: "模型" }),
          h("p", { text: "1.8B 适合日常与 NPU；7B 质量更高，建议 GPU/CPU。" }),
        ]),
        h("div", { class: "hint", text: "模型文件不随安装包分发" }),
      ]),
      h("div", { class: "card-body" }, modelList),
    ]),

    h("section", { class: "section-card" }, [
      h("div", { class: "card-head" }, [
        h("div", {}, [
          h("h2", { text: "划译" }),
          h("p", { text: "选中文字后在选区上方显示翻译；关闭主窗口后仍在托盘运行。" }),
        ]),
        h("span", { class: "badge", text: "桌面" }),
      ]),
      h("div", { class: "card-body" }, [
        h("label", { class: "checkline" }, selectionCheck, "开启划译（选中文字自动翻译）"),
        h("div", { class: "grid-2", style: "margin-top:12px" }, [
          h("div", { class: "field" }, [
            h("label", { text: "划译目标语言" }),
            selectionTarget,
          ]),
          h("div", { class: "field" }, [
            h("label", { text: "模型与设备" }),
            h("div", { class: "hint", text: "沿用当前选择的模型和推理设备，不会另起模型。" }),
          ]),
        ]),
        h("div", { class: "hint", style: "margin-top:10px" },
          "源语言自动检测；单次最多 4000 字；需要目标应用支持 Windows UI Automation。"),
        selectionStatus,
      ]),
    ]),

    h("section", { class: "section-card" }, [
      h("div", { class: "card-head" }, [
        h("div", {}, [h("h2", { text: "推理与生成参数" }), h("p", { text: "设备在下次加载时生效；NPU 仅支持 1.8B。" })]),
        saveHint,
      ]),
      h("div", { class: "card-body" }, [
        h("div", { class: "grid-2" }, [
          h("div", { class: "field" }, [h("label", { text: "推理设备" }), deviceSelect]),
          h("div", { class: "field" }, [h("label", { text: "分段方式" }), splitSelect]),
        ]),
        h("div", { class: "row", style: "margin-top:12px" }, [
          h("label", { class: "checkline" }, preloadCheck, "启动时预加载模型（NPU 首次编译会较慢）"),
        ]),
        h("div", { class: "divider-line" }),
        h("div", { class: "grid-3" }, [
          h("div", { class: "field" }, [h("label", { text: "temperature（0 = 贪心）" }), temperature]),
          h("div", { class: "field" }, [h("label", { text: "top_p" }), topP]),
          h("div", { class: "field" }, [h("label", { text: "top_k" }), topK]),
          h("div", { class: "field" }, [h("label", { text: "repetition_penalty" }), repetition]),
          h("div", { class: "field" }, [h("label", { text: "max_new_tokens" }), maxTokens]),
        ]),
        h("div", { class: "row", style: "margin-top:10px" }, [
          h("button", {
            class: "secondary small",
            text: "稳定贪心",
            on: {
              click: () => {
                temperature.value = "0";
                topP.value = "1";
                topK.value = "0";
                repetition.value = "1.05";
                saveSettings({ temperature: 0, top_p: 1, top_k: 0, repetition_penalty: 1.05 });
              },
            },
          }),
          h("button", {
            class: "secondary small",
            text: "官方采样",
            on: {
              click: () => {
                temperature.value = "0.7";
                topP.value = "0.6";
                topK.value = "20";
                repetition.value = "1.05";
                saveSettings({ temperature: 0.7, top_p: 0.6, top_k: 20, repetition_penalty: 1.05 });
              },
            },
          }),
          h("span", { class: "hint", text: "稳定贪心更适合术语一致性；官方采样更自然但结果有随机性。" }),
        ]),
      ]),
    ]),

    h("section", { class: "section-card" }, [
      h("div", { class: "card-head" }, [
        h("div", {}, [h("h2", { text: "诊断" }), h("p", { text: "检查设备、模型、数据库和目录权限。" })]),
        h("div", { class: "row" }, [
          h("button", { class: "secondary small", on: { click: runDoctor } }, [
            icon("cpu", 14), h("span", { text: "运行诊断" }),
          ]),
          h("button", {
            class: "ghost small",
            text: "复制信息",
            on: {
              click: async () => {
                const payload = JSON.stringify({ system: store.system, doctor }, null, 2);
                try {
                  await navigator.clipboard.writeText(payload);
                  toast("诊断信息已复制", "success", 1800);
                } catch {
                  toast("复制失败，请手动查看日志", "error");
                }
              },
            },
          }),
        ]),
      ]),
      h("div", { class: "card-body" }, [
        doctorBox,
        h("div", { class: "divider-line" }),
        systemBox,
      ]),
    ]),

    h("section", { class: "section-card" }, [
      h("div", { class: "card-head" }, [
        h("div", {}, [h("h2", { text: "数据与隐私" }), h("p", { text: "原文、译文、术语和历史只保存在本机。" })]),
      ]),
      h("div", { class: "card-body" }, [
        tmLine,
        h("div", { class: "row", style: "margin-top:10px" }, [
          h("button", {
            class: "secondary small",
            text: "清空翻译记忆",
            on: {
              click: async () => {
                if (!(await confirmDialog("清空翻译记忆", "清空后相同句子会重新调用模型。", { confirmLabel: "清空" }))) return;
                try {
                  await api.delete("/api/system/tm");
                  await loadTm();
                  toast("翻译记忆已清空", "success", 1800);
                } catch (error) {
                  toast(error.message, "error");
                }
              },
            },
          }),
          h("button", {
            class: "danger small",
            text: "清空历史记录",
            on: {
              click: async () => {
                if (!(await confirmDialog("清空历史记录", "确定删除所有历史记录吗？此操作不可撤销。", { danger: true, confirmLabel: "清空" }))) return;
                try {
                  await api.delete("/api/history");
                  toast("历史记录已清空", "success", 1800);
                } catch (error) {
                  toast(error.message, "error");
                }
              },
            },
          }),
          h("span", { class: "hint", text: `数据目录：${store.system?.paths?.data || ""}` }),
        ]),
      ]),
    ]),

    h("section", { class: "section-card" }, [
      h("div", { class: "card-head" }, [
        h("div", {}, [h("h2", { text: "关于" }), h("p", { text: "本地离线翻译，不上传任何文本。" })]),
        h("span", { class: "badge", text: `v${document.querySelector('meta[name="zc-version"]')?.content || ""}` }),
      ]),
      h("div", { class: "card-body" }, [
        h("div", { class: "grid-2" }, [
          h("div", { class: "field" }, [
            h("label", { text: "翻译模型" }),
            h("div", { class: "hint", text: "腾讯混元 Hy-MT2 1.8B / 7B，Apache-2.0。本应用不修改模型权重。" }),
          ]),
          h("div", { class: "field" }, [
            h("label", { text: "推理与界面" }),
            h("div", { class: "hint", text: "OpenVINO 2026.4 · FastAPI · pywebview · 原生前端。无 CDN、无遥测、无自动更新。" }),
          ]),
        ]),
        h("div", { class: "divider-line" }),
        h("div", { class: "hint", text: "准确率取决于原文、领域和模型档位；法律、文学等场景建议人工审校。" }),
      ]),
    ]),
  ]);

  deviceSelect.addEventListener("change", () => {
    if (deviceSelect.value === "NPU" && (store.settings.profile_id || "balanced") === "quality") {
      toast("7B 不建议在 NPU 上运行", "warn");
      deviceSelect.value = "auto";
      return;
    }
    saveSettings({ device: deviceSelect.value });
  });
  splitSelect.addEventListener("change", () => saveSettings({ split_mode: splitSelect.value }));
  preloadCheck.addEventListener("change", () => saveSettings({ preload_model: preloadCheck.checked }));
  temperature.addEventListener("change", () => saveSettings({ temperature: Number(temperature.value) || 0 }));
  topP.addEventListener("change", () => saveSettings({ top_p: Math.min(1, Math.max(0.05, Number(topP.value) || 1)) }));
  topK.addEventListener("change", () => saveSettings({ top_k: Math.max(0, Math.round(Number(topK.value) || 0)) }));
  repetition.addEventListener("change", () => saveSettings({ repetition_penalty: Math.max(0.5, Math.min(2, Number(repetition.value) || 1.05)) }));
  maxTokens.addEventListener("change", () => saveSettings({ max_new_tokens: Math.max(64, Math.min(4096, Math.round(Number(maxTokens.value) || 4096))) }));

  selectionCheck.addEventListener("change", () => {
    saveSettings({ selection_translate: selectionCheck.checked });
    if (!selectionCheck.checked) {
      const app = window.pywebview?.api;
      if (app && typeof app.overlay_hide === "function") {
        Promise.resolve(app.overlay_hide()).catch(() => {});
      }
    }
    toast(selectionCheck.checked ? "已开启划译" : "已关闭划译", "info", 1800);
  });
  selectionTarget.addEventListener("change", () => saveSettings({ target_lang: selectionTarget.value }));

  function loadSelectionStatus(retry = true) {
    const app = window.pywebview?.api;
    if (!app || typeof app.selection_status !== "function") {
      selectionStatus.textContent = "浏览器模式下不可用；请使用桌面窗口。";
      return;
    }
    Promise.resolve(app.selection_status()).then((status) => {
      const available = Boolean(status?.available);
      selectionStatus.textContent = available
        ? "桌面划译组件可用。"
        : `桌面划译组件：${status?.detail || "正在初始化…"}`;
      if (!available && retry && /初始化|启动/.test(status?.detail || "")) {
        window.clearTimeout(statusTimer);
        statusTimer = window.setTimeout(() => loadSelectionStatus(false), 2500);
      }
    }).catch(() => {
      selectionStatus.textContent = "无法读取桌面划译组件状态。";
    });
  }

  updateDeviceAvailability();
  renderModels();
  renderSystem();
  renderDoctor(null);
  loadTm();
  loadSelectionStatus();

  return {
    el,
    cleanup() {
      window.clearTimeout(saveTimer);
      window.clearTimeout(statusTimer);
    },
  };
}
