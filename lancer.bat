@echo off
REM Garde toujours la fenetre ouverte, meme en cas d'erreur
if not "%~1"=="--garder" (
  cmd /k ""%~f0" --garder"
  exit /b
)
title Vinted Auto
cd /d "%~dp0"

echo.
echo  === Vinted Auto ===
echo  Dossier : %CD%
echo.

if exist ".venv\Scripts\python.exe" goto installer_outils

echo  Premiere installation : creation de l'environnement Python...
py -3 -m venv .venv
if exist ".venv\Scripts\python.exe" goto installer_outils
python -m venv .venv
if exist ".venv\Scripts\python.exe" goto installer_outils
echo.
echo  ERREUR : Python est introuvable.
echo  Installe Python depuis python.org en cochant "Add python.exe to PATH",
echo  redemarre le PC, puis relance lancer.bat.
goto fin

:installer_outils
echo  Installation des outils necessaires, 1 a 2 minutes la premiere fois...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto erreur_pip

if exist ".env" goto lancer
copy ".env.example" ".env" >nul
echo.
echo  ------------------------------------------------------------
echo   Le fichier de reglages .env vient d'etre cree.
echo   Il va s'ouvrir dans le Bloc-notes.
echo   1. Remplis ton mot de passe et tes cles.
echo   2. Enregistre avec Ctrl+S, puis ferme le Bloc-notes.
echo   3. Relance lancer.bat.
echo  ------------------------------------------------------------
echo.
start "" notepad ".env"
goto fin

:lancer
echo.
echo  Demarrage du site...
start "" "http://localhost:8000"
".venv\Scripts\python.exe" app.py
echo.
echo  Le site s'est arrete. Si un message d'erreur est affiche au-dessus,
echo  fais une capture d'ecran de cette fenetre.
goto fin

:erreur_pip
echo.
echo  ERREUR pendant l'installation des outils (voir les messages au-dessus).
echo  Verifie ta connexion internet, puis fais une capture d'ecran de cette fenetre.
goto fin

:fin
echo.
echo  Tu peux fermer cette fenetre.
