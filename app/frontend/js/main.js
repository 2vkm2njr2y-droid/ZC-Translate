import { api, ApiError } from "./api.js";
import { store } from "./state.js";
import { toast } from "./dom.js";
import { initCompact } from "./compact.js";

function desktopCall(method) {
  const app = window.pywebview?.api;
  if (app && typeof app[method] === "function") return app[method]();
  return Promise.resolve(false);
}

function syncFrameColor() {
  const value = getComputedStyle(document.documentElement)
    .getPropertyValue("--bg")
    .trim();
  if (!/^#[0-9a-f]{6}$/i.test(value)) return;
  const app = window.pywebview?.api;
  if (app && typeof app.set_frame_color === "function") {
    Promise.resolve(app.set_frame_color(value)).catch(() => {});
  }
}

window.zcSyncFrameColor = syncFrameColor;

async function boot() {
  const version = document.querySelector('meta[name="zc-version"]')?.content || "";
  const versionLabel = document.getElementById("version-label");
  if (versionLabel) versionLabel.textContent = version ? `v${version}` : "";

  try {
    const [settings, models, system, glossaries] = await Promise.all([
      api.get("/api/settings"),
      api.get("/api/models"),
      api.get("/api/system/info"),
      api.get("/api/glossaries"),
    ]);
    store.set({
      settings,
      models: models.models,
      activeProfile: models.active_profile,
      engine: models.engine,
      system,
      glossaries: glossaries.items,
    });
  } catch (error) {
    console.error(error);
    const engine = document.getElementById("compact-engine");
    if (engine) {
      engine.className = "compact-engine error";
      engine.textContent = "无法连接本地服务";
    }
    toast("无法连接本地服务，请从启动器重新打开", "error", 7000);
    return;
  }

  document.documentElement.dataset.theme = store.settings.theme || "system";
  syncFrameColor();
  initCompact({ store, api, toast, desktopCall });

  window.setInterval(async () => {
    if (document.hidden) return;
    try {
      const info = await api.get("/api/system/info");
      store.set({ engine: info.engine, system: info });
    } catch {
      /* transient */
    }
  }, 5000);

  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
    if ((store.settings.theme || "system") === "system") {
      document.documentElement.dataset.theme = "system";
      syncFrameColor();
    }
  });
}

window.addEventListener("unhandledrejection", (event) => {
  if (event.reason instanceof ApiError) {
    toast(event.reason.message, "error");
  } else {
    console.error(event.reason);
  }
});

document.body.classList.add("compact-mode");
boot();
