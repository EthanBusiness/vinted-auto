"""Site d'automatisation Vinted : point d'entrée.

Lancement : double-clic sur lancer.bat (Windows). Le site s'ouvre sur http://localhost:8000
"""
import os
import secrets
import threading
import time
import traceback
from functools import wraps

from dotenv import load_dotenv
from flask import Flask, abort, flash, redirect, render_template, request, session, url_for

import db
import ia
import scalency
import shein

DOSSIER = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(DOSSIER, ".env"))


def _cle_secrete():
    """Clé qui protège les sessions de connexion, créée une fois et gardée dans data/."""
    os.makedirs(db.DOSSIER_DATA, exist_ok=True)
    chemin = os.path.join(db.DOSSIER_DATA, "cle_session.txt")
    if not os.path.exists(chemin):
        with open(chemin, "w") as f:
            f.write(secrets.token_hex(32))
    with open(chemin) as f:
        return f.read().strip()


app = Flask(__name__)
app.secret_key = _cle_secrete()
app.config["MAX_CONTENT_LENGTH"] = 30 * 1024 * 1024  # pages HTML enregistrées jusqu'à 30 Mo


def eur(usd):
    return usd * float(os.getenv("EUR_PAR_USD", "0.92") or 0.92)


@app.template_filter("euros")
def filtre_euros(usd):
    v = eur(usd or 0)
    if v < 0.01:
        return f"{v:.4f} €".replace(".", ",")
    return f"{v:.2f} €".replace(".", ",")


# ---------------------------------------------------------------- connexion

def connecte(role=None):
    def deco(f):
        @wraps(f)
        def inner(*a, **kw):
            if "role" not in session:
                return redirect(url_for("connexion", suite=request.path))
            if role and session["role"] != role:
                abort(403)
            return f(*a, **kw)

        return inner

    return deco


@app.route("/connexion", methods=["GET", "POST"])
def connexion():
    if request.method == "POST":
        u = request.form.get("utilisateur", "").strip()
        p = request.form.get("mot_de_passe", "")
        comptes = {
            os.getenv("ADMIN_USER", "ethan"): (os.getenv("ADMIN_PASSWORD", ""), "admin"),
            os.getenv("EMPLOYEE_USER", "photos"): (os.getenv("EMPLOYEE_PASSWORD", ""), "photos"),
        }
        if u in comptes and comptes[u][0] and secrets.compare_digest(p, comptes[u][0]):
            session.clear()
            session["role"] = comptes[u][1]
            session["nom"] = u
            suite = request.args.get("suite") or "/"
            return redirect(suite if suite.startswith("/") else "/")
        flash("Identifiant ou mot de passe incorrect.", "erreur")
    return render_template("connexion.html")


@app.route("/deconnexion")
def deconnexion():
    session.clear()
    return redirect(url_for("connexion"))


@app.route("/")
@connecte()
def accueil():
    if session["role"] == "photos":
        return redirect(url_for("file_photos"))
    return redirect(url_for("articles"))


# ---------------------------------------------------------------- admin

@app.route("/ajouter", methods=["GET", "POST"])
@connecte("admin")
def ajouter():
    erreur_comptes, comptes = None, []
    try:
        comptes = scalency.comptes()
    except scalency.ErreurScalency as e:
        erreur_comptes = str(e)

    if request.method == "POST":
        choisis = request.form.getlist("comptes")
        liens = [l.strip() for l in request.form.get("liens", "").splitlines() if l.strip()]
        liens = [l for l in liens if l.lower().startswith("http")]
        if not liens:
            flash("Colle au moins un lien Shein (un par ligne).", "erreur")
            return render_template("ajouter.html", comptes=comptes, erreur_comptes=erreur_comptes)
        for lien in liens:
            db.ajouter_article(lien, choisis)
        flash(f"{len(liens)} article(s) ajouté(s). L'analyse démarre, la page se met à jour toute seule.", "ok")
        return redirect(url_for("articles"))
    return render_template("ajouter.html", comptes=comptes, erreur_comptes=erreur_comptes)


@app.route("/articles")
@connecte("admin")
def articles():
    statut = request.args.get("statut") or None
    liste = db.liste_articles(statut)
    total_jour, nb_jour = db.cout_du_jour()
    en_cours = any(a["statut"] == "a_analyser" for a in liste)
    return render_template(
        "articles.html", articles=liste, statuts=db.STATUTS, statut=statut,
        total_jour=total_jour, nb_jour=nb_jour, en_cours=en_cours,
    )


@app.route("/article/<int:article_id>")
@connecte()
def fiche_article(article_id):
    a = db.article(article_id)
    if not a:
        abort(404)
    doublon = db.sku_deja_present(a["sku"], a["id"])
    return render_template("article.html", a=a, doublon=doublon)


@app.route("/article/<int:article_id>/plan-b", methods=["POST"])
@connecte("admin")
def plan_b(article_id):
    a = db.article(article_id)
    if not a:
        abort(404)
    texte = request.form.get("texte", "").strip()
    fichier = request.files.get("fichier_html")
    html = None
    if fichier and fichier.filename:
        html = fichier.read().decode("utf-8", errors="ignore")
    if not texte and not html:
        flash("Colle le texte de la fiche OU choisis le fichier .html enregistré.", "erreur")
        return redirect(url_for("fiche_article", article_id=article_id))
    db.maj_article(article_id, texte_colle=texte or None, html_source=html, statut="a_analyser", erreur=None)
    flash("C'est reparti : l'analyse recommence.", "ok")
    return redirect(url_for("fiche_article", article_id=article_id))


@app.route("/article/<int:article_id>/relancer", methods=["POST"])
@connecte("admin")
def relancer(article_id):
    db.maj_article(article_id, statut="a_analyser", erreur=None)
    flash("Analyse relancée.", "ok")
    return redirect(url_for("fiche_article", article_id=article_id))


# ---------------------------------------------------------------- employée (étape 3)

@app.route("/photos")
@connecte()
def file_photos():
    liste = db.liste_articles("a_photographier")
    return render_template("photos.html", articles=liste)


# ---------------------------------------------------------------- analyse en arrière-plan

def analyser(a):
    """Lit la fiche Shein puis demande à Claude le prompt Gemini."""
    infos_page = None
    if a["texte_colle"]:
        infos_page = {
            "sku": a["sku"] or (f"SHEIN-{shein.id_depuis_lien(a['lien'])}" if shein.id_depuis_lien(a["lien"]) else ""),
            "titre": "", "images": a["images"], "attributs": [], "tailles": [],
            "texte": a["texte_colle"][:15000],
        }
    else:
        try:
            html = a["html_source"] or shein.telecharger(a["lien"])
            infos_page = shein.extraire(html, a["lien"])
        except shein.LectureImpossible as e:
            db.maj_article(a["id"], statut="lecture_echouee", erreur=str(e))
            return

    db.maj_article(a["id"], sku=infos_page["sku"] or None, images=infos_page["images"])

    try:
        fiche, usage = ia.analyser_fiche(shein.resume_pour_ia(infos_page), infos_page["images"])
    except ia.ErreurIA as e:
        db.maj_article(a["id"], statut="erreur_ia", erreur=str(e))
        return

    db.enregistrer_cout(a["id"], "fiche + prompt Gemini", ia.MODELE, usage.input_tokens, usage.output_tokens, ia.cout_usd(usage))
    db.maj_article(
        a["id"],
        infos=fiche.model_dump(),
        prompt_gemini=ia.construire_prompt_gemini(fiche),
        statut="a_photographier",
        erreur=None,
    )


def boucle_analyse():
    while True:
        a = None
        try:
            a = db.prochain_a_analyser()
            if a:
                analyser(a)
                continue
        except Exception:
            traceback.print_exc()
            try:
                if a:
                    db.maj_article(a["id"], statut="erreur_ia", erreur="Erreur inattendue (voir la fenêtre noire du site).")
            except Exception:
                pass
        time.sleep(2)


def demarrer():
    db.initialiser()
    threading.Thread(target=boucle_analyse, daemon=True).start()


if __name__ == "__main__":
    demarrer()
    from waitress import serve

    port = int(os.getenv("PORT", "8000") or 8000)
    print(f"\n  Site lancé : ouvre http://localhost:{port} dans ton navigateur.")
    print("  Pour l'arrêter : ferme cette fenêtre.\n")
    serve(app, host="127.0.0.1", port=port, threads=8)
