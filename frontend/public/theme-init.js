// Apply the saved theme before the first paint (light by default), so the page never flashes the wrong one.
// A separate file (not an inline script) so the Content-Security-Policy can forbid inline scripts.
try {
  var t = localStorage.getItem("pv-theme");
  document.documentElement.dataset.theme = t === "dark" ? "dark" : "light";
} catch (e) {
  document.documentElement.dataset.theme = "light";
}
