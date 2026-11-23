@echo off
chcp 65001 >nul
title Vinted Auto
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 goto essai_python
py -3 "%~dp0lancer.py" & exit /b
:essai_python
where python >nul 2>nul
if errorlevel 1 goto pas_de_python
python "%~dp0lancer.py" & exit /b
:pas_de_python
echo.
echo   ERREUR : Python est introuvable sur ce PC.
echo   1. Va sur python.org et installe Python.
echo   2. Sur le premier ecran, coche bien la case Add python.exe to PATH.
echo   3. Redemarre le PC, puis double-clique encore sur lancer.bat.
echo.
pause
exit /b
