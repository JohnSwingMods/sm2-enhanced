"""TUFFO CON L3 come codice a sé (John, 2026-10-10: "lo vorrei anche per chi spegne il codice della camera").

Prima il tuffo a comando (cam_ps4._tuffo_comando, 22y-22ac) girava dentro il programma della camera: spenta la camera,
niente tuffo. Ora è un codice Gecko suo con un solo aggancio all'inizio dell'aggiornamento della camera del GIOCO
(0x801A0B6C, stesso indirizzo in tutte e 5 le versioni: lì r31 = oggetto camera, LR e registri da r20 in su già
salvati, f1 (dt) già copiato in f28, r3-r5 stanno per essere riscritti dal gioco): gira a ogni fotogramma con
qualsiasi camera, anche l'originale senza codici.

Cosa fa (uguale a prima): sul fronte di L3 (freccia giù senza Z: nel profilo del pad L3 = D-Pad/Down) mette una
RICHIESTA (817F05D7) che resta finché Spidey è in aria; stato 5 (in aria libera) = tuffo subito; stato 4 (corsa giù
dal bordo, fine della corsa sul muro) = solo se non è già un tuffo comandato, sta scendendo e non è già a testa in giù.
LOCK SUI NEMICI (John, 2026-10-14: L3/R3 = freccia giù = anche il lock): la richiesta aspetta ATTESA_LOCK giri e si
annulla se il gioco chiede o usa la camera del lock (modalità 3): vicino ai nemici L3 in aria fa il lock e non il tuffo.
Il tuffo = stato 4 + animazione DIVE_FALL fatta partire per nome (come il gioco a 0x8012BC4C). Le variabili sono le
stesse di prima (817F05D4-05D7): la camera della picchiata (cam_ps4) le legge se il codice della camera è acceso.
La discesa nello stato 4 la misura da sé (posizione vera di Spidey [[camera+0x164]+0xC]+0x34, ammorbidita in
817F0568; prima usava 817F05C4 del programma della camera).
"""
import ppcasm as asm
import cam_ps4

NOME = "$L3 to dive (anywhere in the air)"
AGGANCIO = 0x801A0B6C
ORIGINALE = 0x3C60804C  # lis r3, -0x7FB4 (uguale nelle 5 versioni: controllato su main.dol)
ATTESA_LOCK = 2  # giri di attesa prima del tuffo: se intanto parte il lock sui nemici (stesso tasto) niente tuffo


def _routine(v):
    pulisci, crea, anima, libera, nome, cost = v["tuffo"]
    pad = v["tasti"]
    pulizie = "".join(f"""    mr r3, r30
    li r4, {k:#x}
    chiama {pulisci:#x}
""" for k in (2, 0xA, 3))
    zeri = "".join(f"    stb r0, {o:#x}(r30)\n" for o in (0x1F03, 0x1ED1, 0x1EFC, 0x1EF9, 0x1EFA, 0x1EFB, 0x1F1E))
    return f"""    bl tuffo
    b fine
tuffo:
    mflr r0
    stw r0, 4(r1)
    stwu r1, -0x40(r1)
    stw r30, 0x38(r1)
    stw r29, 0x34(r1)
    bl dopo_k
    .float 0.0
    .float 0.1
    .float 0.3
dopo_k:
    mflr r29
    lis r12, 0x817F
    ; discesa ammorbidita (817F0568) dalla posizione vera di Spidey (817F0564 = altezza del giro prima)
    lwz r9, 0x164(r31)
    cmpwi r9, 0
    bge tc_dy_fatto
    lwz r9, 0xC(r9)
    cmpwi r9, 0
    bge tc_dy_fatto
    lfs f0, 0x34(r9)
    lfs f1, 0x564(r12)
    stfs f0, 0x564(r12)
    fsubs f0, f0, f1
    lfs f1, 0x568(r12)
    fsubs f0, f0, f1
    lfs f2, 4(r29)
    fmadds f1, f0, f2, f1
    stfs f1, 0x568(r12)
tc_dy_fatto:
    lis r11, {pad >> 16:#x}
    ori r11, r11, {pad & 0xFFFF:#x}
    lhz r11, 0(r11)
    andi. r11, r11, 0x14
    li r10, 0
    cmpwi r11, 4
    bne tc_lt
    li r10, 1
tc_lt:
    lbz r9, 0x5D5(r12)
    stb r10, 0x5D5(r12)
    cmpwi r10, 1
    bne tc_richiesta
    cmpwi r9, 0
    bne tc_richiesta
    li r10, {ATTESA_LOCK + 1}
    stb r10, 0x5D7(r12)
tc_richiesta:
    lis r30, 0x80AD
    ori r30, r30, 0x140
    lwz r0, 0x18C4(r30)
    ; fuori dallo stato 4 il tuffo non è più "comandato" (817F05D6, e l'aggancio della picchiata 05D4): lo faceva solo
    ; il programma della camera, senza camera restava a 1 e i tuffi dallo stato 4 non partivano più
    cmpwi r0, 4
    beq tc_comandato_ok
    li r9, 0
    stb r9, 0x5D6(r12)
    cmpwi r0, 5  ; (l'aggancio della picchiata resta anche nelle cadute a testa in giù: vedi cam_ps4 posa_vera)
    beq tc_comandato_ok
    stb r9, 0x5D4(r12)
tc_comandato_ok:
    cmpwi r0, 5
    beq tc_aria
    cmpwi r0, 4
    bne tc_annulla
    lbz r9, 0x5D6(r12)
    cmpwi r9, 0
    bne tc_annulla
    lfs f0, 0x568(r12)
    lfs f1, 0(r29)
    fcmpu f0, f1
    bge tc_fine
    lwz r9, 0x164(r31)
    cmpwi r9, 0
    bge tc_fine
    lwz r9, 0x134(r9)
    cmpwi r9, 0
    bge tc_fine
    lfs f0, 4(r9)
    lfs f1, 8(r29)
    fcmpu f0, f1
    bge tc_fine
tc_aria:
    lbz r9, 0x5D7(r12)
    cmpwi r9, 0
    beq tc_fine
    ; L3 è anche il LOCK sui nemici (freccia giù): se il gioco ha chiesto o usa la camera del lock (modalità 3 =
    ; elenco +0x1F8; richiesta a +0x230, attuale a +0x22C) niente tuffo. Il lock lo decide il gioco DOPO questo punto
    ; (aggiornamento di Spidey) -> la richiesta aspetta ATTESA_LOCK giri prima di tuffarsi
    lwz r10, 0x1F8(r31)
    lwz r11, 0x230(r31)
    cmpw r10, r11
    beq tc_annulla
    lwz r11, 0x22C(r31)
    cmpw r10, r11
    beq tc_annulla
    addi r9, r9, -1
    stb r9, 0x5D7(r12)
    cmpwi r9, 0
    bne tc_fine
    li r9, 0
    stb r9, 0x5D7(r12)
    stb r9, 0x5D4(r12)
    stw r0, 0x18C0(r30)
    li r0, 4
    stw r0, 0x18C4(r30)
    li r0, 1
    stb r0, 0x5D6(r12)
{pulizie}    lis r9, {(cost + 0x8000) >> 16:#x}
    lfs f0, {cost & 0xFFFF:#x}(r9)
    stfs f0, 0x1B0C(r30)
    stfs f0, 0x1B08(r30)
    li r0, 0
{zeri}    addi r3, r1, 0x20
    lis r4, {(nome + 0x8000) >> 16:#x}
    addi r4, r4, {nome & 0xFFFF:#x}
    li r5, -1
    chiama {crea:#x}
    li r0, 1
    stw r0, 8(r1)
    mr r3, r30
    addi r4, r1, 0x20
    li r5, 2
    li r6, 0xA01
    li r7, 0
    li r8, 0
    li r9, 0
    li r10, 0
    chiama {anima:#x}
    addi r3, r1, 0x20
    li r4, 2
    chiama {libera:#x}
    b tc_fine
tc_annulla:
    lis r12, 0x817F
    li r9, 0
    stb r9, 0x5D7(r12)
tc_fine:
    lwz r29, 0x34(r1)
    lwz r30, 0x38(r1)
    lwz r0, 0x44(r1)
    addi r1, r1, 0x40
    mtlr r0
    blr
fine:
    .word {ORIGINALE:#x}
"""


def codice(ver="GK2I52"):
    """Righe Gecko (senza il nome): un C2 all'inizio dell'aggiornamento della camera del gioco + il C2 di R3 che non fa il
    lock (cam_ps4.CROCE_GIU). Quello sta ANCHE nel codice della camera: chi spegne il tuffo lo tiene con la camera, e il
    pack gratuito (camera classica AR, senza il Gecko della camera) lo tiene col tuffo. Accesi tutti e due = due C2
    identici sullo stesso punto: vince l'ultimo, il risultato è lo stesso. (La corsa sul muro che tiene la velocità dopo
    il tuffo è in muro.py, pezzo di "Momentum pieno sui muri".)"""
    v = cam_ps4.VERSIONI[ver]
    return asm.c2(AGGANCIO, asm.assembla(_routine(v))) + asm.c2(v["croce_giu"], asm.assembla(cam_ps4.CROCE_GIU))


if __name__ == "__main__":
    for g in ("GK2I52", "GK2E52"):
        print(g, len(codice(g)) * 8, "byte Gecko")
