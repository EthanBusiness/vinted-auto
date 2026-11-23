// Test de bout en bout : vrai navigateur Chromium + vraie extension + site + faux Claude/Scalency/Supabase/Shein.
// Lancement : node tests/e2e.js  (depuis le dossier du dépôt)
const { chromium } = require("playwright");
const { spawn } = require("child_process");
const fs = require("fs");
const os = require("os");
const path = require("path");

const RACINE = path.resolve(__dirname, "..");
const FAUX = 8765, SITE = 8811;
const PY = process.env.PY || "python3";
const DONNEES = fs.mkdtempSync(path.join(os.tmpdir(), "va-donnees-"));
const SORTIE = path.join(RACINE, "tests", "_sortie");
fs.mkdirSync(SORTIE, { recursive: true });
const URL_SITE = `http://localhost:${SITE}/`;
let etape = 0;
function ok(msg) { console.log(`  ✔ ${++etape}. ${msg}`); }
function attendre(ms) { return new Promise(r => setTimeout(r, ms)); }
async function jusqua(fn, msg, max = 30000) {
  const t0 = Date.now();
  while (Date.now() - t0 < max) { try { const v = await fn(); if (v) return v; } catch (e) { /* on réessaie */ } await attendre(400); }
  throw new Error("Délai dépassé : " + msg);
}
async function apiGet(chemin) { const r = await fetch(URL_SITE.slice(0, -1) + chemin); return r.json(); }

(async () => {
  const procs = [];
  const faux = spawn(PY, [path.join(RACINE, "tests", "faux_services.py"), String(FAUX)], { stdio: "inherit" });
  procs.push(faux);
  const env = Object.assign({}, process.env, {
    VINTED_AUTO_DONNEES: DONNEES, PORT: String(SITE), VINTED_AUTO_SANS_NAVIGATEUR: "1",
    ANTHROPIC_BASE_URL: `http://127.0.0.1:${FAUX}`, SCALENCY_BASE_URL: `http://127.0.0.1:${FAUX}/api/pub/public_api/v1`,
    ANTHROPIC_API_KEY: "", ANTHROPIC_AUTH_TOKEN: "", HTTPS_PROXY: "", HTTP_PROXY: "", https_proxy: "", http_proxy: "", NO_PROXY: "*", no_proxy: "*",
  });
  const site = spawn(PY, ["-m", "vinted_auto.serveur"], { cwd: RACINE, env, stdio: "inherit" });
  procs.push(site);
  const fin = (code) => { procs.forEach(p => { try { p.kill(); } catch (e) { /* rien */ } }); process.exit(code); };
  try {
    await jusqua(async () => (await fetch(URL_SITE + "api/ping")).ok, "site lancé", 20000);
    ok("Le site démarre (python -m vinted_auto.serveur)");

    const ext = path.join(DONNEES, "extension-chrome");
    if (!fs.existsSync(path.join(ext, "manifest.json"))) throw new Error("extension non copiée dans le dossier de données");
    ok("L'extension est copiée dans le dossier de données : " + ext);

    const ctx = await chromium.launchPersistentContext(fs.mkdtempSync(path.join(os.tmpdir(), "va-chrome-")), {
      channel: "chromium", headless: true, viewport: { width: 1280, height: 900 },
      args: [`--disable-extensions-except=${ext}`, `--load-extension=${ext}`, `--host-resolver-rules=MAP fr.shein.com 127.0.0.1`, "--no-proxy-server"],
    });
    let [sw] = ctx.serviceWorkers();
    if (!sw) sw = await ctx.waitForEvent("serviceworker");
    ok("Chrome charge l'extension (service worker actif)");

    const page = await ctx.newPage();
    const erreursJs = [];
    page.on("pageerror", e => erreursJs.push(e.message + " @ " + (e.stack || "").split("\n").slice(1, 3).join(" ")));
    page.on("dialog", d => d.accept());
    await page.goto(URL_SITE);
    await page.waitForSelector("text=Articles");
    await jusqua(() => page.evaluate(() => !!document.documentElement.getAttribute("data-extension-vinted")), "extension détectée par la page");
    ok("La page détecte l'extension");
    await page.screenshot({ path: path.join(SORTIE, "1-accueil-vide.png") });

    // ---- Réglages : clés
    await page.goto(URL_SITE + "#reglages");
    await page.fill('[data-cle="ANTHROPIC_API_KEY"]', "sk-ant-test");
    await page.fill('[data-cle="SCALENCY_API_KEY"]', "scal_live_test");
    await page.fill('[data-cle="SUPABASE_URL"]', `http://127.0.0.1:${FAUX}`);
    await page.fill('[data-cle="SUPABASE_KEY"]', "sb_secret_test");
    await page.click("#sauver");
    await jusqua(async () => (await page.textContent("#r")).includes("✔ remplie"), "clés enregistrées");
    const envTxt = fs.readFileSync(path.join(DONNEES, ".env"), "utf8");
    if (!envTxt.includes("SCALENCY_API_KEY=scal_live_test")) throw new Error(".env mal écrit");
    ok("Les clés sont enregistrées dans .env (dossier de données, hors GitHub)");
    for (const t of ["anthropic", "scalency", "supabase"]) {
      await page.click(`[data-test="${t}"]`);
      const msg = await jusqua(async () => { const t = await page.textContent("#toast"); return /^[✔✖]/.test(t) ? t : null; }, "résultat du test " + t);
      await page.evaluate(() => { document.getElementById("toast").textContent = ""; });
      if (!msg.startsWith("✔")) throw new Error(`Test ${t} : ${msg}`);
      await page.waitForSelector(`[data-test="${t}"]:not([disabled])`);
      await attendre(300);
    }
    ok("Les boutons « Tester » marchent (Claude, Scalency, Supabase)");

    // ---- Comptes : fond + modèle
    await page.goto(URL_SITE + "#comptes");
    await page.waitForSelector("#c-vt-1");
    const png = path.join(SORTIE, "_image.png");
    await page.screenshot({ path: png, clip: { x: 0, y: 0, width: 300, height: 400 } });
    for (const quoi of ["fond", "modele"]) {
      const [fc] = await Promise.all([page.waitForEvent("filechooser"), page.click(`#c-vt-1 .depot[data-quoi="${quoi}"]`)]);
      await fc.setFiles(png);
      await jusqua(async () => (await page.$(`#c-vt-1 .depot.rempli[data-quoi="${quoi}"] img`)), `image ${quoi} enregistrée`);
    }
    await page.click('#c-vt-1 details >> nth=0');
    await page.fill('#c-vt-1 [data-idee="fond"]', "salon beige cosy");
    await page.click('#c-vt-1 [data-gen="fond"]');
    await jusqua(async () => (await page.textContent("#c-vt-1")).includes("prompt de test"), "prompt de fond généré");
    ok("Compte : fond et modèle importés + prompt de fond généré par l'IA");
    await page.screenshot({ path: path.join(SORTIE, "2-comptes.png"), fullPage: true });

    // ---- Ajouter des liens
    await page.goto(URL_SITE + "#ajouter");
    await page.waitForSelector(".cc");
    await page.fill("#liens", `http://fr.shein.com:${FAUX}/SHEIN-LUNE-Robe-p-24616628.html?src=x M\nhttp://fr.shein.com:${FAUX}/Autre-robe-p-11112222.html`);
    await page.check('.cc[value="vt-1"]');
    await page.check('.cc[value="vt-2"]');
    await page.screenshot({ path: path.join(SORTIE, "3-ajouter.png"), fullPage: true });
    await page.click("#go");
    await page.waitForURL(/#articles/);
    ok("2 liens Shein collés pour 2 comptes → 4 annonces créées");
    const annonces = await jusqua(async () => {
      const r = await apiGet("/api/annonces");
      return r.annonces.length === 4 && r.annonces.every(a => a.statut === "a_photographier") ? r.annonces : null;
    }, "lecture Shein par l'extension puis rédaction par l'IA", 60000);
    ok("L'extension a lu les 2 fiches Shein dans Chrome, l'IA a rédigé les 4 annonces");
    await page.reload(); await page.waitForSelector(".item");
    await page.screenshot({ path: path.join(SORTIE, "4-articles.png"), fullPage: true });

    // ---- Détail d'une annonce
    const a1 = annonces.find(a => a.compte_id === "vt-1" && /24616628/.test(a.lien));
    const det = await apiGet("/api/annonces/" + a1.id);
    const verifs = [
      [det.titre === "Robe courte fuchsia à manches bouffantes 1 taille M" || /taille M$/.test(det.titre), "titre avec la taille : " + det.titre],
      [det.description.includes("Taille : M") && det.description.includes("poitrine 94 cm"), "description avec taille et mesures"],
      [det.size_id === 4, "size_id M = 4 (" + det.size_id + ")"],
      [det.catalog_id === 1774, "catégorie 1774"],
      [JSON.stringify(det.color_ids) === "[5]", "couleur Rose = 5"],
      [JSON.stringify(det.material_ids) === "[45,53]", "matières polyester + élasthanne " + JSON.stringify(det.material_ids)],
      [det.prix === 19, "prix 10,05 × 1,6 + 2 arrondi = 19 € (" + det.prix + ")"],
      [det.prompt_face.includes("Image 1 = le DÉCOR") && det.prompt_face.includes("Image 2 = la FEMME") && det.prompt_face.includes("vue de FACE"), "prompt face avec fond + modèle du compte"],
      [det.prompt_dos.includes("vue de DOS"), "prompt dos"],
      [det.fiche.images[0] === "https://img.ltwebstatic.com/images3_pi/2023/10/13/02/16971684628a3ce766b3e854f3cedee214437dd785.jpg", "lien photo Shein en pleine taille : " + det.fiche.images[0]],
      [det.fiche.prix === 10.05, "prix Shein lu sur la page (10,05 €)"],
    ];
    verifs.forEach(([v, m]) => { if (!v) throw new Error("Vérification ratée : " + m); });
    ok("Annonce complète : titre, description + mesures, taille, catégorie, couleur, matières, prix, prompts, liens photos");
    const a2 = annonces.find(a => a.compte_id === "vt-2" && /24616628/.test(a.lien));
    const det2 = await apiGet("/api/annonces/" + a2.id);
    if (det2.description === det.description) throw new Error("les 2 comptes ont la même description");
    if (!det2.prompt_face.includes("Décor : une chambre simple")) throw new Error("compte sans fond : prompt par défaut absent");
    ok("Chaque compte a sa propre description ; un compte sans fond reçoit un décor par défaut");
    const sansTaille = annonces.find(a => /11112222/.test(a.lien));
    const det3 = await apiGet("/api/annonces/" + sansTaille.id);
    if (det3.size_id) throw new Error("taille inventée alors qu'aucune n'était donnée");
    ok("Sans taille donnée, rien n'est inventé (à choisir avant publication)");

    // ---- Page article : on choisit la taille de l'annonce sans taille
    await page.goto(URL_SITE + "#article/" + sansTaille.id);
    await page.waitForSelector("#taille");
    await page.selectOption("#taille", "S");
    await page.click("#enreg");
    await jusqua(async () => (await apiGet("/api/annonces/" + sansTaille.id)).size_id === 3, "taille S enregistrée");
    ok("Choisir la taille dans la page article met à jour titre, description et size_id");

    // ---- Page photos (employée) : dépôt face + dos sur 2 annonces
    await page.goto(URL_SITE + "#article/" + a1.id);
    await page.waitForSelector(".depot");
    await page.screenshot({ path: path.join(SORTIE, "5-article.png"), fullPage: true });
    const photo = path.join(SORTIE, "_photo.jpg");
    await page.screenshot({ path: photo, type: "jpeg", clip: { x: 0, y: 0, width: 600, height: 800 } });
    for (const id of [a1.id, a2.id, sansTaille.id]) {
      await page.goto(URL_SITE + "#photos");
      await page.waitForSelector("#b" + id + " .depot");
      for (const vue of ["face", "dos"]) {
        const [fc] = await Promise.all([page.waitForEvent("filechooser"), page.click(`#b${id} .depot[data-vue="${vue}"]`)]);
        await fc.setFiles(photo);
        await jusqua(async () => (await page.$(`#b${id} .depot.rempli[data-vue="${vue}"]`)), "photo " + vue);
      }
      await page.click(`#b${id} [data-act="valider"]`);
      await jusqua(async () => (await apiGet("/api/annonces/" + id)).statut === "prete", "annonce prête");
    }
    await page.goto(URL_SITE + "#photos");
    await page.waitForSelector("#pl");
    await page.screenshot({ path: path.join(SORTIE, "6-photos.png"), fullPage: true });
    ok("Page Photos : dépôt face + dos et validation → « Prête à publier »");

    // ---- Essai à blanc
    await page.goto(URL_SITE + "#article/" + a1.id);
    await page.click("#essai");
    await jusqua(async () => (await page.textContent("#msg")).includes("Essai réussi"), "essai à blanc");
    ok("Essai à blanc Scalency réussi (photos envoyées sur Supabase)");

    // ---- Publication des 3 prêtes
    await page.goto(URL_SITE + "#articles");
    await page.waitForSelector(".item");
    await page.click("#toutes");
    await page.click("#pub");
    await jusqua(async () => {
      const r = await apiGet("/api/annonces");
      const s = Object.fromEntries(r.annonces.map(a => [a.id, a]));
      return s[a1.id].statut === "en_file" && s[a2.id].statut === "echec" && s[sansTaille.id].statut === "en_file";
    }, "publication", 30000);
    const r2 = await apiGet("/api/annonces/" + a2.id);
    if (!/Doublon/.test(r2.erreur)) throw new Error("doublon non détecté : " + r2.erreur);
    ok("Publication : 2 annonces en file, le doublon (déjà en ligne sur Scalency) est bloqué");
    const journal = await (await fetch(`http://127.0.0.1:${FAUX}/journal`)).json();
    const vrais = journal.scalency_post.filter(p => !p.dry_run);
    const p1 = vrais.find(p => p.account_id === "vt-1" && p.sku === "SHEIN-sz2310071691901000");
    const attendu = { title: det.titre, price: 19, catalog_id: 1774, status_id: 2, brand_id: 1, size_id: 4, color_ids: [5], package_size_id: 1 };
    for (const k in attendu) if (JSON.stringify(p1[k]) !== JSON.stringify(attendu[k])) throw new Error(`champ ${k} envoyé à Scalency : ${JSON.stringify(p1[k])}`);
    if (p1.photos.length !== 2 || !p1.photos[0].includes("/storage/v1/object/public/vinted-photos/")) throw new Error("photos : " + p1.photos);
    if (JSON.stringify(p1.item_attributes) !== JSON.stringify([{ code: "material", ids: [45, 53] }])) throw new Error("item_attributes");
    const p2 = vrais.find(p => p.account_id === "vt-1" && p !== p1);
    if (!p2 || !(p2.delay_minutes >= 19)) throw new Error("étalement absent : " + JSON.stringify(p2 && p2.delay_minutes));
    ok(`Corps envoyé à Scalency conforme à la doc ; 2e annonce du même compte décalée de ${p2.delay_minutes} min`);
    const claude = journal.anthropic.find(x => x.corps.output_config && x.corps.output_config.format);
    if (claude.corps.model !== "claude-haiku-5-5" || claude.corps.output_config.effort !== "low") throw new Error("appel Claude");
    ok("Appel Claude : modèle claude-haiku-5-5, sortie JSON structurée, effort bas");

    // ---- Suivi des demandes
    await fetch(URL_SITE + "api/suivi", { method: "POST", headers: { "X-Vinted-Auto": "1" } });
    await jusqua(async () => (await apiGet("/api/annonces/" + a1.id)).statut === "publiee", "suivi → publiée");
    ok("Suivi Scalency : la demande passe à « Publiée » avec le numéro Vinted");
    await page.goto(URL_SITE + "#articles"); await page.waitForSelector(".item");
    await page.screenshot({ path: path.join(SORTIE, "7-publiees.png"), fullPage: true });

    // ---- Bouton de l'extension sur une fiche Shein (brouillon)
    const shein = await ctx.newPage();
    await shein.goto(`http://fr.shein.com:${FAUX}/Robe-p-33334444.html`);
    await shein.click(".product-intro__size-radio >> nth=1");
    await shein.evaluate(() => document.querySelectorAll(".product-intro__size-radio")[1].classList.add("product-intro__size-radio_active"));
    const idB = await sw.evaluate(async (url) => {
      const [t] = await chrome.tabs.query({ url: url + "*" });
      const f = await lireOnglet(t.id);
      const r = await envoyer("/api/shein/brouillon", f);
      return r.id;
    }, `http://fr.shein.com:${FAUX}/Robe-p-33334444.html`);
    await page.goto(URL_SITE + "#ajouter?brouillon=" + idB);
    await page.waitForSelector("#taille");
    if ((await page.$eval("#taille", s => s.value)) !== "S") throw new Error("taille choisie sur Shein non reprise");
    await page.check('.cc[value="vt-1"]');
    await page.screenshot({ path: path.join(SORTIE, "8-depuis-shein.png"), fullPage: true });
    await page.click("#go");
    await jusqua(async () => (await apiGet("/api/annonces")).annonces.some(a => /33334444/.test(a.lien) && a.statut === "a_photographier" && a.taille === "S"), "brouillon → annonce");
    ok("Icône de l'extension sur une fiche Shein → l'article arrive dans le site avec la taille choisie");

    // ---- Sécurité : une autre page web ne peut pas piloter le site
    const r403 = await fetch(URL_SITE + "api/importer", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
    const r403b = await fetch(URL_SITE + "api/importer", { method: "POST", headers: { "Content-Type": "application/json", "X-Vinted-Auto": "1", "Origin": "https://pirate.example" }, body: "{}" });
    if (r403.status !== 403 || r403b.status !== 403) throw new Error("protection CSRF");
    ok("Une autre page web ne peut rien déclencher sur le site (protection)");

    if (erreursJs.length) throw new Error("Erreurs JavaScript dans la page : " + erreursJs.join(" | "));
    ok("Aucune erreur JavaScript dans les pages");
    await ctx.close();
    console.log(`\n  TOUT EST OK (${etape} vérifications). Captures : tests/_sortie/`);
    fin(0);
  } catch (e) {
    console.error("\n  ÉCHEC : " + e.message);
    fin(1);
  }
})();
