// In-app manuals: Contents drawer, live search panel and mermaid diagrams (loaded on manual pages only).
(function () {
  if (window.miresManuals) return;
  window.miresManuals = true;

  // ---- Live search panel: Esc or a click outside the search form closes it.
  function closeSearchPanels(keep) {
    for (const panel of document.querySelectorAll(".manual-search-panel")) {
      if (!keep?.contains(panel)) panel.replaceChildren();
    }
  }

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeSearchPanels();
  });

  // ---- Contents drawer: opens from the "Contents" button; ✕, backdrop click and Esc close it.
  document.addEventListener("click", (event) => {
    closeSearchPanels(event.target.closest?.(".manual-search"));
    const opener = event.target.closest("[data-manual-drawer-open]");
    if (opener) {
      document.getElementById(opener.getAttribute("aria-controls"))?.showModal();
      return;
    }
    const closer = event.target.closest("[data-manual-drawer-close]");
    if (closer) {
      closer.closest("dialog")?.close();
      return;
    }
    // A click on the ::backdrop targets the dialog element itself.
    if (event.target.matches?.("dialog.manual-drawer")) event.target.close();
  });

  // ---- Mermaid: render pre.mermaid in the current theme; re-render when the theme toggles.
  function mermaidTheme() {
    return document.body.classList.contains("dark") ? "dark" : "default";
  }

  function renderMermaid() {
    if (typeof window.mermaid === "undefined") return;
    const nodes = [...document.querySelectorAll("pre.mermaid")];
    if (nodes.length === 0) return;
    for (const node of nodes) {
      if (node.dataset.mermaidSource === undefined) node.dataset.mermaidSource = node.textContent;
      node.removeAttribute("data-processed");
      node.textContent = node.dataset.mermaidSource;
    }
    window.mermaid.initialize({ startOnLoad: false, theme: mermaidTheme() });
    window.mermaid.run({ nodes });
  }

  let renderedTheme = null;
  function renderIfThemeChanged() {
    if (renderedTheme === mermaidTheme()) return;
    renderedTheme = mermaidTheme();
    renderMermaid();
  }

  document.addEventListener("DOMContentLoaded", renderMermaid);
  document.addEventListener("htmx:afterSettle", renderMermaid);
  new MutationObserver(renderIfThemeChanged).observe(document.body, { attributes: true, attributeFilter: ["class"] });
  renderedTheme = mermaidTheme();
  if (document.readyState !== "loading") renderMermaid();
})();
