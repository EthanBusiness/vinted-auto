// Lit la fiche produit Shein ouverte (dans TON navigateur, connecté à TON compte Shein).
// Cette fonction est injectée dans la page Shein : elle doit rester autonome.
function extraireFicheShein() {
  try {
    var g = window.gbRawData;
    var m = g && g.modules;
    if (!m || !m.productInfo) {
      var bloque = /captcha|verify|vérif|robot|risk/i.test(document.title + " " + location.href);
      return { pret: false, bloque: bloque, raison: bloque ? "Shein demande une vérification (captcha)." : "Page pas encore chargée ou ce n'est pas une fiche produit." };
    }
    var pi = m.productInfo || {};
    var https = function (u) {
      u = String(u || "");
      if (u.indexOf("//") === 0) u = "https:" + u;
      return u.replace(/^http:/, "https:");
    };
    var original = function (u) {
      // ..._thumbnail_900x.webp -> ....jpg (photo en pleine taille)
      return https(u).replace(/_thumbnail_\d+x\d*/, "").replace(/\.(webp|png|jpeg)$/i, ".jpg");
    };
    var uniques = function (a) {
      var vu = {}, r = [];
      a.forEach(function (x) { if (x && !vu[x]) { vu[x] = 1; r.push(x); } });
      return r;
    };
    var texte = function (el) { return el ? (el.innerText || "").replace(/\s+/g, " ").trim() : ""; };

    // Photos de la couleur affichée
    var img = pi.currentSkcImgInfo || {};
    var images = (img.skcImages || []).concat(img.spuImages || []);
    if (!images.length && pi.goods_img) images.push(pi.goods_img);
    images = uniques(images.map(original)).slice(0, 12);

    // Couleur affichée
    var couleur = "";
    var info = ((m.saleAttr || {}).mainSaleAttribute || {}).info || [];
    for (var i = 0; i < info.length; i++) {
      if (String(info[i].goods_id) === String(pi.goods_id)) couleur = info[i].attr_value || "";
    }

    // Caractéristiques (composition, coupe, col…)
    var desc = pi.productDescriptionInfo || {};
    var details = desc.productDetails || [];
    var parNom = {};
    var ordre = [];
    details.forEach(function (d) {
      if (!d || !d.attr_name) return;
      var nom = String(d.attr_name).trim();
      if (!parNom[nom]) { parNom[nom] = []; ordre.push(nom); }
      if (parNom[nom].indexOf(d.attr_value) < 0) parNom[nom].push(d.attr_value);
    });
    var attributs = ordre.map(function (n) { return n + " : " + parNom[n].join(", "); });
    if (!couleur && parNom["Couleur"]) couleur = parNom["Couleur"].join(", ");

    // Tailles et mesures
    var tailles = [];
    var si = ((m.saleAttr || {}).sizeInfo || {}).sizeInfo || [];
    si.forEach(function (s) {
      var mesures = {};
      Object.keys(s).forEach(function (k) {
        if (/attr_|^id$/i.test(k)) return;
        var v = String(s[k] || "").trim();
        if (/\d/.test(v) && /cm|inch|"/.test(v)) mesures[k.trim()] = v;
      });
      tailles.push({ taille: s.attr_value_name || s.attr_value_name_en || "", mesures: mesures });
    });
    if (!tailles.length) {
      document.querySelectorAll(".product-intro__size-radio").forEach(function (e) { tailles.push({ taille: texte(e), mesures: {} }); });
    }

    // Taille sélectionnée sur la page (si tu en as choisi une)
    var choisie = texte(document.querySelector(".product-intro__size-radio_active, [class*='size-radio_active'], [class*='size-radio--active']"));

    // Prix affiché pour TON compte
    var prix = texte(document.querySelector(".productPrice__main, [class*='productPrice__main'], .product-intro__head-mainprice, [class*='from-price']"));
    if (!prix) {
      var ps = ((m.priceInfo || {}).salePrice || {}).amountWithSymbol;
      if (ps) prix = ps;
    }

    // Catégorie Shein
    var cat = pi.cate_name || "";
    try {
      var ci = pi.cateInfos || {};
      if (ci[pi.cat_id] && ci[pi.cat_id].category_name) cat = ci[pi.cat_id].category_name;
    } catch (e) { /* rien */ }

    var h1 = document.querySelector("h1");
    var lien = location.origin + location.pathname;
    return {
      pret: true,
      lien: lien,
      goods_id: String(pi.goods_id || ""),
      sku: String(pi.goods_sn || ""),
      titre: pi.goods_name || texte(h1) || document.title,
      couleur: couleur,
      categorie: cat,
      prix: prix,
      images: images,
      attributs: attributs.slice(0, 60),
      tailles: tailles.slice(0, 30),
      taille_choisie: choisie,
      description: String(desc.goods_desc || "").replace(/<[^>]+>/g, " ").slice(0, 3000)
    };
  } catch (e) {
    return { pret: false, bloque: false, raison: "Lecture impossible : " + e.message };
  }
}
