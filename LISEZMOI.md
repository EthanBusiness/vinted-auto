# Vinted Auto

Petit site (en français) qui prépare et publie des annonces Vinted à partir de liens Shein.

## Lancer le site (Windows)

1. Installe **Python** (python.org) en cochant **« Add python.exe to PATH »**.
2. Double-clique sur **`lancer.bat`**.
   - La première fois, il installe ce qu'il faut puis ouvre le fichier de réglages `.env`
     dans le Bloc-notes : remplis tes mots de passe et ta clé Anthropic, enregistre, ferme,
     puis relance `lancer.bat`.
3. Le site s'ouvre sur <http://localhost:8000>. Pour l'arrêter, ferme la fenêtre noire.

## Où sont les choses

| Fichier | Rôle |
|---|---|
| `.env` | Tes clés et mots de passe (jamais dans git) |
| `data/vinted.db` | La base de données (articles, coûts) |
| `app.py` | Les pages du site |
| `shein.py` | Lecture des fiches Shein |
| `ia.py` | Appels à Claude Haiku et prompt Gemini |
| `scalency.py` | Appels à l'API Scalency |
| `templates/` | Les pages HTML |

## Avancement

- [x] Étape 2 : coller des liens, lecture Shein (+ plan B), prompt Gemini, coûts
- [ ] Étape 3 : page employée (file, copier le prompt, dépôt des photos)
- [ ] Étape 4 : génération de l'annonce, hébergement photos (Supabase), essai à blanc Scalency
- [ ] Étape 5 : publication réelle sur un compte de test
- [ ] Étape 6 : anti-doublons, étalement, multi-comptes, tableau de bord
- [ ] Étape 7 : démarrage automatique + accès à distance (Tailscale)
