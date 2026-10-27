"""Codice HUD con interruttore (sessione 16, idea di John).

Prima: "$Z + d-pad left to hide HUD, Z + d-pad right to show" scriveva i due byte dell'HUD (1 = nascosto) solo quando
premevi Z + freccia. Il gioco però li rimette a 0 da solo (es. chiudendo la mappa) -> l'HUD tornava.
Adesso:
  - freccia sinistra + destra insieme (sul pad: LB, dal profilo dei tasti) = accendi/spegni;
  - Z + sinistra = nascondi, Z + destra = mostra (come prima);
  - lo stato sta in un byte libero (817F0014, dispari = nascosto) e finché è "nascosto" il codice riscrive 1 a ogni
    frame: dopo la mappa l'HUD resta nascosto. Quando è "visibile" il codice non tocca niente (il gioco fa quello che vuole).
Byte liberi: S = 817F0014, halfword 817F0016 = [A][P] (P = sinistra+destra premute adesso, A = già contate).
Sinistra + destra insieme: il codice del FOV fa +1° e -1° nello stesso frame = nessun cambio.

v3 (sessione 17d): LB + RB apre il menu dell'app, ma LB arriva quasi sempre un attimo prima di RB e faceva scattare l'HUD.
Ora sinistra + destra devono restare premute 4 frame (~0,07 s) prima di contare (contatore C = 817F0015), e se nel
frattempo c'è Z (RB) quella pressione non conta finché non lasci tutto."""
import sys
from pathlib import Path

NOME = "$HUD on/off with LB (hold d-pad left+right), Z + d-pad left to hide, Z + d-pad right to show"
VECCHI = ["$HUD on/off with d-pad left+right (LB), Z + d-pad left to hide, Z + d-pad right to show",
          "$Z + d-pad left to hide HUD, Z + d-pad right to show"]
VECCHIO = VECCHI[-1]
S, C, AP, A, P = 0x817F0014, 0x817F0015, 0x817F0016, 0x817F0016, 0x817F0017
FRAME = 4  # sinistra + destra tenute per 4 frame (~0,07 s): un tocco di LB basta, LB + RB insieme no


def ar(tipo, addr):
    return f"{(tipo << 24 | (addr & 0x01FFFFFF)):08X}"


def riga(tipo, addr, val):
    return f"{ar(tipo, addr)} {val:08X}"


def parti(vecchie):
    """(pausa, indirizzo tasti, byte HUD 1, byte HUD 2) dalle righe di un codice HUD qualsiasi (v1, v2 o v3)."""
    v = [x.split() for x in vecchie if x.strip()]
    a = lambda r: 0x80000000 | (int(r[0], 16) & 0x01FFFFFF)
    if len(v) > 8:  # v2 / v3: tasti nella 3a riga, i due byte HUD nelle ultime due
        return " ".join(v[0]).upper(), a(v[2]), a(v[-2]), a(v[-1])
    return " ".join(v[0]).upper(), a(v[1]), a(v[2]), a(v[3])


def righe(vecchie):
    """Dalle righe del vecchio codice (pausa, tasti, indirizzi HUD della versione) -> righe del nuovo."""
    pausa, tasti, h1, h2 = parti(vecchie)
    return [pausa,
            riga(0x00, P, 0), riga(0x7A, tasti, 0x0001), riga(0x3A, tasti, 0x0002), riga(0x00, P, 1),  # P = sx e dx premute
            riga(0x3A, tasti, 0x0010), riga(0x00, A, 1),                    # c'è anche Z (LB + RB = menu): non conta
            riga(0x0A, AP, 0x0001), riga(0x80, C, 1),                       # tenute e non ancora contate: C + 1
            riga(0x12, AP, 0x0001), riga(0x00, C, 0),                       # altrimenti C = 0
            riga(0x08, C, FRAME), riga(0x00, h1, 0),                        # tenute abbastanza: prima mostro...
            riga(0x08, C, FRAME), riga(0x00, h2, 0),
            riga(0x08, C, FRAME), riga(0x80, S, 1),                         # ...poi stato + 1 (dispari = nascosto)
            riga(0x08, C, FRAME), riga(0x00, A, 1),                         # contata (A = 1)
            riga(0x08, P, 0), riga(0x00, A, 0),                             # lasciate: A = 0
            riga(0x0A, tasti, 0x0011), riga(0x00, S, 1),                    # Z + sinistra: nascondi
            riga(0x4A, tasti, 0x0012), riga(0x00, S, 0), riga(0x00, h1, 0),  # Z + destra: mostra
            riga(0x0A, tasti, 0x0012), riga(0x00, h2, 0),
            riga(0x78, S, 1), riga(0x00, h1, 1), riga(0x00, h2, 1)]         # nascosto: lo tengo nascosto a ogni frame


def migra_txt(f):
    """AR codes <sigla>.txt del pack: nome senza $ e righe separate da una riga vuota."""
    f = Path(f)
    testo = f.read_bytes().decode("utf-8")
    nl = "\r\n" if "\r\n" in testo else "\n"
    L = testo.split(nl)
    pulite = [x.strip() for x in L]
    vecchio = next((v for v in VECCHI if v[1:] in pulite), None)
    if not vecchio:
        return False
    i = pulite.index(vecchio[1:])
    j = i + 1
    while j < len(L) and (not L[j].strip() or len(L[j].split()) == 2 and all(len(p) == 8 for p in L[j].split())):
        j += 1
    while j > i + 1 and not L[j - 1].strip():
        j -= 1
    vecchie = [x for x in L[i + 1:j] if x.strip()]
    nuovo = [NOME[1:], ""]
    for r in righe(vecchie):
        nuovo += [r.lower(), ""]
    L[i:j] = nuovo[:-1]
    f.write_bytes(nl.join(L).encode("utf-8"))
    return True


if __name__ == "__main__":  # python hud_toggle.py file... (ini o txt)
    import app_core as core
    for f in sys.argv[1:]:
        if f.lower().endswith(".txt"):
            print(f, migra_txt(f))
        else:
            vecchio = next((v for v in VECCHI if core.blocco_codice(f, v)), None)
            print(f, core.sostituisci_codice(f, vecchio, NOME, righe(core.blocco_codice(f, vecchio))) if vecchio else "niente")
