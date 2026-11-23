// Fait le lien entre la page du site Vinted Auto et l'extension.
(function () {
  document.documentElement.setAttribute("data-extension-vinted", chrome.runtime.getManifest().version);
  window.addEventListener("message", function (ev) {
    if (ev.source !== window || !ev.data || ev.data.source !== "vinted-auto-site") return;
    if (ev.data.type === "bonjour") {
      chrome.runtime.sendMessage({ type: "site", site: location.origin });
    }
    if (ev.data.type === "lire") {
      chrome.runtime.sendMessage({ type: "lire", produits: ev.data.produits || [], site: location.origin });
    }
  });
})();
