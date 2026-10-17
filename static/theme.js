/*
 * Theme switch: Light (white), Dark (black) or System.
 *
 * Loaded in the <head> of every page (see templates/base.html) so the right
 * theme is applied BEFORE the page is painted -- otherwise a student who chose
 * light would see a dark flash on every page load.
 *
 * What is stored is the student's PREFERENCE: "light", "dark" or "system".
 * What is applied to <html data-theme="..."> is always the RESOLVED theme,
 * "light" or "dark". When the preference is "system" the resolved theme
 * follows the operating system's setting and changes live if the student
 * changes it while Nocturna is open.
 *
 * The preference is remembered in the browser (localStorage), so it survives
 * logging out and closing the tab. It is per browser, not per account.
 */
(function () {
  var KEY = "nocturna-theme";
  var DEFAULT_PREF = "system"; // used until the student picks one
  var root = document.documentElement;
  var media = window.matchMedia ? window.matchMedia("(prefers-color-scheme: dark)") : null;

  function saved() {
    try {
      var v = localStorage.getItem(KEY);
      return v === "light" || v === "dark" || v === "system" ? v : null;
    } catch (e) {
      return null; // storage blocked (private mode etc.) -- just don't remember
    }
  }

  var preference = saved() || DEFAULT_PREF;

  function resolve(pref) {
    if (pref === "system") return media && media.matches ? "dark" : "light";
    return pref;
  }

  function apply() {
    var theme = resolve(preference);
    root.setAttribute("data-theme", theme);
    root.setAttribute("data-theme-pref", preference);
    var btn = document.getElementById("theme-toggle");
    if (btn) {
      var next = theme === "light" ? "dark" : "light";
      btn.setAttribute("aria-label", "Switch to " + next + " theme");
      btn.setAttribute("title", "Switch to " + next + " theme");
    }
  }

  function set(pref) {
    if (pref !== "light" && pref !== "dark" && pref !== "system") return;
    preference = pref;
    apply();
    try { localStorage.setItem(KEY, pref); } catch (e) { /* ignore */ }
  }

  // Lets other scripts (the Settings dialog) read and change the theme.
  window.nocturnaTheme = {
    get: function () { return preference; },       // "light" | "dark" | "system"
    resolved: function () { return resolve(preference); },
    set: set,
  };

  // Follow the operating system while the preference is "system".
  if (media) {
    var onChange = function () { if (preference === "system") apply(); };
    if (media.addEventListener) media.addEventListener("change", onChange);
    else if (media.addListener) media.addListener(onChange);
  }

  // Runs immediately, while the browser is still reading the <head>.
  apply();

  document.addEventListener("DOMContentLoaded", function () {
    var btn = document.getElementById("theme-toggle");
    if (!btn) return;
    apply(); // now the button exists, set its label
    btn.addEventListener("click", function () {
      set(resolve(preference) === "light" ? "dark" : "light");
    });
  });
})();
