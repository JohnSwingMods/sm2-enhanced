"""Salvataggi di Spider-Man 2 (GameCube, file .gci di Dolphin): controllo, conversione ITA <-> USA, nome dello slot.

Formato (sessione 7): 0x40 byte di intestazione GCI, poi i dati (0x30000 byte): scritte/icona/banner, da +0x2040 i
dati di gioco (data, "15:48:10", nome slot a +0x206E, tabella interruttori a +0x230C...).
Ultimi 4 byte = controllo: CRC32 del gioco sui dati (senza gli ultimi 4), partenza 0. Il CRC del gioco (802280xx)
usa "srawi" (spostamento CON segno) invece di uno spostamento normale -> non è il CRC32 standard.
Tabella CRC32 normale (in RAM a 8046B3E4 ITA), qui ricalcolata.
Uso:
  python salvataggio.py controlla <file.gci>
  python salvataggio.py converti <sorgente.gci> <modello_altra_versione.gci> <uscita.gci>
  python salvataggio.py nome <file.gci> <NOME>
"""
import struct
import sys
from pathlib import Path

M = 0xFFFFFFFF
TAB = []
for n in range(256):
    c = n
    for _ in range(8):
        c = (c >> 1) ^ 0xEDB88320 if c & 1 else c >> 1
    TAB.append(c)
NOME_SLOT = 0x40 + 0x206E  # nel file .gci (a +0x207C ci sono i punti eroe)
NOME_MAX = 10


def crc_sm2(buf, crc=0):
    c = ~crc & M
    for b in buf:
        c = TAB[(c ^ b) & 0xFF] ^ ((c >> 8) | (0xFF000000 if c & 0x80000000 else 0))
    return ~c & M


def controllo(gci):
    return crc_sm2(gci[0x40:-4])


def con_controllo(gci):
    return gci[:-4] + struct.pack(">I", controllo(gci))


def converti(sorgente, modello):
    """Dati di gioco da `sorgente`, intestazione/icona/scritte (lingua e codice del gioco) da `modello`."""
    assert len(sorgente) == len(modello)
    return con_controllo(modello[:0x40 + 0x2040] + sorgente[0x40 + 0x2040:])


def per_versione(gci, gid):
    """Cambia il codice del gioco nell'intestazione GCI (es. GK2E52 -> GK2P52): serve per le versioni che hanno lo
    stesso programma dell'americana (UK GK2P52, Germania GK2D52, Francia GK2F52). Le scritte restano quelle del file
    di partenza finché il gioco non risalva. Il controllo copre solo i dati, quindi non cambia."""
    h = bytearray(gci[:0x40])
    vecchio = bytes(h[:4])
    h[:6] = gid.encode("ascii")
    h[8:0x28] = bytes(h[8:0x28]).replace(vecchio, gid[:4].encode("ascii"))
    return bytes(h) + gci[0x40:]


def nome_file(gid):
    return f"{gid[4:6]}-{gid[:4]}-DOL-{gid[:4]}spidermn.gci"


def rinomina(gci, nome):
    b = nome.encode("ascii")
    assert 0 < len(b) <= NOME_MAX
    return con_controllo(gci[:NOME_SLOT] + b.ljust(NOME_MAX, b"\0") + gci[NOME_SLOT + NOME_MAX:])


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "controlla":
        g = Path(sys.argv[2]).read_bytes()
        print("salvato", hex(struct.unpack(">I", g[-4:])[0]), "calcolato", hex(controllo(g)),
              "| nome:", g[NOME_SLOT:NOME_SLOT + NOME_MAX].rstrip(b"\0").decode("ascii", "replace"))
    elif cmd == "converti":
        Path(sys.argv[4]).write_bytes(converti(Path(sys.argv[2]).read_bytes(), Path(sys.argv[3]).read_bytes()))
    elif cmd == "nome":
        p = Path(sys.argv[2])
        p.write_bytes(rinomina(p.read_bytes(), sys.argv[3]))
