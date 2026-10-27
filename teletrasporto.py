"""TELETRASPORTO (idea di John, 2026-10-18: menu in gioco > Mondo, "teletrasportarmi dove voglio, anche sopra un palazzo").

Come si sposta Spider-Man (provato su ITA, dolphin_z): la posizione vera sta in DUE matrici dell'oggetto di Spidey
(oggetto = [[camera]+0x164], fisso 0x80ACAEE0): [oggetto+0xC]+0x30 (quella che il gioco disegna) e [oggetto+0xB0]+0x30
(la sorgente della fisica: scrivendo solo la prima si spostava di metà strada e poi tornava indietro). Scritte tutte e
due = si sposta dove vuoi, anche a 600 m; la città intorno la carica il gioco da solo (per ~1,5 s Spidey resta sospeso
in stato 1 finché arriva il pavimento). Danno da caduta: il gioco lo calcola dal punto più alto del salto
(Spidey +0x1C44 = 0x80AD1D84): tenendolo uguale all'altezza attuale mentre cade non si fa niente (da 500 m senza = morto).

Punto della mappa: con la mappa del gioco aperta (byte ITA 0x8056B96C / USA 0x8056B8EC = 80) la copia della posizione di
Spidey (ITA 0x80495FEC / USA 0x80495F4C) diventa il CENTRO della mappa (y = quota della telecamera della mappa, 500 o
2000): l'app se lo ricorda e poi ci porta Spidey.

Sopra i palazzi: un raggio del gioco (le stesse funzioni della camera moderna: prepara/lancia/chiudi) dall'alto verso il
basso dice dov'è il tetto. Lo lancia una routine in memoria (scritta dal codice AR "$Teleport helper", ROUTINE) chiamata
da un aggancio Gecko all'inizio dell'aggiornamento della camera del gioco (0x801A0B74, dopo tuffo/momentum, prima dello
zip; lì r31 = oggetto camera), solo quando l'app lo chiede (RICHIESTA = 1): l'app scrive da/a, legge l'esito (2 = tetto
trovato, punto in PUNTO; 3 = niente, es. acqua o città non ancora caricata = riprova). Niente tetto dopo qualche
tentativo = Spidey cade da 500 m (protetto dal danno).
"""
import ppcasm as asm
import cam_ps4

NOME = "$Teleport helper (needed by the in-game menu)"
NOME_AGGANCIO = "$Teleport hook (needed by the in-game menu)"
AGGANCIO = 0x801A0B74  # addi r3, r3, ... (camera voluta: ITA 0x804BD364, USA/UK/DE/FR 0x804BD2E4)
ORIGINALE = {"GK2I52": 0x3863D364}  # le altre: 0x3863D2E4
ROUTINE = 0x817FE000
# dati (memoria a zero a ogni avvio): richiesta/esito, da, a, punto colpito, struttura del raggio (0x64 byte)
RICHIESTA = 0x817FF130  # byte: 1 = lancia, 2 = colpito, 3 = niente
DA = 0x817FF134
A = 0x817FF140
PUNTO = 0x817FF150
S = 0x817FF180  # fino a 0x817FF1E4 (la memoria è a zero fino a 0x817FF220)
B = 0x81800000  # base per gli offset (tutti negativi)

# indirizzi per versione (ITA / le altre, stesso programma USA)
# byte = 80 con la mappa grande aperta (qualsiasi scheda), 10 no; le altre 0x8056B8EC (camera_slider.MAPPA_APERTA).
# Chiudere la mappa: i tasti finti in memoria (0x805546A0 / 0x80554670 o nella lettura 0x802CAFD8) NON bastano, il menu
# della mappa legge il controller vero -> l'app preme F14, aggiunto a X nel profilo del pad (app_controller.TASTO_MAPPA).
MAPPA_APERTA = {"GK2I52": 0x8056B96C}
CENTRO_MAPPA = {"GK2I52": 0x80495FEC}  # copia della posizione di Spidey = centro della mappa; le altre 0x80495F4C
CAMERA = {"GK2I52": 0x8056D604}  # puntatore all'oggetto camera; le altre 0x8056D584
TOP = 0x80AD1D84  # punto più alto del salto (danno da caduta)
STATO = 0x80AD1A04
QUOTA = 500.0  # da qui si cade se il raggio non trova niente (sopra tutti i palazzi: è la quota della mappa)


def per(diz, gid, altro):
    return diz.get(gid, altro)


def mappa_aperta(gid):
    return per(MAPPA_APERTA, gid, 0x8056B8EC)


def centro_mappa(gid):
    return per(CENTRO_MAPPA, gid, 0x80495F4C)


def camera(gid):
    return per(CAMERA, gid, 0x8056D584)


def _o(a):  # offset da B (0x81800000)
    return a - B


def routine(gid):
    v = cam_ps4.VERSIONI[gid]
    prep, lancia, chiudi = v["raggio"]
    g = v["raggio_g"]
    copia = "".join(f"    stfs {r}, {o:#x}(r9)\n    stfs {r}, {o + 0x40:#x}(r9)\n"
                    for r, o in (("f8", 0), ("f9", 4), ("f12", 8), ("f1", 0xC), ("f2", 0x10), ("f3", 0x14)))
    return f"""    lis r12, 0x8180
    lbz r11, {_o(RICHIESTA)}(r12)
    cmpwi r11, 1
    beq sonda
    blr
sonda:
    mflr r0
    stw r0, 4(r1)
    stwu r1, -0x20(r1)
    addi r9, r12, {_o(S)}
    lfs f8, {_o(DA)}(r12)
    lfs f9, {_o(DA) + 4}(r12)
    lfs f12, {_o(DA) + 8}(r12)
    lfs f1, {_o(A)}(r12)
    lfs f2, {_o(A) + 4}(r12)
    lfs f3, {_o(A) + 8}(r12)
{copia}    li r11, 0
    stw r11, 0x30(r9)
    stb r11, 0x34(r9)
    addi r3, r9, 0x40
    addi r4, r9, 0x4C
    lwz r5, 0xA70(r31)
    lis r6, {g >> 16:#x}
    ori r6, r6, {g & 0xFFFF:#x}
    chiama {prep:#x}
    lis r12, 0x8180
    stw r3, {_o(S) + 0x60}(r12)
    addi r4, r12, {_o(S)}
    li r5, 0
    li r6, 0
    li r7, 0
    chiama {lancia:#x}
    lis r12, 0x8180
    addi r3, r12, {_o(S) + 0x60}
    chiama {chiudi:#x}
    lis r12, 0x8180
    li r10, 3
    lbz r11, {_o(S) + 0x34}(r12)
    cmpwi r11, 0
    beq sonda_fine
    lfs f0, {_o(S) + 0x18}(r12)
    stfs f0, {_o(PUNTO)}(r12)
    lfs f0, {_o(S) + 0x1C}(r12)
    stfs f0, {_o(PUNTO) + 4}(r12)
    lfs f0, {_o(S) + 0x20}(r12)
    stfs f0, {_o(PUNTO) + 8}(r12)
    li r10, 2
sonda_fine:
    stb r10, {_o(RICHIESTA)}(r12)
    addi r1, r1, 0x20
    lwz r0, 4(r1)
    mtlr r0
    blr
"""


def parole(gid):
    return asm.assembla(routine(gid), base=ROUTINE)


def righe_ar(gid):
    """Codice AR: scrive la routine (la prima parola per ultima: l'aggancio la chiama solo se c'è) e il programma della vista
    3D (programma_3d, stessa regola: l'app lo usa solo se la sua prima parola c'è)."""
    righe = []
    for base, w in ((ROUTINE, parole(gid)), (EST_PROG, programma_3d(gid))):
        righe += [asm.scrivi32(base + 4 * k, w[k]) for k in range(1, len(w))] + [asm.scrivi32(base, w[0])]
    return righe


# VISTA 3D DELLA CITTÀ (mappa3d.py): la mappa del gioco costruisce la vista (funzione 0x802293xx: entità camera ->
# lookAt 0x8022F5A4 / 0x8022F70C, r4 = occhio = posizione dell'entità, r5 = bersaglio = occhio + riga avanti, r6 = su =
# riga +0x10) da una matrice che la mappa rifà con la DESTRA FISSA scelta aprendo la mappa: girando la telecamera di 180°
# la città veniva sottosopra, di 90° guardava in giù di traverso. Due C2 sulle due chiamate (addi r5, r1, 8, dopo mr r6,
# r29): se SU3D_ATTIVA = 1 (lo mette l'app solo nella vista 3D) su = SU3D_VETTORE (0, 1, 0) e bersaglio = SU3D_BERSAGLIO,
# scritti dall'app. r12 è libero prima di una chiamata. Stessi indirizzi in tutte le versioni (verificato ITA e USA).
SU3D_ATTIVA = 0x817FF1F4  # 0 = niente, 1 = su + bersaglio, 2 = in più occhio e bersaglio calcolati DAL GIOCO (EST)
SU3D_VETTORE = 0x817FF1F8  # 3 float
SU3D_BERSAGLIO = 0x817FF204  # 3 float (la memoria è a zero fino a 0x817FF220)
AGGANCI_3D = (0x8022940C, 0x80229450)  # addi r5, r1, 8 (38A10008), subito prima delle due chiamate
ORIGINALE_3D = 0x38A10008
# MOVIMENTO CALCOLATO DAL GIOCO (modo 2; John: "trema tutto"): l'app scriveva la telecamera col suo orologio, ma con la mappa
# il gioco disegna 19-40 fotogrammi al secondo a 1 o 2 scatti del contatore video l'uno e legge la telecamera in momenti
# irregolari (misurato: 0-15 ms dopo lo scatto) = passi diversi da un fotogramma all'altro. Ora l'app scrive a ogni scatto
# n0 lo stato (occhio E0, bersaglio T0) e quanto cambia in uno scatto (VE, VT); il gioco, quando costruisce la vista, prende
# k = contatore - n0 (0..EST_KMAX) e usa E0 + k VE / T0 + k VT: ogni fotogramma si muove in proporzione al tempo del gioco,
# comunque cadano le letture. Due copie (EST + 0, EST + 0x40) e la parola EST + 0x80 dice quale vale (scritta per ultima).
# Il calcolo sta in memoria (programma_3d, scritto dal codice AR del teletrasporto): nel Gecko solo la chiamata (spazio).
EST_PROG = 0x817FE400  # (la routine del raggio finisce a 0x817FE120)
EST = 0x817FE800  # copia: +0 E0, +0xC T0, +0x18 VE, +0x24 VT (3 float ciascuno), +0x30 n0; +0x80 copia valida (0/0x40);
EST_USCITA = EST + 0x90  # occhio (3 float) e bersaglio (+0xC) passati al lookAt (memoria a zero fino a 0x817FF0FF)
EST_KMAX = 6


def _hl(x):
    return (x + 0x8000) >> 16, x - ((x + 0x8000) >> 16 << 16)


def programma_3d(gid):
    """Chiamato (blrl) dagli agganci col modo 2: r4 = occhio, r5 = bersaglio calcolati per adesso. Usa r0, r10-r12, f1-f12
    (prima di una chiamata sono liberi)."""
    he, le = _hl(EST)
    hv, lv = _hl(cam_ps4.VERSIONI[gid]["vi"])
    carica = "\n".join(f"    lfs f{1 + i}, {4 * i:#x}(r11)" for i in range(12))
    somma = "\n".join(f"    fadds f{1 + i}, f{1 + i}, f{7 + i}" for i in range(6))
    salva = "\n".join(f"    stfs f{1 + i}, {0x90 + 4 * i:#x}(r12)" for i in range(6))
    return asm.assembla(f"""
    lis r12, {he:#x}
    addi r12, r12, {le}
    lwz r11, 0x80(r12)
    add r11, r11, r12
    lis r10, {hv:#x}
    lwz r10, {lv}(r10)
    lwz r0, 0x30(r11)
    subf r10, r0, r10
    cmpwi r10, 0
    bge sopra
    li r10, 0
sopra:
    cmpwi r10, {EST_KMAX}
    ble entro
    li r10, {EST_KMAX}
entro:
{carica}
giro:
    cmpwi r10, 0
    ble fatto
{somma}
    addi r10, r10, -1
    b giro
fatto:
{salva}
    addi r4, r12, 0x60  ; (dopo l'aggancio il gioco fa addi r4, r4, 0x30: la sua entità ha l'occhio a +0x30)
    addi r5, r12, 0x9C
    blr
""", base=EST_PROG)


def codice_su3d():
    (ha, la), (hs, ls), (hb, lb), (hp, lp) = _hl(SU3D_ATTIVA), _hl(SU3D_VETTORE), _hl(SU3D_BERSAGLIO), _hl(EST_PROG)
    righe = []
    for a in AGGANCI_3D:
        righe += asm.c2(a, asm.assembla(f"""
    addi r5, r1, 8
    lis r12, {ha:#x}
    lwz r12, {la}(r12)
    cmpwi r12, 1
    blt fine
    lis r6, {hs:#x}
    addi r6, r6, {ls}
    lis r5, {hb:#x}
    addi r5, r5, {lb}
    beq fine
    lis r12, {hp:#x}
    addi r12, r12, {lp}
    mtlr r12
    blrl
fine:
"""))
    return righe


def su3d_versione(dme, gid):
    """Vista 3D nel gioco adesso: 0 = agganci del "su" assenti (gioco avviato prima), 1 = solo su e bersaglio (agganci
    vecchi o programma in memoria mancante), 2 = col movimento calcolato dal gioco (agganci nuovi + programma_3d)."""
    if any(dme.read_word(a) == ORIGINALE_3D for a in AGGANCI_3D):
        return 0
    corpo = codice_su3d()
    n = int(corpo[0].split()[1], 16)
    firma = bytes.fromhex("".join(r.replace(" ", "") for r in corpo[1:1 + n]))[:-8]
    if firma not in dme.read_bytes(0x80001800, 0x1800):
        return 1
    prog = programma_3d(gid)  # tutto il programma (la sola prima parola, "lis r12", è uguale in ogni sua versione)
    return 2 if dme.read_bytes(EST_PROG, 4 * len(prog)) == b"".join(w.to_bytes(4, "big") for w in prog) else 1


def codice_gecko(gid):
    """Aggancio: chiama la routine (mtlr/blrl) se c'è, poi rifà r3 (lis + l'istruzione originale) e r4 = 0 (il gioco li
    usa subito dopo: memset della camera voluta), perché le funzioni del raggio li sporcano. In più i due agganci del "su"
    della vista 3D della città (codice_su3d)."""
    return _codice_gecko(gid) + codice_su3d()


def _codice_gecko(gid):
    h, lo = ROUTINE >> 16, ROUTINE & 0xFFFF
    return asm.c2(AGGANCIO, asm.assembla(f"""
    lis r12, {h:#x}
    ori r12, r12, {lo:#x}
    lwz r0, 0(r12)
    cmpwi r0, 0
    beq salta
    mtlr r12
    blrl
salta:
    lis r3, 0x804C
    .word {per(ORIGINALE, gid, 0x3863D2E4):#x}
    li r4, 0
"""))


if __name__ == "__main__":
    for g in ("GK2I52", "GK2E52"):
        print(g, len(parole(g)), "istruzioni;", len(codice_gecko(g)), "righe Gecko")
    print("\n".join(codice_gecko("GK2I52")))
