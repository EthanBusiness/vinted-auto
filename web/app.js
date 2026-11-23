/* Vinted Auto : interface du site (aucune bibliothèque, juste du JavaScript). */
"use strict";

var ETAT = { role: null, comptes: [], minuteur: null };
var COULEURS = { 1: "Noir", 2: "Marron", 3: "Gris", 4: "Beige", 5: "Rose", 6: "Violet", 7: "Rouge", 8: "Jaune", 9: "Bleu", 10: "Vert", 11: "Orange", 12: "Blanc", 13: "Argenté", 14: "Doré", 15: "Multicolore", 16: "Kaki", 17: "Turquoise", 20: "Crème", 21: "Abricot", 22: "Corail", 23: "Bordeaux", 25: "Lila", 26: "Bleu clair", 27: "Marine", 28: "Vert foncé", 29: "Moutarde", 30: "Menthe" };
var ETATS = { 6: "Neuf avec étiquette", 1: "Neuf sans étiquette", 2: "Très bon état", 3: "Bon état", 4: "Satisfaisant" };
var COLIS = { 1: "Petit", 2: "Moyen", 3: "Grand" };
var ETAPES = { lecture: "Lecture Shein…", generation: "Rédaction…", a_photographier: "À photographier", prete: "Prête à publier", envoi: "Envoi…", en_file: "En file Scalency", publiee: "Publiée", echec: "Échec", annulee: "Annulée" };

// ------------------------------------------------------------ outils
function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
function $(sel, el) { return (el || document).querySelector(sel); }
function $$(sel, el) { return Array.prototype.slice.call((el || document).querySelectorAll(sel)); }
function euros(n) { return (Math.round((n || 0) * 100) / 100).toLocaleString("fr-FR", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " €"; }
function img(nom) { return nom ? "/fichiers/" + encodeURIComponent(nom) : ""; }

function toast(msg, ms) {
  var t = $("#toast"); t.textContent = msg; t.classList.add("vu");
  clearTimeout(t._m); t._m = setTimeout(function () { t.classList.remove("vu"); }, ms || 3500);
}

function api(methode, chemin, corps, brut) {
  var opts = { method: methode, headers: { "X-Vinted-Auto": "1" }, credentials: "same-origin" };
  if (brut) { opts.body = brut; opts.headers["Content-Type"] = brut.type || "application/octet-stream"; }
  else if (corps !== undefined) { opts.body = JSON.stringify(corps); opts.headers["Content-Type"] = "application/json"; }
  return fetch(chemin, opts).then(function (r) {
    return r.text().then(function (t) {
      var j = {}; try { j = t ? JSON.parse(t) : {}; } catch (e) { j = { erreur: "Réponse illisible du site." }; }
      if (r.status === 401) { ETAT.role = null; afficherConnexion(); throw new Error(j.erreur || "Connecte-toi."); }
      if (!r.ok) throw new Error(j.erreur || ("Erreur " + r.status));
      return j;
    });
  });
}

function copier(texte, quoi) {
  function ok() { toast((quoi || "Texte") + " copié ✔"); }
  if (navigator.clipboard && window.isSecureContext) return navigator.clipboard.writeText(texte).then(ok, function () { copierVieux(texte); ok(); });
  copierVieux(texte); ok();
}
function copierVieux(texte) {
  var t = document.createElement("textarea"); t.value = texte; t.style.position = "fixed"; t.style.opacity = "0";
  document.body.appendChild(t); t.select(); try { document.execCommand("copy"); } catch (e) { /* rien */ } document.body.removeChild(t);
}

function extensionPresente() { return !!document.documentElement.getAttribute("data-extension-vinted"); }
function envoyerAExtension(produits) {
  if (produits && produits.length) window.postMessage({ source: "vinted-auto-site", type: "lire", produits: produits }, location.origin);
}

function badge(statut) { return '<span class="badge b-' + esc(statut) + '">' + esc(ETAPES[statut] || statut) + "</span>"; }

function lireFichier(input, rappel) {
  input.addEventListener("change", function () { if (input.files && input.files[0]) rappel(input.files[0]); input.value = ""; });
}

// Zone « glisser-déposer » d'une photo
function zoneDepot(el, rappel) {
  var input = document.createElement("input"); input.type = "file"; input.accept = "image/jpeg,image/png,image/webp"; input.style.display = "none";
  el.appendChild(input);
  el.addEventListener("click", function (e) { if (e.target.tagName !== "BUTTON") input.click(); });
  lireFichier(input, rappel);
  el.addEventListener("dragover", function (e) { e.preventDefault(); el.classList.add("survol"); });
  el.addEventListener("dragleave", function () { el.classList.remove("survol"); });
  el.addEventListener("drop", function (e) {
    e.preventDefault(); el.classList.remove("survol");
    var f = e.dataTransfer.files && e.dataTransfer.files[0];
    if (f) rappel(f); else toast("Dépose un fichier image (télécharge d'abord l'image de Gemini).");
  });
}

// ------------------------------------------------------------ navigation
function routes() {
  if (ETAT.role === "employee") return [["photos", "📸 Photos"]];
  return [["articles", "📋 Articles"], ["ajouter", "➕ Ajouter"], ["photos", "📸 Photos"], ["comptes", "👗 Comptes"], ["reglages", "⚙️ Réglages"]];
}

function lireHash() {
  var h = location.hash.replace(/^#/, "") || (ETAT.role === "employee" ? "photos" : "articles");
  var q = {}; var parts = h.split("?");
  (parts[1] || "").split("&").forEach(function (kv) { if (kv) { var p = kv.split("="); q[decodeURIComponent(p[0])] = decodeURIComponent(p[1] || ""); } });
  var segs = parts[0].split("/");
  return { page: segs[0], id: segs[1], q: q };
}

function rendreMenu(page) {
  $("#menu").innerHTML = routes().map(function (r) { return '<a href="#' + r[0] + '" class="' + (page === r[0] ? "actif" : "") + '">' + r[1] + "</a>"; }).join("");
}

function naviguer() {
  clearInterval(ETAT.minuteur);
  if (!ETAT.role) return;
  var h = lireHash();
  var pages = { articles: pageArticles, ajouter: pageAjouter, article: pageArticle, photos: pagePhotos, comptes: pageComptes, reglages: pageReglages, extension: pageExtension };
  if (ETAT.role === "employee" && h.page !== "photos") { location.hash = "#photos"; return; }
  rendreMenu(h.page === "article" ? "articles" : h.page);
  (pages[h.page] || pageArticles)(h);
  window.scrollTo(0, 0);
}

function rafraichirEtat() {
  return api("GET", "/api/etat").then(function (e) {
    ETAT.role = e.role; ETAT.etat = e;
    $("#cout").textContent = e.role === "admin" ? "Coût IA aujourd'hui : " + euros(e.cout_jour_eur) : "";
    var b = "";
    if (e.role === "admin") {
      var manque = [];
      if (!e.cles.ANTHROPIC_API_KEY) manque.push("clé Claude");
      if (!e.cles.SCALENCY_API_KEY) manque.push("clé Scalency");
      if (!e.cles.SUPABASE_URL || !e.cles.SUPABASE_KEY) manque.push("Supabase (photos)");
      if (manque.length) b += '<div class="bandeau">À faire une seule fois : remplir ' + esc(manque.join(", ")) + ' dans <a href="#reglages">Réglages</a>.</div>';
      if (e.local && !extensionPresente()) b += '<div class="bandeau">L\'extension « lecteur Shein » n\'est pas installée dans ce navigateur : <a href="#extension">l\'installer (2 minutes)</a>.</div>';
    }
    $("#bandeau").innerHTML = b;
    return e;
  });
}

// Relance la lecture des fiches en attente (si le navigateur a été fermé entre-temps)
function relancerLectures() {
  if (ETAT.role !== "admin" || !extensionPresente()) return;
  api("GET", "/api/a-lire").then(function (r) { envoyerAExtension(r.produits); }).catch(function () { /* rien */ });
}

// ------------------------------------------------------------ connexion (accès à distance)
function afficherConnexion() {
  $("#menu").innerHTML = ""; $("#bandeau").innerHTML = ""; $("#cout").textContent = "";
  $("#page").innerHTML = '<div class="carte connexion"><h1>Connexion</h1><p class="aide">Entre ton mot de passe Vinted Auto.</p>' +
    '<form id="f"><label>Mot de passe</label><input type="password" id="mdp" autofocus><p id="e" class="erreur"></p>' +
    '<button class="principal gros" type="submit">Se connecter</button></form></div>';
  $("#f").addEventListener("submit", function (ev) {
    ev.preventDefault();
    api("POST", "/api/connexion", { mot_de_passe: $("#mdp").value }).then(function () { return demarrer(); })
      .catch(function (e) { $("#e").textContent = e.message; });
  });
}

// ------------------------------------------------------------ page : articles (tableau de bord)
var FILTRES = { statut: "", compte: "" };
function pageArticles() {
  var groupes = [["", "Tout"], ["lecture,generation", "En préparation"], ["a_photographier", "À photographier"], ["prete", "Prêtes"], ["en_file,envoi", "En file"], ["publiee", "Publiées"], ["echec", "Échecs"]];
  $("#page").innerHTML = '<div class="ligne"><h1 class="etire">Articles</h1><a class="bouton" href="#ajouter">➕ Ajouter des liens Shein</a></div>' +
    '<div class="compteurs" id="compteurs"></div>' +
    '<div class="filtres">' + groupes.map(function (g) { return '<button class="puce ' + (FILTRES.statut === g[0] ? "actif" : "") + '" data-s="' + g[0] + '">' + g[1] + "</button>"; }).join("") +
    '<select id="fc" style="width:auto"><option value="">Tous les comptes</option></select></div>' +
    '<div class="ligne" style="margin-bottom:10px"><button id="toutes">Cocher les prêtes</button><button class="principal" id="pub">🚀 Publier la sélection</button><span class="aide" id="sel"></span></div>' +
    '<div class="liste" id="liste"><p class="vide">Chargement…</p></div>';
  $$(".puce").forEach(function (b) { b.onclick = function () { FILTRES.statut = b.dataset.s; pageArticles(); }; });
  chargerComptes().then(function () {
    $("#fc").innerHTML += ETAT.comptes.filter(function (c) { return c.relie; }).map(function (c) { return '<option value="' + esc(c.id) + '"' + (FILTRES.compte === c.id ? " selected" : "") + ">" + esc(c.login) + "</option>"; }).join("");
  });
  $("#fc").onchange = function () { FILTRES.compte = this.value; charger(); };
  var coches = {};
  function majSel() { var n = Object.keys(coches).length; $("#sel").textContent = n ? n + " sélectionnée(s)" : ""; }
  function charger() {
    var q = []; if (FILTRES.statut) q.push("statut=" + FILTRES.statut); if (FILTRES.compte) q.push("compte=" + encodeURIComponent(FILTRES.compte));
    api("GET", "/api/annonces?" + q.join("&")).then(function (r) {
      if (!$("#liste")) return;
      var cpt = (ETAT.etat && ETAT.etat.compteurs) || {};
      $("#compteurs").innerHTML = ["a_photographier", "prete", "en_file", "publiee", "echec"].map(function (s) { return "<div><b>" + (cpt[s] || 0) + "</b>" + ETAPES[s] + "</div>"; }).join("");
      if (!r.annonces.length) { $("#liste").innerHTML = '<p class="vide">Rien ici pour l\'instant. <a href="#ajouter">Ajoute des liens Shein</a>.</p>'; return; }
      $("#liste").innerHTML = r.annonces.map(function (a) {
        var info = a.erreur ? '<div class="erreur">' + esc(a.erreur) + "</div>" : (a.job_info && a.statut === "en_file" ? '<div class="m">' + esc(a.job_info) + "</div>" : "");
        return '<div class="item" data-id="' + a.id + '"><input type="checkbox" class="coche" data-id="' + a.id + '"' + (coches[a.id] ? " checked" : "") + ">" +
          (a.image ? '<img src="' + esc(a.image) + '" loading="lazy" referrerpolicy="no-referrer">' : '<div class="vignette"></div>') +
          '<div><div class="t">' + esc(a.titre) + '</div><div class="m">' + esc(a.compte) + (a.prix ? " · " + euros(a.prix) : "") + (a.taille ? " · taille " + esc(a.taille) : "") + "</div>" + info + "</div>" +
          "<div>" + badge(a.statut) + "</div></div>";
      }).join("");
      $$(".item").forEach(function (el) {
        el.onclick = function (e) { if (e.target.classList.contains("coche")) return; location.hash = "#article/" + el.dataset.id; };
      });
      $$(".coche").forEach(function (c) { c.onchange = function () { if (c.checked) coches[c.dataset.id] = 1; else delete coches[c.dataset.id]; majSel(); }; });
      ETAT.derniere = r.annonces;
    }).catch(function (e) { if ($("#liste")) $("#liste").innerHTML = '<p class="erreur">' + esc(e.message) + "</p>"; });
  }
  $("#toutes").onclick = function () { (ETAT.derniere || []).forEach(function (a) { if (a.statut === "prete") coches[a.id] = 1; }); $$(".coche").forEach(function (c) { c.checked = !!coches[c.dataset.id]; }); majSel(); };
  $("#pub").onclick = function () {
    var ids = Object.keys(coches).map(Number);
    if (!ids.length) return toast("Coche d'abord les annonces à publier.");
    if (!confirm("Publier " + ids.length + " annonce(s) sur Vinted via Scalency ?\nElles seront étalées dans le temps sur chaque compte.")) return;
    api("POST", "/api/publier", { ids: ids }).then(function (r) { toast(r.message, 6000); coches = {}; majSel(); setTimeout(charger, 1500); }).catch(function (e) { toast(e.message, 6000); });
  };
  charger();
  ETAT.minuteur = setInterval(function () { rafraichirEtat().then(charger); }, 8000);
}

// ------------------------------------------------------------ page : ajouter
function chargerComptes() {
  return api("GET", "/api/comptes").then(function (r) { ETAT.comptes = r.comptes; return r.comptes; });
}

function casesComptes(comptes) {
  var dispo = comptes.filter(function (c) { return c.relie && c.actif; });
  if (!dispo.length) return '<p class="erreur">Aucun compte Vinted relié trouvé. Remplis ta clé Scalency dans <a href="#reglages">Réglages</a>, puis clique sur « Mettre à jour la liste » dans <a href="#comptes">Comptes</a>.</p>';
  return '<div class="cases">' + dispo.map(function (c) {
    var avert = (!c.fond_fichier || !c.modele_fichier) ? ' <span title="Pas encore de fond ou de modèle pour ce compte">⚠️</span>' : "";
    return '<label><input type="checkbox" class="cc" value="' + esc(c.id) + '"> ' + esc(c.login) + avert + "</label>";
  }).join("") + '</div><p class="aide">⚠️ = ce compte n\'a pas encore de fond ou de modèle (<a href="#comptes">les ajouter</a>).</p>';
}
function brancherCases() {
  $$(".cc").forEach(function (c) { c.onchange = function () { c.parentNode.classList.toggle("coche", c.checked); }; });
}
function comptesCoches() { return $$(".cc").filter(function (c) { return c.checked; }).map(function (c) { return c.value; }); }

function pageAjouter(h) {
  if (h.q.brouillon) return pageBrouillon(h.q.brouillon);
  var ext = extensionPresente();
  $("#page").innerHTML = '<h1>Ajouter des articles Shein</h1>' +
    (h.q.erreur ? '<div class="carte erreur">' + esc(h.q.erreur) + "</div>" : "") +
    '<div class="carte"><label>1. Colle tes liens Shein (un par ligne)</label>' +
    '<textarea id="liens" rows="7" placeholder="https://fr.shein.com/....-p-12345678.html\nhttps://fr.shein.com/....-p-87654321.html M"></textarea>' +
    '<p class="aide">Astuce : ajoute la taille après le lien (ex : <code>…html M</code>) si tu la connais. Sinon tu la choisiras après.</p>' +
    '<label>2. Sur quel(s) compte(s) Vinted ?</label><div id="comptes">Chargement…</div>' +
    '<div class="ligne" style="margin-top:16px"><button class="principal gros" id="go">✨ Lancer</button>' +
    (ext ? '<span class="aide ok">Extension « lecteur Shein » : OK ✔</span>' : '<span class="erreur">L\'extension n\'est pas installée : <a href="#extension">l\'installer</a> (sinon la lecture Shein ne peut pas marcher).</span>') +
    '</div><p id="res"></p></div>' +
    '<div class="carte"><h2>Autre façon, depuis Shein</h2><p class="aide">Quand tu es sur une fiche Shein, clique sur l\'icône de l\'extension Vinted Auto (en haut à droite de Chrome) : la fiche arrive ici avec ton prix et la taille que tu as choisie.</p></div>';
  chargerComptes().then(function (cs) { $("#comptes").innerHTML = casesComptes(cs); brancherCases(); });
  $("#go").onclick = function () {
    var b = this; b.disabled = true;
    api("POST", "/api/importer", { liens: $("#liens").value, comptes: comptesCoches() }).then(function (r) {
      envoyerAExtension(r.produits);
      toast(r.produits.length + " article(s) en préparation : Chrome ouvre les fiches Shein en arrière-plan.", 6000);
      FILTRES.statut = ""; location.hash = "#articles";
    }).catch(function (e) { $("#res").innerHTML = '<span class="erreur">' + esc(e.message) + "</span>"; b.disabled = false; });
  };
}

function pageBrouillon(id) {
  $("#page").innerHTML = '<h1>Nouvel article depuis Shein</h1><div id="b" class="carte">Chargement…</div>';
  Promise.all([api("GET", "/api/brouillons/" + id), chargerComptes()]).then(function (res) {
    var d = res[0], f = d.fiche;
    var tailles = (f.tailles || []).map(function (t) { return t.taille; });
    $("#b").innerHTML = '<div class="ligne" style="align-items:flex-start">' + (f.images[0] ? '<img class="vignette" style="width:110px;height:146px" src="' + esc(f.images[0]) + '" referrerpolicy="no-referrer">' : "") +
      '<div class="etire"><h2>' + esc(f.titre) + '</h2><p class="aide">' + esc(f.couleur) + " · " + esc(f.prix_texte || euros(f.prix)) + "</p></div></div>" +
      "<label>Taille</label><select id=\"taille\"><option value=\"\">— à choisir plus tard —</option>" + tailles.map(function (t) { return "<option" + (t === d.taille || ("(" + t + ")") === d.taille ? " selected" : "") + ">" + esc(t) + "</option>"; }).join("") + "</select>" +
      "<label>Sur quel(s) compte(s) Vinted ?</label>" + casesComptes(res[1]) +
      '<div class="ligne" style="margin-top:16px"><button class="principal gros" id="go">✨ Créer les annonces</button></div><p id="res"></p>';
    if (d.taille && !$("#taille").value) {
      var m = /\(([^)]+)\)/.exec(d.taille); var v = m ? m[1] : d.taille;
      $$("#taille option").forEach(function (o) { if (o.value === v) o.selected = true; });
    }
    brancherCases();
    $("#go").onclick = function () {
      api("POST", "/api/brouillons/" + id + "/valider", { comptes: comptesCoches(), taille: $("#taille").value }).then(function () {
        toast("C'est parti : l'annonce est en cours de rédaction."); location.hash = "#articles";
      }).catch(function (e) { $("#res").innerHTML = '<span class="erreur">' + esc(e.message) + "</span>"; });
    };
  }).catch(function (e) { $("#b").innerHTML = '<p class="erreur">' + esc(e.message) + '</p><a href="#articles">Retour aux articles</a>'; });
}

// ------------------------------------------------------------ page : un article
function pageArticle(h) {
  $("#page").innerHTML = '<p><a href="#articles">← Articles</a></p><div id="a">Chargement…</div>';
  var id = h.id;
  function charger() { return api("GET", "/api/annonces/" + id).then(rendre).catch(function (e) { $("#a").innerHTML = '<p class="erreur">' + esc(e.message) + "</p>"; }); }
  function rendre(a) {
    if (!$("#a") || lireHash().id !== String(id)) return;
    var f = a.fiche || {};
    var envoyee = ["envoi", "en_file", "publiee"].indexOf(a.statut) >= 0;
    var enCours = a.statut === "lecture" || a.statut === "generation";
    var tailles = (f.tailles || []).map(function (t) { return t.taille; });
    var liensPhotos = (f.images || []).join("\n");
    var html = '<div class="ligne"><h1 class="etire">' + esc(a.titre) + "</h1>" + badge(a.statut) + "</div>" +
      '<p class="aide">Compte : <b>' + esc(a.compte) + "</b>" + (a.lien ? ' · <a href="' + esc(a.lien) + '" target="_blank" rel="noopener">Fiche Shein</a>' : "") + (f.prix ? " · prix Shein : " + esc(f.prix_texte || euros(f.prix)) : "") + (a.cout_eur ? " · coût IA : " + euros(a.cout_eur) : "") + "</p>" +
      (a.erreur ? '<div class="carte erreur">' + esc(a.erreur) + (a.statut === "echec" && a.lecture_erreur ? ' <button id="relire">🔄 Relire la fiche Shein</button>' : "") + "</div>" : "") +
      (a.job_info && (a.statut === "en_file" || a.statut === "publiee") ? '<div class="carte">Scalency : ' + esc(a.job_info) + (a.vinted_id ? " · annonce Vinted n°" + esc(a.vinted_id) : "") + "</div>" : "") +
      (enCours ? '<div class="carte">⏳ ' + esc(ETAPES[a.statut]) + ' Cette page se met à jour toute seule.' + (a.statut === "lecture" && !extensionPresente() ? ' <span class="erreur">L\'extension n\'est pas installée : <a href="#extension">l\'installer</a>.</span>' : "") + "</div>" : "");
    if (!enCours && f.titre) {
      html += '<div class="grille2"><div>' +
        '<div class="carte"><div class="ligne"><h2 class="etire">Description Vinted</h2><button id="copierTout">📋 Copier titre + description</button></div>' +
        '<label>Titre</label><input id="titre" maxlength="100" value="' + esc(a.titre) + '"' + (envoyee ? " disabled" : "") + ">" +
        '<label>Description</label><textarea id="description" rows="9"' + (envoyee ? " disabled" : "") + ">" + esc(a.description) + "</textarea>" +
        '<div class="grille2"><div><label>Prix (€)</label><input id="prix" type="number" step="0.5" min="1" value="' + esc(a.prix) + '"' + (envoyee ? " disabled" : "") + "></div>" +
        "<div><label>Taille</label><select id=\"taille\"" + (envoyee ? " disabled" : "") + "><option value=\"\">— à choisir —</option>" + tailles.map(function (t) { return "<option" + (t === a.taille ? " selected" : "") + ">" + esc(t) + "</option>"; }).join("") + "</select>" + (a.taille && !a.size_id ? '<p class="erreur">Taille non trouvée dans cette catégorie Vinted : change la catégorie.</p>' : "") + "</div></div>" +
        '<label>Catégorie Vinted</label><input id="cat" value="' + esc(a.catalogue || "") + '" placeholder="Tape pour chercher (ex : robe)"' + (envoyee ? " disabled" : "") + '><div id="catres"></div>' +
        '<label>Couleurs (2 max)</label><div class="cases" id="couleurs">' + Object.keys(COULEURS).map(function (k) { var c = a.color_ids.indexOf(Number(k)) >= 0; return '<label class="' + (c ? "coche" : "") + '"><input type="checkbox" value="' + k + '"' + (c ? " checked" : "") + (envoyee ? " disabled" : "") + "> " + COULEURS[k] + "</label>"; }).join("") + "</div>" +
        '<div class="grille2"><div><label>État</label><select id="etat"' + (envoyee ? " disabled" : "") + ">" + Object.keys(ETATS).map(function (k) { return '<option value="' + k + '"' + (Number(k) === a.status_id ? " selected" : "") + ">" + ETATS[k] + "</option>"; }).join("") + "</select></div>" +
        '<div><label>Colis</label><select id="colis"' + (envoyee ? " disabled" : "") + ">" + Object.keys(COLIS).map(function (k) { return '<option value="' + k + '"' + (Number(k) === a.package_size_id ? " selected" : "") + ">" + COLIS[k] + "</option>"; }).join("") + "</select></div></div>" +
        (envoyee ? "" : '<div class="ligne" style="margin-top:14px"><button class="principal" id="enreg">💾 Enregistrer</button><button id="regen">✍️ Réécrire avec l\'IA</button></div>') + "</div>" +
        '<div class="carte"><div class="ligne"><h2 class="etire">Liens des photos Shein</h2><button id="copierLiens">📋 Copier les liens</button></div><div class="photos-shein">' +
        (f.images || []).map(function (u, i) { return '<a href="' + esc(u) + '" target="_blank" rel="noopener" title="Ouvrir en grand"><span class="num">' + (i + 1) + '</span><img src="' + esc(u) + '" loading="lazy" referrerpolicy="no-referrer"></a>'; }).join("") + "</div>" +
        '<p class="aide">Clique sur une photo pour l\'ouvrir en grand (clic droit › Enregistrer l\'image).</p></div>' +
        "</div><div>" + blocPhotos(a) +
        '<div class="carte"><h2>Publication</h2>' + actions(a) + '<p id="msg" class="aide">' + esc(a.essai || "") + "</p></div>" +
        "</div></div>";
    }
    $("#a").innerHTML = html;
    if ($("#relire")) $("#relire").onclick = function () { api("POST", "/api/produits/" + a.produit_id + "/relire").then(function () { relancerLectures(); toast("Relecture lancée."); charger(); }).catch(function (e) { toast(e.message); }); };
    if (enCours || !f.titre) return;
    $("#copierTout").onclick = function () { copier($("#titre").value + "\n\n" + $("#description").value, "Titre + description"); };
    $("#copierLiens").onclick = function () { copier(liensPhotos, "Liens des photos"); };
    brancherPhotos(a, charger);
    $$("#couleurs input").forEach(function (c) { c.onchange = function () { c.parentNode.classList.toggle("coche", c.checked); if ($$("#couleurs input:checked").length > 2) { c.checked = false; c.parentNode.classList.remove("coche"); toast("2 couleurs maximum."); } }; });
    brancherActions(a, charger);
    if (envoyee) return;
    var catChoisie = null;
    $("#cat").oninput = function () {
      var v = this.value.trim(); if (v.length < 2) { $("#catres").innerHTML = ""; return; }
      api("GET", "/api/categories?q=" + encodeURIComponent(v)).then(function (r) {
        $("#catres").innerHTML = '<div class="liste" style="max-height:220px;overflow:auto;margin-top:6px">' + r.categories.map(function (c) { return '<button class="choixcat" data-id="' + c.id + '" style="justify-content:flex-start">' + esc(c.chemin) + "</button>"; }).join("") + "</div>";
        $$(".choixcat").forEach(function (b) { b.onclick = function () { catChoisie = Number(b.dataset.id); $("#cat").value = b.textContent; $("#catres").innerHTML = ""; }; });
      }).catch(function (e) { $("#catres").innerHTML = '<p class="erreur">' + esc(e.message) + "</p>"; });
    };
    var titre0 = a.titre, desc0 = a.description, taille0 = a.taille;
    $("#enreg").onclick = function () {
      var corps = { prix: $("#prix").value, status_id: $("#etat").value, package_size_id: $("#colis").value, color_ids: $$("#couleurs input:checked").map(function (c) { return Number(c.value); }) };
      if (catChoisie) corps.catalog_id = catChoisie;
      if ($("#taille").value !== taille0) corps.taille = $("#taille").value;
      else {
        if ($("#titre").value !== titre0) corps.titre = $("#titre").value;
        if ($("#description").value !== desc0) corps.description = $("#description").value;
      }
      api("POST", "/api/annonces/" + id, corps).then(function () { toast("Enregistré ✔"); charger(); }).catch(function (e) { toast(e.message, 6000); });
    };
    $("#regen").onclick = function () {
      if (!confirm("Réécrire le titre et la description avec l'IA ? (tes modifications seront remplacées)")) return;
      api("POST", "/api/annonces/" + id + "/regenerer").then(function () { toast("Réécriture en cours…"); charger(); }).catch(function (e) { toast(e.message); });
    };
  }
  charger();
  ETAT.minuteur = setInterval(function () {
    var actif = document.activeElement && ["INPUT", "TEXTAREA", "SELECT"].indexOf(document.activeElement.tagName) >= 0;
    var badgeEl = $(".badge"); var st = badgeEl ? badgeEl.className : "";
    if (!actif && /b-(lecture|generation|envoi|en_file)/.test(st)) charger();
  }, 5000);
}

function actions(a) {
  var b = "";
  if (a.statut === "prete" || a.statut === "echec" || a.statut === "annulee") {
    b += '<button id="essai">🧪 Essai à blanc</button> <button class="principal" id="publier">🚀 Publier sur Vinted</button> ';
  }
  if (a.statut === "a_photographier") b += '<p class="aide">Il faut d\'abord les 2 photos (face et dos).</p>';
  if (a.statut === "en_file") b += '<button class="danger" id="annuler">✋ Annuler la publication</button> ';
  if (["envoi", "en_file"].indexOf(a.statut) < 0) b += '<button class="danger" id="supprimer">🗑️ Supprimer</button>';
  if (a.statut === "echec" && /Doublon/.test(a.erreur)) b += '<div class="sep"></div><button id="forcer">Publier quand même (je suis sûr que ce n\'est pas un doublon)</button>';
  return '<div class="ligne">' + b + "</div>";
}

function brancherActions(a, recharger) {
  var id = a.id;
  if ($("#essai")) $("#essai").onclick = function () {
    $("#msg").textContent = "Essai en cours (envoi des photos puis vérification par Scalency)…";
    api("POST", "/api/annonces/" + id + "/essai").then(function (r) { $("#msg").textContent = r.message; }).catch(function (e) { $("#msg").innerHTML = '<span class="erreur">' + esc(e.message) + "</span>"; });
  };
  if ($("#publier")) $("#publier").onclick = function () {
    if (!confirm("Publier cette annonce sur Vinted via Scalency ?")) return;
    api("POST", "/api/publier", { ids: [id] }).then(function (r) { toast(r.message, 5000); setTimeout(recharger, 1500); }).catch(function (e) { toast(e.message, 6000); });
  };
  if ($("#forcer")) $("#forcer").onclick = function () {
    if (!confirm("Vraiment publier ? Vinted sanctionne les doublons.")) return;
    api("POST", "/api/publier", { ids: [id], ignorer_doublon: true }).then(function (r) { toast(r.message); setTimeout(recharger, 1500); }).catch(function (e) { toast(e.message); });
  };
  if ($("#annuler")) $("#annuler").onclick = function () {
    if (!confirm("Annuler la publication en file ?")) return;
    api("POST", "/api/annonces/" + id + "/annuler").then(recharger).catch(function (e) { toast(e.message); });
  };
  if ($("#supprimer")) $("#supprimer").onclick = function () {
    if (!confirm("Supprimer cet article de la liste ? (rien n'est supprimé sur Vinted)")) return;
    api("POST", "/api/annonces/" + id + "/supprimer").then(function () { location.hash = "#articles"; }).catch(function (e) { toast(e.message); });
  };
}

// Bloc « photos Gemini » : prompts + dépôt (utilisé par la page article et la page photos)
function blocPhotos(a) {
  var f = a.fiche || {};
  var envoyee = ["envoi", "en_file", "publiee"].indexOf(a.statut) >= 0;
  var n = 1, pieces = "";
  if (a.fond) { pieces += '<figure><img src="' + img(a.fond) + '"><a href="' + img(a.fond) + '" download="fond.' + a.fond.split(".").pop() + '">Image ' + n + " : fond</a></figure>"; n++; }
  if (a.modele) { pieces += '<figure><img src="' + img(a.modele) + '"><a href="' + img(a.modele) + '" download="modele.' + a.modele.split(".").pop() + '">Image ' + n + " : modèle</a></figure>"; n++; }
  (f.images || []).slice(0, 4).forEach(function (u, i) { pieces += '<figure><a href="' + esc(u) + '" target="_blank" rel="noopener"><img src="' + esc(u) + '" referrerpolicy="no-referrer"></a>Image ' + (n + i) + " : article</figure>"; });
  function depot(vue, titre) {
    var p = a["photo_" + vue];
    return '<div class="depot ' + (p ? "rempli" : "") + '" data-vue="' + vue + '">' + (p ? '<img src="' + img(p) + '">' : "<b>" + titre + "</b><span>Glisse la photo ici<br>ou clique pour la choisir</span>") + "</div>";
  }
  return '<div class="carte"><h2>Photos Gemini</h2>' +
    (!a.fond || !a.modele ? '<p class="erreur">Ce compte n\'a pas encore ' + (!a.fond ? "de fond" : "") + (!a.fond && !a.modele ? " ni " : "") + (!a.modele ? "de modèle" : "") + (ETAT.role === "admin" ? ' : <a href="#comptes">l\'ajouter</a>' : "") + ". Le prompt décrit alors un décor et une femme par défaut.</p>" : "") +
    '<p class="aide">Dans Gemini : joins ces images dans cet ordre, puis colle le prompt.</p><div class="images-compte">' + pieces + "</div>" +
    '<div class="grille2" style="margin-top:12px"><div><div class="ligne"><h3 class="etire">1. Photo de face</h3><button class="cp" data-v="face">📋 Copier le prompt</button></div>' +
    '<details><summary class="aide">Voir le prompt</summary><div class="prompt">' + esc(a.prompt_face) + "</div></details>" + (envoyee ? (a.photo_face ? '<img style="width:100%;border-radius:8px" src="' + img(a.photo_face) + '">' : "") : depot("face", "Photo de FACE")) + "</div>" +
    '<div><div class="ligne"><h3 class="etire">2. Photo de dos</h3><button class="cp" data-v="dos">📋 Copier le prompt</button></div>' +
    '<details><summary class="aide">Voir le prompt</summary><div class="prompt">' + esc(a.prompt_dos) + "</div></details>" + (envoyee ? (a.photo_dos ? '<img style="width:100%;border-radius:8px" src="' + img(a.photo_dos) + '">' : "") : depot("dos", "Photo de DOS")) + "</div></div>" +
    (envoyee ? "" : '<div class="ligne" style="margin-top:12px">' + (a.photo_face && a.photo_dos && a.statut === "a_photographier" ? '<button class="principal" data-act="valider">✅ Les photos sont bonnes</button>' : "") +
      ((a.photo_face || a.photo_dos) ? '<button data-act="refaire">🔁 Refaire les photos</button>' : "") + "</div>") +
    "</div>";
}

function brancherPhotos(a, recharger, racine) {
  var r = racine || document;
  $$(".cp", r).forEach(function (b) { b.onclick = function (e) { e.stopPropagation(); copier(b.dataset.v === "face" ? a.prompt_face : a.prompt_dos, "Prompt " + b.dataset.v); }; });
  $$(".depot", r).forEach(function (z) {
    zoneDepot(z, function (fichier) {
      if (!/^image\/(jpeg|png|webp)$/.test(fichier.type)) return toast("Format refusé : JPG, PNG ou WEBP.");
      z.innerHTML = "Envoi…";
      api("POST", "/api/annonces/" + a.id + "/photo/" + z.dataset.vue, undefined, fichier).then(function () { toast("Photo enregistrée ✔"); recharger(); }).catch(function (e) { toast(e.message, 6000); recharger(); });
    });
  });
  $$("[data-act]", r).forEach(function (b) {
    b.onclick = function () {
      var act = b.dataset.act;
      api("POST", "/api/annonces/" + a.id + (act === "valider" ? "/valider-photos" : "/refaire")).then(function () { toast(act === "valider" ? "Validé ✔" : "Photos effacées : tu peux les refaire."); recharger(); }).catch(function (e) { toast(e.message, 6000); });
    };
  });
}

// ------------------------------------------------------------ page : photos (employée)
function pagePhotos() {
  $("#page").innerHTML = '<h1>Photos à faire</h1><p class="aide">Pour chaque article : 1) ouvre Gemini, joins les images dans l\'ordre indiqué, colle le prompt « face » ; 2) télécharge la photo et glisse-la dans « Photo de FACE » ; 3) pareil pour le dos ; 4) vérifie que la couleur, la coupe et les détails sont identiques à l\'article, puis clique « Les photos sont bonnes ».</p><div id="pl"><p class="vide">Chargement…</p></div>';
  function bloc(a) {
    var fini = a.statut !== "a_photographier";
    return '<div class="bloc" id="b' + a.id + '"><h2>' + (fini ? "✅ " : "") + esc(a.titre) + ' <span class="aide">· ' + esc(a.compte) + "</span></h2>" +
      (fini ? '<p class="aide ok">Terminé. Merci !</p>' : blocPhotos(a)) + "</div>";
  }
  function brancher(a) {
    var el = $("#b" + a.id); if (!el) return;
    brancherPhotos(a, function () {
      api("GET", "/api/annonces/" + a.id).then(function (n) {
        var vieux = $("#b" + a.id); if (!vieux) return;
        var tmp = document.createElement("div"); tmp.innerHTML = bloc(n); vieux.replaceWith(tmp.firstChild); brancher(n);
      });
    }, el);
  }
  function charger() {
    api("GET", "/api/annonces?statut=a_photographier").then(function (r) {
      var pl = $("#pl"); if (!pl) return;
      if (!r.annonces.length) { pl.innerHTML = '<p class="vide">🎉 Aucune photo à faire pour le moment.</p>'; return; }
      var ids = r.annonces.slice(0, 15).map(function (a) { return a.id; });
      Promise.all(ids.map(function (i) { return api("GET", "/api/annonces/" + i); })).then(function (liste) {
        var pl2 = $("#pl"); if (!pl2) return;
        pl2.innerHTML = liste.map(bloc).join("") +
          (r.annonces.length > 15 ? '<p class="aide">… et ' + (r.annonces.length - 15) + ' autres après celles-ci. <button id="suite">Afficher la suite</button></p>' : "");
        liste.forEach(brancher);
        if ($("#suite")) $("#suite").onclick = charger;
      });
    }).catch(function (e) { var pl = $("#pl"); if (pl) pl.innerHTML = '<p class="erreur">' + esc(e.message) + "</p>"; });
  }
  charger();
}

// ------------------------------------------------------------ page : comptes (fond + modèle)
function pageComptes() {
  $("#page").innerHTML = '<div class="ligne"><h1 class="etire">Comptes Vinted</h1><button id="sync">🔄 Mettre à jour la liste depuis Scalency</button></div>' +
    '<p class="aide">Chaque compte a <b>un seul fond</b> et <b>un seul modèle</b> (la même femme sur toutes les photos du compte). Les prompts des photos les reprennent automatiquement.</p><div id="lc"><p class="vide">Chargement…</p></div>';
  $("#sync").onclick = function () {
    this.disabled = true;
    api("POST", "/api/comptes/synchroniser").then(function (r) { toast(r.nombre + " comptes lus dans Scalency."); pageComptes(); }).catch(function (e) { toast(e.message, 6000); $("#sync").disabled = false; });
  };
  chargerComptes().then(function (cs) {
    if (!cs.length) { $("#lc").innerHTML = '<p class="vide">Aucun compte. Remplis ta clé Scalency dans <a href="#reglages">Réglages</a>, puis clique sur « Mettre à jour la liste ».</p>'; return; }
    var relies = cs.filter(function (c) { return c.relie; }), autres = cs.filter(function (c) { return !c.relie; });
    $("#lc").innerHTML = relies.map(carteCompte).join("") +
      (autres.length ? '<details class="carte"><summary>' + autres.length + " compte(s) non reliés à Scalency Plugin (ils ne peuvent pas publier)</summary><p class=\"aide\">" + autres.map(function (c) { return esc(c.login); }).join(", ") + "</p></details>" : "");
    relies.forEach(brancherCompte);
  });
}

function carteCompte(c) {
  function bloc(quoi, titre, desc, idee) {
    var fichier = c[quoi + "_fichier"];
    return '<div><h3>' + titre + "</h3>" +
      '<div class="depot ' + (fichier ? "rempli" : "") + '" data-quoi="' + quoi + '">' + (fichier ? '<img src="' + img(fichier) + '">' : "<b>Glisse ici l'image du " + (quoi === "fond" ? "fond" : "modèle") + "</b><span>ou clique pour la choisir</span>") + "</div>" +
      (fichier ? '<button class="danger petit" data-suppr="' + quoi + '">Retirer l\'image</button>' : "") +
      "<label>Description courte du " + (quoi === "fond" ? "décor" : "modèle") + " (facultatif)</label>" +
      '<textarea rows="2" data-desc="' + quoi + '_description" placeholder="' + desc + '">' + esc(c[quoi + "_description"]) + "</textarea>" +
      "<details><summary class=\"aide\">✨ Je n'ai pas d'image : générer un prompt pour la créer dans Gemini</summary>" +
      '<input data-idee="' + quoi + '" placeholder="' + idee + '"><button data-gen="' + quoi + '" style="margin-top:6px">Générer le prompt</button>' +
      (c["prompt_" + quoi] ? '<div class="prompt" style="margin-top:6px">' + esc(c["prompt_" + quoi]) + '</div><button data-cpp="' + quoi + '">📋 Copier ce prompt</button>' : "") +
      "<p class=\"aide\">Colle ce prompt dans Gemini, télécharge l'image, puis glisse-la dans la zone au-dessus.</p></details></div>";
  }
  return '<div class="carte" id="c-' + esc(c.id) + '"><div class="ligne"><h2 class="etire">' + esc(c.login) + "</h2>" +
    '<label style="margin:0;font-weight:500"><input type="checkbox" data-actif ' + (c.actif ? "checked" : "") + ' style="width:auto"> utiliser ce compte</label></div>' +
    '<div class="grille2">' + bloc("fond", "🖼️ Fond (décor)", "ex : chambre blanche, parquet clair, plante verte", "Ton idée de décor (ex : salon beige cosy avec miroir)") +
    bloc("modele", "👩 Modèle (femme)", "ex : 23 ans, cheveux châtains mi-longs, silhouette fine", "Ton idée de modèle (ex : blonde, cheveux longs ondulés)") + "</div>" +
    '<div class="ligne" style="margin-top:10px"><button class="principal" data-save>💾 Enregistrer les descriptions</button></div></div>';
}

function brancherCompte(c) {
  var el = document.getElementById("c-" + c.id);
  var url = "/api/comptes/" + encodeURIComponent(c.id);
  function maj() { chargerComptes().then(function (cs) { var n = cs.filter(function (x) { return x.id === c.id; })[0]; var tmp = document.createElement("div"); tmp.innerHTML = carteCompte(n); el.replaceWith(tmp.firstChild); brancherCompte(n); }); }
  $$(".depot", el).forEach(function (z) {
    zoneDepot(z, function (f) {
      if (!/^image\/(jpeg|png|webp)$/.test(f.type)) return toast("Format refusé : JPG, PNG ou WEBP.");
      z.innerHTML = "Envoi…";
      api("POST", url + "/image/" + z.dataset.quoi, undefined, f).then(function () { toast("Image enregistrée ✔"); maj(); }).catch(function (e) { toast(e.message, 6000); maj(); });
    });
  });
  $$("[data-suppr]", el).forEach(function (b) { b.onclick = function () { api("POST", url + "/image/" + b.dataset.suppr + "?supprimer=1").then(maj).catch(function (e) { toast(e.message); }); }; });
  $$("[data-gen]", el).forEach(function (b) {
    b.onclick = function () {
      b.disabled = true; b.textContent = "Génération…";
      api("POST", url + "/prompt/" + b.dataset.gen, { idee: $('[data-idee="' + b.dataset.gen + '"]', el).value }).then(function () { maj(); setTimeout(function () { var d = $$("#c-" + CSS.escape(c.id) + " details"); d.forEach(function (x) { if ($("[data-gen='" + b.dataset.gen + "']", x)) x.open = true; }); }, 300); })
        .catch(function (e) { toast(e.message, 6000); b.disabled = false; b.textContent = "Générer le prompt"; });
    };
  });
  $$("[data-cpp]", el).forEach(function (b) { b.onclick = function () { copier(c["prompt_" + b.dataset.cpp], "Prompt"); }; });
  $("[data-actif]", el).onchange = function () { api("POST", url, { actif: this.checked }).then(function () { toast("Enregistré ✔"); }); };
  $("[data-save]", el).onclick = function () {
    var d = {}; $$("[data-desc]", el).forEach(function (t) { d[t.dataset.desc] = t.value; });
    api("POST", url, d).then(function () { toast("Enregistré ✔ (prompts mis à jour)"); }).catch(function (e) { toast(e.message); });
  };
}

// ------------------------------------------------------------ page : réglages
function pageReglages() {
  $("#page").innerHTML = '<h1>Réglages</h1><div id="r">Chargement…</div>';
  api("GET", "/api/reglages").then(function (d) {
    var c = d.cles, g = d.reglages;
    function cle(k, aide, test) {
      return "<label>" + esc(c[k].libelle) + (c[k].rempli ? ' <span class="ok">✔ remplie</span>' : ' <span class="erreur">à remplir</span>') + "</label>" +
        '<div class="ligne"><input class="etire" data-cle="' + k + '" type="' + (k === "SUPABASE_URL" ? "text" : "password") + '" placeholder="' + esc(c[k].rempli ? "Actuelle : " + c[k].apercu + " (laisse vide pour la garder)" : "Colle-la ici") + '">' +
        (test ? '<button data-test="' + test + '">Tester</button>' : "") + "</div><p class=\"aide\">" + aide + "</p>";
    }
    $("#r").innerHTML =
      '<div class="carte"><h2>🔑 Tes clés</h2><p class="aide">Elles restent uniquement sur ce PC (fichier .env dans <code>' + esc(ETAT.etat.donnees) + "</code>), jamais sur GitHub.</p>" +
      cle("ANTHROPIC_API_KEY", 'Sur <a href="https://console.anthropic.com/settings/keys" target="_blank">console.anthropic.com</a> › API Keys › Create Key. Commence par <code>sk-ant-</code>.', "anthropic") +
      cle("SCALENCY_API_KEY", "Dans Scalency › Paramètres › Clé API. Commence par <code>scal_live_</code>.", "scalency") +
      cle("SUPABASE_URL", 'Sur <a href="https://supabase.com/dashboard" target="_blank">supabase.com</a> : ouvre ton projet › Project Settings › Data API › « Project URL » (ex : https://abcd.supabase.co).', "") +
      cle("SUPABASE_KEY", "Même endroit : Project Settings › API Keys › la clé <b>secret</b> (ou « service_role »). Elle sert à héberger les photos.", "supabase") +
      '<button class="principal" id="sauver">💾 Enregistrer les clés</button> <span id="rt" class="aide"></span></div>' +
      '<div class="carte"><h2>💶 Prix et annonces</h2><div class="grille3">' +
      '<div><label>Prix Vinted = prix Shein ×</label><input data-r="prix_coef" value="' + esc(g.prix_coef) + '"></div>' +
      '<div><label>+ (en €)</label><input data-r="prix_ajout" value="' + esc(g.prix_ajout) + '"></div>' +
      '<div><label>Prix minimum (€)</label><input data-r="prix_min" value="' + esc(g.prix_min) + '"></div></div>' +
      '<p class="aide">Exemple : un article à 10 € sur Shein sera mis à ' + esc(Math.max(Number(g.prix_min), Math.ceil(10 * Number(g.prix_coef) + Number(g.prix_ajout)))) + " € (arrondi à l'euro au-dessus). Tu peux toujours changer le prix d'une annonce.</p>" +
      '<div class="grille3"><div><label>État par défaut</label><select data-r="etat_id">' + Object.keys(ETATS).map(function (k) { return '<option value="' + k + '"' + (k === String(g.etat_id) ? " selected" : "") + ">" + ETATS[k] + "</option>"; }).join("") + "</select></div>" +
      '<div><label>Taille de colis par défaut</label><select data-r="colis_id">' + Object.keys(COLIS).map(function (k) { return '<option value="' + k + '"' + (k === String(g.colis_id) ? " selected" : "") + ">" + COLIS[k] + "</option>"; }).join("") + "</select></div>" +
      '<div><label>Minutes entre 2 publications d\'un même compte</label><input data-r="espacement_min" value="' + esc(g.espacement_min) + '"></div></div>' +
      '<label><input type="checkbox" data-r="publier_auto" style="width:auto"' + (g.publier_auto === "1" ? " checked" : "") + "> Publier automatiquement dès que les photos sont validées</label>" +
      '<button class="principal" id="sauverR">💾 Enregistrer</button></div>' +
      '<div class="carte"><h2>👩‍💻 Accès de ton employée (à distance)</h2><p class="aide">Sur ce PC, tu n\'as pas besoin de mot de passe. Pour que ton employée se connecte depuis chez elle, choisis les mots de passe ici (l\'installation de Tailscale pour l\'accès à distance viendra ensuite).</p>' +
      cle("EMPLOYEE_PASSWORD", "Ton employée ne verra que la page Photos.", "") + cle("ADMIN_PASSWORD", "Pour toi, si tu ouvres le site depuis un autre appareil.", "") +
      '<button class="principal" id="sauverM">💾 Enregistrer les mots de passe</button></div>' +
      '<div class="carte"><h2>🧩 Extension Chrome</h2><p><a href="#extension">Installer ou vérifier l\'extension « lecteur Shein »</a></p></div>' +
      '<div class="carte"><h2>⬆️ Mise à jour</h2><p id="mv" class="aide">Version installée : ' + esc(ETAT.etat.version) + "</p><button id=\"maj\">⬆️ Mettre à jour maintenant</button></div>";
    function enregistrerCles(btn) {
      var cles = {}; $$("[data-cle]").forEach(function (i) { if (i.value.trim()) cles[i.dataset.cle] = i.value.trim(); });
      if (!Object.keys(cles).length) return toast("Rien à enregistrer : colle d'abord une clé.");
      api("POST", "/api/reglages", { cles: cles }).then(function () { toast("Enregistré ✔"); rafraichirEtat().then(pageReglages); }).catch(function (e) { toast(e.message); });
    }
    $("#sauver").onclick = enregistrerCles; $("#sauverM").onclick = enregistrerCles;
    $("#sauverR").onclick = function () {
      var r = {}; $$("[data-r]").forEach(function (i) { r[i.dataset.r] = i.type === "checkbox" ? (i.checked ? "1" : "0") : i.value; });
      api("POST", "/api/reglages", { reglages: r }).then(function () { toast("Enregistré ✔"); pageReglages(); }).catch(function (e) { toast(e.message); });
    };
    $$("[data-test]").forEach(function (b) {
      b.onclick = function () {
        var champ = $("[data-cle]", b.parentNode);
        var avant = champ && champ.value.trim() ? api("POST", "/api/reglages", { cles: (function () { var o = {}; o[champ.dataset.cle] = champ.value.trim(); var u = $('[data-cle="SUPABASE_URL"]'); if (u && u.value.trim()) o.SUPABASE_URL = u.value.trim(); return o; })() }) : Promise.resolve();
        b.disabled = true; b.textContent = "Test…";
        avant.then(function () { return api("POST", "/api/tester", { quoi: b.dataset.test }); })
          .then(function (r) { toast("✔ " + r.message, 7000); rafraichirEtat().then(pageReglages); })
          .catch(function (e) { toast("✖ " + e.message, 9000); b.disabled = false; b.textContent = "Tester"; });
      };
    });
    api("GET", "/api/maj").then(function (m) { if (m.disponible) $("#mv").innerHTML = "Version installée : " + esc(m.version) + " · dernière version : <b>" + esc(m.disponible) + "</b>" + (m.disponible !== m.version ? ' <span class="ok">(nouvelle version disponible)</span>' : " (à jour)"); }).catch(function () { /* rien */ });
    $("#maj").onclick = function () {
      var b = this; b.disabled = true; b.textContent = "Téléchargement…";
      api("POST", "/api/maj").then(function (r) {
        toast(r.message, 8000);
        var essais = 0; var t = setInterval(function () { essais++; fetch("/api/ping").then(function (x) { if (x.ok && essais > 2) { clearInterval(t); location.reload(); } }).catch(function () { /* redémarre */ }); if (essais > 60) clearInterval(t); }, 1500);
      }).catch(function (e) { toast(e.message, 8000); b.disabled = false; b.textContent = "⬆️ Mettre à jour maintenant"; });
    };
  }).catch(function (e) { $("#r").innerHTML = '<p class="erreur">' + esc(e.message) + "</p>"; });
}

// ------------------------------------------------------------ page : installer l'extension
function pageExtension() {
  var ok = extensionPresente();
  var dossier = (ETAT.etat && ETAT.etat.extension_dossier) || "";
  $("#page").innerHTML = '<h1>Extension « lecteur Shein »</h1>' +
    (ok ? '<div class="carte ok">✔ L\'extension est installée dans ce navigateur. Tu n\'as plus rien à faire.</div>' : "") +
    '<div class="carte"><p>Shein bloque les robots. Cette petite extension lit les fiches <b>dans ton propre Chrome</b>, connecté à <b>ton compte Shein</b> (donc avec tes prix). Elle ne lit jamais ton mot de passe. À installer <b>une seule fois</b> (2 minutes) :</p>' +
    '<ol class="etapes">' +
    '<li>Clique ici : <button id="ouvrir">📂 Ouvrir le dossier de l\'extension</button> <span class="aide">(il s\'ouvre dans l\'Explorateur Windows)</span><br><span class="aide">Son emplacement : <code>' + esc(dossier) + '</code> <button id="cpd">📋 Copier</button></span></li>' +
    '<li>Dans Chrome, ouvre un nouvel onglet, tape <code>chrome://extensions</code> dans la barre d\'adresse puis Entrée. <button id="cpu">📋 Copier l\'adresse</button></li>' +
    "<li>En haut à droite de cette page, active <b>Mode développeur</b>.</li>" +
    "<li>Clique sur <b>Charger l'extension non empaquetée</b> (en haut à gauche).</li>" +
    "<li>Dans la fenêtre qui s'ouvre, colle l'emplacement du dossier dans la barre du haut (Ctrl+V), Entrée, puis clique sur <b>Sélectionner un dossier</b>.</li>" +
    "<li>Reviens sur cet onglet et appuie sur <b>F5</b> : le message vert « installée » doit apparaître.</li></ol>" +
    '<p class="aide">Astuce : clique sur la pièce de puzzle 🧩 en haut à droite de Chrome, puis sur l\'épingle 📌 à côté de « Vinted Auto » pour garder son icône visible.</p></div>';
  $("#ouvrir").onclick = function () { api("POST", "/api/extension/ouvrir").then(function () { toast("Dossier ouvert."); }).catch(function (e) { toast(e.message); }); };
  $("#cpd").onclick = function () { copier(dossier, "Emplacement"); };
  $("#cpu").onclick = function () { copier("chrome://extensions", "Adresse"); };
}

// ------------------------------------------------------------ démarrage
function demarrer() {
  return rafraichirEtat().then(function () {
    window.postMessage({ source: "vinted-auto-site", type: "bonjour" }, location.origin);
    naviguer(); relancerLectures();
  }).catch(function (e) { if (ETAT.role === null && /Connecte/.test(e.message)) return; $("#page").innerHTML = '<p class="erreur">' + esc(e.message) + "</p>"; });
}
window.addEventListener("hashchange", naviguer);
// l'extension s'annonce juste après le chargement : on attend un instant
setTimeout(demarrer, 150);
setInterval(relancerLectures, 30000);
