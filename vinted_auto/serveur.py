"""Le serveur web du site (aucun outil à installer : uniquement Python)."""
import hmac
import ipaddress
import json
import mimetypes
import os
import re
import secrets
import shutil
import sys
import threading
import time
import traceback
import webbrowser
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import atelier, config, db, ia, maj, paquet, photos, scalency
from .config import CODE, DONNEES, IMAGES, VERSION

WEB = CODE / "web"
EXTENSION_SOURCE = CODE / "extension"
EXTENSION_DOSSIER = DONNEES / "extension-chrome"
TYPES_IMAGES = {"image/jpeg": "jpg", "image/jpg": "jpg", "image/png": "png", "image/webp": "webp"}
MAX_UPLOAD = 20 * 1024 * 1024
CODE_SORTIE = {"code": 0}


class Refus(Exception):
    def __init__(self, message, http=400):
        super().__init__(message)
        self.http = http


# ------------------------------------------------------------------ outils

def json_annonce(a: dict, detail=False) -> dict:
    p = db.q1("SELECT * FROM produits WHERE id = ?", (a["produit_id"],)) or {}
    c = db.q1("SELECT * FROM comptes WHERE id = ?", (a["compte_id"],)) or {}
    fiche = json.loads(p.get("donnees") or "{}")
    d = {
        "id": a["id"], "produit_id": a["produit_id"], "statut": a["statut"], "etape": atelier.ETAPES.get(a["statut"], a["statut"]),
        "erreur": a["erreur"], "titre": a["titre"] or fiche.get("titre") or p.get("lien", ""), "prix": a["prix"],
        "taille": a["taille"], "compte_id": a["compte_id"], "compte": c.get("login") or a["compte_id"],
        "image": (fiche.get("images") or [""])[0], "photo_face": a["photo_face"], "photo_dos": a["photo_dos"],
        "job_info": a["job_info"], "job_statut": a["job_statut"], "vinted_id": a["vinted_id"],
        "lien": fiche.get("lien") or p.get("lien", ""), "cree": a["cree"], "maj": a["maj"],
        "lecture_erreur": p.get("erreur", ""),
    }
    if detail:
        analyse = json.loads(p.get("analyse") or "{}")
        d.update({
            "description": a["description"], "titre_base": a["titre_base"], "catalog_id": a["catalog_id"],
            "catalogue": a["catalogue"], "size_id": a["size_id"], "status_id": a["status_id"],
            "color_ids": json.loads(a["color_ids"] or "[]"), "material_ids": json.loads(a["material_ids"] or "[]"),
            "package_size_id": a["package_size_id"], "prompt_face": a["prompt_face"], "prompt_dos": a["prompt_dos"],
            "essai": a["essai"], "cout_eur": round((a["cout"] or 0) * float(db.reglage("eur_par_usd") or 0.92), 4),
            "fiche": {k: fiche.get(k) for k in ("titre", "couleur", "prix", "prix_texte", "images", "tailles", "attributs", "categorie", "lien")},
            "description_visuelle": analyse.get("description_visuelle", ""),
            "fond": c.get("fond_fichier", ""), "modele": c.get("modele_fichier", ""),
            "scene": c.get("scene_fichier", ""), "scene_description": c.get("scene_description", ""),
            "images_article": atelier.images_article(fiche),
            "modele_description": c.get("modele_description", ""), "fond_description": c.get("fond_description", ""),
            "photos_en_ligne": json.loads(a["photos_en_ligne"] or "[]"),
        })
    return d


def copier_extension():
    try:
        if EXTENSION_DOSSIER.exists():
            shutil.rmtree(EXTENSION_DOSSIER, ignore_errors=True)
        shutil.copytree(EXTENSION_SOURCE, EXTENSION_DOSSIER)
    except OSError:
        pass


def synchroniser_comptes():
    liste = scalency.comptes()
    for c in liste:
        db.ex("INSERT INTO comptes(id, login, relie) VALUES (?, ?, ?) ON CONFLICT(id) DO UPDATE SET login = excluded.login, relie = excluded.relie",
              (c["id"], c.get("login") or c["id"], 1 if c.get("linked") else 0))
    return len(liste)


# ------------------------------------------------------------------ serveur HTTP

class Handler(BaseHTTPRequestHandler):
    server_version = "VintedAuto"
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    # ---- réponses
    def envoyer(self, code, corps: bytes, type_contenu="application/json; charset=utf-8", extra=None):
        self.send_response(code)
        self.send_header("Content-Type", type_contenu)
        self.send_header("Content-Length", str(len(corps)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(corps)

    def json(self, obj, code=200, extra=None):
        self.envoyer(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"), extra=extra)

    def fichier(self, chemin):
        if not chemin.is_file():
            return self.json({"erreur": "Introuvable"}, 404)
        type_c = mimetypes.guess_type(str(chemin))[0] or "application/octet-stream"
        if type_c.startswith("text/") or type_c in ("application/javascript",):
            type_c += "; charset=utf-8"
        self.envoyer(200, chemin.read_bytes(), type_c)

    # ---- sécurité
    def est_local(self) -> bool:
        try:
            ip = ipaddress.ip_address(self.client_address[0])
        except ValueError:
            return False
        hote = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]").lower()
        return ip.is_loopback and hote in ("localhost", "127.0.0.1", "::1")

    def role(self):
        if self.est_local():
            return "admin"
        jar = SimpleCookie(self.headers.get("Cookie") or "")
        if "va_session" in jar:
            s = db.q1("SELECT role FROM sessions WHERE jeton = ?", (jar["va_session"].value,))
            if s:
                return s["role"]
        return None

    def verifier_ecriture(self):
        if self.headers.get("X-Vinted-Auto") != "1":
            raise Refus("Requête refusée.", 403)
        origine = self.headers.get("Origin")
        if origine and not origine.startswith("chrome-extension://") and not origine.startswith("moz-extension://"):
            hote = urlparse(origine).netloc.lower()
            if hote != (self.headers.get("Host") or "").lower():
                raise Refus("Requête refusée (autre site).", 403)

    def corps(self, max_taille=2 * 1024 * 1024) -> bytes:
        n = int(self.headers.get("Content-Length") or 0)
        if n > max_taille:
            raise Refus("Fichier trop gros.", 413)
        return self.rfile.read(n) if n else b""

    def corps_json(self) -> dict:
        b = self.corps()
        if not b:
            return {}
        try:
            return json.loads(b.decode("utf-8"))
        except ValueError:
            raise Refus("Données illisibles.")

    # ---- aiguillage
    def do_GET(self):
        self.traiter("GET")

    def do_HEAD(self):
        self.traiter("GET")

    def do_POST(self):
        self.traiter("POST")

    def do_DELETE(self):
        self.traiter("DELETE")

    def traiter(self, methode):
        url = urlparse(self.path)
        chemin = url.path
        self.params = {k: v[0] for k, v in parse_qs(url.query).items()}
        try:
            if chemin == "/api/ping":
                return self.json({"ok": True, "app": "vinted-auto", "version": VERSION})
            if methode == "GET" and not chemin.startswith("/api/") and not chemin.startswith("/fichiers/"):
                return self.statique(chemin)
            if methode != "GET":
                self.verifier_ecriture()
            if chemin == "/api/connexion" and methode == "POST":
                return self.connexion()
            role = self.role()
            if not role:
                raise Refus("Connecte-toi d'abord.", 401)
            if chemin.startswith("/fichiers/"):
                nom = chemin.rsplit("/", 1)[-1]
                if not re.fullmatch(r"[A-Za-z0-9_.-]+", nom):
                    raise Refus("Introuvable", 404)
                return self.fichier(IMAGES / nom)
            for (m, motif, fonction, roles) in ROUTES:
                if m != methode:
                    continue
                res = re.fullmatch(motif, chemin)
                if res:
                    if role not in roles:
                        raise Refus("Réservé à l'administrateur.", 403)
                    return fonction(self, *res.groups())
            raise Refus("Adresse inconnue.", 404)
        except Refus as e:
            self.json({"erreur": str(e)}, e.http)
        except (ValueError, KeyError, RuntimeError) as e:
            self.json({"erreur": str(e)}, 400)
        except (scalency.ErreurScalency, ia.ErreurIA, photos.ErreurPhotos) as e:
            self.json({"erreur": str(e)}, 502)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:  # noqa
            atelier.log_erreur(f"{methode} {self.path}", e)
            traceback.print_exc()
            try:
                self.json({"erreur": f"Erreur inattendue : {e}"}, 500)
            except OSError:
                pass

    def statique(self, chemin):
        if chemin in ("/", "/index.html"):
            return self.fichier(WEB / "index.html")
        rel = chemin.lstrip("/")
        if rel.startswith("static/"):
            cible = (WEB / rel[len("static/"):]).resolve()
            if WEB.resolve() in cible.parents:
                return self.fichier(cible)
        if chemin == "/favicon.ico":
            return self.envoyer(204, b"", "image/x-icon")
        return self.fichier(WEB / "index.html")

    def connexion(self):
        d = self.corps_json()
        mdp = str(d.get("mot_de_passe") or "")
        admin = config.get("ADMIN_PASSWORD")
        employe = config.get("EMPLOYEE_PASSWORD")
        if not admin and not employe:
            raise Refus("L'accès à distance n'est pas encore activé : Ethan doit choisir les mots de passe dans Réglages.", 403)
        role = None
        if admin and hmac.compare_digest(mdp, admin):
            role = "admin"
        elif employe and hmac.compare_digest(mdp, employe):
            role = "employee"
        if not role:
            time.sleep(1)
            raise Refus("Mot de passe incorrect.", 401)
        jeton = secrets.token_urlsafe(32)
        db.ex("INSERT INTO sessions(jeton, role, quand) VALUES (?, ?, ?)", (jeton, role, time.time()))
        self.json({"ok": True, "role": role},
                  extra={"Set-Cookie": f"va_session={jeton}; Path=/; HttpOnly; SameSite=Strict; Max-Age=31536000"})


# ------------------------------------------------------------------ routes

def r_etat(h):
    cles = {k: bool(config.get(k)) for k in config.CLES}
    eur = float(db.reglage("eur_par_usd") or 0.92)
    compteurs = {r["statut"]: r["n"] for r in db.q("SELECT statut, COUNT(*) AS n FROM annonces GROUP BY statut")}
    h.json({
        "role": h.role(), "local": h.est_local(), "version": VERSION, "cles": cles,
        "cout_jour_eur": round(db.cout_du_jour_usd() * eur, 6), "cout_mois_eur": round(db.cout_du_mois_usd() * eur, 6),
        "compteurs": compteurs,
        "extension_dossier": str(EXTENSION_DOSSIER), "donnees": str(DONNEES),
        "publier_auto": db.reglage("publier_auto") == "1",
    })


def r_annonces(h):
    sql, args = "SELECT * FROM annonces WHERE 1=1", []
    if h.role() == "employee":
        sql += " AND statut IN ('a_photographier', 'prete')"
    if h.params.get("compte"):
        sql += " AND compte_id = ?"
        args.append(h.params["compte"])
    st = h.params.get("statut")
    if st:
        sql += f" AND statut IN ({','.join('?' * len(st.split(',')))})"
        args += st.split(",")
    sql += " ORDER BY id DESC LIMIT 400"
    h.json({"annonces": [json_annonce(a) for a in db.q(sql, args)]})


def _annonce(id_):
    a = db.q1("SELECT * FROM annonces WHERE id = ?", (int(id_),))
    if not a:
        raise Refus("Annonce introuvable.", 404)
    return a


def r_annonce(h, id_):
    h.json(json_annonce(_annonce(id_), detail=True))


def r_annonce_modifier(h, id_):
    a = _annonce(id_)
    if a["statut"] in ("envoi", "en_file", "publiee"):
        raise Refus("Cette annonce est déjà envoyée : on ne peut plus la modifier ici.")
    d = h.corps_json()
    champs = {}
    if "catalog_id" in d and d["catalog_id"]:
        cid = int(d["catalog_id"])
        chemins = dict(scalency.chemins_categories())
        champs["catalog_id"] = cid
        champs["catalogue"] = chemins.get(cid, "")
    for k, conv in (("prix", float), ("status_id", int), ("package_size_id", int)):
        if k in d and d[k] not in (None, ""):
            champs[k] = conv(str(d[k]).replace(",", "."))
    if "color_ids" in d:
        champs["color_ids"] = [int(x) for x in d["color_ids"]][:2]
    if champs:
        db.maj("annonces", a["id"], **champs)
    if "taille" in d:
        atelier.appliquer_taille(a["id"], str(d["taille"]))
    elif "catalog_id" in champs:
        atelier.appliquer_taille(a["id"], a["taille"])
    if "size_id" in d and d["size_id"]:
        db.maj("annonces", a["id"], size_id=int(d["size_id"]))
    textes = {}
    if d.get("titre"):
        textes["titre"] = str(d["titre"])[:100]
    if d.get("description"):
        textes["description"] = str(d["description"])[:2000]
    if textes:
        db.maj("annonces", a["id"], **textes)
    a = _annonce(id_)
    if a["statut"] == "echec" and not atelier.verifier(a):
        db.maj("annonces", a["id"], statut="prete", erreur="")
    h.json(json_annonce(_annonce(id_), detail=True))


def r_photo(h, id_, vue):
    type_c = (h.headers.get("Content-Type") or "").split(";")[0].strip().lower()
    if type_c not in TYPES_IMAGES:
        raise Refus("Format refusé : envoie une photo JPG, PNG ou WEBP.")
    contenu = h.corps(MAX_UPLOAD)
    if len(contenu) < 1000:
        raise Refus("Photo vide ou abîmée.")
    atelier.enregistrer_photo(int(id_), vue, contenu, TYPES_IMAGES[type_c])
    h.json(json_annonce(_annonce(id_), detail=True))


def r_images_zip(h, id_):
    nom, octets = paquet.zip_de(int(id_), h.params.get("quoi", "tout"))
    from urllib.parse import quote
    h.envoyer(200, octets, "application/zip",
              {"Content-Disposition": f"attachment; filename=\"images.zip\"; filename*=UTF-8''{quote(nom)}"})


def r_images_ouvrir(h, id_):
    if not h.est_local():
        raise Refus("Le dossier ne peut s'ouvrir que sur le PC du site : utilise le bouton ZIP.")
    cible = paquet.ecrire_dossier(int(id_), (h.corps_json().get("quoi") or "tout"))
    h.json({"ok": True, "dossier": str(cible), "fichiers": sorted(f.name for f in cible.iterdir())})


def r_valider_photos(h, id_):
    atelier.valider_photos(int(id_))
    h.json(json_annonce(_annonce(id_), detail=True))


def r_refaire(h, id_):
    atelier.refaire_photos(int(id_))
    h.json(json_annonce(_annonce(id_), detail=True))


def r_regenerer(h, id_):
    a = _annonce(id_)
    if a["statut"] in ("envoi", "en_file", "publiee"):
        raise Refus("Annonce déjà envoyée.")
    p = db.q1("SELECT statut FROM produits WHERE id = ?", (a["produit_id"],))
    if p["statut"] != "lu":
        raise Refus("La fiche Shein n'a pas encore été lue.")
    db.maj("annonces", a["id"], statut="generation", erreur="")
    atelier.lancer(atelier.generer, a["produit_id"], [a["id"]])
    h.json({"ok": True})


def r_essai(h, id_):
    h.json({"message": atelier.essai(int(id_))})


def r_publier(h):
    d = h.corps_json()
    ids = [int(i) for i in d.get("ids") or []]
    if not ids:
        raise Refus("Aucune annonce choisie.")
    atelier.lancer(atelier.publier_plusieurs, ids, bool(d.get("ignorer_doublon")))
    h.json({"ok": True, "message": f"{len(ids)} annonce(s) envoyée(s) à Scalency. Suis leur état dans la liste."})


def r_annuler(h, id_):
    atelier.annuler(int(id_))
    h.json(json_annonce(_annonce(id_), detail=True))


def r_supprimer(h, id_):
    a = _annonce(id_)
    if a["statut"] in ("envoi", "en_file"):
        raise Refus("Annule d'abord la publication en cours.")
    db.ex("DELETE FROM annonces WHERE id = ?", (a["id"],))
    if not db.q1("SELECT id FROM annonces WHERE produit_id = ?", (a["produit_id"],)):
        db.ex("DELETE FROM produits WHERE id = ?", (a["produit_id"],))
    h.json({"ok": True})


def r_suivi(h):
    n = atelier.suivre_une_fois()
    h.json({"ok": True, "suivies": n})


# ---- import Shein

def r_importer(h):
    d = h.corps_json()
    produits = atelier.importer(d.get("liens") or "", d.get("comptes") or [], d.get("tailles"))
    h.json({"produits": produits})


def r_a_lire(h):
    h.json({"produits": atelier.produits_a_lire()})


def r_fiche(h, pid):
    d = json.loads(h.corps(4 * 1024 * 1024).decode("utf-8") or "{}")
    atelier.recevoir_fiche(int(pid), d)
    h.json({"ok": True})


def r_relire(h, pid):
    db.maj("produits", int(pid), statut="lecture", erreur="")
    db.ex("UPDATE annonces SET statut = 'lecture', erreur = '' WHERE produit_id = ? AND statut IN ('echec', 'lecture')", (int(pid),))
    h.json({"ok": True})


def r_brouillon(h):
    d = json.loads(h.corps(4 * 1024 * 1024).decode("utf-8") or "{}")
    pid = atelier.creer_brouillon(d)
    h.json({"id": pid})


def r_brouillon_lire(h, pid):
    p = db.q1("SELECT * FROM produits WHERE id = ? AND brouillon = 1", (int(pid),))
    if not p:
        raise Refus("Cet article a déjà été traité.", 404)
    h.json({"id": p["id"], "fiche": json.loads(p["donnees"]), "taille": p["taille_demandee"]})


def r_brouillon_valider(h, pid):
    d = h.corps_json()
    atelier.valider_brouillon(int(pid), d.get("comptes") or [], d.get("taille") or "")
    h.json({"ok": True})


# ---- catégories

def r_categories(h):
    q = (h.params.get("q") or "").lower()
    res = [{"id": i, "chemin": c} for i, c in scalency.chemins_categories() if not q or q in c.lower()]
    h.json({"categories": res[:80]})


def r_categorie(h, id_):
    d = scalency.categorie(int(id_))
    tailles = []
    for g in d.get("size_groups") or []:
        for s in g.get("sizes") or []:
            tailles.append({"id": s["id"], "titre": s["title"]})
    h.json({"tailles": tailles, "etats": d.get("conditions") or []})


# ---- comptes

def r_comptes(h):
    h.json({"comptes": db.q("SELECT * FROM comptes ORDER BY relie DESC, login")})


def r_comptes_sync(h):
    n = synchroniser_comptes()
    h.json({"ok": True, "nombre": n, "comptes": db.q("SELECT * FROM comptes ORDER BY relie DESC, login")})


def _compte(id_):
    c = db.q1("SELECT * FROM comptes WHERE id = ?", (id_,))
    if not c:
        raise Refus("Compte introuvable.", 404)
    return c


def _rafraichir_prompts(compte_id):
    for a in db.q("SELECT id FROM annonces WHERE compte_id = ? AND statut IN ('a_photographier', 'prete', 'echec') AND titre_base != ''", (compte_id,)):
        atelier.refaire_prompts(a["id"])


def r_compte_modifier(h, id_):
    c = _compte(id_)
    d = h.corps_json()
    champs = {}
    if "actif" in d:
        champs["actif"] = 1 if d["actif"] else 0
    for k in ("fond_description", "modele_description", "scene_description"):
        if k in d:
            champs[k] = str(d[k] or "")[:1500]
    if champs:
        sets = ", ".join(f"{k} = ?" for k in champs)
        db.ex(f"UPDATE comptes SET {sets} WHERE id = ?", (*champs.values(), c["id"]))
        _rafraichir_prompts(c["id"])
    h.json(_compte(id_))


def r_compte_image(h, id_, quoi):
    c = _compte(id_)
    if quoi not in ("fond", "modele", "scene"):
        raise Refus("Image inconnue.")
    if h.params.get("supprimer"):
        db.ex(f"UPDATE comptes SET {quoi}_fichier = '' WHERE id = ?", (c["id"],))
    else:
        type_c = (h.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if type_c not in TYPES_IMAGES:
            raise Refus("Format refusé : envoie une image JPG, PNG ou WEBP.")
        contenu = h.corps(MAX_UPLOAD)
        if len(contenu) < 1000:
            raise Refus("Image vide ou abîmée.")
        nom = f"compte-{re.sub(r'[^A-Za-z0-9_-]', '', c['id'])[:40]}-{quoi}-{int(time.time())}.{TYPES_IMAGES[type_c]}"
        (IMAGES / nom).write_bytes(contenu)
        db.ex(f"UPDATE comptes SET {quoi}_fichier = ? WHERE id = ?", (nom, c["id"]))
    _rafraichir_prompts(c["id"])
    h.json(_compte(id_))


def r_compte_prompt(h, id_, quoi):
    c = _compte(id_)
    idee = str(h.corps_json().get("idee") or "")[:600]
    if quoi == "scene":
        texte, _ = ia.prompt_scene(idee)
    else:
        raise Refus("Inconnu.")
    db.ex(f"UPDATE comptes SET prompt_{quoi} = ? WHERE id = ?", (texte.strip(), c["id"]))
    h.json(_compte(id_))


def r_compte_copier(h, id_):
    """Copie le fond et/ou le modèle d'un compte vers d'autres (pratique au début)."""
    c = _compte(id_)
    d = h.corps_json()
    for autre in d.get("vers") or []:
        _compte(autre)
        if "scene" in (d.get("quoi") or []):
            db.ex("UPDATE comptes SET scene_fichier = ?, scene_description = ? WHERE id = ?", (c["scene_fichier"], c["scene_description"], autre))
        if "fond" in (d.get("quoi") or []):
            db.ex("UPDATE comptes SET fond_fichier = ?, fond_description = ? WHERE id = ?", (c["fond_fichier"], c["fond_description"], autre))
        if "modele" in (d.get("quoi") or []):
            db.ex("UPDATE comptes SET modele_fichier = ?, modele_description = ? WHERE id = ?", (c["modele_fichier"], c["modele_description"], autre))
        _rafraichir_prompts(autre)
    h.json({"ok": True})


# ---- réglages

def r_reglages(h):
    cles = {k: {"libelle": lib, "rempli": bool(config.get(k)),
                "apercu": config.masquer(config.get(k)) if k in config.SECRETES else config.get(k)}
            for k, lib in config.CLES.items()}
    h.json({"cles": cles, "reglages": db.reglages()})


def r_reglages_enregistrer(h):
    d = h.corps_json()
    modifs = {k: v for k, v in (d.get("cles") or {}).items() if k in config.CLES and str(v or "").strip()}
    for k in (d.get("effacer") or []):
        if k in config.CLES:
            modifs[k] = ""
    if modifs:
        config.enregistrer_env(modifs)
    for k, v in (d.get("reglages") or {}).items():
        if k in db.REGLAGES_DEFAUT:
            db.set_reglage(k, str(v).strip().replace(",", "."))
    r_reglages(h)


def r_tester(h):
    quoi = h.corps_json().get("quoi")
    if quoi == "anthropic":
        rep = ia.tester()
        msg = f"Claude répond : {rep[:60]}"
    elif quoi == "scalency":
        m = scalency.moi()
        n = synchroniser_comptes()
        relies = db.q1("SELECT COUNT(*) AS n FROM comptes WHERE relie = 1")["n"]
        msg = f"Scalency OK ({(m.get('account') or {}).get('name', '')}) : {n} comptes trouvés, dont {relies} reliés à Scalency Plugin."
    elif quoi == "supabase":
        photos.preparer()
        msg = "Supabase OK : le dossier « vinted-photos » est prêt."
    else:
        raise Refus("Test inconnu.")
    h.json({"ok": True, "message": msg})


def r_maj_info(h):
    h.json({"version": VERSION, "disponible": maj.version_disponible()})


def r_maj(h):
    maj.installer()
    h.json({"ok": True, "message": "Mise à jour installée : le site redémarre, la page va se recharger."})
    threading.Thread(target=_redemarrer, daemon=True).start()


def _redemarrer():
    time.sleep(1)
    CODE_SORTIE["code"] = 42
    SERVEUR["s"].shutdown()


def r_ouvrir_extension(h):
    copier_extension()
    if os.name == "nt" and h.est_local():
        os.startfile(str(EXTENSION_DOSSIER))  # noqa
    h.json({"dossier": str(EXTENSION_DOSSIER)})


ADMIN = ("admin",)
TOUS = ("admin", "employee")
N = r"(\d+)"
ROUTES = [
    ("GET", r"/api/etat", r_etat, TOUS),
    ("GET", r"/api/annonces", r_annonces, TOUS),
    ("GET", rf"/api/annonces/{N}", r_annonce, TOUS),
    ("POST", rf"/api/annonces/{N}", r_annonce_modifier, ADMIN),
    ("POST", rf"/api/annonces/{N}/photo/(face|dos)", r_photo, TOUS),
    ("POST", rf"/api/annonces/{N}/valider-photos", r_valider_photos, TOUS),
    ("GET", rf"/api/annonces/{N}/images.zip", r_images_zip, TOUS),
    ("POST", rf"/api/annonces/{N}/images/ouvrir", r_images_ouvrir, TOUS),
    ("POST", rf"/api/annonces/{N}/refaire", r_refaire, TOUS),
    ("POST", rf"/api/annonces/{N}/regenerer", r_regenerer, ADMIN),
    ("POST", rf"/api/annonces/{N}/essai", r_essai, ADMIN),
    ("POST", rf"/api/annonces/{N}/annuler", r_annuler, ADMIN),
    ("POST", rf"/api/annonces/{N}/supprimer", r_supprimer, ADMIN),
    ("POST", r"/api/publier", r_publier, ADMIN),
    ("POST", r"/api/suivi", r_suivi, ADMIN),
    ("POST", r"/api/importer", r_importer, ADMIN),
    ("GET", r"/api/a-lire", r_a_lire, ADMIN),
    ("POST", rf"/api/shein/{N}", r_fiche, ADMIN),
    ("POST", rf"/api/produits/{N}/relire", r_relire, ADMIN),
    ("POST", r"/api/shein/brouillon", r_brouillon, ADMIN),
    ("GET", rf"/api/brouillons/{N}", r_brouillon_lire, ADMIN),
    ("POST", rf"/api/brouillons/{N}/valider", r_brouillon_valider, ADMIN),
    ("GET", r"/api/categories", r_categories, ADMIN),
    ("GET", rf"/api/categories/{N}", r_categorie, ADMIN),
    ("GET", r"/api/comptes", r_comptes, ADMIN),
    ("POST", r"/api/comptes/synchroniser", r_comptes_sync, ADMIN),
    ("POST", r"/api/comptes/([A-Za-z0-9_-]+)", r_compte_modifier, ADMIN),
    ("POST", r"/api/comptes/([A-Za-z0-9_-]+)/image/(fond|modele|scene)", r_compte_image, ADMIN),
    ("POST", r"/api/comptes/([A-Za-z0-9_-]+)/prompt/(scene)", r_compte_prompt, ADMIN),
    ("POST", r"/api/comptes/([A-Za-z0-9_-]+)/copier", r_compte_copier, ADMIN),
    ("GET", r"/api/reglages", r_reglages, ADMIN),
    ("POST", r"/api/reglages", r_reglages_enregistrer, ADMIN),
    ("POST", r"/api/tester", r_tester, ADMIN),
    ("GET", r"/api/maj", r_maj_info, ADMIN),
    ("POST", r"/api/maj", r_maj, ADMIN),
    ("POST", r"/api/extension/ouvrir", r_ouvrir_extension, ADMIN),
]
SERVEUR = {}


def main():
    db.init()
    copier_extension()
    port = int(config.get("PORT", "8000") or 8000)
    # Accès depuis un autre appareil seulement si un mot de passe est choisi (sinon : ce PC uniquement,
    # et Windows n'affiche pas d'alerte du pare-feu).
    hote = "0.0.0.0" if (config.get("EMPLOYEE_PASSWORD") or config.get("ADMIN_PASSWORD")) else "127.0.0.1"
    try:
        s = ThreadingHTTPServer((hote, port), Handler)
    except OSError:
        print(f"\n  ERREUR : le port {port} est déjà utilisé par un autre programme.")
        print("  Ferme l'autre fenêtre noire de Vinted Auto, ou redémarre le PC.")
        sys.exit(3)
    s.daemon_threads = True
    SERVEUR["s"] = s
    stop = threading.Event()
    threading.Thread(target=atelier.boucle_suivi, args=(stop,), daemon=True).start()
    atelier.reprendre_au_demarrage()
    if db.q1("SELECT COUNT(*) AS n FROM comptes")["n"] == 0 and config.get("SCALENCY_API_KEY"):
        atelier.lancer(synchroniser_comptes)
    adresse = f"http://localhost:{port}/"
    print("\n  ------------------------------------------------------------")
    print(f"   Le site est lancé : {adresse}")
    print("   Laisse cette fenêtre ouverte (tu peux la réduire).")
    print("   Pour arrêter le site : ferme cette fenêtre.")
    print("  ------------------------------------------------------------\n")
    if not os.environ.get("VINTED_AUTO_SANS_NAVIGATEUR"):
        threading.Timer(0.8, lambda: webbrowser.open(adresse)).start()
    try:
        s.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        s.server_close()
    sys.exit(CODE_SORTIE["code"])


if __name__ == "__main__":
    main()
