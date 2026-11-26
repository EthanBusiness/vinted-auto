"""Petite base SQLite (un seul fichier dans VintedAuto-donnees)."""
import json
import sqlite3
import threading
import time

from .config import DONNEES

FICHIER = DONNEES / "base.sqlite"
_local = threading.local()
_verrou_ecriture = threading.RLock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS produits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lien TEXT NOT NULL,
    goods_id TEXT DEFAULT '',
    sku TEXT DEFAULT '',
    statut TEXT DEFAULT 'lecture',      -- lecture / lu / erreur
    erreur TEXT DEFAULT '',
    taille_demandee TEXT DEFAULT '',
    donnees TEXT DEFAULT '{}',          -- fiche Shein lue (JSON)
    analyse TEXT DEFAULT '{}',          -- résultat de l'IA (JSON)
    brouillon INTEGER DEFAULT 0,        -- 1 = envoyé par l'extension, comptes pas encore choisis
    cree REAL, maj REAL
);
CREATE TABLE IF NOT EXISTS annonces (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    produit_id INTEGER NOT NULL,
    compte_id TEXT NOT NULL,
    statut TEXT DEFAULT 'lecture',
    erreur TEXT DEFAULT '',
    titre TEXT DEFAULT '', description TEXT DEFAULT '',
    titre_base TEXT DEFAULT '', corps TEXT DEFAULT '',
    prix REAL DEFAULT 0,
    catalog_id INTEGER, catalogue TEXT DEFAULT '',
    taille TEXT DEFAULT '', size_id INTEGER,
    status_id INTEGER DEFAULT 2,
    color_ids TEXT DEFAULT '[]',
    material_ids TEXT DEFAULT '[]',
    package_size_id INTEGER DEFAULT 1,
    prompt_face TEXT DEFAULT '', prompt_dos TEXT DEFAULT '',
    photo_face TEXT DEFAULT '', photo_dos TEXT DEFAULT '',
    photos_en_ligne TEXT DEFAULT '[]',
    job_id INTEGER, job_statut TEXT DEFAULT '', job_info TEXT DEFAULT '',
    vinted_id TEXT DEFAULT '',
    essai TEXT DEFAULT '',
    cout REAL DEFAULT 0,
    cree REAL, maj REAL
);
CREATE TABLE IF NOT EXISTS comptes (
    id TEXT PRIMARY KEY,
    login TEXT, relie INTEGER DEFAULT 0, actif INTEGER DEFAULT 1,
    fond_fichier TEXT DEFAULT '', fond_description TEXT DEFAULT '',
    modele_fichier TEXT DEFAULT '', modele_description TEXT DEFAULT '',
    prompt_fond TEXT DEFAULT '', prompt_modele TEXT DEFAULT '',
    scene_fichier TEXT DEFAULT '', scene_description TEXT DEFAULT '', prompt_scene TEXT DEFAULT '',
    profil_fichier TEXT DEFAULT '',
    prochain_creneau REAL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS couts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    jour TEXT, usd REAL, quoi TEXT, quand REAL
);
CREATE TABLE IF NOT EXISTS cache (cle TEXT PRIMARY KEY, valeur TEXT, quand REAL);
CREATE TABLE IF NOT EXISTS reglages (cle TEXT PRIMARY KEY, valeur TEXT);
CREATE TABLE IF NOT EXISTS sessions (jeton TEXT PRIMARY KEY, role TEXT, quand REAL);
"""

REGLAGES_DEFAUT = {
    "prix_coef": "1.6",          # prix Vinted = prix Shein x coef + ajout
    "prix_ajout": "2",
    "prix_min": "6",
    "etat_id": "2",              # Très bon état
    "colis_id": "1",             # Petit
    "espacement_min": "20",
    "chrome_profil": "",         # dossier du profil Chrome où ouvrir le site (vide = navigateur par défaut)      # minutes entre 2 publications d'un même compte
    "publier_auto": "0",         # publier dès que les photos sont validées
    "eur_par_usd": "0.92",
}


def cx() -> sqlite3.Connection:
    c = getattr(_local, "c", None)
    if c is None:
        c = sqlite3.connect(FICHIER, timeout=30, check_same_thread=False)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA busy_timeout=30000")
        _local.c = c
    return c


# Colonnes ajoutées après la première version (les anciennes bases sont complétées au démarrage)
COLONNES_AJOUTEES = {
    "comptes": {"scene_fichier": "TEXT DEFAULT ''", "scene_description": "TEXT DEFAULT ''", "prompt_scene": "TEXT DEFAULT ''",
                "profil_fichier": "TEXT DEFAULT ''"},
    "annonces": {"attributs": "TEXT DEFAULT '{}'"},   # autres champs Vinted de la catégorie (ex : longueur de jupe)
}


def init():
    with _verrou_ecriture:
        cx().executescript(SCHEMA)
        for table, cols in COLONNES_AJOUTEES.items():
            existantes = {r[1] for r in cx().execute(f"PRAGMA table_info({table})")}
            for nom, typ in cols.items():
                if nom not in existantes:
                    cx().execute(f"ALTER TABLE {table} ADD COLUMN {nom} {typ}")
        for k, v in REGLAGES_DEFAUT.items():
            cx().execute("INSERT OR IGNORE INTO reglages(cle, valeur) VALUES (?, ?)", (k, v))
        cx().commit()


def q(sql, args=()):
    return [dict(r) for r in cx().execute(sql, args).fetchall()]


def q1(sql, args=()):
    r = cx().execute(sql, args).fetchone()
    return dict(r) if r else None


def ex(sql, args=()):
    with _verrou_ecriture:
        cur = cx().execute(sql, args)
        cx().commit()
        return cur.lastrowid


def maj(table, id_, **champs):
    if not champs:
        return
    champs["maj"] = time.time() if table in ("produits", "annonces") else None
    if champs["maj"] is None:
        champs.pop("maj")
    for k, v in list(champs.items()):
        if isinstance(v, (list, dict)):
            champs[k] = json.dumps(v, ensure_ascii=False)
    sets = ", ".join(f"{k} = ?" for k in champs)
    ex(f"UPDATE {table} SET {sets} WHERE id = ?", (*champs.values(), id_))


def reglage(cle) -> str:
    r = q1("SELECT valeur FROM reglages WHERE cle = ?", (cle,))
    return r["valeur"] if r else REGLAGES_DEFAUT.get(cle, "")


def reglages() -> dict:
    d = dict(REGLAGES_DEFAUT)
    d.update({r["cle"]: r["valeur"] for r in q("SELECT cle, valeur FROM reglages")})
    return d


def set_reglage(cle, valeur):
    ex("INSERT INTO reglages(cle, valeur) VALUES (?, ?) ON CONFLICT(cle) DO UPDATE SET valeur = excluded.valeur",
       (cle, str(valeur)))


def cache_get(cle, max_age):
    r = q1("SELECT valeur, quand FROM cache WHERE cle = ?", (cle,))
    if r and time.time() - r["quand"] < max_age:
        return json.loads(r["valeur"])
    return None


def cache_set(cle, valeur):
    ex("INSERT INTO cache(cle, valeur, quand) VALUES (?, ?, ?) ON CONFLICT(cle) DO UPDATE SET valeur = excluded.valeur, quand = excluded.quand",
       (cle, json.dumps(valeur, ensure_ascii=False), time.time()))


def ajouter_cout(usd, quoi):
    ex("INSERT INTO couts(jour, usd, quoi, quand) VALUES (date('now', 'localtime'), ?, ?, ?)", (usd, quoi, time.time()))


def cout_du_jour_usd():
    r = q1("SELECT COALESCE(SUM(usd), 0) AS s FROM couts WHERE jour = date('now', 'localtime')")
    return r["s"] if r else 0.0


def cout_du_mois_usd():
    r = q1("SELECT COALESCE(SUM(usd), 0) AS s FROM couts WHERE substr(jour, 1, 7) = strftime('%Y-%m', 'now', 'localtime')")
    return r["s"] if r else 0.0
