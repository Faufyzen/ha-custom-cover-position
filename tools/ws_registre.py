"""Lecture des options du registre des entités par le websocket de Home Assistant.

Petit client écrit avec la seule bibliothèque standard (aucune installation) : l'API REST ne
donne pas les options du registre, que seules les commandes websocket exposent.
"""

from __future__ import annotations

import base64
import json
import os
import socket
import struct
from pathlib import Path

HOTE, PORT = "10.10.30.30", 80
JETON = Path.home().joinpath(".ha-sandbox-token").read_text().strip()


def _connexion():
    s = socket.create_connection((HOTE, PORT), timeout=20)
    cle = base64.b64encode(os.urandom(16)).decode()
    s.sendall((f"GET /api/websocket HTTP/1.1\r\nHost: {HOTE}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
               f"Sec-WebSocket-Key: {cle}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
    tampon = b""
    while b"\r\n\r\n" not in tampon:
        tampon += s.recv(4096)
    return s, tampon.split(b"\r\n\r\n", 1)[1]


def _echange(commandes: list[dict]) -> dict:
    s, tampon = _connexion()

    def lire(n):
        nonlocal tampon
        while len(tampon) < n:
            tampon += s.recv(65536)
        d, tampon = tampon[:n], tampon[n:]
        return d

    def recevoir():
        donnees = b""
        while True:
            b1, b2 = lire(2)
            fin, ln = b1 & 0x80, b2 & 0x7F
            if ln == 126:
                ln = struct.unpack(">H", lire(2))[0]
            elif ln == 127:
                ln = struct.unpack(">Q", lire(8))[0]
            donnees += lire(ln)
            if fin:
                return json.loads(donnees)

    def envoyer(obj):
        p = json.dumps(obj).encode()
        masque = os.urandom(4)
        L = len(p)
        entete = b"\x81" + (bytes([0x80 | L]) if L < 126 else b"\xfe" + struct.pack(">H", L))
        s.sendall(entete + masque + bytes(c ^ masque[i % 4] for i, c in enumerate(p)))

    recevoir()
    envoyer({"type": "auth", "access_token": JETON})
    assert recevoir()["type"] == "auth_ok"
    reponses = {}
    for i, commande in enumerate(commandes, start=1):
        envoyer({"id": i, **commande})
        while True:
            m = recevoir()
            if m.get("id") == i:
                reponses[i] = m
                break
    s.close()
    return reponses


def options_cover(entity_id: str) -> dict:
    """Options du domaine « cover » d'une entité (par exemple favorite_positions)."""
    rep = _echange([{"type": "config/entity_registry/get", "entity_id": entity_id}])[1]
    return ((rep.get("result") or {}).get("options") or {}).get("cover", {}) or {}
