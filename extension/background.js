// Lit les fiches Shein une par une dans des onglets en arrière-plan, puis les envoie au site.
importScripts("extraction.js");

var file = [];
var enCours = false;
var dejaVus = {};

function pause(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }

async function site() {
  var d = await chrome.storage.local.get("site");
  return d.site || "http://localhost:8000";
}

async function envoyer(chemin, donnees) {
  var base = await site();
  var r = await fetch(base + chemin, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Vinted-Auto": "1" },
    body: JSON.stringify(donnees)
  });
  var t = await r.text();
  var j = {};
  try { j = JSON.parse(t); } catch (e) { /* rien */ }
  if (!r.ok) throw new Error(j.erreur || ("Le site a répondu " + r.status));
  return j;
}

function attendreChargement(tabId, maxMs) {
  return new Promise(function (resolve) {
    var fini = false;
    function fin() { if (!fini) { fini = true; chrome.tabs.onUpdated.removeListener(ecoute); resolve(); } }
    function ecoute(id, info) { if (id === tabId && info.status === "complete") fin(); }
    chrome.tabs.onUpdated.addListener(ecoute);
    chrome.tabs.get(tabId, function (t) { if (t && t.status === "complete") fin(); });
    setTimeout(fin, maxMs);
  });
}

async function lireOnglet(tabId) {
  var dernier = { pret: false, raison: "Page Shein non chargée." };
  for (var i = 0; i < 20; i++) {
    try {
      var res = await chrome.scripting.executeScript({ target: { tabId: tabId }, world: "MAIN", func: extraireFicheShein });
      dernier = (res && res[0] && res[0].result) || dernier;
      if (dernier.pret) return dernier;
    } catch (e) {
      dernier = { pret: false, raison: e.message };
    }
    await pause(1500);
  }
  return dernier;
}

async function traiter() {
  if (enCours) return;
  enCours = true;
  try {
    while (file.length) {
      var p = file.shift();
      var tab = null;
      try {
        tab = await chrome.tabs.create({ url: p.lien, active: false });
        await attendreChargement(tab.id, 45000);
        var fiche = await lireOnglet(tab.id);
        if (fiche.pret) {
          await envoyer("/api/shein/" + p.id, fiche);
          await chrome.tabs.remove(tab.id);
        } else if (fiche.bloque) {
          // On laisse l'onglet ouvert : il suffit de résoudre la vérification puis de cliquer sur l'icône de l'extension.
          await chrome.tabs.update(tab.id, { active: true });
          await envoyer("/api/shein/" + p.id, { erreur: "Shein demande une vérification : résous-la dans l'onglet Shein ouvert, puis clique sur « Relire »." });
        } else {
          await chrome.tabs.remove(tab.id);
          await envoyer("/api/shein/" + p.id, { erreur: fiche.raison || "Lecture impossible." });
        }
      } catch (e) {
        try { if (tab) await chrome.tabs.remove(tab.id); } catch (e2) { /* rien */ }
        try { await envoyer("/api/shein/" + p.id, { erreur: String(e.message || e) }); } catch (e3) { /* rien */ }
      }
      delete dejaVus[p.id];
      await pause(1500 + Math.random() * 2000);
    }
  } finally {
    enCours = false;
  }
}

chrome.runtime.onMessage.addListener(function (msg, sender) {
  if (msg && msg.site) chrome.storage.local.set({ site: msg.site });
  if (msg && msg.type === "lire") {
    (msg.produits || []).forEach(function (p) {
      if (p && p.id && p.lien && !dejaVus[p.id]) { dejaVus[p.id] = 1; file.push(p); }
    });
    traiter();
  }
});

// Clic sur l'icône de l'extension depuis une fiche Shein : on l'envoie au site.
chrome.action.onClicked.addListener(async function (tab) {
  var base = await site();
  if (!tab.url || !/shein\./i.test(tab.url)) {
    chrome.tabs.create({ url: base + "/#ajouter" });
    return;
  }
  var fiche = await lireOnglet(tab.id);
  if (!fiche.pret) {
    chrome.tabs.create({ url: base + "/#ajouter?erreur=" + encodeURIComponent(fiche.raison || "Lecture impossible") });
    return;
  }
  try {
    var r = await envoyer("/api/shein/brouillon", fiche);
    chrome.tabs.create({ url: base + "/#ajouter?brouillon=" + r.id });
  } catch (e) {
    chrome.tabs.create({ url: base + "/#ajouter?erreur=" + encodeURIComponent("Le site Vinted Auto ne répond pas : lance-le (raccourci sur le Bureau). " + e.message) });
  }
});
