/**
 * Alerts page — create alert + cancel all by email
 */
(function () {
  function prefillFromSearchParams() {
    var params = new URLSearchParams(window.location.search);
    var keyword = params.get("keyword") || params.get("q") || "";
    var location = params.get("location") || "";
    var employment = params.get("employment_type") || "";
    var remote = params.get("is_remote");
    var searchMode = params.get("search_mode") || "semantic";

    var keywordEl = document.getElementById("a_keyword");
    var locationEl = document.getElementById("a_location");
    var employmentEl = document.getElementById("a_employment");
    var remoteEl = document.getElementById("a_remote");

    if (keywordEl && keyword) keywordEl.value = keyword;
    if (locationEl && location) locationEl.value = location;
    if (employmentEl && employment) employmentEl.value = employment;
    if (remoteEl) remoteEl.checked = remote === "true";

    window.__alertPrefillFilters = { search_mode: searchMode };
  }

  function init() {
    prefillFromSearchParams();
    var form = document.getElementById("alertForm");
    if (form) {
      form.addEventListener("submit", async function (e) {
        e.preventDefault();
        var status = document.getElementById("alertStatus");
        if (status) status.textContent = "Creating…";

        var email =
          (document.getElementById("a_notify_email") && document.getElementById("a_notify_email").value.trim()) || "";
        if (!email) {
          if (status) status.textContent = "Email is required.";
          return;
        }

        var payload = {
          keyword: (document.getElementById("a_keyword") && document.getElementById("a_keyword").value.trim()) || "",
          location_text:
            (document.getElementById("a_location") && document.getElementById("a_location").value.trim()) || "",
          is_remote: document.getElementById("a_remote") && document.getElementById("a_remote").checked ? true : null,
          employment_type:
            (document.getElementById("a_employment") && document.getElementById("a_employment").value) || "",
          notify_email: email,
          filters: window.__alertPrefillFilters || {},
        };

        var resp = await window.apiFetch("/api/alerts/", {
          method: "POST",
          body: JSON.stringify(payload),
        });
        var data = await resp.json();
        if (!resp.ok) {
          if (status) {
            status.textContent =
              (data.notify_email && data.notify_email[0]) || data.detail || JSON.stringify(data) || "Failed";
          }
          return;
        }
        if (status) status.textContent = "Alert created.";
        form.reset();
        window.__alertPrefillFilters = {};
        if (window.history.replaceState) {
          window.history.replaceState({}, "", "/alerts/");
        }
      });
    }

    var cancelForm = document.getElementById("cancelAlertsForm");
    if (cancelForm) {
      cancelForm.addEventListener("submit", async function (e) {
        e.preventDefault();
        var status = document.getElementById("cancelAlertStatus");
        var emailEl = document.getElementById("cancel_email");
        var email = emailEl && emailEl.value.trim();
        if (!email) {
          if (status) status.textContent = "Email is required.";
          return;
        }
        if (!confirm("Cancel all alerts for " + email + "?")) return;

        if (status) status.textContent = "Cancelling alerts…";
        var submitBtn = cancelForm.querySelector('button[type="submit"]');
        if (submitBtn) submitBtn.disabled = true;

        try {
          var resp = await window.apiFetch("/api/alerts/cancel-all/", {
            method: "POST",
            body: JSON.stringify({ notify_email: email }),
          });
          var data = await resp.json();
          if (!resp.ok) {
            if (status) {
              status.textContent =
                (data.notify_email && data.notify_email[0]) || data.detail || "Could not cancel alerts.";
            }
            return;
          }
          if (status) status.textContent = data.detail || "Alerts cancelled.";
          if (emailEl) emailEl.value = "";
        } catch (err) {
          if (status) status.textContent = "Network error. Please try again.";
        } finally {
          if (submitBtn) submitBtn.disabled = false;
        }
      });
    }
  }

  document.addEventListener("DOMContentLoaded", init);
})();
