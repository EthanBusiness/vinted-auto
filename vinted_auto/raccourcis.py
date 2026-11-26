"""Raccourcis Windows « Vinted Auto » : Bureau, menu Démarrer et (au choix) lancement à l'allumage du PC.

Le raccourci passe par cmd.exe (et pas directement par lancer.bat) : Windows n'autorise pas
l'épinglage d'un .bat dans la barre des tâches, alors qu'il autorise celui de cmd.exe.
"""
import os
import subprocess
from pathlib import Path

CODE = Path(__file__).resolve().parent.parent
ICONE = CODE / "web" / "icone.ico"
NOM = "Vinted Auto.lnk"


def _ps(texte: str) -> str:
    return "'" + str(texte).replace("'", "''") + "'"


def script_raccourci(dossier_special: str, minimise=False, arguments="") -> str:
    """Commande PowerShell qui crée le raccourci dans un dossier spécial de Windows
    (Desktop, Programs = menu Démarrer, Startup = démarrage du PC)."""
    bat = CODE / "lancer.bat"
    args = f'/c ""{bat}"{(" " + arguments) if arguments else ""}"'
    icone = f"{ICONE},0" if ICONE.exists() else "%SystemRoot%\\System32\\shell32.dll,13"
    return (f"$d=[Environment]::GetFolderPath({_ps(dossier_special)});"
            f"$s=(New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $d {_ps(NOM)}));"
            "$s.TargetPath=(Join-Path $env:SystemRoot 'System32\\cmd.exe');"
            f"$s.Arguments={_ps(args)};$s.WorkingDirectory={_ps(CODE)};"
            f"$s.IconLocation={_ps(icone)};$s.Description='Ouvrir Vinted Auto';"
            f"$s.WindowStyle={7 if minimise else 1};$s.Save()")


def _lancer_ps(script: str) -> bool:
    if os.name != "nt":
        return False
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
        return r.returncode == 0
    except Exception:  # noqa
        return False


def installer():
    """Icône sur le Bureau + dans le menu Démarrer (on la retrouve en tapant « Vinted »)."""
    _lancer_ps(script_raccourci("Desktop") + ";" + script_raccourci("Programs"))
    if demarrage_actif():          # garde le raccourci de démarrage à jour (dossier ou icône déplacés)
        demarrage_auto(True)


def dossier_demarrage() -> Path:
    return Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def disponible() -> bool:
    return os.name == "nt" and bool(os.environ.get("APPDATA"))


def demarrage_actif() -> bool:
    return disponible() and (dossier_demarrage() / NOM).exists()


def demarrage_auto(actif: bool) -> bool:
    """Lance Vinted Auto (fenêtre réduite, sans ouvrir le navigateur) quand on allume le PC."""
    if not disponible():
        return False
    lien = dossier_demarrage() / NOM
    if not actif:
        try:
            lien.unlink()
        except FileNotFoundError:
            pass
        return True
    return _lancer_ps(script_raccourci("Startup", minimise=True, arguments="--demarrage")) and lien.exists()
