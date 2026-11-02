"use strict";
(() => {
  const api = String(window.RCS_API_BASE || "").replace(/\/$/, "");
  const $ = (id) => document.getElementById(id);
  let token = "";
  const note = $("connectionNote");
  const msg = (id, text, ok = false) => {
    const el = $(id); el.textContent = text; el.classList.toggle("ok", ok);
  };
  const request = async (path, options = {}) => {
    if (!api) throw new Error("Backend URL is not configured yet.");
    const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
    if (token) headers.Authorization = `Bearer ${token}`;
    const response = await fetch(`${api}${path}`, { ...options, headers, cache: "no-store", credentials: "omit" });
    const data = await response.json().catch(() => ({}));
    if (response.status === 401 && path !== "/api/admin/login") {
      location.reload();
    }
    if (!response.ok) throw new Error(data.error || `Request failed (${response.status})`);
    return data;
  };
  const showDashboard = () => {
    $("loginCard").classList.add("hidden"); $("dashboard").classList.remove("hidden");
    note.classList.add("hidden"); loadSettings(); loadAnalytics();
  };
  const loadSettings = async () => {
    try {
      const s = await request("/api/admin/settings");
      $("siteTitle").value = s.site_title || ""; $("announcement").value = s.announcement || "";
      $("announcementEnabled").checked = !!s.announcement_enabled;
    } catch (e) { msg("settingsMessage", e.message); }
  };
  const loadAnalytics = async () => {
    try {
      const a = await request(`/api/admin/analytics?days=${$("days").value}`);
      $("totalViews").textContent = String(a.total_views ?? 0);
      const labels = { home: "Welcome / Home", resume: "Resume maker", cards: "Card designer", rent: "Rent & bills", login: "Login" };
      const counts = $("pageCounts"); counts.replaceChildren();
      Object.entries(labels).forEach(([key, label]) => {
        const box = document.createElement("div"); box.className = "count";
        const number = document.createElement("b"); number.textContent = String(a.by_page?.[key] || 0);
        const text = document.createElement("span"); text.textContent = label;
        box.append(number, text); counts.append(box);
      });
      msg("analyticsMessage", a.privacy || "", true);
    } catch (e) { msg("analyticsMessage", e.message); }
  };

  if (!api) note.textContent = "Backend abhi connect nahi hai. Python server host karne ke baad webcontrol-config.js mein uska public URL set karna hoga.";
  else note.classList.add("hidden");

  $("loginForm").addEventListener("submit", async (event) => {
    event.preventDefault(); msg("loginMessage", "Signing in…");
    try {
      const result = await request("/api/admin/login", { method: "POST", body: JSON.stringify({ username: $("username").value, password: $("password").value }) });
      token = result.token; $("password").value = ""; showDashboard();
    } catch (e) { msg("loginMessage", e.message); }
  });
  $("settingsForm").addEventListener("submit", async (event) => {
    event.preventDefault(); msg("settingsMessage", "Saving…");
    try {
      await request("/api/admin/settings", { method: "POST", body: JSON.stringify({ site_title: $("siteTitle").value, announcement: $("announcement").value, announcement_enabled: $("announcementEnabled").checked }) });
      msg("settingsMessage", "Settings saved.", true);
    } catch (e) { msg("settingsMessage", e.message); }
  });
  $("days").addEventListener("change", loadAnalytics);
  $("logout").addEventListener("click", () => { token = ""; location.reload(); });
})();
