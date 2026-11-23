"""Faux services pour tester tout le circuit sans rien publier pour de vrai :
Claude (API Anthropic), Scalency, Supabase et une fiche Shein (copie de la vraie structure gbRawData).

Lancement : python tests/faux_services.py 8765
"""
import json
import re
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

JOURNAL = {"anthropic": [], "scalency_post": [], "supabase": [], "jobs_lus": 0}
JOBS = {}
FICHIERS = {}

CATALOGUES = [
    {"id": 1904, "title": "Femmes", "parent_id": None},
    {"id": 4, "title": "Vêtements", "parent_id": 1904},
    {"id": 10, "title": "Robes", "parent_id": 4},
    {"id": 1065, "title": "Robes d'été", "parent_id": 10},
    {"id": 1774, "title": "Mini-robes", "parent_id": 10},
    {"id": 12, "title": "Hauts et t-shirts", "parent_id": 4},
    {"id": 221, "title": "T-shirts", "parent_id": 12},
    {"id": 5, "title": "Hommes", "parent_id": None},
    {"id": 2050, "title": "Vêtements", "parent_id": 5},
]
DETAIL = {
    "attributes": [{"code": "material", "options": [{"id": 45, "title": "Polyester"}, {"id": 53, "title": "Élasthanne"}, {"id": 44, "title": "Coton"}]}],
    "conditions": [{"id": 2, "title": "Très bon état"}, {"id": 6, "title": "Neuf avec étiquette"}],
    "size_groups": [
        {"id": 4, "title": "Taille", "sizes": [{"id": 2, "title": "XS / 34 / 6"}, {"id": 3, "title": "S / 36 / 8"}, {"id": 4, "title": "M / 38 / 10"}, {"id": 5, "title": "L / 40 / 12"}, {"id": 6, "title": "XL / 42 / 14"}, {"id": 7, "title": "XXL / 44 / 16"}]},
        {"id": 80, "title": "Taille", "sizes": [{"id": 1738, "title": "S"}]},
    ],
}
ITEMS_EXISTANTS = {"vt-2": [{"id": "999", "account_id": "vt-2", "title": "Robe déjà en ligne", "sku": "SHEIN-sz2310071691901000", "status": "active"}]}


def gb_raw_data(goods_id="24616628", sn="sz2310071691901000"):
    # Structure copiée d'une vraie fiche fr.shein.com (novembre 2026), contenu raccourci
    img = "//img.ltwebstatic.com/images3_pi/2023/10/13/02/16971684628a3ce766b3e854f3cedee214437dd785_thumbnail_900x.webp"
    img2 = "//img.ltwebstatic.com/images3_pi/2023/10/13/9f/169716846484c3da950090f770457b566f551cb3a2_thumbnail_900x.webp"
    return {"modules": {
        "productInfo": {
            "goods_id": goods_id, "goods_sn": sn, "goods_name": "SHEIN LUNE Robe Col Surplis Manches Bouffantes À Ruchés",
            "cat_id": "1727", "cate_name": "Robes pour femmes",
            "cateInfos": {"1727": {"category_name": "Robes courtes pour femmes"}},
            "currentSkcImgInfo": {"spuImages": ["//img.ltwebstatic.com/images3_spmp/2023/10/13/aa/tableau01.jpg"], "skcImages": [img, img2]},
            "productDescriptionInfo": {"goods_desc": "", "productDetails": [
                {"attr_name": "Couleur", "attr_value": "Fushia"}, {"attr_name": "Encolure", "attr_value": "Col en V"},
                {"attr_name": "Type de manches", "attr_value": "Manches bishop"}, {"attr_name": "Détails", "attr_value": "Plissé, Froncé"},
                {"attr_name": "Composition", "attr_value": "95% Polyester, 5% Élasthanne"}]},
        },
        "saleAttr": {
            "mainSaleAttribute": {"info": [{"goods_id": "20832200", "attr_value": "Noir"}, {"goods_id": goods_id, "attr_value": "Fushia"}]},
            "sizeInfo": {"sizeInfo": [
                {"attr_id": "87", "attr_name": "Taille", "attr_value_id": "755", "attr_value_name": "XS", "Carrure ": " 34 cm", "Tour de poitrine ": " 86 cm", "Longueur ": " 88 cm"},
                {"attr_id": "87", "attr_name": "Taille", "attr_value_id": "568", "attr_value_name": "S", "Carrure ": " 35 cm", "Tour de poitrine ": " 90 cm", "Longueur ": " 90 cm"},
                {"attr_id": "87", "attr_name": "Taille", "attr_value_id": "417", "attr_value_name": "M", "Carrure ": " 36 cm", "Tour de poitrine ": " 94 cm", "Longueur ": " 92 cm"}]},
        },
        "priceInfo": {"salePrice": {"amount": "10.05", "amountWithSymbol": "10,05€"}},
    }}


def page_shein(goods_id, sn):
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>SHEIN LUNE Robe | SHEIN FRANCE</title></head><body>
<h1>SHEIN LUNE Robe Col Surplis Manches Bouffantes À Ruchés</h1>
<div class="productPriceContainer"><div class="productPrice"><div class="productPrice__main">10,05€</div></div></div>
<div class="product-intro__size-radio">34 (XS)</div><div class="product-intro__size-radio">36 (S)</div><div class="product-intro__size-radio">38 (M)</div>
<script>window.gbRawData = {json.dumps(gb_raw_data(goods_id, sn))};</script></body></html>"""


def reponse_claude(corps):
    texte_user = json.dumps(corps.get("messages", []), ensure_ascii=False)
    fmt = (corps.get("output_config") or {}).get("format")
    if fmt:
        m = re.search(r"Nombre d'annonces à rédiger : (\d+)", texte_user)
        n = int(m.group(1)) if m else 1
        res = {
            "description_visuelle": "Robe courte fuchsia vif, col en V croisé, manches bouffantes resserrées aux poignets, taille froncée, jupe évasée.",
            "type_article": "Robe courte", "couleurs": ["Rose"], "matieres": ["Polyester", "Élasthanne"], "categorie_id": 1774,
            "annonces": [{"titre": f"Robe courte fuchsia à manches bouffantes {i + 1}", "description": f"Jolie robe fuchsia, col croisé. Très bon état. Version {i + 1}.\n#robe #fuchsia #mode"} for i in range(n)],
        }
        texte = json.dumps(res, ensure_ascii=False)
    else:
        texte = "Photo réaliste d'une chambre lumineuse… (prompt de test)"
    return {"id": "msg_test", "type": "message", "role": "assistant", "model": corps.get("model"),
            "content": [{"type": "text", "text": texte}], "stop_reason": "end_turn", "stop_sequence": None,
            "usage": {"input_tokens": 3000, "output_tokens": 400, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}}


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def rep(self, code, obj=None, brut=None, type_c="application/json"):
        b = brut if brut is not None else json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", type_c)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def corps(self):
        n = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(n) if n else b""

    def do_GET(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        hote = (self.headers.get("Host") or "")
        if "shein" in hote:
            m = re.search(r"-p-(\d+)", u.path)
            if not m:
                return self.rep(404, brut=b"not found", type_c="text/html")
            sn = "sz2310071691901000" if m.group(1) == "24616628" else "sz" + m.group(1)
            return self.rep(200, brut=page_shein(m.group(1), sn).encode(), type_c="text/html; charset=utf-8")
        p = u.path
        if p.startswith("/images"):   # fausses photos produit Shein (img.ltwebstatic.com)
            JOURNAL.setdefault("images", []).append(p)
            return self.rep(200, brut=b"\xff\xd8\xff\xe0" + p.encode() + b"\x00" * 2000, type_c="image/jpeg")
        if p.startswith("/api/pub/public_api/v1"):
            if self.headers.get("Authorization") != "Bearer scal_live_test":
                return self.rep(401, {"error": {"code": "cle_invalide", "message": "Clé inconnue ou révoquée."}})
            p = p[len("/api/pub/public_api/v1"):]
            if p == "/me":
                return self.rep(200, {"account": {"name": "Test"}, "limits": {"requests_per_minute": 60}})
            if p == "/accounts":
                return self.rep(200, {"data": [{"id": "vt-1", "login": "compte_un", "linked": True}, {"id": "vt-2", "login": "compte_deux", "linked": True},
                                               {"id": "x-3", "login": "pas_relie", "linked": False}], "has_more": False, "next_cursor": None})
            if p == "/catalogs":
                o = int(q.get("cursor") or 0)
                page = CATALOGUES[o:o + 5]
                plus = o + 5 < len(CATALOGUES)
                return self.rep(200, {"data": page, "has_more": plus, "next_cursor": str(o + 5) if plus else None})
            if re.fullmatch(r"/catalogs/\d+", p):
                return self.rep(200, dict(DETAIL, id=int(p.rsplit("/", 1)[1])))
            if p == "/items":
                return self.rep(200, {"data": ITEMS_EXISTANTS.get(q.get("account_id"), []), "has_more": False, "next_cursor": None})
            if p == "/jobs":
                if q.get("ids"):
                    JOURNAL["jobs_lus"] += 1
                    res = []
                    for i in q["ids"].split(","):
                        j = JOBS.get(int(i))
                        if j:
                            if j["status"] == "queued":
                                j["status"], j["status_label"], j["new_item_id"] = "done", "Terminée", 5550000 + j["id"]
                            res.append(j)
                    return self.rep(200, {"data": res, "has_more": False, "next_cursor": None})
                return self.rep(200, {"data": [], "has_more": False, "next_cursor": None})
        if p.startswith("/storage/v1/bucket/"):
            return self.rep(200, {"id": "vinted-photos", "public": True})
        if p.startswith("/storage/v1/object/public/"):
            b = FICHIERS.get(p.split("/public/", 1)[1])
            return self.rep(200 if b else 404, brut=b or b"", type_c="image/jpeg")
        if p == "/journal":
            return self.rep(200, {**JOURNAL, "jobs": JOBS})
        self.rep(404, {"error": {"code": "introuvable", "message": "?"}})

    def do_POST(self):
        u = urlparse(self.path)
        p = u.path
        b = self.corps()
        if p == "/v1/messages":
            corps = json.loads(b)
            JOURNAL["anthropic"].append({"headers": {k.lower(): v for k, v in self.headers.items() if k.lower() in ("x-api-key", "authorization", "anthropic-version")}, "corps": corps})
            if self.headers.get("x-api-key") != "sk-ant-test" and self.headers.get("Authorization") != "Bearer sk-ant-test":
                return self.rep(401, {"type": "error", "error": {"type": "authentication_error", "message": "invalid x-api-key"}})
            return self.rep(200, reponse_claude(corps))
        if p.startswith("/api/pub/public_api/v1"):
            if self.headers.get("Authorization") != "Bearer scal_live_test":
                return self.rep(401, {"error": {"code": "cle_invalide", "message": "Clé inconnue ou révoquée."}})
            p = p[len("/api/pub/public_api/v1"):]
            corps = json.loads(b or b"{}")
            if p == "/items":
                JOURNAL["scalency_post"].append(corps)
                manque = [k for k in ("account_id", "title", "description", "price", "catalog_id", "status_id", "photos") if not corps.get(k)]
                if manque:
                    return self.rep(400, {"error": {"code": "requete_invalide", "message": "Champs manquants : " + ", ".join(manque)}})
                if corps.get("dry_run"):
                    return self.rep(200, {"dry_run": True, "would_queue": True, "reason": "", "message": "Essai à blanc : rien n'est mis en file ni envoyé."})
                jid = 1000 + len(JOBS) + 1
                JOBS[jid] = {"id": jid, "account_id": corps["account_id"], "type": "publish", "status": "queued", "status_label": "En file",
                             "reason": "En file : part après la publication en cours sur ce compte.", "title": corps["title"], "refs": {"sku": corps.get("sku")}}
                return self.rep(202, {"status": "queued", "job": JOBS[jid]})
            if re.fullmatch(r"/jobs/\d+/cancel", p):
                j = JOBS[int(p.split("/")[2])]
                j["status"] = "cancelled"
                return self.rep(200, {"status": "cancelled", "job": j})
        if p == "/storage/v1/bucket":
            return self.rep(200, {"name": "vinted-photos"})
        if p.startswith("/storage/v1/object/vinted-photos/"):
            nom = p.split("/storage/v1/object/", 1)[1]
            FICHIERS[nom] = b
            JOURNAL["supabase"].append({"nom": nom, "taille": len(b), "type": self.headers.get("Content-Type"), "apikey": bool(self.headers.get("apikey"))})
            return self.rep(200, {"Key": nom})
        self.rep(404, {"error": {"code": "introuvable", "message": "?"}})

    do_PUT = do_POST


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    s = ThreadingHTTPServer(("0.0.0.0", port), H)
    print(f"faux services sur {port}", flush=True)
    s.serve_forever()
