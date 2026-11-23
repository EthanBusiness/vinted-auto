"""Le circuit complet : lien Shein -> fiche -> annonce + prompts -> photos -> publication Scalency."""
import json
import re
import threading
import time
import traceback

from . import db, ia, photos, scalency
from .config import IMAGES
from .vinted import (choisir_taille, couleurs_ids, lire_prix, matieres_ids, prix_vente, taille_lettre)

# Étapes d'une annonce (affichées dans le site)
ETAPES = {
    "lecture": "Lecture Shein…",
    "generation": "Rédaction…",
    "a_photographier": "À photographier",
    "prete": "Prête à publier",
    "envoi": "Envoi…",
    "en_file": "En file Scalency",
    "publiee": "Publiée",
    "echec": "Échec",
    "annulee": "Annulée",
}

_verrou_gen = threading.Semaphore(3)
_verrou_pub = threading.Lock()


def log_erreur(contexte, e):
    try:
        with open(IMAGES.parent / "erreurs.log", "a", encoding="utf-8") as f:
            f.write(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] {contexte}\n{traceback.format_exc()}\n")
    except OSError:
        pass


# ---------------------------------------------------------------- 1. Import des liens

RE_LIEN = re.compile(r"https?://[^\s<>\"']+", re.I)


def analyser_lignes(texte: str):
    """« lien [taille] » par ligne -> [(lien, taille)]."""
    res = []
    for ligne in (texte or "").splitlines():
        m = RE_LIEN.search(ligne)
        if not m:
            continue
        lien = m.group(0).rstrip(").,;")
        reste = (ligne[:m.start()] + " " + ligne[m.end():]).strip(" \t|;,-")
        res.append((lien, reste[:20]))
    return res


def goods_id_de(lien: str) -> str:
    m = re.search(r"-p-(\d{4,})", lien) or re.search(r"goods_id=(\d{4,})", lien)
    return m.group(1) if m else ""


def lien_propre(lien: str) -> str:
    return lien.split("#")[0].split("?")[0] if "shein." in lien else lien


def importer(texte: str, comptes: list):
    lignes = analyser_lignes(texte)
    if not lignes:
        raise ValueError("Aucun lien trouvé. Colle un lien Shein par ligne.")
    if not comptes:
        raise ValueError("Coche au moins un compte Vinted.")
    if not all("shein." in l for l, _ in lignes):
        raise ValueError("Seuls les liens Shein sont acceptés (un par ligne).")
    ids = []
    now = time.time()
    for lien, taille in lignes:
        pid = db.ex("INSERT INTO produits(lien, goods_id, taille_demandee, statut, cree, maj) VALUES (?, ?, ?, 'lecture', ?, ?)",
                    (lien_propre(lien), goods_id_de(lien), taille, now, now))
        for c in comptes:
            db.ex("INSERT INTO annonces(produit_id, compte_id, statut, cree, maj) VALUES (?, ?, 'lecture', ?, ?)",
                  (pid, c, now, now))
        ids.append({"id": pid, "lien": lien})
    return ids


def produits_a_lire():
    return db.q("SELECT id, lien FROM produits WHERE statut = 'lecture' ORDER BY id")


# ---------------------------------------------------------------- 2. Fiche reçue de l'extension

def nettoyer_fiche(d: dict) -> dict:
    if not isinstance(d, dict):
        raise ValueError("Fiche illisible.")
    s = lambda v, n=500: str(v or "")[:n]
    images = [s(u, 400) for u in (d.get("images") or []) if str(u).startswith("https://")][:12]
    tailles = []
    for t in (d.get("tailles") or [])[:30]:
        if isinstance(t, dict):
            tailles.append({"taille": s(t.get("taille"), 30),
                            "mesures": {s(k, 40): s(v, 40) for k, v in (t.get("mesures") or {}).items()}})
    fiche = {
        "lien": s(d.get("lien"), 600), "goods_id": s(d.get("goods_id"), 30), "sku": s(d.get("sku"), 60),
        "titre": s(d.get("titre"), 300), "couleur": s(d.get("couleur"), 80), "categorie": s(d.get("categorie"), 200),
        "prix": lire_prix(d.get("prix")), "prix_texte": s(d.get("prix"), 40),
        "images": images, "attributs": [s(a, 200) for a in (d.get("attributs") or [])][:60],
        "tailles": tailles, "taille_choisie": s(d.get("taille_choisie"), 30),
        "description": s(d.get("description"), 3000),
    }
    if not fiche["titre"] or not fiche["images"]:
        raise ValueError("La fiche Shein est incomplète (pas de nom ou pas de photo). Ouvre bien une page produit.")
    return fiche


def recevoir_fiche(produit_id: int, donnees: dict):
    p = db.q1("SELECT * FROM produits WHERE id = ?", (produit_id,))
    if not p:
        raise ValueError("Article introuvable.")
    if donnees.get("erreur"):
        db.maj("produits", produit_id, statut="erreur", erreur=str(donnees["erreur"])[:300])
        db.ex("UPDATE annonces SET statut = 'echec', erreur = ?, maj = ? WHERE produit_id = ? AND statut = 'lecture'",
              ("Lecture Shein : " + str(donnees["erreur"])[:250], time.time(), produit_id))
        return
    fiche = nettoyer_fiche(donnees)
    db.maj("produits", produit_id, statut="lu", erreur="", donnees=fiche,
           goods_id=fiche["goods_id"] or p["goods_id"], sku=fiche["sku"])
    db.ex("UPDATE annonces SET statut = 'generation', erreur = '', maj = ? WHERE produit_id = ? AND statut IN ('lecture', 'echec')",
          (time.time(), produit_id))
    lancer(generer, produit_id)


def creer_brouillon(donnees: dict) -> int:
    """Fiche envoyée par le bouton de l'extension : on choisira les comptes ensuite."""
    fiche = nettoyer_fiche(donnees)
    now = time.time()
    return db.ex("INSERT INTO produits(lien, goods_id, sku, statut, donnees, brouillon, taille_demandee, cree, maj) "
                 "VALUES (?, ?, ?, 'lu', ?, 1, ?, ?, ?)",
                 (fiche["lien"], fiche["goods_id"], fiche["sku"], json.dumps(fiche, ensure_ascii=False),
                  fiche.get("taille_choisie", ""), now, now))


def valider_brouillon(produit_id: int, comptes: list, taille: str = ""):
    if not comptes:
        raise ValueError("Coche au moins un compte Vinted.")
    now = time.time()
    db.maj("produits", produit_id, brouillon=0, taille_demandee=taille or "")
    for c in comptes:
        db.ex("INSERT INTO annonces(produit_id, compte_id, statut, cree, maj) VALUES (?, ?, 'generation', ?, ?)",
              (produit_id, c, now, now))
    lancer(generer, produit_id)


# ---------------------------------------------------------------- 3. Rédaction par Claude

def lancer(fn, *args):
    def run():
        try:
            fn(*args)
        except Exception as e:  # noqa
            log_erreur(f"{fn.__name__}{args}", e)
    threading.Thread(target=run, daemon=True).start()


def generer(produit_id: int, annonce_ids=None):
    with _verrou_gen:
        p = db.q1("SELECT * FROM produits WHERE id = ?", (produit_id,))
        fiche = json.loads(p["donnees"] or "{}")
        if annonce_ids:
            annonces = [db.q1("SELECT * FROM annonces WHERE id = ?", (i,)) for i in annonce_ids]
        else:
            annonces = db.q("SELECT * FROM annonces WHERE produit_id = ? AND statut = 'generation'", (produit_id,))
        annonces = [a for a in annonces if a]
        if not annonces:
            return
        try:
            try:
                cats = scalency.chemins_categories()
            except scalency.ErreurScalency:
                cats = []
            res, usd = ia.analyser(fiche, len(annonces), cats)
        except (ia.ErreurIA, Exception) as e:
            if not isinstance(e, ia.ErreurIA):
                log_erreur("analyse", e)
            for a in annonces:
                db.maj("annonces", a["id"], statut="echec", erreur=f"Rédaction : {e}")
            return
        analyse = {k: res.get(k) for k in ("description_visuelle", "type_article", "couleurs", "matieres", "categorie_id")}
        cat_ok = {i: c for i, c in cats}
        cat_id = res.get("categorie_id") if res.get("categorie_id") in cat_ok else None
        analyse["catalogue"] = cat_ok.get(cat_id, "")
        db.maj("produits", produit_id, analyse=analyse)
        details = {}
        if cat_id:
            try:
                details = scalency.categorie(cat_id)
            except scalency.ErreurScalency:
                details = {}
        regl = db.reglages()
        textes = res.get("annonces") or []
        taille = p["taille_demandee"] or fiche.get("taille_choisie") or ""
        if not taille and len(fiche.get("tailles", [])) == 1:
            taille = fiche["tailles"][0]["taille"]
        for n, a in enumerate(annonces):
            t = textes[n % len(textes)] if textes else {"titre": res.get("type_article", "Article"), "description": ""}
            champs = dict(
                titre_base=t["titre"].strip()[:90], corps=t["description"].strip(),
                prix=prix_vente(fiche.get("prix", 0), regl),
                catalog_id=cat_id, catalogue=analyse["catalogue"],
                color_ids=couleurs_ids(res.get("couleurs")),
                material_ids=matieres_ids(res.get("matieres"), details),
                status_id=int(regl.get("etat_id") or 2), package_size_id=int(regl.get("colis_id") or 1),
                cout=round(usd / len(annonces), 6), erreur="",
            )
            db.maj("annonces", a["id"], **champs)
            appliquer_taille(a["id"], taille, details)
            refaire_prompts(a["id"])
            statut = "prete" if (a.get("photo_face") and a.get("photo_dos")) else "a_photographier"
            db.maj("annonces", a["id"], statut=statut)


def mesures_texte(fiche: dict, taille: str) -> str:
    if not taille:
        return ""
    lettre = taille_lettre(taille)
    for t in fiche.get("tailles", []):
        if taille_lettre(t.get("taille", "")) == lettre and t.get("mesures"):
            parts = [f"{k.strip().lower()} {str(v).strip()}" for k, v in t["mesures"].items() if str(v).strip()]
            return ", ".join(parts[:7])
    return ""


def appliquer_taille(annonce_id: int, taille: str, details=None):
    """Met la taille dans le titre, la description et le size_id."""
    a = db.q1("SELECT * FROM annonces WHERE id = ?", (annonce_id,))
    p = db.q1("SELECT * FROM produits WHERE id = ?", (a["produit_id"],))
    fiche = json.loads(p["donnees"] or "{}")
    if details is None and a["catalog_id"]:
        try:
            details = scalency.categorie(a["catalog_id"])
        except scalency.ErreurScalency:
            details = {}
    size_id, libelle = choisir_taille(taille, details or {}) if taille else (None, "")
    lettre = taille_lettre(taille) if taille else ""
    titre = a["titre_base"]
    if lettre:
        titre = f"{titre} taille {lettre}" if lettre != "Taille unique" else f"{titre} taille unique"
    # Les hashtags restent tout à la fin, après la taille et les mesures
    texte, tags = [], []
    for ligne in (a["corps"] or "").splitlines():
        mots = ligne.split()
        if mots and all(m.startswith("#") for m in mots):
            tags.append(ligne.strip())
        else:
            texte.append(ligne)
    lignes = ["\n".join(texte).strip()]
    if lettre:
        info = f"Taille : {lettre}"
        m = mesures_texte(fiche, taille)
        if m:
            info += f"\nMesures ({lettre}) : {m}"
        lignes.append(info)
    if tags:
        lignes.append(" ".join(tags))
    corps = "\n\n".join(x for x in lignes if x)
    db.maj("annonces", annonce_id, taille=lettre, size_id=size_id, titre=titre[:100], description=corps[:2000])
    return size_id, libelle


def refaire_prompts(annonce_id: int):
    a = db.q1("SELECT * FROM annonces WHERE id = ?", (annonce_id,))
    p = db.q1("SELECT * FROM produits WHERE id = ?", (a["produit_id"],))
    c = db.q1("SELECT * FROM comptes WHERE id = ?", (a["compte_id"],)) or {}
    analyse = json.loads(p["analyse"] or "{}")
    fiche = json.loads(p["donnees"] or "{}")
    face, dos = construire_prompts(analyse, fiche, c)
    db.maj("annonces", annonce_id, prompt_face=face, prompt_dos=dos)


def construire_prompts(analyse: dict, fiche: dict, compte: dict):
    """Deux prompts Gemini (face / dos) qui reprennent le fond et le modèle du compte."""
    n = 1
    pieces, consignes = [], []
    if compte.get("fond_fichier"):
        pieces.append(f"Image {n} = le DÉCOR à utiliser")
        consignes.append(f"Utilise exactement le décor de l'image {n} : même pièce, mêmes meubles, même lumière, même angle.")
        n += 1
    else:
        decor = compte.get("fond_description") or "une chambre simple et lumineuse, murs blancs, parquet clair, une plante"
        consignes.append(f"Décor : {decor}.")
    if compte.get("modele_fichier"):
        pieces.append(f"Image {n} = la FEMME à utiliser")
        consignes.append(f"La femme est exactement celle de l'image {n} : même visage, même coiffure, même couleur de cheveux, même silhouette.")
        n += 1
    else:
        femme = compte.get("modele_description") or "une femme européenne d'une vingtaine d'années, naturelle, cheveux châtains"
        consignes.append(f"La femme : {femme}.")
    if compte.get("modele_description") and compte.get("modele_fichier"):
        consignes.append(f"Rappel du modèle : {compte['modele_description']}.")
    pieces.append(f"Image {n} et suivantes = l'ARTICLE à reproduire (photos produit)")
    article = analyse.get("description_visuelle") or fiche.get("titre", "")
    couleur = fiche.get("couleur")

    def prompt(vue):
        if vue == "face":
            pose = ("Elle est debout, vue de FACE, en pied (de la tête aux genoux au minimum), posture naturelle et détendue, "
                    "une main le long du corps, regard vers l'objectif ou légèrement de côté.")
        else:
            pose = ("Elle est debout, vue de DOS (elle tourne le dos à l'objectif, tête légèrement tournée), en pied, "
                    "pour montrer tout le dos de l'article. Utilise la photo de dos de l'article si elle est jointe.")
        return "\n".join([
            "Crée une photo réaliste d'une femme qui porte l'article, pour une annonce Vinted.",
            "Images jointes : " + " ; ".join(pieces) + ".",
            *consignes,
            pose,
            f"L'article : {article}" + (f" Couleur : {couleur}." if couleur else ""),
            "TRÈS IMPORTANT : reproduis l'article EXACTEMENT comme sur les photos produit : même couleur (même nuance), même coupe, "
            "même longueur, même motif, même matière, mêmes détails (boutons, coutures, volants, col, manches). N'ajoute et ne retire rien. "
            "L'article doit être entièrement visible, ni caché par les cheveux, ni par un sac ou une veste.",
            "Rendu : photo prise au smartphone par une amie, lumière naturelle douce, légère imperfection naturelle, pas de rendu studio "
            "ni retouché, format portrait 3:4, sans texte, sans logo, sans filigrane.",
        ])

    return prompt("face"), prompt("dos")


# ---------------------------------------------------------------- 4. Photos de l'employée

def enregistrer_photo(annonce_id: int, vue: str, contenu: bytes, ext: str):
    if vue not in ("face", "dos"):
        raise ValueError("Vue inconnue.")
    a = db.q1("SELECT * FROM annonces WHERE id = ?", (annonce_id,))
    if not a:
        raise ValueError("Annonce introuvable.")
    if a["statut"] in ("envoi", "en_file", "publiee"):
        raise ValueError("Cette annonce est déjà envoyée : impossible de changer ses photos.")
    nom = f"annonce{annonce_id}-{vue}-{int(time.time())}.{ext}"
    (IMAGES / nom).write_bytes(contenu)
    db.maj("annonces", annonce_id, **{f"photo_{vue}": nom, "photos_en_ligne": []})


def valider_photos(annonce_id: int):
    a = db.q1("SELECT * FROM annonces WHERE id = ?", (annonce_id,))
    if not (a["photo_face"] and a["photo_dos"]):
        raise ValueError("Il faut les 2 photos (face et dos).")
    if a["statut"] in ("a_photographier", "echec", "prete"):
        db.maj("annonces", annonce_id, statut="prete", erreur="")
    if db.reglage("publier_auto") == "1":
        lancer(publier_plusieurs, [annonce_id], False)


def refaire_photos(annonce_id: int):
    a = db.q1("SELECT * FROM annonces WHERE id = ?", (annonce_id,))
    if a["statut"] in ("envoi", "en_file", "publiee"):
        raise ValueError("Cette annonce est déjà envoyée.")
    db.maj("annonces", annonce_id, photo_face="", photo_dos="", photos_en_ligne=[], statut="a_photographier")


# ---------------------------------------------------------------- 5. Publication

def corps_scalency(a: dict, p: dict, urls: list) -> dict:
    fiche = json.loads(p["donnees"] or "{}")
    corps = {
        "account_id": a["compte_id"], "title": a["titre"], "description": a["description"],
        "price": a["prix"], "catalog_id": a["catalog_id"], "status_id": a["status_id"] or 2,
        "brand_id": 1, "package_size_id": a["package_size_id"] or 1, "photos": urls,
        "sku": sku_de(p), "supplier_link": (fiche.get("lien") or p["lien"])[:500],
    }
    if a["size_id"]:
        corps["size_id"] = a["size_id"]
    couleurs = json.loads(a["color_ids"] or "[]")
    if couleurs:
        corps["color_ids"] = couleurs
    mat = json.loads(a["material_ids"] or "[]")
    if mat:
        corps["item_attributes"] = [{"code": "material", "ids": mat}]
    return corps


def sku_de(p: dict) -> str:
    return "SHEIN-" + (p.get("sku") or p.get("goods_id") or f"P{p['id']}")


def verifier(a: dict) -> list:
    pb = []
    if not a["titre"] or len(a["titre"]) < 5:
        pb.append("titre manquant")
    if not a["description"] or len(a["description"]) < 5:
        pb.append("description manquante")
    if not a["catalog_id"]:
        pb.append("catégorie à choisir")
    if not a["size_id"]:
        pb.append("taille à choisir")
    if not a["prix"] or a["prix"] <= 0:
        pb.append("prix manquant")
    if not (a["photo_face"] and a["photo_dos"]):
        pb.append("photos manquantes")
    return pb


def doublon(a: dict, p: dict, cache: dict):
    """Vrai si cet article est déjà en ligne ou en file sur ce compte."""
    sku = sku_de(p)
    autres = db.q("SELECT a.id FROM annonces a JOIN produits p ON p.id = a.produit_id WHERE a.compte_id = ? AND a.id != ? "
                  "AND a.statut IN ('envoi', 'en_file', 'publiee') AND (p.sku = ? OR (p.goods_id != '' AND p.goods_id = ?))",
                  (a["compte_id"], a["id"], p["sku"] or "-", p["goods_id"] or "-"))
    if autres:
        return f"déjà envoyé sur ce compte (annonce n°{autres[0]['id']})"
    cle = a["compte_id"]
    if cle not in cache:
        skus = set()
        for it in scalency.annonces_du_compte(cle):
            if it.get("sku"):
                skus.add(it["sku"])
        for j in scalency.demandes_actives(cle):
            s = (j.get("refs") or {}).get("sku")
            if s:
                skus.add(s)
        cache[cle] = skus
    if sku in cache[cle]:
        return "déjà en ligne ou en file sur ce compte (vérifié dans Scalency)"
    return ""


def urls_photos(a: dict) -> list:
    deja = json.loads(a["photos_en_ligne"] or "[]")
    if len(deja) == 2:
        return deja
    urls = []
    for vue in ("face", "dos"):
        nom = a[f"photo_{vue}"]
        contenu = (IMAGES / nom).read_bytes()
        urls.append(photos.envoyer(contenu, nom.rsplit(".", 1)[-1], f"annonce{a['id']}-{vue}"))
    db.maj("annonces", a["id"], photos_en_ligne=urls)
    return urls


def essai(annonce_id: int) -> str:
    a = db.q1("SELECT * FROM annonces WHERE id = ?", (annonce_id,))
    p = db.q1("SELECT * FROM produits WHERE id = ?", (a["produit_id"],))
    pb = verifier(a)
    if pb:
        raise ValueError("À compléter : " + ", ".join(pb))
    urls = urls_photos(a)
    r = scalency.publier(corps_scalency(a, p, urls), essai=True)
    if r.get("would_queue") is False:
        msg = "Essai : Scalency ne la mettrait pas en file. " + (r.get("reason") or "")
    else:
        msg = "Essai réussi : Scalency accepte l'annonce. " + (r.get("reason") or "")
    db.maj("annonces", annonce_id, essai=msg.strip())
    return msg.strip()


def publier_plusieurs(ids: list, ignorer_doublon=False):
    """Publie une liste d'annonces, étalées dans le temps par compte."""
    with _verrou_pub:
        cache = {}
        regl = db.reglages()
        try:
            espace = max(0, float(regl.get("espacement_min") or 0))
        except ValueError:
            espace = 20
        bilan = {"ok": 0, "refus": 0}
        for i in ids:
            a = db.q1("SELECT * FROM annonces WHERE id = ?", (i,))
            if not a or a["statut"] not in ("prete", "echec", "a_photographier", "annulee"):
                continue
            p = db.q1("SELECT * FROM produits WHERE id = ?", (a["produit_id"],))
            pb = verifier(a)
            if pb:
                db.maj("annonces", i, statut="echec" if a["statut"] != "a_photographier" else a["statut"],
                       erreur="À compléter : " + ", ".join(pb))
                bilan["refus"] += 1
                continue
            db.maj("annonces", i, statut="envoi", erreur="")
            try:
                if not ignorer_doublon:
                    d = doublon(a, p, cache)
                    if d:
                        db.maj("annonces", i, statut="echec", erreur="Doublon bloqué : " + d)
                        bilan["refus"] += 1
                        continue
                urls = urls_photos(a)
                corps = corps_scalency(a, p, urls)
                compte = db.q1("SELECT * FROM comptes WHERE id = ?", (a["compte_id"],)) or {}
                now = time.time()
                depart = max(now, compte.get("prochain_creneau") or 0)
                delai = int(round((depart - now) / 60))
                if delai > 0:
                    corps["delay_minutes"] = delai
                r = scalency.publier(corps)
                job = r.get("job") or {}
                db.maj("annonces", i, statut="en_file", job_id=job.get("id"), job_statut=job.get("status", "queued"),
                       job_info=job.get("reason") or job.get("status_label") or "En file")
                if compte:
                    db.ex("UPDATE comptes SET prochain_creneau = ? WHERE id = ?", (depart + espace * 60, a["compte_id"]))
                cache.setdefault(a["compte_id"], set()).add(corps["sku"])
                bilan["ok"] += 1
            except (scalency.ErreurScalency, photos.ErreurPhotos) as e:
                db.maj("annonces", i, statut="echec", erreur=str(e))
                bilan["refus"] += 1
            except Exception as e:  # noqa
                log_erreur("publication", e)
                db.maj("annonces", i, statut="echec", erreur=f"Erreur inattendue : {e}")
                bilan["refus"] += 1
        return bilan


def annuler(annonce_id: int):
    a = db.q1("SELECT * FROM annonces WHERE id = ?", (annonce_id,))
    if a["job_id"] and a["statut"] == "en_file":
        scalency.annuler(a["job_id"])
    db.maj("annonces", annonce_id, statut="annulee", job_statut="cancelled", job_info="Annulée")


# ---------------------------------------------------------------- 6. Suivi des demandes Scalency

EN_COURS = {"queued", "waiting", "planned", "sent", "running", "retry", "maybe", "verify"}


def suivre_une_fois():
    en_file = db.q("SELECT id, job_id FROM annonces WHERE statut = 'en_file' AND job_id IS NOT NULL")
    if not en_file:
        return 0
    par_job = {a["job_id"]: a["id"] for a in en_file}
    ids = list(par_job)
    for k in range(0, len(ids), 100):
        for j in scalency.lire_demandes(ids[k:k + 100]):
            aid = par_job.get(j.get("id"))
            if not aid:
                continue
            st = j.get("status", "")
            info = j.get("reason") or j.get("status_label") or st
            if st == "done":
                db.maj("annonces", aid, statut="publiee", job_statut=st, job_info=j.get("status_label") or "Publiée",
                       vinted_id=str(j.get("new_item_id") or j.get("item_id") or ""))
            elif st == "failed":
                db.maj("annonces", aid, statut="echec", job_statut=st, job_info=info, erreur="Scalency : " + str(info))
            elif st in ("cancelled", "skipped", "draft_orphaned"):
                db.maj("annonces", aid, statut="annulee", job_statut=st, job_info=info)
            else:
                db.maj("annonces", aid, job_statut=st, job_info=info)
    return len(ids)


def boucle_suivi(stop: threading.Event, intervalle=90):
    while not stop.wait(intervalle):
        try:
            suivre_une_fois()
        except scalency.ErreurScalency:
            pass
        except Exception as e:  # noqa
            log_erreur("suivi", e)


def reprendre_au_demarrage():
    """Si le site a été fermé pendant une rédaction, on la relance."""
    for p in db.q("SELECT DISTINCT produit_id FROM annonces WHERE statut = 'generation'"):
        lancer(generer, p["produit_id"])
    db.ex("UPDATE annonces SET statut = 'echec', erreur = 'Envoi interrompu (site fermé) : relance la publication.' WHERE statut = 'envoi'")
