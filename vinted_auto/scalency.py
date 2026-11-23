"""Client de l'API Scalency (documentation : scalencyai.com/docs/api)."""
import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from . import config, db

BASE = os.environ.get("SCALENCY_BASE_URL", "https://app.scalencyai.com/api/pub/public_api/v1")
_ecritures = []  # horodatage des dernières écritures (10 par minute au plus)
_verrou = threading.Lock()


class ErreurScalency(Exception):
    def __init__(self, message, code="", http=0):
        super().__init__(message)
        self.code = code
        self.http = http


def _attendre_ecriture():
    with _verrou:
        while True:
            now = time.time()
            while _ecritures and now - _ecritures[0] > 61:
                _ecritures.pop(0)
            if len(_ecritures) < 9:
                _ecritures.append(now)
                return
            time.sleep(max(1, 61 - (now - _ecritures[0])))


def appel(methode, chemin, corps=None, params=None, essais=4):
    cle = config.get("SCALENCY_API_KEY")
    if not cle:
        raise ErreurScalency("La clé Scalency n'est pas encore remplie (page Réglages).", "cle_absente")
    url = BASE + chemin
    if params:
        url += "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v not in (None, "")})
    data = json.dumps(corps).encode() if corps is not None else None
    if methode != "GET":
        _attendre_ecriture()
    for essai in range(essais):
        req = urllib.request.Request(url, data=data, method=methode, headers={
            "Authorization": f"Bearer {cle}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "VintedAuto/" + config.VERSION,
        })
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                texte = r.read().decode("utf-8") or "{}"
                return json.loads(texte)
        except urllib.error.HTTPError as e:
            texte = e.read().decode("utf-8", "replace")
            try:
                err = json.loads(texte).get("error", {})
            except ValueError:
                err = {}
            if e.code == 429 and essai < essais - 1:
                time.sleep(min(90, int(e.headers.get("Retry-After") or 20)))
                continue
            if e.code >= 500 and essai < essais - 1:
                time.sleep(5 * (essai + 1))
                continue
            raise ErreurScalency(err.get("message") or f"Scalency a répondu {e.code}.", err.get("code", ""), e.code)
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            if essai < essais - 1:
                time.sleep(3 * (essai + 1))
                continue
            raise ErreurScalency(f"Impossible de joindre Scalency ({e}). Vérifie ta connexion internet.", "reseau")


def tout_lire(chemin, params=None, max_pages=60):
    params = dict(params or {}, limit=100)
    res = []
    for _ in range(max_pages):
        r = appel("GET", chemin, params=params)
        res += r.get("data", [])
        if not r.get("has_more") or not r.get("next_cursor"):
            break
        params["cursor"] = r["next_cursor"]
    return res


def moi():
    return appel("GET", "/me")


def comptes():
    return tout_lire("/accounts")


def categories():
    """Toutes les catégories Vinted (gardées 30 jours en mémoire)."""
    c = db.cache_get("catalogues", 30 * 86400)
    if c:
        return c
    c = tout_lire("/catalogs")
    if c:
        db.cache_set("catalogues", c)
    return c


def categorie(id_):
    cle = f"catalogue:{id_}"
    c = db.cache_get(cle, 14 * 86400)
    if c:
        return c
    c = appel("GET", f"/catalogs/{int(id_)}")
    db.cache_set(cle, c)
    return c


def chemins_categories(racine=1904):
    """Liste des catégories « feuilles » sous Femmes : [(id, 'Femmes > Vêtements > Robes > Robes d'été')]."""
    cats = categories()
    par_id = {c["id"]: c for c in cats}
    enfants = {}
    for c in cats:
        enfants.setdefault(c.get("parent_id"), []).append(c["id"])

    def chemin(i):
        noms, vus = [], set()
        while i in par_id and i not in vus:
            vus.add(i)
            noms.append(par_id[i]["title"])
            i = par_id[i].get("parent_id")
        return list(reversed(noms))

    def sous(i):
        vus, pile = set(), [i]
        while pile:
            x = pile.pop()
            if x in vus:
                continue
            vus.add(x)
            pile += enfants.get(x, [])
        return vus

    zone = sous(racine)
    res = []
    for i in zone:
        if i == racine or enfants.get(i):
            continue
        res.append((i, " > ".join(chemin(i))))
    return sorted(res, key=lambda x: x[1])


def annonces_du_compte(compte_id):
    return tout_lire("/items", {"account_id": compte_id, "status": "active"}, max_pages=30)


def demandes_actives(compte_id):
    return tout_lire("/jobs", {"account_id": compte_id, "scope": "active"}, max_pages=10)


def publier(annonce: dict, essai=False):
    corps = dict(annonce)
    if essai:
        corps["dry_run"] = True
    return appel("POST", "/items", corps)


def lire_demandes(ids):
    if not ids:
        return []
    return appel("GET", "/jobs", params={"ids": ",".join(str(i) for i in ids), "limit": 100}).get("data", [])


def annuler(job_id):
    return appel("POST", f"/jobs/{int(job_id)}/cancel")
