"""Démarre Vinted Auto. Lancé par lancer.bat (double-clic).

1. Prépare Python (une seule fois, 1 à 2 minutes).
2. Démarre le site et ouvre le navigateur quand il est prêt.
3. Le relance tout seul après une mise à jour ou un plantage.
"""
import hashlib
import os
import subprocess
import sys
import time
import traceback
import urllib.request
from pathlib import Path

CODE = Path(__file__).resolve().parent
sys.path.insert(0, str(CODE))


def titre(t):
    print("\n  " + t)


def pause_et_quitter(code=1):
    print()
    try:
        input("  Appuie sur Entrée pour fermer cette fenêtre...")
    except (EOFError, KeyboardInterrupt):
        pass
    sys.exit(code)


def erreur(message):
    print("\n  " + "=" * 62)
    for ligne in message.strip().splitlines():
        print("  " + ligne)
    print("  " + "=" * 62)
    print("  Si tu ne sais pas quoi faire : fais une capture de cette fenêtre")
    print("  et envoie-la à Claude.")
    pause_et_quitter(1)


def python_env(donnees: Path) -> Path:
    env = donnees / "python-env"
    exe = env / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    version = f"{sys.version_info.major}.{sys.version_info.minor}"
    marque = env / "version.txt"
    if exe.exists() and marque.exists() and marque.read_text().strip() == version:
        return exe
    titre("Première installation : préparation de Python (1 à 2 minutes)...")
    if env.exists():
        import shutil
        shutil.rmtree(env, ignore_errors=True)
    r = subprocess.run([sys.executable, "-m", "venv", str(env)])
    if r.returncode != 0 or not exe.exists():
        erreur("Impossible de préparer Python.\n"
               "Réinstalle Python depuis python.org en cochant « Add python.exe to PATH »,\n"
               "puis relance lancer.bat.")
    marque.write_text(version)
    return exe


def installer_outils(exe: Path, donnees: Path):
    req = CODE / "requirements.txt"
    empreinte = hashlib.sha256(req.read_bytes()).hexdigest()[:16]
    marque = donnees / "python-env" / "outils.txt"
    if marque.exists() and marque.read_text().strip() == empreinte:
        return
    titre("Installation des outils nécessaires (une seule fois)...")
    r = subprocess.run([str(exe), "-m", "pip", "install", "--disable-pip-version-check", "-q", "-r", str(req)])
    if r.returncode != 0:
        erreur("L'installation des outils a échoué.\n"
               "Vérifie que ta connexion internet marche, puis relance lancer.bat.")
    marque.write_text(empreinte)
    print("  Outils installés.")


def site_deja_lance(port) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/ping", timeout=2) as r:
            return b"vinted-auto" in r.read()
    except Exception:  # noqa
        return False


def raccourci_bureau():
    """Crée (ou met à jour) un raccourci « Vinted Auto » sur le Bureau."""
    if os.name != "nt":
        return
    try:
        bat = str(CODE / "lancer.bat").replace("'", "''")
        dossier = str(CODE).replace("'", "''")
        ps = ("$d=[Environment]::GetFolderPath('Desktop');"
              "$s=(New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $d 'Vinted Auto.lnk'));"
              f"$s.TargetPath='{bat}';$s.WorkingDirectory='{dossier}';"
              "$s.IconLocation='%SystemRoot%\\System32\\shell32.dll,13';$s.Save()")
        subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
    except Exception:  # noqa
        pass


def main():
    print("\n  ==========================================")
    print("              VINTED AUTO")
    print("  ==========================================")
    if sys.version_info < (3, 10):
        erreur(f"Ta version de Python ({sys.version.split()[0]}) est trop ancienne.\n"
               "Installe Python 3.12 ou plus récent depuis python.org.")
    from vinted_auto.config import DONNEES, get
    port = int(get("PORT", "8000") or 8000)
    print(f"  Dossier du site    : {CODE}")
    print(f"  Tes données / clés : {DONNEES}")

    if "--maj" in sys.argv:
        titre("Téléchargement de la dernière version depuis GitHub...")
        try:
            from vinted_auto import maj
            maj.installer()
            print("  Mise à jour installée. Relance lancer.bat (ou le raccourci du Bureau).")
        except Exception as e:  # noqa
            erreur(f"La mise à jour a échoué : {e}\nVérifie ta connexion internet.")
        pause_et_quitter(0)

    if site_deja_lance(port):
        titre("Le site est déjà lancé : j'ouvre le navigateur.")
        import webbrowser
        webbrowser.open(f"http://localhost:{port}/")
        time.sleep(2)
        return

    exe = python_env(DONNEES)
    installer_outils(exe, DONNEES)
    raccourci_bureau()

    plantages = []
    ouvrir = True
    while True:
        env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
        if not ouvrir:
            env["VINTED_AUTO_SANS_NAVIGATEUR"] = "1"
        titre("Démarrage du site...")
        try:
            code = subprocess.run([str(exe), "-m", "vinted_auto.serveur"], cwd=str(CODE), env=env).returncode
        except KeyboardInterrupt:
            code = 0
        ouvrir = False
        if code == 0:
            titre("Le site est arrêté.")
            return
        if code == 42:  # mise à jour faite : on relance avec le nouveau code
            titre("Mise à jour installée, redémarrage...")
            installer_outils(exe, DONNEES)
            continue
        if code == 3:  # message déjà affiché par le site
            pause_et_quitter(1)
        plantages = [t for t in plantages if time.time() - t < 120] + [time.time()]
        if len(plantages) >= 4:
            erreur("Le site s'est arrêté plusieurs fois de suite (voir les messages au-dessus).")
        titre("Le site s'est arrêté de façon inattendue : je le relance dans 5 secondes...")
        time.sleep(5)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except KeyboardInterrupt:
        pass
    except Exception:  # noqa
        traceback.print_exc()
        erreur("Erreur inattendue au démarrage (détails au-dessus).")
