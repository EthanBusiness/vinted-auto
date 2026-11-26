"""Adresses où l'employée peut ouvrir le site : même wifi (réseau local) ou à distance avec Tailscale."""
import ipaddress
import json
import os
import shutil
import socket
import subprocess
from pathlib import Path

TAILSCALE_RESEAU = ipaddress.ip_network("100.64.0.0/10")


def _ips() -> set:
    ips = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except OSError:
        pass
    try:   # adresse utilisée pour sortir sur le réseau (aucun paquet n'est envoyé)
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("192.168.255.255", 1))
        ips.add(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    return ips


def tailscale_exe():
    exe = shutil.which("tailscale")
    if exe:
        return exe
    if os.name == "nt":
        p = Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "Tailscale" / "tailscale.exe"
        if p.exists():
            return str(p)
    return None


def tailscale_nom():
    """Nom de ce PC dans Tailscale (ex : pc-ethan), ou None."""
    exe = tailscale_exe()
    if not exe:
        return None
    try:
        r = subprocess.run([exe, "status", "--json"], capture_output=True, timeout=8)
        moi = json.loads(r.stdout.decode("utf-8", "replace")).get("Self") or {}
        nom = (moi.get("DNSName") or "").rstrip(".")
        return nom.split(".")[0] or (moi.get("HostName") or None)
    except Exception:  # noqa
        return None


def adresses() -> dict:
    local, tailscale = [], []
    for ip in sorted(_ips()):
        try:
            a = ipaddress.ip_address(ip)
        except ValueError:
            continue
        if a in TAILSCALE_RESEAU:
            tailscale.append(ip)
        elif a.is_private and not a.is_loopback and not a.is_link_local:
            local.append(ip)
    return {"local": local, "tailscale": tailscale, "tailscale_installe": bool(tailscale_exe()),
            "tailscale_nom": tailscale_nom() if tailscale else None}
