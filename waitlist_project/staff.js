(() => {
  const config = window.WAITLIST_CONFIG || {};
  const apiBase = String(config.apiBaseUrl || "").replace(/\/$/, "");
  const pollInterval = Math.max(3000, Number(config.pollIntervalMs) || 5000);
  const TOKEN_KEY = "waitlist.staffSession";
  const loginPanel = document.getElementById("login-panel");
  const dashboard = document.getElementById("staff-dashboard");
  const loginForm = document.getElementById("staff-login");
  const loginMessage = document.getElementById("login-message");
  const pageError = document.getElementById("staff-page-error");
  const queueBody = document.getElementById("staff-queue-body");
  let token = "";
  let lane = "all";
  let pollTimer = null;
  let busyAction = false;

  function safeReadToken() {
    try { return sessionStorage.getItem(TOKEN_KEY) || ""; } catch { return ""; }
  }

  function setToken(value) {
    token = value;
    try {
      if (value) sessionStorage.setItem(TOKEN_KEY, value);
      else sessionStorage.removeItem(TOKEN_KEY);
    } catch { /* The token remains available in memory for this page. */ }
  }

  function escapeHTML(value) {
    return String(value ?? "").replace(/[&<>"']/g, (character) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    })[character]);
  }

  async function request(path, options = {}) {
    if (!apiBase) throw new Error("後端 API 網址尚未設定，請先完成部署設定。");
    let response;
    try {
      response = await fetch(`${apiBase}${path}`, {
        method: options.method || "GET",
        headers: {
          ...(options.body ? { "Content-Type": "application/json" } : {}),
          ...(options.auth !== false && token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: options.body ? JSON.stringify(options.body) : undefined,
        cache: "no-store",
      });
    } catch {
      throw new Error("無法連接候位後端，請確認服務是否啟動。");
    }
    let payload = {};
    try { payload = await response.json(); } catch { /* Report a useful fallback below. */ }
    if (!response.ok) {
      const error = new Error(payload.message || "請求未完成，請稍後重試。");
      error.status = response.status;
      error.code = payload.error;
      throw error;
    }
    return payload;
  }

  function toast(message, isError = false) {
    const item = document.createElement("div");
    item.className = `toast${isError ? " toast-error" : ""}`;
    item.textContent = message;
    document.getElementById("staff-toast").append(item);
    window.setTimeout(() => item.remove(), 3500);
  }

  function showLogin(message = "") {
    setToken("");
    dashboard.hidden = true;
    loginPanel.hidden = false;
    queueBody.replaceChildren();
    document.getElementById("staff-queue-count").textContent = "0";
    document.getElementById("staff-empty").hidden = true;
    pageError.textContent = "";
    if (pollTimer) window.clearInterval(pollTimer);
    pollTimer = null;
    if (message) loginMessage.textContent = message;
    document.getElementById("staff-password").value = "";
  }

  function showDashboard() {
    loginPanel.hidden = true;
    dashboard.hidden = false;
    loginMessage.textContent = "";
    pageError.textContent = "";
  }

  function formatDateTime(value) {
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? "—" : date.toLocaleTimeString("zh-TW", { hour: "2-digit", minute: "2-digit" });
  }

  function statusLabel(status) {
    return ({ waiting: "候位中", notifying: "寄送中", notified: "已通知" })[status] || status;
  }

  function renderRows(entries) {
    document.getElementById("staff-queue-count").textContent = entries.length;
    document.getElementById("staff-empty").hidden = entries.length > 0;
    queueBody.innerHTML = entries.map((entry) => {
      const laneClass = entry.tableType === "4p" ? "lane-badge lane-4" : "lane-badge";
      let actionButtons = "";
      if (entry.status === "waiting") {
        actionButtons = `<button class="staff-action action-notify" type="button" data-action="notify" data-id="${entry.id}">通知</button><button class="staff-action action-seat" type="button" data-action="seat" data-id="${entry.id}">入座</button><button class="staff-action" type="button" data-action="cancel" data-id="${entry.id}">取消</button>`;
      } else if (entry.status === "notifying") {
        actionButtons = `<button class="staff-action" type="button" disabled>寄送中…</button>`;
      } else {
        actionButtons = `<button class="staff-action action-seat" type="button" data-action="seat" data-id="${entry.id}">入座</button><button class="staff-action" type="button" data-action="cancel" data-id="${entry.id}">取消</button>`;
      }
      return `<tr>
        <td class="ticket-cell"><strong>${escapeHTML(entry.ticket)}</strong></td>
        <td class="guest-cell"><strong>${escapeHTML(entry.name)}</strong><small>${escapeHTML(entry.gender)}</small></td>
        <td>${escapeHTML(entry.partySize)} 位 <span class="${laneClass}">${entry.tableType === "2p" ? "2 人桌" : "4 人桌"}</span></td>
        <td>${escapeHTML(entry.email)}</td>
        <td>${escapeHTML(formatDateTime(entry.createdAt))} <span class="wait-minutes">(${escapeHTML(entry.waitMinutes)} 分)</span></td>
        <td><span class="staff-status status-${escapeHTML(entry.status)}">${escapeHTML(statusLabel(entry.status))}</span></td>
        <td><div class="staff-actions">${actionButtons}</div></td>
      </tr>`;
    }).join("");
  }

  function renderStats(data) {
    document.getElementById("stat-total").textContent = data.totalToday ?? 0;
    document.getElementById("stat-active").textContent = data.activeTotal ?? 0;
    document.getElementById("stat-average").textContent = data.averageWaitMinutes === null ? "—" : data.averageWaitMinutes;
    document.getElementById("stat-abandonment").textContent = `${data.abandonmentRate ?? 0}%`;
    document.getElementById("stat-cancelled").textContent = `今日取消 ${data.cancelled ?? 0} 組`;
  }

  async function refreshDashboard() {
    if (!token || busyAction) return;
    try {
      const [queue, stats] = await Promise.all([
        request(`/api/staff/queue?lane=${encodeURIComponent(lane)}`),
        request("/api/staff/stats"),
      ]);
      renderRows(queue.entries || []);
      renderStats(stats);
      document.getElementById("staff-updated").textContent = `更新於 ${formatDateTime(queue.updatedAt)}`;
      pageError.textContent = "";
    } catch (error) {
      if (error.status === 401) {
        showLogin("登入已逾時，請重新輸入員工密碼。");
      } else {
        pageError.textContent = error.message;
      }
    }
  }

  async function login(event) {
    event.preventDefault();
    loginMessage.textContent = "";
    if (!loginForm.reportValidity()) return;
    const button = document.getElementById("login-button");
    const password = document.getElementById("staff-password").value;
    button.disabled = true;
    button.querySelector("span").textContent = "驗證中…";
    try {
      const response = await request("/api/staff/login", { method: "POST", auth: false, body: { password } });
      setToken(response.token);
      showDashboard();
      await refreshDashboard();
      if (!pollTimer) pollTimer = window.setInterval(refreshDashboard, pollInterval);
    } catch (error) {
      loginMessage.textContent = error.message;
    } finally {
      button.disabled = false;
      button.querySelector("span").textContent = "安全登入";
      document.getElementById("staff-password").value = "";
    }
  }

  async function handleQueueAction(action, id) {
    if (!token || busyAction) return;
    if (action === "cancel" && !window.confirm("確定取消這組候位？該組客人會從目前 Queue 移除。")) return;
    const labels = { notify: "正在寄送通知…", seat: "正在更新入座狀態…", cancel: "正在取消候位…" };
    busyAction = true;
    pageError.textContent = labels[action] || "正在更新…";
    try {
      const result = await request(`/api/staff/entries/${encodeURIComponent(id)}/${action}`, { method: "POST", body: {} });
      toast(result.message || (action === "notify" ? "通知 E-mail 已寄出。" : action === "seat" ? "已更新為入座。" : "已從候位 Queue 移除。"));
      pageError.textContent = "";
    } catch (error) {
      pageError.textContent = error.message;
      toast(error.message, true);
    } finally {
      busyAction = false;
      await refreshDashboard();
    }
  }

  loginForm.addEventListener("submit", login);
  document.getElementById("logout-button").addEventListener("click", () => showLogin("已安全登出。"));
  document.querySelectorAll(".lane-filter").forEach((button) => {
    button.addEventListener("click", () => {
      lane = button.dataset.lane;
      document.querySelectorAll(".lane-filter").forEach((filter) => {
        const selected = filter === button;
        filter.classList.toggle("is-active", selected);
        filter.setAttribute("aria-pressed", String(selected));
      });
      refreshDashboard();
    });
  });
  queueBody.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-action]");
    if (button) handleQueueAction(button.dataset.action, button.dataset.id);
  });

  token = safeReadToken();
  if (token) {
    showDashboard();
    refreshDashboard().then(() => {
      if (token && !pollTimer) pollTimer = window.setInterval(refreshDashboard, pollInterval);
    });
  }
})();
