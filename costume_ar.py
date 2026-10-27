"""Codice AR "interruttore costume": un COLPETTO di RB (= Z del GameCube) da solo cambia costume (idea di John: L3 ora fa
il tuffo, e RB con le nostre camere non serviva a niente; col gioco originale Z rimette la camera dietro Spidey).
Non conta se mentre RB è tenuto premi una freccia o Start (R3 = Z + giù, Select = Z + Start, LB + RB = menu,
Z + frecce = HUD e rallenty) né se lo tieni più di 0,25 secondi (John: con 0,4 s raddrizzare la camera era troppo lento). Tenuto a lungo, Z arriva al
gioco e raddrizza la camera (rb_aggancio.py: col colpetto il gioco non vede Z, così la camera non si raddrizza).

Usa costume_info.json (creato da costume.py): per ogni texture il byte da cambiare, valore originale e nuovo.
Memoria dell'interruttore in una zona sempre a zero:
  F = 817F0000 (Z tenuto nel frame prima), R = 817F0001 (richiesta), T = 817F0002 (Z tenuto adesso),
  C = 817F0003 (annullato: altro tasto o tenuto troppo), N = 817F0005 (fotogrammi con Z tenuto)
Il corpo fa da "stato": se il suo byte è l'originale il costume è normale, se è il nuovo è quello alternativo.

Uso: python costume_ar.py <file.ini|file.txt> ...  -> sostituisce il codice vecchio (freccia giù) con questo,
tenendo le righe di ogni versione (tasti, "solo in partita", texture).
"""
import json
import sys
from pathlib import Path

import camera_slider as cs

NOME = "$RB (Z) tap to switch skin"
VECCHI_NOMI = ["$d-pad down to switch skin"]
TASTI, Z, ALTRI = 0x80554620, 0x0010, 0x100F  # halfword dei tasti (USA); Z, frecce + Start
F, R, T, C, N = 0x817F0000, 0x817F0001, 0x817F0002, 0x817F0003, 0x817F0005
MAX_FOTOGRAMMI = 15  # 0,25 s a 60 fps (0,4 s come L3 era troppo per raddrizzare la camera): tenuto di più non è un colpetto (= rb_aggancio.TENUTA)
N_TETTO = 200  # il contatore è un byte: fermo qui, se no tenendo Z più di 4 s ripartirebbe da 0


def riga(tipo, addr, val):
    return f"{cs.ar(tipo, addr)} {val:08X}"


def interruttore(tasti):
    """Righe che mettono R = 1 al rilascio di un colpetto di Z (prima della parte che cambia le texture)."""
    return [
        riga(0x00, T, 0), riga(0x3A, tasti, Z), riga(0x00, T, 1),      # T = Z tenuto
        riga(0x48, T, 1), riga(0x3A, tasti, ALTRI), riga(0x00, C, 1),  # Z + freccia/Start = combinazione, non colpetto
        riga(0x08, T, 1), riga(0x80, N, 1),                            # conta i fotogrammi con Z tenuto
        riga(0x30, N, MAX_FOTOGRAMMI), riga(0x00, C, 1),                # troppo lungo
        riga(0x30, N, N_TETTO), riga(0x00, N, N_TETTO),
        riga(0x48, T, 0), riga(0x08, F, 1), riga(0x00, R, 1),          # appena lasciato -> richiesta...
        riga(0x48, T, 0), riga(0x08, C, 1), riga(0x00, R, 0),          # ...se non annullata
        riga(0x08, T, 0), riga(0x00, C, 0), riga(0x08, T, 0), riga(0x00, N, 0),
        riga(0x08, T, 0), riga(0x00, F, 0),                            # F = T
        riga(0x08, T, 1), riga(0x00, F, 1),
    ]


def genera(info, tasti=TASTI, pausa=None):
    corpo = info["corpo"]
    s = int(corpo["indirizzo"], 16)
    righe = [NOME, *(pausa if pausa is not None else cs.riga_pausa()), *interruttore(tasti),
             riga(0x48, R, 1), riga(0x08, s, corpo["originale"]), riga(0x00, R, 2),  # normale -> vai alternativo
             riga(0x48, R, 1), riga(0x08, s, corpo["nuovo"]), riga(0x00, R, 3)]      # alternativo -> vai normale
    for stato, chiave in ((2, "nuovo"), (3, "originale")):
        for nome, t in info.items():
            righe += [riga(0x08, R, stato), riga(0x00, int(t["indirizzo"], 16), t[chiave])]
    righe.append(riga(0x00, R, 0))                      # richiesta gestita
    return righe


def da_vecchio(vecchie):
    """Codice vecchio (freccia giù) di una versione -> nuovo: stesse righe "solo in partita", stesso indirizzo dei
    tasti, stessa parte che cambia le texture (dalla prima riga che guarda la richiesta R)."""
    corpo = [r.strip().upper() for r in vecchie if r.strip()]
    pausa = corpo[:corpo.index("017F0002 00000000")]
    tasti = next(int("80" + r[2:8], 16) for r in corpo if r.startswith("3A") and r.endswith("00000004"))
    coda = corpo[corpo.index("497F0001 00000001"):]
    return [NOME, *pausa, *interruttore(tasti), *coda]


def rifai(vecchie):
    """Codice attuale di una versione (qualsiasi soglia) -> rifatto con interruttore() di adesso: stesse righe "solo in
    partita", stesso indirizzo dei tasti, stessa parte che cambia le texture."""
    corpo = [x.strip().upper() for x in vecchie if x.strip()]
    pausa = corpo[:corpo.index("017F0002 00000000")]
    tasti = next(int("80" + x[2:8], 16) for x in corpo if x.startswith("3A") and x.endswith("00000010"))
    coda = corpo[corpo.index("497F0001 00000001"):]
    return [*pausa, *interruttore(tasti), *coda]


def sostituisci_in(percorso):
    p = Path(percorso)
    testo = p.read_bytes().decode("utf-8")
    nl = "\r\n" if "\r\n" in testo else "\n"
    righe = testo.split(nl)
    for vecchio in VECCHI_NOMI[:1]:
        if vecchio not in righe:
            continue
        i = righe.index(vecchio)
        j = i + 1
        while j < len(righe) and righe[j].strip() and not righe[j].startswith(("$", "[")):
            j += 1
        nuove = da_vecchio(righe[i + 1:j])
        righe[i:j] = nuove
        testo = nl.join(righe)
        # nell'elenco dei codici accesi il nome cambia uguale
        testo = testo.replace(nl + vecchio + nl, nl + NOME + nl)
        p.write_bytes(testo.encode("utf-8"))
        return True
    return False


if __name__ == "__main__":
    for f in sys.argv[1:]:
        print(f, "ok" if sostituisci_in(f) else "niente")
