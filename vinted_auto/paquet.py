"""Les images à joindre dans Gemini, numérotées dans l'ordre : 1 = scène du compte, 2… = photos de l'article."""
import hashlib
import io
import json
import os
import re
import urllib.request
import zipfile
from pathlib import Path

from . import db
from .atelier import images_article
from .config import IMAGES

CACHE = IMAGES / "shein"
# Pour les tests : remplace l'adresse des images Shein par un faux serveur
REMPLACE = os.environ.get("VINTED_AUTO_IMAGES_SHEIN", "")


def _image_shein(url: str) -> bytes:
    CACHE.mkdir(parents=True, exist_ok=True)
    fichier = CACHE / (hashlib.sha1(url.encode()).hexdigest()[:20] + ".jpg")
    if fichier.is_file() and fichier.stat().st_size > 500:
        return fichier.read_bytes()
    vraie = re.sub(r"^https://[^/]+", REMPLACE, url) if REMPLACE else url
    req = urllib.request.Request(vraie, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36",
        "Referer": "https://fr.shein.com/", "Accept": "image/avif,image/webp,image/*,*/*;q=0.8"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            contenu = r.read(15 * 1024 * 1024)
    except Exception as e:  # noqa
        raise RuntimeError(f"Impossible de télécharger une photo Shein ({e}). Ouvre l'article et enregistre les photos à la main.")
    if len(contenu) < 500:
        raise RuntimeError("Photo Shein vide : réessaie dans un instant.")
    fichier.write_bytes(contenu)
    return contenu


def _court(texte: str, n=40) -> str:
    t = re.sub(r"[^\w\s-]", "", texte or "", flags=re.UNICODE).strip()
    return re.sub(r"\s+", " ", t)[:n].strip() or "article"


def contenu(annonce_id: int, quoi: str = "tout"):
    """-> (nom du dossier, [(nom de fichier, octets)]) dans l'ordre attendu par le prompt."""
    a = db.q1("SELECT * FROM annonces WHERE id = ?", (annonce_id,))
    if not a:
        raise ValueError("Annonce introuvable.")
    p = db.q1("SELECT * FROM produits WHERE id = ?", (a["produit_id"],))
    c = db.q1("SELECT * FROM comptes WHERE id = ?", (a["compte_id"],)) or {}
    fiche = json.loads(p["donnees"] or "{}")
    fichiers = []
    n = 1
    if c.get("scene_fichier") and (IMAGES / c["scene_fichier"]).is_file():
        ext = c["scene_fichier"].rsplit(".", 1)[-1]
        fichiers.append((f"{n} - scene {_court(c.get('login') or c['id'], 25)}.{ext}", (IMAGES / c["scene_fichier"]).read_bytes()))
        n += 1
    else:
        for cle, nom in (("fond_fichier", "fond"), ("modele_fichier", "modele")):
            if c.get(cle) and (IMAGES / c[cle]).is_file():
                ext = c[cle].rsplit(".", 1)[-1]
                fichiers.append((f"{n} - {nom}.{ext}", (IMAGES / c[cle]).read_bytes()))
                n += 1
    if quoi != "scene":
        for url in images_article(fiche):
            fichiers.append((f"{n} - article.jpg", _image_shein(url)))
            n += 1
    if not fichiers:
        raise ValueError("Ce compte n'a pas encore de scène (fond + modèle) : ajoute-la dans la page Comptes.")
    dossier = f"{a['produit_id']} {_court(a['titre_base'] or fiche.get('titre', ''))} - {_court(c.get('login') or a['compte_id'], 25)}"
    if quoi == "scene":
        dossier += " (scene)"
    return dossier, fichiers


def zip_de(annonce_id: int, quoi: str = "tout"):
    dossier, fichiers = contenu(annonce_id, quoi)
    tampon = io.BytesIO()
    with zipfile.ZipFile(tampon, "w", zipfile.ZIP_STORED) as z:
        for nom, octets in fichiers:
            z.writestr(nom, octets)
    return dossier + ".zip", tampon.getvalue()


def dossier_telechargements() -> Path:
    base = Path.home() / "Downloads"
    if os.name == "nt":
        try:
            import winreg  # noqa
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders") as k:
                base = Path(winreg.QueryValueEx(k, "{374DE290-123F-4565-9164-39C4925E467B}")[0])
        except OSError:
            pass
    return base / "Vinted Auto"


def ecrire_dossier(annonce_id: int, quoi: str = "tout") -> Path:
    """Écrit les images dans Téléchargements\\Vinted Auto\\<article> et ouvre ce dossier (sur ce PC)."""
    nom, fichiers = contenu(annonce_id, quoi)
    cible = dossier_telechargements() / nom
    cible.mkdir(parents=True, exist_ok=True)
    for ancien in cible.iterdir():
        if ancien.is_file():
            ancien.unlink()
    for f, octets in fichiers:
        (cible / f).write_bytes(octets)
    if os.name == "nt":
        os.startfile(str(cible))  # noqa
    return cible
