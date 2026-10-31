import { api } from "../api.js";
import {
  h, clear, selectOption, toast, confirmDialog, modal,
} from "../dom.js";
import { icon } from "../icons.js";

const LANGS = [
  { value: "zh", label: "中文" },
  { value: "ja", label: "日语" },
  { value: "en", label: "英语" },
];

function langLabel(value) {
  return LANGS.find((item) => item.value === value)?.label || value;
}

function downloadBlob(filename, blob) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function render(ctx) {
  const { store } = ctx;
  let glossaries = [...store.glossaries];
  let selectedId = localStorage.getItem("zc.glossary.selected") || "";
  let terms = [];
  let search = "";
  let editingTerm = null;
  let busy = false;

  if (!glossaries.find((item) => item.id === selectedId)) {
    selectedId = glossaries[0]?.id || "";
  }

  const listEl = h("div", { class: "glossary-list" });
  const detailEl = h("div", { class: "card-body", style: "padding:14px" });
  const searchInput = h("input", {
    type: "search",
    attrs: { placeholder: "搜索术语…", "aria-label": "搜索术语" },
    style: "height:32px;min-width:180px",
  });
  const importButton = h("button", { class: "ghost small" }, [
    icon("upload", 14), h("span", { text: "导入 CSV" }),
  ]);
  const exportButton = h("button", { class: "ghost small" }, [
    icon("download", 14), h("span", { text: "导出 CSV" }),
  ]);
  const deleteGlossaryButton = h("button", { class: "ghost small", style: "color:var(--red)" }, [
    icon("trash", 14), h("span", { text: "删除术语库" }),
  ]);

  const headerActions = h("div", { class: "row" }, [
    h("button", { class: "secondary small", on: { click: () => createGlossary() } }, [
      icon("plus", 14), h("span", { text: "新建术语库" }),
    ]),
  ]);

  const el = h("div", { class: "page-stack" }, [
    h("section", { class: "section-card" }, [
      h("div", { class: "card-head" }, [
        h("div", {}, [
          h("h2", { text: "术语库" }),
          h("p", { text: "把固定译法交给模型，适合产品名、技术术语、法律/合同用语。" }),
        ]),
        headerActions,
      ]),
      h("div", { class: "glossary-layout" }, [
        h("div", { style: "border-right:1px solid var(--border);min-height:420px" }, listEl),
        h("div", {}, [
          h("div", { class: "row between", style: "padding:10px 14px;border-bottom:1px solid var(--border)" }, [
            searchInput,
            h("div", { class: "row" }, [importButton, exportButton, deleteGlossaryButton]),
          ]),
          detailEl,
        ]),
      ]),
    ]),
  ]);

  function glossaryName(id) {
    return glossaries.find((item) => item.id === id)?.name || "";
  }

  function renderList() {
    clear(listEl);
    if (!glossaries.length) {
      listEl.appendChild(h("div", { class: "empty-state" }, [
        h("strong", { text: "还没有术语库" }),
        h("div", { text: "新建一个，把固定译法保存下来。" }),
      ]));
      return;
    }
    for (const glossary of glossaries) {
      const button = h("button", {
        class: `glossary-item${glossary.id === selectedId ? " active" : ""}`,
        on: {
          click: () => {
            selectedId = glossary.id;
            localStorage.setItem("zc.glossary.selected", selectedId);
            editingTerm = null;
            renderList();
            loadTerms();
          },
        },
      }, [
        h("span", { class: "gi-name", text: glossary.name }),
        h("span", {
          class: "gi-meta",
          text: `${langLabel(glossary.src_lang)} → ${langLabel(glossary.tgt_lang)} · ${glossary.term_count || 0} 条`,
        }),
      ]);
      listEl.appendChild(button);
    }
  }

  function renderTermForm() {
    if (!selectedId) return null;
    const glossary = glossaries.find((item) => item.id === selectedId);
    if (!glossary) return null;
    const sourceInput = h("input", { type: "text", attrs: { placeholder: "原文术语" } });
    const targetInput = h("input", { type: "text", attrs: { placeholder: "目标译文" } });
    const noteInput = h("input", { type: "text", attrs: { placeholder: "备注（可选）" } });
    const caseCheck = h("input", { type: "checkbox" });
    if (editingTerm) {
      sourceInput.value = editingTerm.source;
      targetInput.value = editingTerm.target;
      noteInput.value = editingTerm.note || "";
      caseCheck.checked = Boolean(editingTerm.case_sensitive);
    }
    const saveButton = h("button", { class: "primary small" }, [
      icon(editingTerm ? "check" : "plus", 14),
      h("span", { text: editingTerm ? "保存修改" : "添加" }),
    ]);
    const cancelButton = editingTerm
      ? h("button", {
        class: "ghost small",
        text: "取消编辑",
        on: {
          click: () => {
            editingTerm = null;
            renderDetail();
          },
        },
      })
      : null;

    saveButton.addEventListener("click", async () => {
      const source = sourceInput.value.trim();
      const target = targetInput.value.trim();
      if (!source || !target) {
        toast("原文和译文都不能为空", "warn");
        return;
      }
      if (busy) return;
      busy = true;
      saveButton.disabled = true;
      try {
        if (editingTerm) {
          await api.put(`/api/glossaries/${selectedId}/terms/${editingTerm.id}`, {
            source, target, note: noteInput.value.trim(), case_sensitive: caseCheck.checked,
          });
          toast("术语已更新", "success", 1800);
        } else {
          await api.post(`/api/glossaries/${selectedId}/terms`, {
            source, target, note: noteInput.value.trim(), case_sensitive: caseCheck.checked,
          });
          toast("术语已添加", "success", 1800);
        }
        editingTerm = null;
        await loadTerms();
      } catch (error) {
        toast(error.message, "error");
      } finally {
        busy = false;
        saveButton.disabled = false;
      }
    });

    return h("div", { class: "term-form", style: "margin-bottom:14px" }, [
      h("div", { class: "field" }, [h("label", { text: "原文" }), sourceInput]),
      h("div", { class: "field" }, [h("label", { text: "译文" }), targetInput]),
      h("div", { class: "field" }, [h("label", { text: "备注" }), noteInput]),
      h("div", { class: "row" }, [
        h("label", { class: "checkline" }, caseCheck, "区分大小写"),
        saveButton,
        cancelButton,
      ]),
    ]);
  }

  function renderDetail() {
    clear(detailEl);
    const glossary = glossaries.find((item) => item.id === selectedId);
    if (!glossary) {
      detailEl.appendChild(h("div", { class: "empty-state" }, [
        h("strong", { text: "选择一个术语库" }),
        h("div", { text: "或新建一个术语库开始维护固定译法。" }),
      ]));
      return;
    }

    const title = h("div", { class: "row between", style: "margin-bottom:12px" }, [
      h("div", {}, [
        h("h3", { text: glossary.name, style: "margin:0;font-size:14px" }),
        h("div", {
          class: "hint",
          text: `${langLabel(glossary.src_lang)} → ${langLabel(glossary.tgt_lang)} · 双向：${glossary.bidirectional ? "是" : "否"} · ${terms.length} 条`,
        }),
      ]),
    ]);
    const bidirectional = h("input", { type: "checkbox", checked: Boolean(glossary.bidirectional) });
    bidirectional.addEventListener("change", async () => {
      try {
        await api.put(`/api/glossaries/${selectedId}`, { bidirectional: bidirectional.checked });
        glossary.bidirectional = bidirectional.checked ? 1 : 0;
        toast("已更新术语库设置", "success", 1600);
      } catch (error) {
        toast(error.message, "error");
      }
    });
    title.appendChild(h("label", { class: "checkline" }, bidirectional, "双向匹配"));

    const form = renderTermForm();
    if (form) detailEl.appendChild(form);

    const filtered = terms.filter((term) => {
      if (!search) return true;
      const needle = search.toLowerCase();
      return term.source.toLowerCase().includes(needle)
        || term.target.toLowerCase().includes(needle)
        || (term.note || "").toLowerCase().includes(needle);
    });

    if (!filtered.length) {
      detailEl.appendChild(h("div", { class: "empty-state" }, [
        h("strong", { text: terms.length ? "没有匹配的术语" : "还没有术语" }),
        h("div", { text: terms.length ? "换个关键词试试。" : "在上方添加第一条固定译法。" }),
      ]));
    } else {
      const table = h("table", { class: "terms-table" }, [
        h("thead", {}, h("tr", {}, [
          h("th", { text: "原文" }),
          h("th", { text: "译文" }),
          h("th", { text: "备注" }),
          h("th", { text: "" }),
        ])),
      ]);
      const tbody = h("tbody");
      for (const term of filtered) {
        tbody.appendChild(h("tr", {}, [
          h("td", {}, [
            h("div", { class: "term-source", text: term.source }),
            term.case_sensitive ? h("span", { class: "badge", text: "区分大小写" }) : null,
          ]),
          h("td", { text: term.target }),
          h("td", { class: "hint", text: term.note || "" }),
          h("td", { class: "term-actions" }, [
            h("button", {
              class: "ghost small",
              text: "编辑",
              on: {
                click: () => {
                  editingTerm = term;
                  renderDetail();
                },
              },
            }),
            h("button", {
              class: "ghost small",
              text: "删除",
              on: {
                click: async () => {
                  if (!(await confirmDialog("删除术语", `确定删除“${term.source}”吗？`, { danger: true }))) return;
                  try {
                    await api.delete(`/api/glossaries/${selectedId}/terms/${term.id}`);
                    await loadTerms();
                  } catch (error) {
                    toast(error.message, "error");
                  }
                },
              },
            }),
          ]),
        ]));
      }
      table.appendChild(tbody);
      detailEl.appendChild(table);
    }
    detailEl.prepend(title);
  }

  async function loadTerms() {
    if (!selectedId) {
      terms = [];
      renderDetail();
      return;
    }
    try {
      const data = await api.get(`/api/glossaries/${selectedId}/terms`);
      terms = data.items || [];
      const glossary = glossaries.find((item) => item.id === selectedId);
      if (glossary) glossary.term_count = terms.length;
      renderList();
      renderDetail();
    } catch (error) {
      toast(error.message, "error");
    }
  }

  async function refreshGlossaries(preferredId = "") {
    const data = await api.get("/api/glossaries");
    glossaries = data.items || [];
    store.glossaries = glossaries;
    ctx.updateChrome();
    if (preferredId) selectedId = preferredId;
    if (!glossaries.find((item) => item.id === selectedId)) {
      selectedId = glossaries[0]?.id || "";
    }
    localStorage.setItem("zc.glossary.selected", selectedId);
    renderList();
    await loadTerms();
    ctx.reload(false);
  }

  function createGlossary() {
    const nameInput = h("input", { type: "text", attrs: { placeholder: "例如：产品术语 / 合同条款" } });
    const srcSelect = h("select");
    const tgtSelect = h("select");
    for (const item of LANGS) {
      srcSelect.appendChild(selectOption(item.value, item.label));
      tgtSelect.appendChild(selectOption(item.value, item.label));
    }
    srcSelect.value = "en";
    tgtSelect.value = "zh";
    const bidirectional = h("input", { type: "checkbox" });
    const body = h("div", { class: "page-stack", style: "gap:12px" }, [
      h("div", { class: "field" }, [h("label", { text: "名称" }), nameInput]),
      h("div", { class: "grid-2" }, [
        h("div", { class: "field" }, [h("label", { text: "源语言" }), srcSelect]),
        h("div", { class: "field" }, [h("label", { text: "目标语言" }), tgtSelect]),
      ]),
      h("label", { class: "checkline" }, bidirectional, "允许反向使用（目标→源）"),
      h("div", { class: "hint", text: "术语库只在匹配当前翻译方向时生效；双向模式会自动交换原文/译文。" }),
    ]);
    const dialog = modal({
      title: "新建术语库",
      body,
      actions: [
        { label: "取消", onClick: ({ close }) => close() },
        {
          label: "创建",
          kind: "primary",
          onClick: async ({ close }) => {
            const name = nameInput.value.trim();
            if (!name) {
              toast("请输入名称", "warn");
              return;
            }
            if (srcSelect.value === tgtSelect.value) {
              toast("源语言和目标语言不能相同", "warn");
              return;
            }
            try {
              const created = await api.post("/api/glossaries", {
                name,
                src_lang: srcSelect.value,
                tgt_lang: tgtSelect.value,
                bidirectional: bidirectional.checked,
              });
              close();
              await refreshGlossaries(created.id);
              toast("术语库已创建", "success", 1800);
            } catch (error) {
              toast(error.message, "error");
            }
          },
        },
      ],
    });
    window.setTimeout(() => nameInput.focus(), 30);
    return dialog;
  }

  searchInput.addEventListener("input", () => {
    search = searchInput.value.trim();
    renderDetail();
  });

  importButton.addEventListener("click", () => {
    if (!selectedId) {
      toast("请先选择术语库", "warn");
      return;
    }
    const input = h("input", { type: "file", attrs: { accept: ".csv,text/csv" } });
    input.addEventListener("change", () => {
      const file = input.files?.[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = async () => {
        try {
          const result = await api.post(`/api/glossaries/${selectedId}/import`, {
            csv_text: String(reader.result || ""),
            replace: false,
          });
          toast(`导入完成：新增 ${result.added}，更新 ${result.updated}，跳过 ${result.skipped}`, "success", 4200);
          await loadTerms();
          await refreshGlossaries(selectedId);
        } catch (error) {
          toast(error.message, "error");
        }
      };
      reader.onerror = () => toast("文件读取失败", "error");
      reader.readAsText(file, "utf-8");
    });
    input.click();
  });

  exportButton.addEventListener("click", async () => {
    if (!selectedId) {
      toast("请先选择术语库", "warn");
      return;
    }
    try {
      const blob = await api.download(`/api/glossaries/${selectedId}/export`);
      downloadBlob(`glossary-${glossaryName(selectedId)}.csv`, blob);
    } catch (error) {
      toast(error.message, "error");
    }
  });

  deleteGlossaryButton.addEventListener("click", async () => {
    if (!selectedId) return;
    const name = glossaryName(selectedId);
    if (!(await confirmDialog("删除术语库", `确定删除“${name}”及其全部术语吗？此操作不可撤销。`, { danger: true, confirmLabel: "删除" }))) return;
    try {
      await api.delete(`/api/glossaries/${selectedId}`);
      toast("术语库已删除", "success", 1800);
      await refreshGlossaries();
    } catch (error) {
      toast(error.message, "error");
    }
  });

  // Initial render: the list is local, terms are fetched.
  renderList();
  if (selectedId) {
    loadTerms();
  } else {
    renderDetail();
  }

  return {
    el,
    cleanup() {
      /* no timers */
    },
  };
}
