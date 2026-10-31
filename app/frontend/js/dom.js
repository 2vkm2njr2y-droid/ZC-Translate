import { icon } from "./icons.js";

export function h(tag, props = {}, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(props || {})) {
    if (value === null || value === undefined || value === false) continue;
    if (key === "class") el.className = value;
    else if (key === "text") el.textContent = value;
    else if (key === "html") el.innerHTML = value;
    else if (key === "dataset") Object.assign(el.dataset, value);
    else if (key === "on") {
      for (const [event, handler] of Object.entries(value)) {
        el.addEventListener(event, handler);
      }
    } else if (key === "attrs") {
      for (const [attr, attrValue] of Object.entries(value)) {
        if (attrValue !== null && attrValue !== undefined && attrValue !== false) {
          el.setAttribute(attr, attrValue === true ? "" : String(attrValue));
        }
      }
    } else if (key.startsWith("on") && typeof value === "function") {
      el.addEventListener(key.slice(2).toLowerCase(), value);
    } else if (value === true) {
      el.setAttribute(key, "");
    } else {
      el.setAttribute(key, String(value));
    }
  }
  append(el, children);
  return el;
}

export function append(parent, children) {
  for (const child of children.flat(Infinity)) {
    if (child === null || child === undefined || child === false) continue;
    parent.appendChild(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return parent;
}

export function clear(el) {
  while (el.firstChild) el.removeChild(el.firstChild);
  return el;
}

export function iconButton(name, title, onClick, cls = "ghost small") {
  const button = h("button", { class: cls, title, attrs: { "aria-label": title }, on: { click: onClick } });
  button.appendChild(icon(name, 14));
  return button;
}

let toastId = 0;
export function toast(message, type = "info", timeout = 3600) {
  const root = document.getElementById("toasts");
  if (!root) return;
  const item = h("div", { class: `toast ${type}`, dataset: { id: String(++toastId) } }, message);
  root.appendChild(item);
  window.setTimeout(() => {
    item.style.opacity = "0";
    item.style.transform = "translateY(4px)";
    window.setTimeout(() => item.remove(), 180);
  }, timeout);
}

export function modal({ title, body, actions = [], width = 560, onClose = null }) {
  const root = document.getElementById("modal-root");
  const close = () => {
    backdrop.remove();
    if (onClose) onClose();
  };
  const dialog = h("div", { class: "modal", attrs: { role: "dialog", "aria-modal": "true" }, style: `width:min(${width}px,100%)` });
  const head = h("div", { class: "modal-head" }, h("h2", { text: title }));
  const closeButton = h("button", { class: "icon-button", attrs: { "aria-label": "关闭" }, on: { click: close } });
  closeButton.appendChild(icon("x", 16));
  head.appendChild(closeButton);
  const bodyEl = h("div", { class: "modal-body" });
  append(bodyEl, [body]);
  const foot = h("div", { class: "modal-foot" });
  for (const action of actions) {
    foot.appendChild(h("button", {
      class: action.kind || "secondary",
      text: action.label,
      on: { click: () => action.onClick ? action.onClick({ close, dialog }) : close() },
    }));
  }
  if (actions.length === 0) foot.remove();
  append(dialog, [head, bodyEl, actions.length ? foot : null]);
  const backdrop = h("div", {
    class: "modal-backdrop",
    on: { click: (event) => { if (event.target === backdrop) close(); } },
  }, dialog);
  root.appendChild(backdrop);
  return { close, dialog, body: bodyEl };
}

export function confirmDialog(title, message, { danger = false, confirmLabel = "确定" } = {}) {
  return new Promise((resolve) => {
    // modal.close() synchronously calls onClose, so record the decision before
    // closing; resolving true after close() would be ignored.
    let confirmed = false;
    modal({
      title,
      body: h("p", { class: "hint", text: message, style: "margin:0;line-height:1.7" }),
      actions: [
        { label: "取消", onClick: ({ close }) => close() },
        {
          label: confirmLabel,
          kind: danger ? "danger" : "primary",
          onClick: ({ close }) => {
            confirmed = true;
            close();
          },
        },
      ],
      onClose: () => resolve(confirmed),
    });
  });
}

export function formatBytes(bytes) {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  let value = bytes;
  let index = 0;
  while (value >= 1024 && index < units.length - 1) {
    value /= 1024;
    index += 1;
  }
  return `${value.toFixed(value >= 10 || index === 0 ? 0 : 1)} ${units[index]}`;
}

export function formatTime(iso) {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString("zh-CN", { hour12: false });
}

export function debounce(fn, delay = 250) {
  let timer = 0;
  return (...args) => {
    window.clearTimeout(timer);
    timer = window.setTimeout(() => fn(...args), delay);
  };
}

export function downloadText(filename, text, mime = "text/plain;charset=utf-8") {
  const blob = new Blob([text], { type: mime });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function selectOption(value, label, disabled = false) {
  return h("option", { value, text: label, disabled });
}

export function spinner(text = "") {
  return h("span", { class: "loading-line" }, h("span", { class: "spin" }), text);
}
