"""Réglages du site : dossier de données et fichier .env.

Le code et les données sont séparés :
- le code est dans le dossier téléchargé (il peut être remplacé à chaque mise à jour) ;
- les données (clés, base, photos) sont dans « VintedAuto-donnees », dans ton dossier
  personnel. Elles ne sont jamais écrasées par une mise à jour et ne vont jamais sur GitHub.
"""
import os
import threading
from pathlib import Path

VERSION = "3.2.0"
DEPOT_GITHUB = "EthanBusiness/vinted-auto"

CODE = Path(__file__).resolve().parent.parent


def dossier_donnees() -> Path:
    perso = os.environ.get("VINTED_AUTO_DONNEES")
    d = Path(perso) if perso else Path.home() / "VintedAuto-donnees"
    d.mkdir(parents=True, exist_ok=True)
    (d / "images").mkdir(exist_ok=True)
    return d


DONNEES = dossier_donnees()
FICHIER_ENV = DONNEES / ".env"
IMAGES = DONNEES / "images"

# Clés modifiables depuis la page Réglages (stockées uniquement dans .env)
CLES = {
    "ANTHROPIC_API_KEY": "Clé Claude (Anthropic)",
    "SCALENCY_API_KEY": "Clé API Scalency",
    "SUPABASE_URL": "Adresse Supabase",
    "SUPABASE_KEY": "Clé secrète Supabase",
    "ADMIN_PASSWORD": "Ton mot de passe (accès à distance)",
    "EMPLOYEE_PASSWORD": "Mot de passe de ton employée",
}
SECRETES = {"ANTHROPIC_API_KEY", "SCALENCY_API_KEY", "SUPABASE_KEY", "ADMIN_PASSWORD", "EMPLOYEE_PASSWORD"}

_verrou = threading.Lock()


def lire_env() -> dict:
    valeurs = {}
    if FICHIER_ENV.exists():
        for ligne in FICHIER_ENV.read_text(encoding="utf-8-sig").splitlines():
            ligne = ligne.strip()
            if not ligne or ligne.startswith("#") or "=" not in ligne:
                continue
            k, v = ligne.split("=", 1)
            v = v.strip()
            if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
                v = v[1:-1]
            valeurs[k.strip()] = v
    return valeurs


def get(cle: str, defaut: str = "") -> str:
    # Les variables d'environnement passent en premier (pratique pour les tests)
    return os.environ.get(cle) or lire_env().get(cle) or defaut


def enregistrer_env(modifs: dict) -> None:
    with _verrou:
        valeurs = lire_env()
        for k, v in modifs.items():
            v = (v or "").strip().replace("\n", "").replace("\r", "")
            if v:
                valeurs[k] = v
            else:
                valeurs.pop(k, None)
        lignes = [
            "# Réglages secrets de Vinted Auto. Ne partage jamais ce fichier.",
            "# Tu peux les changer depuis la page Réglages du site.",
        ]
        lignes += [f"{k}={v}" for k, v in sorted(valeurs.items())]
        tmp = FICHIER_ENV.with_suffix(".tmp")
        tmp.write_text("\n".join(lignes) + "\n", encoding="utf-8")
        os.replace(tmp, FICHIER_ENV)


def masquer(v: str) -> str:
    if not v:
        return ""
    if len(v) <= 8:
        return "••••"
    return v[:4] + "••••" + v[-4:]
