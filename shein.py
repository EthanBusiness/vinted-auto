"""Lecture d'une fiche produit Shein.

Shein bloque souvent les robots : si la lecture automatique échoue, le site
propose de coller le texte de la fiche ou d'importer la page enregistrée (.html).
"""
import json
import re

import requests
from bs4 import BeautifulSoup

ENTETES = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
}

MOTS_BLOCAGE = ("captcha", "access denied", "verify you are human", "robot", "challenge-platform")


class LectureImpossible(Exception):
    pass


def id_depuis_lien(lien):
    """Extrait l'identifiant produit Shein d'un lien (ex. ...-p-12345678.html)."""
    if not lien:
        return None
    m = re.search(r"-p-(\d{5,})", lien) or re.search(r"goods_id=(\d{5,})", lien)
    return m.group(1) if m else None


def telecharger(lien):
    try:
        r = requests.get(lien, headers=ENTETES, timeout=25, allow_redirects=True)
    except requests.RequestException as e:
        raise LectureImpossible(f"Connexion à Shein impossible ({e.__class__.__name__}).")
    if r.status_code != 200:
        raise LectureImpossible(f"Shein a répondu avec le code {r.status_code}.")
    return r.text


def _unique(liste):
    vus, res = set(), []
    for x in liste:
        if x and x not in vus:
            vus.add(x)
            res.append(x)
    return res


def _normaliser_image(url):
    url = url.replace("\\/", "/").replace("\\u002F", "/")
    if url.startswith("//"):
        url = "https:" + url
    # Les miniatures Shein ont "_thumbnail_XXXxYYY" : on prend l'image complète
    url = re.sub(r"_thumbnail_\d+x\d*", "", url)
    return url


def extraire(html, lien=None):
    """Transforme le HTML d'une fiche Shein en infos utiles pour l'IA.

    Renvoie un dict : sku, titre, images (liens), attributs, texte.
    Lève LectureImpossible si la page ne ressemble pas à une fiche produit.
    """
    soup = BeautifulSoup(html, "html.parser")

    titre = ""
    og = soup.find("meta", attrs={"property": "og:title"})
    if og and og.get("content"):
        titre = og["content"].strip()
    if not titre:
        h1 = soup.find("h1")
        titre = h1.get_text(" ", strip=True) if h1 else ""
    if not titre:
        m = re.search(r'"goods_name"\s*:\s*"([^"]+)"', html)
        titre = m.group(1) if m else ""

    sku = ""
    m = re.search(r'"goods_sn"\s*:\s*"([^"]+)"', html)
    if m:
        sku = m.group(1)
    goods_id = id_depuis_lien(lien)
    if not goods_id:
        m = re.search(r'"goods_id"\s*:\s*"?(\d{5,})', html)
        goods_id = m.group(1) if m else ""

    # Photos produit
    images = []
    og_img = soup.find("meta", attrs={"property": "og:image"})
    if og_img and og_img.get("content"):
        images.append(_normaliser_image(og_img["content"]))
    for m in re.finditer(r'"origin_image"\s*:\s*"([^"]+)"', html):
        images.append(_normaliser_image(m.group(1)))
    if len(images) < 2:
        for m in re.finditer(r'((?:https:)?//img\.ltwebstatic\.com/[^"\'\s>]+?\.(?:jpg|jpeg|webp|png))', html):
            images.append(_normaliser_image(m.group(1)))
    images = _unique(images)[:8]

    # Attributs (couleur, matière, coupe, longueur...)
    attributs = []
    for m in re.finditer(r'"attr_name"\s*:\s*"([^"]{1,60})"\s*,\s*"attr_value"\s*:\s*"([^"]{1,200})"', html):
        attributs.append(f"{m.group(1)} : {m.group(2)}")
    attributs = _unique(attributs)[:40]

    # Tailles disponibles
    tailles = []
    for m in re.finditer(r'"attr_value_name"\s*:\s*"([^"]{1,12})"', html):
        tailles.append(m.group(1))
    tailles = _unique(tailles)[:15]

    # Texte visible de la page (sans scripts ni styles)
    for balise in soup(["script", "style", "noscript", "svg"]):
        balise.decompose()
    texte = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))

    bas = (html[:5000] + texte[:2000]).lower()
    if not titre and not sku and not attributs:
        if any(mot in bas for mot in MOTS_BLOCAGE):
            raise LectureImpossible("Shein a bloqué la lecture automatique (page anti-robot).")
        raise LectureImpossible("La page ne ressemble pas à une fiche produit Shein.")

    return {
        # Identifiant unique du produit (sert à éviter les doublons) : basé sur le numéro du lien
        "sku": f"SHEIN-{goods_id}" if goods_id else sku,
        "ref_shein": sku,
        "goods_id": goods_id,
        "titre": titre,
        "images": images,
        "attributs": attributs,
        "tailles": tailles,
        # Le texte complet peut être énorme : on garde le début, qui contient la fiche.
        "texte": texte[:15000],
    }


def resume_pour_ia(infos):
    """Prépare un texte compact décrivant le produit pour Claude."""
    lignes = []
    if infos.get("titre"):
        lignes.append(f"Titre Shein : {infos['titre']}")
    if infos.get("sku"):
        lignes.append(f"SKU : {infos['sku']}")
    if infos.get("attributs"):
        lignes.append("Caractéristiques :\n- " + "\n- ".join(infos["attributs"]))
    if infos.get("tailles"):
        lignes.append("Tailles vues sur la page : " + ", ".join(infos["tailles"]))
    if infos.get("texte"):
        lignes.append("Texte de la page :\n" + infos["texte"])
    return "\n\n".join(lignes)


def dumps(o):
    return json.dumps(o, ensure_ascii=False)
