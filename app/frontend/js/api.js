const token = document.querySelector('meta[name="zc-token"]')?.content || "";

export class ApiError extends Error {
  constructor(message, status = 0, code = "") {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

async function readError(response) {
  let body = null;
  try {
    body = await response.json();
  } catch {
    /* ignore */
  }
  const message = body?.error?.message || body?.message || `请求失败（${response.status}）`;
  const code = body?.error?.code || "";
  return new ApiError(message, response.status, code);
}

async function request(path, { method = "GET", body = null, signal = null } = {}) {
  const headers = { "X-ZC-Token": token };
  if (body !== null) headers["Content-Type"] = "application/json";
  let response;
  try {
    response = await fetch(path, {
      method,
      headers,
      body: body === null ? undefined : JSON.stringify(body),
      signal,
    });
  } catch (error) {
    if (error.name === "AbortError") throw error;
    throw new ApiError("无法连接本地服务，请重启应用。", 0, "NETWORK");
  }
  if (!response.ok) throw await readError(response);
  if (response.status === 204) return null;
  return response.json();
}

export const api = {
  get: (path, options = {}) => request(path, { ...options, method: "GET" }),
  post: (path, body = null, options = {}) => request(path, { ...options, method: "POST", body }),
  put: (path, body = null, options = {}) => request(path, { ...options, method: "PUT", body }),
  delete: (path, options = {}) => request(path, { ...options, method: "DELETE" }),

  async stream(path, payload, handlers = {}, signal = null) {
    const response = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-ZC-Token": token },
      body: JSON.stringify(payload),
      signal,
    });
    if (!response.ok) throw await readError(response);
    if (handlers.onOpen) handlers.onOpen(response);
    if (!response.body) throw new ApiError("当前环境不支持流式响应。", 0, "NO_STREAM");

    const reader = response.body.getReader();
    const decoder = new TextDecoder("utf-8");
    let buffer = "";
    const dispatch = (chunk) => {
      const lines = chunk.split("\n");
      let event = "message";
      const dataLines = [];
      for (const line of lines) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
      }
      if (!dataLines.length) return;
      let data = {};
      try {
        data = JSON.parse(dataLines.join("\n"));
      } catch {
        data = { raw: dataLines.join("\n") };
      }
      if (handlers.onEvent) handlers.onEvent(event, data);
      if (handlers[event]) handlers[event](data);
    };

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let index = buffer.indexOf("\n\n");
      while (index >= 0) {
        dispatch(buffer.slice(0, index));
        buffer = buffer.slice(index + 2);
        index = buffer.indexOf("\n\n");
      }
    }
    if (buffer.trim()) dispatch(buffer);
  },

  translateStream(payload, handlers = {}, signal = null) {
    return api.stream("/api/translate/stream", payload, handlers, signal);
  },

  screenshotStream(payload, handlers = {}, signal = null) {
    return api.stream("/api/screenshot/translate/stream", payload, handlers, signal);
  },

  documentStream(payload, handlers = {}, signal = null) {
    return api.stream("/api/document/translate/stream", payload, handlers, signal);
  },

  speechStatus() {
    return api.get("/api/speech/status");
  },

  speechDownload() {
    return api.post("/api/speech/model/download");
  },

  speechStart(mode) {
    return api.post("/api/speech/session/start", { mode });
  },

  speechStop(sessionId) {
    return api.post("/api/speech/session/stop", { session_id: sessionId });
  },

  speechSessionStatus(sessionId, since = 0) {
    const query = new URLSearchParams({ session_id: sessionId, since: String(since) });
    return api.get(`/api/speech/session/status?${query.toString()}`);
  },

  async cancelJob(jobId) {
    if (!jobId) return;
    try {
      await api.post(`/api/translate/cancel/${encodeURIComponent(jobId)}`);
    } catch {
      /* disconnect already cancels */
    }
  },

  async download(path) {
    const response = await fetch(path, { headers: { "X-ZC-Token": token } });
    if (!response.ok) throw await readError(response);
    return response.blob();
  },

  token,
};
