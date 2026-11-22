@echo off
chcp 65001 >nul
title Vinted Auto
cd /d "%~dp0"

echo.
echo  === Vinted Auto ===
echo.

REM 1) Premiere fois : creer l'environnement Python
if not exist ".venv\Scripts\python.exe" (
  echo  Premiere installation, ca peut prendre 1 a 2 minutes...
  py -3 -m venv .venv 2>nul || python -m venv .venv
  if not exist ".venv\Scripts\python.exe" (
    echo.
    echo  ERREUR : Python est introuvable.
    echo  Installe Python depuis python.org en cochant "Add python.exe to PATH", puis relance.
    pause
    exit /b 1
  )
)

REM 2) Installer / mettre a jour les outils necessaires
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt
if errorlevel 1 (
  echo.
  echo  ERREUR pendant l'installation des outils. Verifie ta connexion internet et relance.
  pause
  exit /b 1
)

REM 3) Premiere fois : creer le fichier de reglages .env
if not exist ".env" (
  copy ".env.example" ".env" >nul
  echo.
  echo  Le fichier de reglages .env vient d'etre cree.
  echo  Il va s'ouvrir dans le Bloc-notes : remplis-le, enregistre (Ctrl+S), ferme-le,
  echo  puis relance lancer.bat.
  echo.
  pause
  notepad ".env"
  exit /b 0
)

REM 4) Lancer le site et ouvrir le navigateur
start "" "http://localhost:8000"
".venv\Scripts\python.exe" app.py
echo.
echo  Le site s'est arrete.
pause
