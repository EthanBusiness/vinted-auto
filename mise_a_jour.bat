@echo off
chcp 65001 >nul
title Vinted Auto - mise a jour
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 goto essai_python
py -3 "%~dp0lancer.py" --maj & exit /b
:essai_python
python "%~dp0lancer.py" --maj & exit /b
