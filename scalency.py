"""Accès à l'API Scalency (pour l'instant : la liste des comptes Vinted)."""
import os
import time

import requests

BASE = "https://app.scalencyai.com/api/pub/public_api/v1"

_cache = {"quand": 0, "comptes": None}


class ErreurScalency(Exception):
    pass


def _entetes():
    cle = os.getenv("SCALENCY_API_KEY", "").strip()
    if not cle:
        raise ErreurScalency("Ajoute ta clé SCALENCY_API_KEY dans le fichier .env pour voir tes comptes.")
    return {"Authorization": f"Bearer {cle}", "Accept": "application/json"}


def get(chemin, params=None):
    for essai in range(3):
        try:
            r = requests.get(BASE + chemin, headers=_entetes(), params=params, timeout=20)
        except requests.RequestException as e:
            raise ErreurScalency(f"Connexion à Scalency impossible ({e.__class__.__name__}).")
        if r.status_code == 429:
            attente = min(int(r.headers.get("Retry-After", "5") or 5), 30)
            time.sleep(attente)
            continue
        if r.status_code == 401:
            raise ErreurScalency("Clé Scalency refusée : vérifie SCALENCY_API_KEY dans le fichier .env.")
        if r.status_code >= 400:
            raise ErreurScalency(f"Scalency a répondu avec le code {r.status_code}.")
        return r.json()
    raise ErreurScalency("Scalency limite les demandes en ce moment, réessaie dans une minute.")


def comptes(force=False):
    """Liste des comptes Vinted : [{id, login, actif}], comptes reliés à l'agent en premier.
    Gardée en mémoire 10 minutes."""
    if not force and _cache["comptes"] is not None and time.time() - _cache["quand"] < 600:
        return _cache["comptes"]
    res, curseur = [], None
    for _ in range(20):
        params = {"limit": 100}
        if curseur:
            params["cursor"] = curseur
        page = get("/accounts", params)
        for c in page.get("data", []):
            res.append({"id": c["id"], "login": c.get("login") or c["id"], "actif": bool(c.get("linked"))})
        if not page.get("has_more") or not page.get("next_cursor"):
            break
        curseur = page["next_cursor"]
    res.sort(key=lambda c: (not c["actif"], c["login"].lower()))
    _cache.update(quand=time.time(), comptes=res)
    return res
