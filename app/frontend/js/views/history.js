import { api } from "../api.js";
import { h, clear, toast, confirmDialog, formatTime, debounce } from "../dom.js";
import { icon } from "../icons.js";

const STATUS_LABEL = { completed: "完成", cancelled: "已取消", error: "失败" };

export function render(ctx) {
  const { store } = ctx;
  let items = [];
  let total = 0;
  let selectedId = "";
  let detail = null;
  let query = "";
  let limit = 30;
  let loadSeq = 0;
  let disposed = false;

  const listEl = h("div", { class: "scroll-thin", style: "max-height:calc(100vh - 260px);overflow:auto;padding-right:2px" });
  const detailEl = h("div", { class: "history-detail" });
  const searchInput = h("input", {
    type: "search",
    attrs: { placeholder: "搜索原文或译文…", "aria-label": "搜索历史" },
    style: "height:32px;width:230px",
  });
  const clearButton = h("button", { class: "ghost small", style: "color:var(--red)" }, [
    icon("trash", 14), h("span", { text: "清空历史" }),
  ]);
  const loadMoreButton = h("button", { class: "ghost small hidden", text: "加载更多" });

  const el = h("div", { class: "page-stack" }, [
    h("section", { class: "section-card" }, [
      h("div", { class: "card-head" }, [
        h("div", {}, [
          h("h2", { text: "历史记录" }),
          h("p", { text: "只保存在本机；可以载入译文继续编辑。" }),
        ]),
        h("div", { class: "row" }, [searchInput, clearButton]),
      ]),
      h("div", { class: "card-body" }, [
        h("div", { class: "history-layout" }, [
          h("div", {}, [listEl, loadMoreButton]),
          h("div", { class: "section-card", style: "box-shadow:none" }, detailEl),
        ]),
      ]),
    ]),
  ]);

  function renderEmptyDetail() {
    clear(detailEl);
    detailEl.appendChild(h("div", { class: "empty-state" }, [
      h("strong", { text: "选择一条历史" }),
      h("div", { text: "查看原文、译文和校验提示。" }),
    ]));
  }

  function renderList() {
    clear(listEl);
    if (!items.length) {
      listEl.appendChild(h("div", { class: "empty-state" }, [
        h("strong", { text: query ? "没有匹配记录" : "还没有翻译记录" }),
        h("div", { text: query ? "换个关键词试试。" : "完成一次翻译后会自动出现在这里。" }),
      ]));
      loadMoreButton.classList.add("hidden");
      return;
    }
    for (const item of items) {
      const active = item.id === selectedId;
      const button = h("button", {
        class: `history-item${active ? " active" : ""}`,
        on: { click: () => select(item.id) },
      }, [
        h("div", { class: "hi-top" }, [
          h("span", { text: formatTime(item.created_at) }),
          h("span", { class: "badge" }, [
            item.src_lang || item.detected_lang || "?",
            " → ",
            item.tgt_lang || "?",
          ]),
          h("span", { class: "badge", text: item.profile === "quality" ? "7B" : "1.8B" }),
          item.status !== "completed"
            ? h("span", { class: `badge ${item.status === "error" ? "err" : "warn"}`, text: STATUS_LABEL[item.status] || item.status })
            : null,
          item.warning_count ? h("span", { class: "badge warn", text: `${item.warning_count} 提示` }) : null,
        ]),
        h("div", { class: "hi-excerpt", text: item.excerpt || "" }),
      ]);
      listEl.appendChild(button);
    }
    loadMoreButton.classList.toggle("hidden", items.length >= total);
  }

  function renderDetail() {
    clear(detailEl);
    if (!detail) {
      renderEmptyDetail();
      return;
    }
    const meta = h("div", { class: "row", style: "margin-bottom:10px;flex-wrap:wrap" }, [
      h("span", { class: "badge", text: `${detail.src_lang || detail.detected_lang || "?"} → ${detail.tgt_lang || "?"}` }),
      h("span", { class: "badge", text: detail.device || "?" }),
      h("span", { class: "badge", text: detail.profile === "quality" ? "Hy-MT2 7B" : "Hy-MT2 1.8B" }),
      h("span", { class: "hint", text: `${formatTime(detail.created_at)} · ${detail.duration_ms || 0} ms` }),
    ]);
    const actions = h("div", { class: "row", style: "margin:10px 0 12px" }, [
      h("button", {
        class: "primary small",
        on: {
          click: async () => {
            store.draftText = detail.source_text || "";
            store.draftTarget = detail.result_text || "";
            store.settings = {
              ...store.settings,
              source_lang: detail.src_lang || "auto",
              target_lang: detail.tgt_lang || "zh",
            };
            try {
              await api.put("/api/settings", {
                source_lang: detail.src_lang || "auto",
                target_lang: detail.tgt_lang || "zh",
              });
            } catch (error) {
              toast(error.message, "error");
            }
            ctx.navigate("translate");
          },
        },
      }, [icon("arrow", 14), h("span", { text: "载入翻译" })]),
      h("button", {
        class: "ghost small",
        text: "删除",
        on: {
          click: async () => {
            const target = detail;
            if (!target) return;
            if (!(await confirmDialog("删除历史", "确定删除这条记录吗？", { danger: true, confirmLabel: "删除" }))) return;
            if (disposed) return;
            try {
              await api.delete(`/api/history/${target.id}`);
            } catch (error) {
              toast(error.message, "error");
              return;
            }
            if (disposed) return;
            // Remove locally first so the deleted row disappears immediately;
            // the reload below reconciles with the server.
            loadSeq += 1;
            items = items.filter((item) => item.id !== target.id);
            total = Math.max(0, total - 1);
            selectedId = "";
            detail = null;
            renderList();
            renderEmptyDetail();
            toast("已删除", "success", 1500);
            await loadHistory();
          },
        },
      }),
    ]);

    detailEl.appendChild(h("div", { class: "row between", style: "margin-bottom:2px" }, [
      h("h3", { text: "记录详情" }), actions,
    ]));
    detailEl.appendChild(meta);
    if (detail.warnings?.length) {
      detailEl.appendChild(h("div", { class: "warn-tip", style: "margin-bottom:12px" }, [
        h("strong", { text: `校验提示（${detail.warnings.length}）` }),
        ...detail.warnings.slice(0, 8).map((warning) => h("div", { text: warning })),
      ]));
    }
    if (detail.error) {
      detailEl.appendChild(h("div", { class: "error-box", text: detail.error }));
    }
    detailEl.appendChild(h("div", { class: "field", style: "margin-bottom:12px" }, [
      h("label", { text: "原文" }),
      h("div", { class: "hd-text", text: detail.source_text || "" }),
    ]));
    detailEl.appendChild(h("div", { class: "field" }, [
      h("label", { text: "译文" }),
      h("div", { class: "hd-text", text: detail.result_text || "" }),
    ]));
  }

  async function select(id) {
    selectedId = id;
    renderList();
    const seq = loadSeq;
    try {
      const item = await api.get(`/api/history/${id}`);
      if (disposed || seq !== loadSeq || selectedId !== id) return;
      detail = item;
      renderDetail();
    } catch (error) {
      if (disposed || seq !== loadSeq || selectedId !== id) return;
      detail = null;
      renderEmptyDetail();
      toast(error.message, "error");
    }
  }

  async function loadHistory({ autoSelect = false } = {}) {
    if (disposed) return;
    const seq = ++loadSeq;
    try {
      const data = await api.get(`/api/history?query=${encodeURIComponent(query)}&limit=${limit}&offset=0`);
      if (disposed || seq !== loadSeq) return;
      items = data.items || [];
      total = data.total || 0;
      if (selectedId && !items.some((item) => item.id === selectedId)) {
        selectedId = "";
        detail = null;
      }
      renderList();
      if (!selectedId) renderEmptyDetail();
      if (autoSelect && !selectedId && items.length) {
        await select(items[0].id);
      }
    } catch (error) {
      if (disposed || seq !== loadSeq) return;
      toast(error.message, "error");
    }
  }

  searchInput.addEventListener("input", debounce(() => {
    query = searchInput.value.trim();
    loadHistory();
  }, 260));

  clearButton.addEventListener("click", async () => {
    if (!(await confirmDialog("清空历史", "确定删除全部历史记录吗？此操作不可撤销。", { danger: true, confirmLabel: "清空" }))) return;
    try {
      await api.delete("/api/history");
      if (disposed) return;
      loadSeq += 1;
      items = [];
      total = 0;
      selectedId = "";
      detail = null;
      renderList();
      renderEmptyDetail();
      toast("历史已清空", "success", 1600);
    } catch (error) {
      toast(error.message, "error");
    }
  });

  loadMoreButton.addEventListener("click", async () => {
    limit += 30;
    await loadHistory();
  });

  loadHistory({ autoSelect: true });

  return {
    el,
    cleanup() {
      disposed = true;
      loadSeq += 1;
    },
  };
}
