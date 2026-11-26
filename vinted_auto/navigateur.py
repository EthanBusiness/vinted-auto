"""Ouvre le site dans le bon profil Chrome (celui choisi dans Réglages), sinon dans le navigateur par défaut."""
import json
import os
import subprocess
import webbrowser
from pathlib import Path


def dossier_chrome() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "User Data"


def chrome_exe():
    if os.name != "nt":
        return None
    for base in (os.environ.get("PROGRAMFILES"), os.environ.get("PROGRAMFILES(X86)"), os.environ.get("LOCALAPPDATA")):
        if base:
            p = Path(base) / "Google" / "Chrome" / "Application" / "chrome.exe"
            if p.exists():
                return p
    return None


def profils(dossier: Path = None) -> list:
    """Profils Chrome du PC : [{dossier: 'Profile 1', nom: 'ethan', email: '...'}]."""
    f = (dossier or dossier_chrome()) / "Local State"
    try:
        cache = json.loads(f.read_text(encoding="utf-8")).get("profile", {}).get("info_cache", {})
    except (OSError, ValueError):
        return []
    res = []
    for d, info in cache.items():
        if isinstance(info, dict):
            res.append({"dossier": d, "nom": info.get("name") or info.get("gaia_name") or d,
                        "email": info.get("user_name") or ""})
    return sorted(res, key=lambda p: (p["dossier"] != "Default", p["nom"].lower()))


def profil_choisi() -> str:
    try:
        from . import db
        return db.reglage("chrome_profil") or ""
    except Exception:  # noqa : base pas encore prête
        return ""


def ouvrir(url: str, profil: str = None) -> bool:
    """True si ouvert dans le profil Chrome choisi ; sinon navigateur par défaut."""
    profil = profil_choisi() if profil is None else profil
    exe = chrome_exe()
    if profil and exe:
        try:
            subprocess.Popen([str(exe), f"--profile-directory={profil}", url])
            return True
        except OSError:
            pass
    webbrowser.open(url)
    return False
