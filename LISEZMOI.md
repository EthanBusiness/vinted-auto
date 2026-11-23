# Vinted Auto

Tu colles un lien Shein, le site te donne : la description Vinted, les liens des photos Shein et les 2 prompts Gemini (face et dos) avec le fond et le modèle du compte choisi. Ton employée dépose les photos, puis tu publies sur tes comptes Vinted via Scalency.

## Installer (une seule fois)

1. Télécharge le ZIP : bouton vert **Code** › **Download ZIP** sur cette page GitHub.
2. Clic droit sur le ZIP › **Extraire tout**. Range le dossier où tu veux (par exemple dans Documents).
3. Ouvre le dossier et double-clique sur **lancer.bat**.
   - Si Windows affiche « Windows a protégé votre ordinateur » : **Informations complémentaires** › **Exécuter quand même**.
   - La première fois, il prépare Python (1 à 2 minutes). Ensuite le site s'ouvre tout seul dans ton navigateur.
   - Un raccourci **Vinted Auto** est créé sur ton Bureau : la prochaine fois, double-clique simplement dessus.
4. Dans le site, page **Réglages** : colle tes clés (Claude, Scalency, Supabase) et clique sur **Tester** pour chacune.
5. Installe l'extension Chrome « lecteur Shein » : le site te guide (page **Extension**, 2 minutes).
6. Page **Comptes** : ajoute un fond et un modèle pour chaque compte (ton image, ou un prompt généré pour la créer dans Gemini).

## Utiliser

- **Ajouter** : colle tes liens Shein (un par ligne, tu peux mettre la taille après le lien), coche les comptes, clique **Lancer**.
- **Photos** : pour chaque article, copie le prompt dans Gemini avec les images indiquées, puis glisse les 2 photos.
- **Articles** : vérifie, corrige si besoin, puis **Publier la sélection** (Scalency étale les publications).

## Mettre à jour

Page **Réglages** › **Mettre à jour maintenant**. Le site télécharge la dernière version et redémarre tout seul.
Si le site ne démarre plus : double-clique sur **mise_a_jour.bat**.

## Où sont mes données ?

Dans le dossier **VintedAuto-donnees** de ton dossier personnel (`C:\Users\<toi>\VintedAuto-donnees`) :
clés (`.env`), base des articles, images. Elles ne sont jamais sur GitHub et ne sont jamais écrasées par une mise à jour.

## En cas de problème

La fenêtre noire reste ouverte et affiche l'erreur : fais-en une capture d'écran. Les erreurs détaillées sont aussi
dans `VintedAuto-donnees\erreurs.log`.

## Pour les développeurs

- Serveur : Python (bibliothèque standard + `anthropic`), base SQLite, pages HTML/JS sans framework.
- Test de bout en bout (Chromium + extension + faux services) : `node tests/e2e.js` (variable `PY` = Python avec `anthropic`).
