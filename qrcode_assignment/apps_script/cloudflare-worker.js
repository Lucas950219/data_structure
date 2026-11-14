// Cloudflare Worker for the QR assignment. The Apps Script URL is a public
// write-only endpoint; it must already be deployed with the IP column update.
const APPS_SCRIPT_URL = "https://script.google.com/macros/s/AKfycbzsAoFd_nyToblSZRN_azzwB4AgYmwQozqwtodffOl4SMGcQw3p27nBTgVCfvV7IagS/exec";
const ALLOWED_ORIGIN = "https://lucas950219.github.io";

function reply(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Access-Control-Allow-Origin": ALLOWED_ORIGIN,
      "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type",
      "Vary": "Origin",
      "Cache-Control": "no-store"
    }
  });
}

export default {
  async fetch(request) {
    if (request.method === "GET") return reply({ ok: true, service: "qrcode-ip-proxy" });
    if (request.headers.get("Origin") !== ALLOWED_ORIGIN) return reply({ ok: false }, 403);
    if (request.method === "OPTIONS") return reply({ ok: true });
    if (request.method !== "POST") return reply({ ok: false }, 405);

    try {
      const body = await request.text();
      if (body.length > 8192) return reply({ ok: false, error: "Request too large" }, 413);
      const data = JSON.parse(new URLSearchParams(body).get("payload") || "{}");
      if (!["visit", "checkin"].includes(data.type)) return reply({ ok: false, error: "Invalid event" }, 400);
      const clientIp = request.headers.get("CF-Connecting-IP");
      if (!clientIp) return reply({ ok: false, error: "Client IP unavailable" }, 503);

      const record = {
        type: data.type,
        pageUrl: String(data.pageUrl || "").slice(0, 500),
        userAgent: String(data.userAgent || "").slice(0, 300),
        name: String(data.name || "").slice(0, 50),
        message: String(data.message || "").slice(0, 300),
        clientIp
      };
      const upstream = await fetch(APPS_SCRIPT_URL, {
        method: "POST",
        body: new URLSearchParams({ payload: JSON.stringify(record) }),
        redirect: "follow"
      });
      const result = await upstream.json();
      if (!upstream.ok || !result.ok || result.ipLogging !== true) {
        return reply({ ok: false, error: "IP-enabled Apps Script deployment required" }, 502);
      }
      return reply({ ok: true });
    } catch (_error) {
      return reply({ ok: false, error: "Record failed" }, 502);
    }
  }
};
