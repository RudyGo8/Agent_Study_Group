/**
 * Mermaid loader for MkDocs Material.
 *
 * Material's `navigation.instant` swaps page content without a full reload,
 * so Mermaid must be (re-)initialized after every page swap. We hook into
 * both the initial load and Material's custom `document-subscriber` event.
 *
 * The mermaid.js runtime itself is loaded via mkdocs.yml `extra_javascript`
 * with `defer`, so it's available by the time this script runs.
 */
(function () {
  function isMermaidReady() {
    return typeof window.mermaid !== 'undefined';
  }

  function renderAll() {
    if (!isMermaidReady()) return;
    try {
      window.mermaid.initialize({
        startOnLoad: false,
        theme: document.documentElement.getAttribute('data-md-color-scheme') === 'slate'
          ? 'dark'
          : 'default',
        securityLevel: 'loose',     // allow $ in labels, e.g. $web_search
        flowchart: { curve: 'basis', useMaxWidth: true },
      });
      window.mermaid.run({ querySelector: '.mermaid:not([data-processed])' });
    } catch (e) {
      console.warn('[mermaid] render failed:', e);
    }
  }

  // Re-render whenever Material swaps to a new page.
  document.addEventListener('DOMContentLoaded', renderAll);
  document$.subscribe(renderAll);   // `document$` is provided by Material

  // Re-theme when the user toggles light/dark.
  new MutationObserver(renderAll)
    .observe(document.documentElement,
      { attributes: true, attributeFilter: ['data-md-color-scheme'] });
})();
