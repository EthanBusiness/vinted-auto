(function () {
  var SITE = "__SITE__";
  if (!/shein\./i.test(location.hostname)) {
    alert("Ouvre d'abord une fiche produit Shein, puis clique sur ce favori.");
    return;
  }
  var h = document.documentElement.outerHTML;
  function tous(re) { var r = [], m; re.lastIndex = 0; while ((m = re.exec(h)) && r.length < 200) r.push(m[1]); return r; }
  function uniques(a) { var v = {}, r = []; a.forEach(function (x) { if (x && !v[x]) { v[x] = 1; r.push(x); } }); return r; }
  function propre(s) {
    s = String(s).replace(/\\u002F/gi, "/").replace(/\\\//g, "/");
    if (s.indexOf("//") === 0) s = "https:" + s;
    return s.replace(/_thumbnail_\d+x\d*/, "");
  }
  var og = document.querySelector('meta[property="og:title"]');
  var h1 = document.querySelector("h1");
  var titre = (h1 && h1.innerText.trim()) || (og && og.content) || document.title;

  var imgs = [];
  var ogi = document.querySelector('meta[property="og:image"]');
  if (ogi) imgs.push(ogi.content);
  imgs = imgs.concat(tous(/"origin_image"\s*:\s*"([^"]+)"/g));
  var zone = document.querySelector('[class*="product-intro__main"], [class*="product-intro__thumbs"], [class*="crop-image-container"]');
  if (zone) zone.parentElement.querySelectorAll("img").forEach(function (i) { imgs.push(i.currentSrc || i.src || i.getAttribute("data-src")); });
  imgs = uniques(imgs.filter(Boolean).map(propre).filter(function (s) { return /^https:\/\/.*ltwebstatic\.com/.test(s); })).slice(0, 8);

  var attributs = [], re = /"attr_name"\s*:\s*"([^"]{1,60})"\s*,\s*"attr_value"\s*:\s*"([^"]{1,200})"/g, m;
  while ((m = re.exec(h)) && attributs.length < 60) attributs.push(m[1] + " : " + m[2]);
  attributs = uniques(attributs).slice(0, 40);

  // Prix affiché pour TON compte (tu es connecté sur Shein dans ce navigateur)
  var prix = "";
  var zp = document.querySelector('[class*="productPrice"], [class*="product-intro__head-price"], [class*="from-price"], [class*="sale-price"]');
  if (zp) prix = zp.innerText.replace(/\s+/g, " ").trim().slice(0, 120);
  if (!prix) { var pj = tous(/"salePrice"\s*:\s*\{[^}]*?"amountWithSymbol"\s*:\s*"([^"]+)"/g); if (pj.length) prix = pj[0]; }

  var sn = tous(/"goods_sn"\s*:\s*"([^"]+)"/g)[0] || "";
  var gid = (location.pathname.match(/-p-(\d{5,})/) || [])[1] || (location.search.match(/goods_id=(\d{5,})/) || [])[1] || "";
  var principal = document.querySelector("main") || document.body;
  var d = {
    lien: location.href.split("?")[0], goods_id: gid, ref_shein: sn, titre: titre, prix: prix,
    images: imgs, attributs: attributs, tailles: uniques(tous(/"attr_value_name"\s*:\s*"([^"]{1,12})"/g)).slice(0, 15),
    texte: (principal.innerText || "").replace(/\s+/g, " ").slice(0, 15000)
  };
  window.open(SITE + "import#" + encodeURIComponent(JSON.stringify(d)), "_blank");
})();
