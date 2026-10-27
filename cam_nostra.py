"""Camera "nostra" (Gecko): sostituisce posizione e direzione finali della camera del gioco.

Come funziona (ITA per ora):
- gancio FINE: la funzione vuota chiamata alla fine dell'aggiornamento della camera (r3 = oggetto camera). Lì salvo la
  matrice finale del gioco ([r3+0x30]: righe destra, su, avanti, posizione; ATTENZIONE [r3+0x164] è Spidey!) e ci scrivo la nostra.
- gancio INIZIO: all'inizio dell'aggiornamento della camera del frame dopo rimetto la matrice del gioco, così il gioco
  continua a ragionare con la sua camera (se no la nostra posizione gli rientra come punto di partenza e "vola via").
Memoria nostra: 817F0100 matrice salvata (0x40), 817F0140 = 1 se salvata, 817F0150.. costanti, 817F0200.. stato.

uso: python cam_nostra.py [prova] -> stampa le righe Gecko."""
import sys

import ppcasm as asm

VERSIONI = {
    # camera: inizio aggiornamento (stwu r1,-0x1e8(r1)), funzione vuota della fine, posizione di Spidey
    "GK2I52": {"inizio": 0x801A0B44, "fine": 0x801A1E40, "spidey": 0x80495FEC},
}
BASE = 0x817F0000
COST = {"mezzo": (0x150, 0.5), "unoemezzo": (0x154, 1.5), "dist": (0x158, 3.0), "spalle": (0x15C, 1.0)}

RIMETTI = """
    lis r12, 0x817F
    lwz r11, 0x140(r12)
    cmpwi r11, 0
    beq fuori
    lwz r10, 0x30(r3)
    addi r9, r12, 0x100
    li r11, 16
    mtctr r11
copia:
    lwz r11, 0(r9)
    stw r11, 0(r10)
    addi r9, r9, 4
    addi r10, r10, 4
    bdnz copia
    li r11, 0
    stw r11, 0x140(r12)
fuori:
    stwu r1, -0x1e8(r1)
"""

# rsqrt(f) = solo la stima del processore (frsqrte): sul Gekko/Broadway è già precisa a 1/4096 (0,02%), più che
# abbastanza per normalizzare le direzioni della camera. Prima c'erano 1-2 passi di Newton: 4-8 istruzioni in più x 10
# = spazio Gecko sprecato (Dolphin ne ha ~3264 byte in tutto). x e t non servono più (tenuti per non cambiare le chiamate).
def _rsqrt(dest, x, t):
    return f"""
    frsqrte {dest}, {x}
"""


def prova(v):
    """Tappa 1: stessa direzione della camera del gioco, distanza fissa, sguardo sulle spalle di Spidey."""
    s = v["spidey"]
    return f"""
    lis r12, 0x817F
    lwz r10, 0x30(r3)
    ; salva la matrice del gioco
    addi r9, r12, 0x100
    mr r8, r10
    li r11, 16
    mtctr r11
salva:
    lwz r11, 0(r8)
    stw r11, 0(r9)
    addi r8, r8, 4
    addi r9, r9, 4
    bdnz salva
    li r11, 1
    stw r11, 0x140(r12)
    lfs f12, 0x150(r12)
    lfs f13, 0x154(r12)
    ; T = Spidey + (0, spalle, 0)
    lis r11, {s >> 16:#x}
    ori r11, r11, {s & 0xFFFF:#x}
    lfs f1, 0(r11)
    lfs f2, 4(r11)
    lfs f3, 8(r11)
    lfs f0, 0x15C(r12)
    fadds f2, f2, f0
    ; v = P_gioco - T
    lfs f4, 0x30(r10)
    lfs f5, 0x34(r10)
    lfs f6, 0x38(r10)
    fsubs f4, f4, f1
    fsubs f5, f5, f2
    fsubs f6, f6, f3
    fmuls f7, f4, f4
    fmadds f7, f5, f5, f7
    fmadds f7, f6, f6, f7
    {_rsqrt("f8", "f7", "f9")}
    fmuls f4, f4, f8
    fmuls f5, f5, f8
    fmuls f6, f6, f8
    ; P = T + dir * dist
    lfs f0, 0x158(r12)
    fmadds f9, f4, f0, f1
    fmadds f10, f5, f0, f2
    fmadds f11, f6, f0, f3
    stfs f9, 0x30(r10)
    stfs f10, 0x34(r10)
    stfs f11, 0x38(r10)
    ; avanti = -dir
    fneg f4, f4
    fneg f5, f5
    fneg f6, f6
    stfs f4, 0x20(r10)
    stfs f5, 0x24(r10)
    stfs f6, 0x28(r10)
    ; destra = normalize(fz, 0, -fx)
    fmuls f7, f4, f4
    fmadds f7, f6, f6, f7
    {_rsqrt("f8", "f7", "f9")}
    fmuls f1, f6, f8
    fneg f3, f4
    fmuls f3, f3, f8
    stfs f1, 0x00(r10)
    li r11, 0
    stw r11, 0x04(r10)
    stfs f3, 0x08(r10)
    ; su = avanti x destra = (fy*rz, fz*rx - fx*rz, -fy*rx)
    fmuls f7, f5, f3
    stfs f7, 0x10(r10)
    fmuls f7, f6, f1
    fnmsubs f7, f4, f3, f7
    stfs f7, 0x14(r10)
    fmuls f7, f5, f1
    fneg f7, f7
    stfs f7, 0x18(r10)
"""


def codice(ver="GK2I52", logica=prova):
    v = VERSIONI[ver]
    righe = [asm.scrivi32(BASE + o, asm.f32(x)) for o, x in COST.values()]
    righe += asm.c2(v["inizio"], asm.assembla(RIMETTI))
    righe += asm.c2(v["fine"], asm.assembla(logica(v)))
    return righe


if __name__ == "__main__":
    print("\n".join(codice()))
