/**
 * Search page — semantic search only + inline alert creation
 */
(function () {
  var PAGE_SIZE = 5;

  function escapeHtml(str) {
    if (!str) return "";
    var div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  function sanitizeJobDescriptionHtml(html) {
    if (!html || typeof html !== "string") return "";
    var parser = new DOMParser();
    var doc = parser.parseFromString(html, "text/html");
    var forbidden = {
      SCRIPT: 1,
      STYLE: 1,
      IFRAME: 1,
      OBJECT: 1,
      EMBED: 1,
      FORM: 1,
      INPUT: 1,
      BUTTON: 1,
      SELECT: 1,
      TEXTAREA: 1,
      LINK: 1,
      META: 1,
      BASE: 1,
      SVG: 1,
      MATH: 1,
    };

    function stripDangerousAttrs(el) {
      var tag = el.tagName;
      var removeNames = [];
      var i;
      var attr;
      var n;
      var v;
      for (i = 0; i < el.attributes.length; i++) {
        attr = el.attributes[i];
        n = attr.name.toLowerCase();
        v = attr.value;
        if (n.startsWith("on")) removeNames.push(attr.name);
        else if (n === "style" || n === "id") removeNames.push(attr.name);
        else if ((n === "href" || n === "src" || n === "xlink:href") && tag !== "A") removeNames.push(attr.name);
        else if (n === "src" || n === "srcset" || n === "poster") removeNames.push(attr.name);
        else if (tag === "A" && n === "href") {
          if (/^\s*javascript:/i.test(v) || /^\s*data:/i.test(v) || /^\s*vbscript:/i.test(v))
            removeNames.push(attr.name);
        }
      }
      for (i = 0; i < removeNames.length; i++) el.removeAttribute(removeNames[i]);
      if (tag === "A" && el.getAttribute("href")) {
        if (!el.getAttribute("rel")) el.setAttribute("rel", "noopener noreferrer");
        if (!el.getAttribute("target")) el.setAttribute("target", "_blank");
      }
    }

    function walk(node) {
      var child = node.firstChild;
      while (child) {
        var next = child.nextSibling;
        if (child.nodeType === 1) {
          if (forbidden[child.tagName]) {
            child.remove();
          } else {
            stripDangerousAttrs(child);
            walk(child);
          }
        } else if (child.nodeType === 8) {
          child.remove();
        }
        child = next;
      }
    }

    walk(doc.body);
    return doc.body.innerHTML;
  }

  function buildJobBadges(job) {
    var parts = [];

    if (job.source_label) {
      parts.push('<span class="badge badge--source">' + escapeHtml(job.source_label) + "</span>");
    }

    var remoteText = (job.remote_label || (job.is_remote ? "Remote" : "On-site")).trim();
    if (remoteText) {
      parts.push(
        '<span class="badge ' +
          (job.is_remote ? "badge--remote" : "badge--onsite") +
          '">' +
          escapeHtml(remoteText) +
          "</span>"
      );
    }

    var empLabel = (job.employment_type_label || "").trim();
    if (empLabel && empLabel !== "—" && empLabel !== "-") {
      parts.push('<span class="badge badge--type">' + escapeHtml(empLabel) + "</span>");
    }

    var salary = (job.salary_display || "").trim();
    if (salary) {
      parts.push('<span class="badge badge--salary">' + escapeHtml(salary) + "</span>");
    }

    var category = (job.category_label || "").trim();
    if (category && category.indexOf("[") === -1 && category.indexOf("Code") === -1) {
      parts.push('<span class="badge badge--category">' + escapeHtml(category) + "</span>");
    }

    return parts.join("");
  }

  function renderJobs(results) {
    var root = document.getElementById("jobResults");
    if (!root) return;

    if (!results || results.length === 0) {
      root.innerHTML =
        '<div class="empty-state" id="emptyAfterSearch"><strong>No jobs found</strong><span>Try a different search query or filters.</span></div>';
      return;
    }

    var html = results
      .map(function (job) {
        var title = escapeHtml(job.title || "");
        var company = escapeHtml(job.company_name || "");
        var loc = escapeHtml(job.location_display || job.location_text || "");
        var desc = job.description_clean || "";
        var snippet = sanitizeJobDescriptionHtml(desc);
        var url = job.job_url || "#";
        var badges = buildJobBadges(job);
        return (
          '<article class="job-card">' +
          '<h3 class="job-card__title">' +
          title +
          "</h3>" +
          '<p class="job-card__meta">' +
          company +
          " · " +
          loc +
          "</p>" +
          (badges ? '<div class="job-card__badges">' + badges + "</div>" : "") +
          '<div class="job-card__snippet job-card__snippet--html">' +
          snippet +
          "</div>" +
          '<a class="btn btn--primary btn--sm" href="' +
          escapeHtml(url) +
          '" target="_blank" rel="noopener noreferrer">View job</a>' +
          "</article>"
        );
      })
      .join("");

    root.innerHTML = '<div class="job-grid">' + html + "</div>";
  }

  function renderPagination(page, totalCount) {
    var nav = document.getElementById("jobPagination");
    if (!nav) return;

    var totalPages = Math.max(1, Math.ceil(totalCount / PAGE_SIZE));
    if (totalCount === 0) {
      nav.hidden = true;
      nav.innerHTML = "";
      return;
    }

    nav.hidden = false;
    var prevDisabled = page <= 1;
    var nextDisabled = page >= totalPages;
    var start = (page - 1) * PAGE_SIZE + 1;
    var end = Math.min(page * PAGE_SIZE, totalCount);

    nav.innerHTML =
      '<button type="button" class="btn btn--ghost pagination__btn" data-page="prev"' +
      (prevDisabled ? " disabled" : "") +
      ">Previous</button>" +
      '<span class="pagination__info">Page ' +
      page +
      " of " +
      totalPages +
      " · " +
      start +
      "–" +
      end +
      " of " +
      totalCount +
      "</span>" +
      '<button type="button" class="btn btn--ghost pagination__btn" data-page="next"' +
      (nextDisabled ? " disabled" : "") +
      ">Next</button>";

    nav.querySelectorAll(".pagination__btn").forEach(function (btn) {
      btn.addEventListener("click", function () {
        if (btn.disabled) return;
        var target = btn.getAttribute("data-page");
        if (target === "prev") loadJobs(page - 1);
        else if (target === "next") loadJobs(page + 1);
      });
    });
  }

  function showLoading() {
    var root = document.getElementById("jobResults");
    if (!root) return;
    root.innerHTML =
      '<div class="loading-state" id="searchLoading"><div class="spinner"></div><strong>Loading…</strong><span>Finding semantically similar jobs.</span></div>';
    var nav = document.getElementById("jobPagination");
    if (nav) nav.hidden = true;
  }

  function getSearchValues() {
    return {
      query: (document.getElementById("query") && document.getElementById("query").value.trim()) || "",
      location: (document.getElementById("location") && document.getElementById("location").value.trim()) || "",
      employment:
        (document.getElementById("employment_type") && document.getElementById("employment_type").value) || "",
      remoteChecked: !!(document.getElementById("is_remote") && document.getElementById("is_remote").checked),
    };
  }

  function buildRequest(page) {
    var values = getSearchValues();
    var params = new URLSearchParams();
    params.set("page", String(page));
    params.set("page_size", String(PAGE_SIZE));
    params.set("q", values.query);
    if (values.location) params.set("location", values.location);
    if (values.employment) params.set("employment_type", values.employment);
    if (values.remoteChecked) params.set("is_remote", "true");
    return { endpoint: "/api/jobs/semantic-search/", params: params, query: values.query };
  }

  function buildAlertPayload() {
    var values = getSearchValues();
    return {
      keyword: values.query,
      location_text: values.location,
      is_remote: values.remoteChecked ? true : null,
      employment_type: values.employment,
      notify_email: (document.getElementById("alertEmail") && document.getElementById("alertEmail").value.trim()) || "",
      filters: { search_mode: "semantic" },
    };
  }

  var loadJobs;

  function init() {
    var form = document.getElementById("searchForm");
    if (!form) return;

    var currentPage = 1;
    var alertPanel = document.getElementById("alertPanel");
    var alertQueryPreview = document.getElementById("alertQueryPreview");
    var alertFormStatus = document.getElementById("alertFormStatus");

    function openAlertPanel() {
      var values = getSearchValues();
      if (!values.query) {
        if (alertFormStatus) alertFormStatus.textContent = "Enter a search query first.";
        if (alertPanel) alertPanel.hidden = false;
        return;
      }
      if (alertQueryPreview) alertQueryPreview.textContent = values.query;
      if (alertFormStatus) alertFormStatus.textContent = "";
      if (alertPanel) {
        alertPanel.hidden = false;
        var emailEl = document.getElementById("alertEmail");
        if (emailEl) emailEl.focus();
      }
    }

    loadJobs = async function (page) {
      currentPage = page;
      var statusEl = document.getElementById("searchStatus");
      var req = buildRequest(page);

      if (!req.query) {
        if (statusEl) statusEl.textContent = "Enter a search query to run semantic search.";
        document.getElementById("jobResults").innerHTML =
          '<div class="empty-state"><strong>Start with a search query</strong><span>Describe the role you want, then click Search Jobs.</span></div>';
        renderPagination(1, 0);
        return;
      }

      showLoading();
      try {
        var resp = await window.apiFetch(req.endpoint + "?" + req.params.toString());
        var data = await resp.json();
        if (!resp.ok) {
          document.getElementById("jobResults").innerHTML =
            '<div class="empty-state"><strong>Request failed</strong><span>' +
            escapeHtml(data.detail || "Error") +
            "</span></div>";
          if (statusEl) statusEl.textContent = data.detail || "Error";
          renderPagination(1, 0);
          return;
        }
        var results = data.results || [];
        var total = data.count != null ? data.count : results.length;
        renderJobs(results);
        renderPagination(page, total);
        if (statusEl) {
          statusEl.textContent = total + " semantically matched job" + (total === 1 ? "" : "s") + ".";
        }
      } catch (err) {
        document.getElementById("jobResults").innerHTML =
          '<div class="empty-state"><strong>Network error</strong><span>Please try again.</span></div>';
        if (statusEl) statusEl.textContent = "Network error";
        renderPagination(1, 0);
      }
    };

    form.addEventListener("submit", function (e) {
      e.preventDefault();
      loadJobs(1);
    });

    var alertBtn = document.getElementById("createAlertBtn");
    if (alertBtn) {
      alertBtn.addEventListener("click", openAlertPanel);
    }

    var alertSubmitBtn = document.getElementById("alertSubmitBtn");
    if (alertSubmitBtn) {
      alertSubmitBtn.addEventListener("click", async function () {
        var values = getSearchValues();
        if (!values.query) {
          if (alertFormStatus) alertFormStatus.textContent = "Enter a search query first.";
          return;
        }

        var payload = buildAlertPayload();
        if (!payload.notify_email) {
          if (alertFormStatus) alertFormStatus.textContent = "Email is required.";
          return;
        }

        if (alertFormStatus) alertFormStatus.textContent = "Creating alert…";
        alertSubmitBtn.disabled = true;

        try {
          var resp = await window.apiFetch("/api/alerts/", {
            method: "POST",
            body: JSON.stringify(payload),
          });
          var data = await resp.json();
          if (!resp.ok) {
            if (alertFormStatus) {
              alertFormStatus.textContent =
                (data.notify_email && data.notify_email[0]) || data.detail || "Could not create alert.";
            }
            return;
          }
          if (alertFormStatus) alertFormStatus.textContent = "Alert created. You will receive email updates for this search.";
          var emailEl = document.getElementById("alertEmail");
          if (emailEl) emailEl.value = "";
        } catch (err) {
          if (alertFormStatus) alertFormStatus.textContent = "Network error. Please try again.";
        } finally {
          alertSubmitBtn.disabled = false;
        }
      });
    }
  }

  document.addEventListener("DOMContentLoaded", init);
})();
