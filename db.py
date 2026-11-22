"""Petite base de données SQLite (un simple fichier : data/vinted.db)."""
import json
import os
import sqlite3
from datetime import datetime

DOSSIER_DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
CHEMIN_DB = os.path.join(DOSSIER_DATA, "vinted.db")

# Les étapes possibles d'un article (code -> texte affiché)
STATUTS = {
    "a_analyser": "En cours d'analyse",
    "lecture_echouee": "Lecture Shein impossible : coller la fiche",
    "erreur_ia": "Erreur de l'IA",
    "a_photographier": "À photographier",
}


def connexion():
    os.makedirs(DOSSIER_DATA, exist_ok=True)
    con = sqlite3.connect(CHEMIN_DB, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    return con


def initialiser():
    with connexion() as con:
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cree_le TEXT NOT NULL,
                lien TEXT,
                sku TEXT,
                comptes TEXT NOT NULL DEFAULT '[]',
                statut TEXT NOT NULL,
                html_source TEXT,
                texte_colle TEXT,
                images TEXT NOT NULL DEFAULT '[]',
                infos TEXT,
                prompt_gemini TEXT,
                erreur TEXT
            );
            CREATE TABLE IF NOT EXISTS couts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                article_id INTEGER,
                date TEXT NOT NULL,
                etape TEXT NOT NULL,
                modele TEXT,
                tokens_entree INTEGER,
                tokens_sortie INTEGER,
                cout_usd REAL NOT NULL
            );
            """
        )


def maintenant():
    return datetime.now().isoformat(timespec="seconds")


def ajouter_article(lien, comptes, texte_colle=None, html_source=None):
    with connexion() as con:
        cur = con.execute(
            "INSERT INTO articles (cree_le, lien, comptes, statut, texte_colle, html_source)"
            " VALUES (?, ?, ?, 'a_analyser', ?, ?)",
            (maintenant(), lien, json.dumps(comptes), texte_colle, html_source),
        )
        return cur.lastrowid


def maj_article(article_id, **champs):
    for cle in ("comptes", "images", "infos"):
        if cle in champs and not isinstance(champs[cle], str) and champs[cle] is not None:
            champs[cle] = json.dumps(champs[cle], ensure_ascii=False)
    cols = ", ".join(f"{k} = ?" for k in champs)
    with connexion() as con:
        con.execute(f"UPDATE articles SET {cols} WHERE id = ?", (*champs.values(), article_id))


def _decoder(ligne):
    if ligne is None:
        return None
    a = dict(ligne)
    a["comptes"] = json.loads(a["comptes"] or "[]")
    a["images"] = json.loads(a["images"] or "[]")
    a["infos"] = json.loads(a["infos"]) if a["infos"] else {}
    a["statut_texte"] = STATUTS.get(a["statut"], a["statut"])
    return a


def article(article_id):
    with connexion() as con:
        a = _decoder(con.execute("SELECT * FROM articles WHERE id = ?", (article_id,)).fetchone())
        if a:
            a["cout_usd"] = con.execute(
                "SELECT COALESCE(SUM(cout_usd), 0) FROM couts WHERE article_id = ?", (article_id,)
            ).fetchone()[0]
        return a


def liste_articles(statut=None, limite=200):
    sql = (
        "SELECT a.*, (SELECT COALESCE(SUM(cout_usd),0) FROM couts c WHERE c.article_id = a.id) AS cout_usd"
        " FROM articles a"
    )
    params = []
    if statut:
        sql += " WHERE a.statut = ?"
        params.append(statut)
    sql += " ORDER BY a.id DESC LIMIT ?"
    params.append(limite)
    with connexion() as con:
        lignes = con.execute(sql, params).fetchall()
    res = []
    for l in lignes:
        a = _decoder(l)
        a["cout_usd"] = l["cout_usd"]
        res.append(a)
    return res


def prochain_a_analyser():
    with connexion() as con:
        return _decoder(
            con.execute("SELECT * FROM articles WHERE statut = 'a_analyser' ORDER BY id LIMIT 1").fetchone()
        )


def sku_deja_present(sku, sauf_id):
    """Renvoie l'id d'un autre article avec le même SKU Shein, s'il existe."""
    if not sku:
        return None
    with connexion() as con:
        l = con.execute("SELECT id FROM articles WHERE sku = ? AND id != ? LIMIT 1", (sku, sauf_id)).fetchone()
        return l["id"] if l else None


def enregistrer_cout(article_id, etape, modele, tokens_entree, tokens_sortie, cout_usd):
    with connexion() as con:
        con.execute(
            "INSERT INTO couts (article_id, date, etape, modele, tokens_entree, tokens_sortie, cout_usd)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (article_id, maintenant(), etape, modele, tokens_entree, tokens_sortie, cout_usd),
        )


def cout_du_jour():
    jour = datetime.now().date().isoformat()
    with connexion() as con:
        l = con.execute(
            "SELECT COALESCE(SUM(cout_usd),0) AS total, COUNT(DISTINCT article_id) AS nb FROM couts WHERE date LIKE ?",
            (jour + "%",),
        ).fetchone()
        return l["total"], l["nb"]
