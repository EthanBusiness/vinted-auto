"""Appels à Claude (modèle Claude Haiku 5.5, le moins cher)."""
import os

import anthropic
from pydantic import BaseModel, Field

MODELE = "claude-haiku-5-5"
# Prix Claude Haiku 5.5, en dollars par million de tokens (requêtes de moins de 100 000 tokens)
PRIX_ENTREE_USD = 0.10
PRIX_SORTIE_USD = 0.50


class ErreurIA(Exception):
    pass


class FicheProduit(BaseModel):
    nom: str = Field(description="Nom court du vêtement en français, ex. 'Robe midi à manches bouffantes'")
    categorie: str = Field(description="Type de vêtement en français : robe, top, jean, pull, jupe, ensemble...")
    couleur: str = Field(description="Couleur(s) exacte(s) en français")
    matiere: str = Field(description="Matière/composition si connue, sinon chaîne vide")
    coupe: str = Field(description="Coupe, longueur, col, manches, en français")
    motif: str = Field(description="Motif/imprimé (uni, fleuri, rayé...) en français")
    details: str = Field(description="Détails visibles : boutons, nœuds, fentes, volants, poches... en français")
    tailles_disponibles: list[str] = Field(description="Tailles proposées (ex. XS, S, M)")
    mesures: str = Field(description="Mesures du tableau des tailles si présentes (longueur, poitrine, taille...), sinon chaîne vide")
    description_visuelle_en: str = Field(
        description=(
            "Very precise visual description of the garment in English, for an image generator: "
            "garment type, exact colour shade, fabric look and texture, cut and fit, length, neckline, "
            "sleeves, pattern and where it sits, every visible detail (buttons, ties, ruffles, slits, "
            "seams, pockets, lining), front AND back details. 4 to 8 sentences. No brand names."
        )
    )


CONSIGNES = """Tu aides un revendeur Vinted. On te donne une fiche produit Shein (texte, et parfois les photos du produit).
Extrais les informations du vêtement, fidèlement, sans rien inventer : si une info est absente, laisse le champ vide.
Si les photos et le texte se contredisent sur la couleur ou un détail, fais confiance aux photos.
Les champs en français sont courts et naturels. La description visuelle en anglais doit permettre de reproduire
le vêtement à l'identique (couleur, coupe, motif, détails)."""


def _client():
    cle = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not cle:
        raise ErreurIA("La clé ANTHROPIC_API_KEY est vide dans le fichier .env.")
    return anthropic.Anthropic(api_key=cle, max_retries=3)


def cout_usd(usage):
    entree = (usage.input_tokens or 0) + (getattr(usage, "cache_creation_input_tokens", 0) or 0) + (
        getattr(usage, "cache_read_input_tokens", 0) or 0
    )
    return entree * PRIX_ENTREE_USD / 1_000_000 + (usage.output_tokens or 0) * PRIX_SORTIE_USD / 1_000_000


def analyser_fiche(texte_fiche, images):
    """Renvoie (FicheProduit, usage). Envoie jusqu'à 3 photos produit à Claude."""
    client = _client()

    def appel(avec_images):
        contenu = []
        if avec_images:
            for url in images[:3]:
                contenu.append({"type": "image", "source": {"type": "url", "url": url}})
        contenu.append({"type": "text", "text": "Fiche produit Shein :\n\n" + texte_fiche})
        return client.messages.parse(
            model=MODELE,
            max_tokens=4000,
            system=CONSIGNES,
            messages=[{"role": "user", "content": contenu}],
            output_format=FicheProduit,
            output_config={"effort": "low"},
        )

    try:
        try:
            rep = appel(avec_images=bool(images))
        except anthropic.BadRequestError:
            if not images:
                raise
            # Une photo Shein n'a pas pu être lue par Claude : on réessaie avec le texte seul.
            rep = appel(avec_images=False)
    except anthropic.AuthenticationError:
        raise ErreurIA("Clé Anthropic refusée : vérifie ANTHROPIC_API_KEY dans le fichier .env.")
    except anthropic.RateLimitError:
        raise ErreurIA("Trop de demandes à Claude pour le moment. Réessaie dans une minute.")
    except anthropic.APIStatusError as e:
        raise ErreurIA(f"Erreur de l'API Claude ({e.status_code}) : {e.message}")
    except anthropic.APIConnectionError:
        raise ErreurIA("Impossible de joindre l'API Claude (connexion internet ?).")

    if rep.stop_reason == "refusal" or rep.parsed_output is None:
        raise ErreurIA("Claude n'a pas pu analyser cette fiche.")
    return rep.parsed_output, rep.usage


def construire_prompt_gemini(fiche: FicheProduit):
    """Prompt prêt à coller dans l'app Gemini (à envoyer AVEC la photo produit Shein en pièce jointe)."""
    taille = "S"
    if fiche.tailles_disponibles:
        taille = "S" if "S" in fiche.tailles_disponibles else fiche.tailles_disponibles[0]
    return f"""Use the attached product photo as the exact reference for the garment.
Create TWO separate photorealistic images of this exact garment, worn by the same European woman in her early twenties:
- Image 1: FRONT view, full garment visible.
- Image 2: BACK view, same woman, same outfit, same room and same light.

Garment: {fiche.description_visuelle_en.strip()}

The garment must be IDENTICAL to the reference photo: exactly the same colour and shade, the same cut, length and fit, the same pattern or print (same scale and placement), the same fabric texture and the same details (buttons, seams, ties, ruffles, pockets, neckline, sleeves). Do not add, remove or change anything on the garment. No logo, no text, no watermark. The garment is worn in size {taille} and fits naturally.

Style: realistic second-hand listing photo taken with a smartphone, natural daylight from a window, simple bright home interior (plain light wall, wooden floor), vertical 3:4 format, garment fully in frame and in sharp focus, natural relaxed pose, face cropped at the chin or turned away, no studio lighting, no heavy retouching, no filters."""
