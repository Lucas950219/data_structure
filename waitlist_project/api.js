(() => {
  const pending = new Map();
  let sequence = 0;

  function requestId() {
    sequence += 1;
    const randomPart = window.crypto?.randomUUID?.() || Math.random().toString(36).slice(2);
    return `${Date.now()}_${sequence}_${randomPart}`.replace(/[^a-zA-Z0-9_-]/g, "").slice(0, 80);
  }

  function finish(id, error, result) {
    const item = pending.get(id);
    if (!item) return;
    pending.delete(id);
    window.clearTimeout(item.timer);
    item.frame.remove();
    if (error) item.reject(error);
    else if (!result || result.ok !== true) {
      const failure = new Error(result?.message || "候位服務發生錯誤，請稍後再試。");
      failure.status = result?.status || 500;
      failure.code = result?.error || "server_error";
      item.reject(failure);
    } else {
      item.resolve(result.data);
    }
  }

  window.addEventListener("message", (event) => {
    let origin;
    try { origin = new URL(event.origin); } catch { return; }
    if (origin.protocol !== "https:" || !(origin.hostname === "script.google.com" || origin.hostname === "script.googleusercontent.com" || origin.hostname.endsWith("-script.googleusercontent.com"))) return;
    if (event.data?.type !== "waitlist-rpc-result") return;
    const id = String(event.data.requestId || "");
    const item = pending.get(id);
    // Apps Script may execute the response in a nested sandbox frame. The
    // unpredictable request ID links its message to the pending request.
    if (!item) return;
    finish(id, null, event.data.result);
  });

  window.waitlistRpc = function waitlistRpc(request) {
    const config = window.WAITLIST_CONFIG || {};
    const endpoint = String(config.gasWebAppUrl || "").trim();
    if (!endpoint) return Promise.reject(new Error("候位服務尚未設定，請聯絡餐廳員工。"));
    let parsed;
    try { parsed = new URL(endpoint); } catch {
      return Promise.reject(new Error("候位服務網址設定錯誤。"));
    }
    if (parsed.protocol !== "https:" || parsed.hostname !== "script.google.com" || !parsed.pathname.endsWith("/exec")) {
      return Promise.reject(new Error("候位服務網址必須是 Apps Script 的 HTTPS /exec 網址。"));
    }

    const id = requestId();
    return new Promise((resolve, reject) => {
      const frame = document.createElement("iframe");
      frame.name = `waitlist_rpc_${id}`;
      frame.title = "候位服務連線";
      frame.setAttribute("aria-hidden", "true");
      frame.style.cssText = "position:fixed;width:1px;height:1px;left:-10000px;top:-10000px;border:0;";
      const timer = window.setTimeout(() => finish(id, new Error("候位服務回應逾時，請稍後重試。")), 30000);
      pending.set(id, { frame, resolve, reject, timer });
      document.body.append(frame);

      const form = document.createElement("form");
      form.method = "post";
      form.action = parsed.toString();
      form.target = frame.name;
      form.hidden = true;
      const values = { requestId: id, request: JSON.stringify(request || {}) };
      Object.entries(values).forEach(([name, value]) => {
        const input = document.createElement("input");
        input.type = "hidden";
        input.name = name;
        input.value = value;
        form.append(input);
      });
      document.body.append(form);
      form.submit();
      form.remove();
    });
  };
})();
