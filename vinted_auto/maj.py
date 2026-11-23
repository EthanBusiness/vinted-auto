"""Mise à jour en un clic depuis GitHub (le dépôt est public, aucune clé n'y est)."""
import io
import json
import os
import urllib.request
import zipfile

from .config import CODE, DEPOT_GITHUB, VERSION

BRANCHE = os.environ.get("VINTED_AUTO_BRANCHE", "main")
ZIP = f"https://codeload.github.com/{DEPOT_GITHUB}/zip/refs/heads/{BRANCHE}"
VERSION_DISTANTE = f"https://raw.githubusercontent.com/{DEPOT_GITHUB}/{BRANCHE}/vinted_auto/config.py"
A_GARDER = {".git", ".venv", "data", "__pycache__"}


def _get(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": "VintedAuto/" + VERSION})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def version_disponible():
    try:
        texte = _get(VERSION_DISTANTE, 15).decode("utf-8")
        for ligne in texte.splitlines():
            if ligne.startswith("VERSION"):
                return json.loads(ligne.split("=", 1)[1].strip().replace("'", '"'))
    except Exception:  # noqa
        return ""
    return ""


def installer():
    """Télécharge la dernière version et remplace le code (jamais les données)."""
    if (CODE / ".git").exists():
        raise RuntimeError("Ce dossier est une copie de développement (git) : mise à jour automatique désactivée.")
    contenu = _get(ZIP, 120)
    z = zipfile.ZipFile(io.BytesIO(contenu))
    racine = z.namelist()[0].split("/")[0] + "/"
    noms = set(z.namelist())
    if racine + "lancer.bat" not in noms or racine + "vinted_auto/serveur.py" not in noms:
        raise RuntimeError("Le fichier téléchargé ne ressemble pas à Vinted Auto.")
    for nom in z.namelist():
        rel = nom[len(racine):]
        if not rel or rel.split("/")[0] in A_GARDER:
            continue
        cible = CODE / rel
        if nom.endswith("/"):
            cible.mkdir(parents=True, exist_ok=True)
            continue
        cible.parent.mkdir(parents=True, exist_ok=True)
        neuf = z.read(nom)
        if cible.exists() and cible.read_bytes() == neuf:
            continue
        tmp = cible.with_name(cible.name + ".nouveau")
        tmp.write_bytes(neuf)
        tmp.replace(cible)
    return True
