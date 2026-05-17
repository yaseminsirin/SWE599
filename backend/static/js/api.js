/**
 * JobSense AI — shared API helpers
 */
(function () {
  window.apiFetch = async function (url, options) {
    options = options || {};
    var headers = Object.assign({}, options.headers || {});
    if (!headers["Content-Type"] && options.body && typeof options.body === "string") {
      headers["Content-Type"] = "application/json";
    }
    var opts = Object.assign({}, options, { headers: headers });
    return fetch(url, opts);
  };

  function highlightNav() {
    var path = window.location.pathname;
    document.querySelectorAll(".nav-link[data-path]").forEach(function (a) {
      var p = a.getAttribute("data-path");
      a.classList.toggle("nav-link--active", p === path);
    });
  }

  document.addEventListener("DOMContentLoaded", highlightNav);
})();
