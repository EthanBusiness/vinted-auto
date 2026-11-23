"""Hébergement des photos sur Supabase Storage (liens https publics pour Vinted)."""
import json
import secrets
import urllib.error
import urllib.request

from . import config

BUCKET = "vinted-photos"
TYPES = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}


class ErreurPhotos(Exception):
    pass


def _base():
    url = config.get("SUPABASE_URL").strip().rstrip("/")
    cle = config.get("SUPABASE_KEY").strip()
    if not url or not cle:
        raise ErreurPhotos("Supabase n'est pas encore réglé (page Réglages).")
    if not url.startswith("http"):
        url = "https://" + url
    return url, cle


def _req(methode, chemin, data=None, type_contenu="application/json", extra=None):
    url, cle = _base()
    h = {"apikey": cle, "Authorization": f"Bearer {cle}", "Content-Type": type_contenu}
    h.update(extra or {})
    req = urllib.request.Request(url + chemin, data=data, method=methode, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except (urllib.error.URLError, OSError) as e:
        raise ErreurPhotos(f"Impossible de joindre Supabase ({e}). Vérifie l'adresse Supabase.")


def preparer():
    """Crée le dossier public des photos s'il n'existe pas."""
    code, texte = _req("GET", f"/storage/v1/bucket/{BUCKET}")
    if code == 200:
        if '"public":false' in texte.replace(" ", ""):
            _req("PUT", f"/storage/v1/bucket/{BUCKET}", json.dumps({"id": BUCKET, "name": BUCKET, "public": True}).encode())
        return True
    if code in (401, 403):
        raise ErreurPhotos("Supabase refuse la clé : colle la clé « secret » (ou « service_role »), pas la clé « publishable/anon ».")
    code, texte = _req("POST", "/storage/v1/bucket", json.dumps({"id": BUCKET, "name": BUCKET, "public": True}).encode())
    if code in (200, 201) or "already exists" in texte.lower():
        return True
    raise ErreurPhotos(f"Supabase n'a pas pu créer le dossier photos ({code}) : {texte[:200]}")


def envoyer(contenu: bytes, extension: str, prefixe: str) -> str:
    ext = extension.lower().lstrip(".")
    if ext not in TYPES:
        ext = "jpg"
    nom = f"{prefixe}-{secrets.token_hex(6)}.{ext}"
    code, texte = _req("POST", f"/storage/v1/object/{BUCKET}/{nom}", contenu, TYPES[ext], {"x-upsert": "true"})
    if code == 404 or "bucket not found" in texte.lower():
        preparer()
        code, texte = _req("POST", f"/storage/v1/object/{BUCKET}/{nom}", contenu, TYPES[ext], {"x-upsert": "true"})
    if code not in (200, 201):
        raise ErreurPhotos(f"Envoi de la photo refusé par Supabase ({code}) : {texte[:200]}")
    url, _ = _base()
    return f"{url}/storage/v1/object/public/{BUCKET}/{nom}"
