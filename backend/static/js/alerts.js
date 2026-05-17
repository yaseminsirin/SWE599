/**
 * Alerts page — list + create + delete
 */
(function () {
  function escapeHtml(str) {
    if (str === null || str === undefined) return "";
    var div = document.createElement("div");
    div.textContent = String(str);
    return div.innerHTML;
  }

  async function loadAlerts() {
    var root = document.getElementById("alertsList");
    if (!root) return;
    root.innerHTML =
      '<div class="card card--flat"><div class="loading-state"><div class="spinner"></div><strong>Loading alerts…</strong></div></div>';

    var resp = await window.apiFetch("/api/alerts/");
    var data = await resp.json();
    if (!resp.ok) {
      root.innerHTML =
        '<div class="card"><p class="form-msg error">Failed: ' + escapeHtml(data.detail || "error") + "</p></div>";
      return;
    }
    var rows = data.results || [];
    if (rows.length === 0) {
      root.innerHTML =
        '<div class="empty-state"><strong>No alerts yet</strong><span>Create your first alert using the form above.</span></div>';
      return;
    }

    var html = rows
      .map(function (a) {
        var remoteBadge =
          a.is_remote === true
            ? '<span class="badge badge--remote">Remote</span>'
            : a.is_remote === false
              ? '<span class="badge">On-site</span>'
              : '<span class="badge">Any</span>';
        return (
          '<div class="card job-card">' +
          '<div class="alert-item">' +
          '<div class="alert-item__head">' +
          '<div><div class="alert-item__keyword">' +
          escapeHtml(a.keyword || "(no keyword)") +
          "</div>" +
          '<p class="job-card__meta">' +
          escapeHtml(a.location_text || "—") +
          " · " +
          escapeHtml(a.employment_type || "—") +
          "</p></div>" +
          '<div class="alert-item__actions">' +
          '<button type="button" class="btn btn--danger btn--sm" data-delete-id="' +
          a.id +
          '">Delete</button>' +
          "</div></div>" +
          '<div class="job-card__badges">' +
          remoteBadge +
          "</div></div></div>"
        );
      })
      .join("");
    root.innerHTML = html;

    root.querySelectorAll("[data-delete-id]").forEach(function (btn) {
      btn.addEventListener("click", async function () {
        var id = btn.getAttribute("data-delete-id");
        if (!confirm("Delete this alert?")) return;
        var r = await window.apiFetch("/api/alerts/" + id + "/", { method: "DELETE" });
        if (r.ok) loadAlerts();
      });
    });
  }

  function init() {
    var form = document.getElementById("alertForm");
    if (!form) return;

    form.addEventListener("submit", async function (e) {
      e.preventDefault();
      var status = document.getElementById("alertStatus");
      if (status) status.textContent = "Creating…";

      var payload = {
        keyword: (document.getElementById("a_keyword") && document.getElementById("a_keyword").value.trim()) || "",
        location_text:
          (document.getElementById("a_location") && document.getElementById("a_location").value.trim()) || "",
        is_remote: document.getElementById("a_remote") && document.getElementById("a_remote").checked ? true : null,
        employment_type:
          (document.getElementById("a_employment") && document.getElementById("a_employment").value) || "",
        notify_email:
          (document.getElementById("a_notify_email") && document.getElementById("a_notify_email").value.trim()) || ""
      };

      var resp = await window.apiFetch("/api/alerts/", {
        method: "POST",
        body: JSON.stringify(payload)
      });
      var data = await resp.json();
      if (!resp.ok) {
        if (status) status.textContent = data.detail || "Failed";
        return;
      }
      if (status) status.textContent = "Alert created.";
      form.reset();
      loadAlerts();
    });

    loadAlerts();
  }

  document.addEventListener("DOMContentLoaded", init);
})();
