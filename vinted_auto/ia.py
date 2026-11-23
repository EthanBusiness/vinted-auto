"""Appels à Claude Haiku 5.5 (le modèle le moins cher) pour les textes."""
import json

from . import config, db
from .vinted import COULEURS, MATIERES

MODELE = "claude-haiku-5-5"
# Prix en dollars par million de jetons (Claude Haiku 5.5, prompts < 100k jetons)
PRIX_ENTREE, PRIX_SORTIE = 0.10, 0.50
PRIX_CACHE_LU, PRIX_CACHE_ECRIT = 0.01, 0.125


class ErreurIA(Exception):
    pass


def _client():
    import anthropic  # installé automatiquement par lancer.bat
    cle = config.get("ANTHROPIC_API_KEY")
    if not cle:
        raise ErreurIA("La clé Claude (Anthropic) n'est pas encore remplie (page Réglages).")
    return anthropic.Anthropic(api_key=cle, max_retries=3, timeout=120)


def _cout(usage) -> float:
    g = lambda n: getattr(usage, n, 0) or 0
    return (g("input_tokens") * PRIX_ENTREE + g("output_tokens") * PRIX_SORTIE
            + g("cache_read_input_tokens") * PRIX_CACHE_LU + g("cache_creation_input_tokens") * PRIX_CACHE_ECRIT) / 1e6


def _appel(quoi, **params):
    import anthropic
    client = _client()
    try:
        r = client.messages.create(model=MODELE, **params)
    except anthropic.AuthenticationError:
        raise ErreurIA("Claude refuse la clé Anthropic : vérifie-la dans Réglages.")
    except anthropic.PermissionDeniedError:
        raise ErreurIA("Ta clé Anthropic n'a pas accès à ce modèle (vérifie ton compte Anthropic).")
    except anthropic.RateLimitError:
        raise ErreurIA("Trop de demandes à Claude en même temps : réessaie dans une minute.")
    except anthropic.BadRequestError as e:
        msg = str(getattr(e, "message", e))
        if "credit" in msg.lower() or "balance" in msg.lower():
            raise ErreurIA("Ton compte Anthropic n'a plus de crédit : ajoute du crédit sur console.anthropic.com (Billing).")
        raise ErreurIA(f"Claude a refusé la demande : {msg[:300]}")
    except anthropic.APIStatusError as e:
        raise ErreurIA(f"Claude est indisponible pour le moment ({e.status_code}). Réessaie plus tard.")
    except anthropic.APIConnectionError:
        raise ErreurIA("Impossible de joindre Claude : vérifie ta connexion internet.")
    usd = _cout(r.usage)
    db.ajouter_cout(usd, quoi)
    if r.stop_reason == "refusal":
        raise ErreurIA("Claude a refusé de traiter cet article.")
    if r.stop_reason == "max_tokens":
        raise ErreurIA("La réponse de Claude a été coupée (trop longue). Réessaie.")
    texte = "".join(b.text for b in r.content if b.type == "text")
    return texte, usd


SYSTEME_ANALYSE = """Tu aides une revendeuse Vinted (France). Elle achète des vêtements femme sur Shein et les revend sur Vinted.
On te donne la fiche Shein d'un article. Tu réponds en JSON, en français.

1. description_visuelle : 2 à 4 phrases qui décrivent l'article VISUELLEMENT, avec une précision maximale, pour qu'une IA d'image le reproduise à l'identique : type d'article, couleur exacte (nuance), longueur, coupe, col/encolure, manches, motif (taille, couleurs, disposition), matière et texture apparentes, fermetures, boutons, ceinture, détails (froncés, volants, fentes, dentelle, transparence…). Ne parle ni de la marque ni du prix.
2. type_article : 2 à 4 mots (ex : « Robe midi », « Pull court »).
3. couleurs : 1 ou 2 couleurs, prises uniquement dans la liste des couleurs Vinted.
4. matieres : 0 à 3 matières tirées de la composition, prises uniquement dans la liste des matières.
5. categorie_id : le numéro de la catégorie Vinted la plus précise, pris uniquement dans la liste des catégories.
6. annonces : exactement le nombre d'annonces demandé. Chaque annonce est rédigée DIFFÉREMMENT des autres (autres mots, autre ordre), car elles vont sur des comptes différents :
   - titre : 40 à 70 caractères, style « Robe midi noire à manches bouffantes » : type + couleur + 1 ou 2 détails clés. SANS la taille (elle est ajoutée automatiquement), sans marque, sans « Shein », sans emoji, sans majuscules partout.
   - description : 3 à 5 phrases courtes et naturelles, comme une vraie particulière : ce que c'est, la coupe, la matière/le toucher, avec quoi le porter, l'état « très bon état ». Termine par une ligne de 4 à 6 hashtags (#robe #mode …). N'écris PAS la taille ni les mesures (ajoutées automatiquement). Jamais « Shein », jamais de prix.

Liste des couleurs Vinted : {couleurs}

Liste des matières : {matieres}

Liste des catégories Vinted (numéro : chemin) :
{categories}
"""


def _schema_analyse():
    return {
        "type": "object",
        "properties": {
            "description_visuelle": {"type": "string"},
            "type_article": {"type": "string"},
            "couleurs": {"type": "array", "items": {"type": "string", "enum": list(COULEURS)}},
            "matieres": {"type": "array", "items": {"type": "string", "enum": MATIERES}},
            "categorie_id": {"type": "integer"},
            "annonces": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"titre": {"type": "string"}, "description": {"type": "string"}},
                    "required": ["titre", "description"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["description_visuelle", "type_article", "couleurs", "matieres", "categorie_id", "annonces"],
        "additionalProperties": False,
    }


def resume_fiche(d: dict) -> dict:
    """Ne garde que ce qui sert à l'IA (moins de jetons = moins cher)."""
    return {
        "nom": d.get("titre"),
        "couleur_shein": d.get("couleur"),
        "categorie_shein": d.get("categorie"),
        "caracteristiques": d.get("attributs", [])[:40],
        "description_shein": (d.get("description") or "")[:1500],
        "tailles": [t.get("taille") for t in d.get("tailles", [])][:20],
    }


def analyser(fiche: dict, nb_annonces: int, categories: list):
    systeme = SYSTEME_ANALYSE.format(
        couleurs=", ".join(COULEURS),
        matieres=", ".join(MATIERES),
        categories="\n".join(f"{i} : {c}" for i, c in categories) or "(liste indisponible : mets 0)",
    )
    texte, usd = _appel(
        "analyse d'un article",
        max_tokens=6000,
        system=[{"type": "text", "text": systeme, "cache_control": {"type": "ephemeral"}}],
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": _schema_analyse()}},
        messages=[{"role": "user", "content":
                   f"Nombre d'annonces à rédiger : {nb_annonces}\n\nFiche Shein :\n"
                   + json.dumps(resume_fiche(fiche), ensure_ascii=False, indent=1)}],
    )
    try:
        res = json.loads(texte)
    except ValueError:
        raise ErreurIA("Réponse illisible de Claude, réessaie.")
    return res, usd


SYSTEME_PROMPTS = """Tu écris des prompts pour l'application Gemini (génération d'images), en français.
Le prompt doit produire UNE photo très réaliste, comme prise au smartphone (iPhone), lumière naturelle, rendu « vraie annonce Vinted », format portrait 3:4, sans texte, sans logo, sans filigrane.
Réponds uniquement avec le prompt, sans titre ni explication, en 6 à 10 lignes."""


def prompt_fond(idee: str):
    demande = ("Écris un prompt pour générer un DÉCOR VIDE (aucune personne) qui servira de fond unique pour toutes les photos "
               "d'un compte Vinted : un intérieur simple et lumineux, réaliste, avec assez de place debout au centre pour "
               "photographier une femme en pied plus tard. Cadrage vertical, à hauteur de poitrine, mise au point nette. "
               f"Idée de la vendeuse : {idee or 'chambre claire et cosy, murs blancs, parquet clair, une plante, un miroir'}")
    return _appel("prompt de fond", max_tokens=1500, system=SYSTEME_PROMPTS,
                  output_config={"effort": "low"}, messages=[{"role": "user", "content": demande}])


def prompt_modele(idee: str):
    demande = ("Écris un prompt pour générer la photo de référence d'UN mannequin féminin unique, qui portera ensuite tous les "
               "vêtements d'un compte Vinted : femme européenne d'une vingtaine d'années, naturelle (pas de pose de mannequin "
               "professionnel), debout de face, en pied, tenue simple et neutre (débardeur blanc et legging noir), fond uni "
               "clair, visage bien visible et net, sans lunettes ni accessoire. Décris précisément visage, coiffure, couleur "
               f"de cheveux, silhouette et taille pour qu'on la reconnaisse d'une photo à l'autre. Idée de la vendeuse : {idee or 'cheveux châtains mi-longs, silhouette fine'}")
    return _appel("prompt de modèle", max_tokens=1500, system=SYSTEME_PROMPTS,
                  output_config={"effort": "low"}, messages=[{"role": "user", "content": demande}])


def tester():
    texte, usd = _appel("test de la clé", max_tokens=1000, output_config={"effort": "low"},
                        messages=[{"role": "user", "content": "Réponds juste : OK"}])
    return texte.strip()
