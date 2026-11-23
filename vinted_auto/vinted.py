"""Listes Vinted et règles simples (couleurs, matières, tailles, prix)."""
import math
import re
import unicodedata

# Couleurs officielles de Vinted (nom -> color_id)
COULEURS = {
    "Noir": 1, "Marron": 2, "Gris": 3, "Beige": 4, "Rose": 5, "Violet": 6, "Rouge": 7,
    "Jaune": 8, "Bleu": 9, "Vert": 10, "Orange": 11, "Blanc": 12, "Argenté": 13, "Doré": 14,
    "Multicolore": 15, "Kaki": 16, "Turquoise": 17, "Crème": 20, "Abricot": 21, "Corail": 22,
    "Bordeaux": 23, "Lila": 25, "Bleu clair": 26, "Marine": 27, "Vert foncé": 28,
    "Moutarde": 29, "Menthe": 30,
}

# Matières les plus courantes (noms exacts de Vinted)
MATIERES = [
    "Coton", "Polyester", "Élasthanne", "Viscose", "Nylon", "Lin", "Laine", "Acrylique",
    "Soie", "Satin", "Denim", "Dentelle", "Velours", "Velours côtelé", "Mousseline", "Maille",
    "Cuir synthétique", "Cuir", "Daim", "Polaire", "Sequin", "Tulle", "Cachemire", "Fausse fourrure",
]

ETATS = {6: "Neuf avec étiquette", 1: "Neuf sans étiquette", 2: "Très bon état", 3: "Bon état", 4: "Satisfaisant"}
COLIS = {1: "Petit", 2: "Moyen", 3: "Grand"}

# Tailles « Curve » de Shein -> taille habituelle
CURVE = {"0XL": "XL", "1XL": "XXL", "2XL": "XXXL", "3XL": "4XL", "4XL": "5XL", "5XL": "6XL", "6XL": "7XL"}
UNIQUE = {"TAILLE UNIQUE", "ONE-SIZE", "ONE SIZE", "ONESIZE", "TU", "UNIQUE"}


def sans_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s or "") if unicodedata.category(c) != "Mn").lower().strip()


def taille_lettre(t: str) -> str:
    """'36 (S)' -> 'S' ; '0XL' -> 'XL' ; 'm' -> 'M'."""
    t = (t or "").strip()
    m = re.search(r"\(([^)]+)\)", t)
    if m:
        t = m.group(1)
    if t.upper() in UNIQUE:
        return "Taille unique"
    t = t.upper().replace(" ", "")
    return CURVE.get(t, t)


def choisir_taille(taille: str, details_catalogue: dict):
    """Trouve le size_id Vinted pour une taille Shein. Renvoie (size_id, libellé) ou (None, '')."""
    if not taille:
        return None, ""
    groupes = (details_catalogue or {}).get("size_groups") or []
    lettre = taille_lettre(taille)
    brut = taille.strip()
    # 1) groupe « S / 36 / 8 » (le plus courant chez Vinted)
    for g in groupes:
        for s in g.get("sizes", []):
            parts = [p.strip().upper() for p in s.get("title", "").split("/")]
            if len(parts) > 1 and parts[0] == lettre.upper():
                return s["id"], s["title"]
    # 2) titre identique dans n'importe quel groupe
    for cible in (lettre, brut):
        for g in groupes:
            for s in g.get("sizes", []):
                if sans_accents(s.get("title", "")) == sans_accents(cible):
                    return s["id"], s["title"]
    # 3) taille numérique : « FR 38 » / « EU 38 »
    num = re.sub(r"\D", "", brut.split("(")[0])
    if num:
        for prefixe in ("FR ", "EU "):
            for g in groupes:
                for s in g.get("sizes", []):
                    if s.get("title", "").upper() == prefixe + num:
                        return s["id"], s["title"]
    return None, ""


def couleurs_ids(noms) -> list:
    ids = []
    index = {sans_accents(k): v for k, v in COULEURS.items()}
    for n in noms or []:
        i = index.get(sans_accents(n))
        if i and i not in ids:
            ids.append(i)
    return ids[:2]


def matieres_ids(noms, details_catalogue: dict) -> list:
    options = []
    for a in (details_catalogue or {}).get("attributes") or []:
        if a.get("code") == "material":
            options = a.get("options") or []
    index = {sans_accents(o["title"]): o["id"] for o in options}
    ids = []
    for n in noms or []:
        i = index.get(sans_accents(n))
        if i and i not in ids:
            ids.append(i)
    return ids[:3]


def prix_vente(prix_shein: float, reglages: dict) -> float:
    try:
        coef = float(str(reglages.get("prix_coef", "1.6")).replace(",", "."))
        ajout = float(str(reglages.get("prix_ajout", "2")).replace(",", "."))
        mini = float(str(reglages.get("prix_min", "6")).replace(",", "."))
    except ValueError:
        coef, ajout, mini = 1.6, 2, 6
    if not prix_shein:
        return mini
    return float(max(mini, math.ceil(prix_shein * coef + ajout)))


def lire_prix(texte) -> float:
    """'10,05€' -> 10.05"""
    if isinstance(texte, (int, float)):
        return float(texte)
    m = re.search(r"(\d+(?:[.,]\d{1,2})?)", str(texte or "").replace(" ", "").replace(" ", ""))
    return float(m.group(1).replace(",", ".")) if m else 0.0
