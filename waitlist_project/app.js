(() => {
  const config = window.WAITLIST_CONFIG || {};
  const pollInterval = Math.max(3000, Number(config.pollIntervalMs) || 5000);
  const TOKEN_KEY = "waitlist.customerAccessToken";
  const form = document.getElementById("join-form");
  const formMessage = document.getElementById("join-message");
  const joinButton = document.getElementById("join-button");
  const ticketCard = document.getElementById("ticket-card");
  const cancelButton = document.getElementById("cancel-ticket");
  let token = readToken();
  let lastStatus = null;

  function readToken() {
    try { return localStorage.getItem(TOKEN_KEY) || ""; } catch { return ""; }
  }

  function saveToken(value) {
    token = value;
    try { localStorage.setItem(TOKEN_KEY, value); } catch { /* The current page can still show the ticket. */ }
  }

  async function request(path, options = {}) {
    return window.waitlistRpc({
      path,
      method: options.method || "GET",
      body: options.body || {},
      authorization: options.headers?.Authorization || "",
    });
  }

  function showMessage(message, kind = "error") {
    formMessage.textContent = message;
    formMessage.classList.toggle("message-success", kind === "success");
  }

  function formatWait(minutes) {
    if (!Number.isFinite(Number(minutes))) return "估算中";
    const value = Number(minutes);
    if (value <= 0) return "即將輪到您";
    if (value < 60) return `預估約 ${value} 分鐘`;
    const hours = Math.floor(value / 60);
    const rest = value % 60;
    return rest ? `預估約 ${hours} 小時 ${rest} 分鐘` : `預估約 ${hours} 小時`;
  }

  function statusText(status) {
    return ({ waiting: "候位中", notifying: "通知寄送中", notified: "已通知", seated: "已入座", cancelled: "已取消" })[status] || "狀態更新中";
  }

  function renderTicket(data) {
    if (!data) return;
    lastStatus = data.status;
    ticketCard.hidden = false;
    document.getElementById("ticket-number").textContent = data.ticket || "—";
    document.getElementById("ticket-lane").textContent = `${data.tableType === "2p" ? "2 人桌" : "4 人桌"} · ${data.partySize} 位用餐`;
    document.getElementById("ticket-status").textContent = statusText(data.status);
    document.getElementById("ticket-queue-size").textContent = `${data.queueSize ?? 0} 組`;
    document.getElementById("ticket-ahead").textContent = `${data.groupsAhead ?? 0} 組`;
    const waitText = data.status === "notified"
      ? "已寄送通知，請查看 E-mail 並前往櫃檯。"
      : data.status === "notifying"
        ? "通知郵件正在寄送，候位位置已保留。"
        : data.status === "seated"
          ? "您已入座，祝用餐愉快。"
          : data.status === "cancelled"
            ? "此候位已取消。若仍需要服務，請重新填寫候位表單。"
            : `${formatWait(data.estimatedWaitMinutes)}。頁面每 5 秒自動更新。`;
    document.getElementById("ticket-wait").textContent = waitText;
    cancelButton.hidden = !["waiting", "notified"].includes(data.status);
  }

  async function loadSummary() {
    try {
      const data = await request("/api/queue/summary");
      document.getElementById("lane-2-count").textContent = data.lanes?.["2p"] ?? 0;
      document.getElementById("lane-4-count").textContent = data.lanes?.["4p"] ?? 0;
      document.getElementById("total-queue-count").innerHTML = `${Number(data.queueSize) || 0} <small>組</small>`;
      document.getElementById("summary-update").textContent = `更新時間 ${new Date(data.updatedAt).toLocaleTimeString("zh-TW", { hour: "2-digit", minute: "2-digit" })}`;
    } catch (error) {
      document.getElementById("summary-update").textContent = error.message;
    }
  }

  async function loadTicket() {
    if (!token) return;
    try {
      const data = await request("/api/queue/status", { headers: { Authorization: `Bearer ${token}` } });
      renderTicket(data);
    } catch (error) {
      document.getElementById("ticket-card").hidden = false;
      document.getElementById("ticket-wait").textContent = error.message;
    }
  }

  async function processEmailCancelLink() {
    const url = new URL(window.location.href);
    const linkToken = new URLSearchParams(url.hash.slice(1)).get("cancel");
    if (!linkToken) return;
    saveToken(linkToken);
    url.hash = "";
    window.history.replaceState({}, "", `${url.pathname}${url.search}`);
    try {
      const data = await request("/api/queue/cancel", { method: "POST", body: { token: linkToken } });
      renderTicket(data);
      showMessage("候位已取消。", "success");
      ticketCard.scrollIntoView({ behavior: "smooth", block: "center" });
    } catch (error) {
      document.getElementById("ticket-card").hidden = false;
      document.getElementById("ticket-wait").textContent = error.message;
    }
  }

  async function submitJoin(event) {
    event.preventDefault();
    showMessage("");
    if (!form.reportValidity()) return;
    const fields = new FormData(form);
    joinButton.disabled = true;
    joinButton.querySelector("span").textContent = "正在加入…";
    try {
      const result = await request("/api/queue", {
        method: "POST",
        body: {
          name: String(fields.get("name") || "").trim(),
          gender: fields.get("gender"),
          partySize: Number(fields.get("partySize")),
          email: String(fields.get("email") || "").trim(),
          consent: document.getElementById("guest-consent").checked,
        },
      });
      saveToken(result.token);
      renderTicket(result);
      form.reset();
      document.getElementById("guest-size").value = "2";
      showMessage(`已加入候位，您的號碼是 ${result.ticket}。`, "success");
      ticketCard.scrollIntoView({ behavior: "smooth", block: "center" });
      await loadSummary();
    } catch (error) {
      showMessage(error.message);
    } finally {
      joinButton.disabled = false;
      joinButton.querySelector("span").textContent = "取得候位號碼";
    }
  }

  async function cancelTicket() {
    if (!token || !window.confirm("確定取消這組候位嗎？取消後，前方等候組數會更新。")) return;
    cancelButton.disabled = true;
    try {
      const data = await request("/api/queue/cancel", { method: "POST", body: { token } });
      renderTicket(data);
      showMessage("候位已取消。", "success");
      await loadSummary();
    } catch (error) {
      showMessage(error.message);
    } finally {
      cancelButton.disabled = false;
    }
  }

  form.addEventListener("submit", submitJoin);
  cancelButton.addEventListener("click", cancelTicket);
  document.addEventListener("DOMContentLoaded", () => {});
  (async () => {
    await processEmailCancelLink();
    await Promise.all([loadSummary(), loadTicket()]);
    window.setInterval(() => {
      loadSummary();
      if (lastStatus && !["seated", "cancelled"].includes(lastStatus)) loadTicket();
      else if (!lastStatus && token) loadTicket();
    }, pollInterval);
  })();
})();
