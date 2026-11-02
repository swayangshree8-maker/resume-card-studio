"use strict";
(() => {
  const api = String(window.RCS_API_BASE || "").replace(/\/$/, "");
  if (!api || location.protocol === "file:") return;
  const pageName = () => {
    const hash = location.hash;
    if (hash === "#resume") return "resume";
    if (hash === "#card") return "cards";
    if (hash === "#docs") return "rent";
    if (document.body.classList.contains("in")) return "home";
    return "login";
  };
  const refresh = () => {
    fetch(`${api}/api/settings`, { cache: "no-store", credentials: "omit" })
      .then((r) => r.ok ? r.json() : null)
      .then((settings) => {
        if (!settings) return;
        if (settings.site_title) document.title = String(settings.site_title).slice(0, 80);
        if (settings.announcement) {
          let banner = document.getElementById("remoteAnnouncement");
          if (!banner) {
            banner = document.createElement("aside"); banner.id = "remoteAnnouncement";
            Object.assign(banner.style, { position: "relative", zIndex: "55", padding: "11px 16px", textAlign: "center", color: "#fff", background: "linear-gradient(100deg,#167ec3,#6a32a5)", font: "600 14px system-ui" });
            document.body.insertBefore(banner, document.body.firstChild);
          }
          banner.textContent = settings.announcement;
        } else document.getElementById("remoteAnnouncement")?.remove();
      }).catch(() => {});
  };
  const sendPage = () => {
    fetch(`${api}/api/analytics/event`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ page: pageName() }), credentials: "omit", keepalive: true }).catch(() => {});
    refresh();
  };
  window.addEventListener("hashchange", sendPage);
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", sendPage, { once: true });
  else sendPage();
})();
