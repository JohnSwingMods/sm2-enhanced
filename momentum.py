"""Momentum all'atterraggio (idea di John): uscendo da uno swing o atterrando da un salto Spidey tiene un po' della
velocità che aveva in aria e rallenta piano fino alla sua corsa normale.

Il gioco a terra non ha una "velocità di corsa" da cambiare: la corsa la muove l'animazione (nessun RUN_SPEED tra i
parametri di Spidey, vedi crea_codici_db / 8028Dxxx) e atterrando la velocità scende subito a quella della corsa.
Allora la spinta la do io: a ogni aggiornamento della camera (il programma della camera gira a ogni fotogramma del
gioco, prima che il gioco muova Spidey) sposto la sua posizione di direzione * e * dt. La posizione VERA è quella della
matrice [[camera+0x164]+0xC] (+0x30; ITA 0x80ACF6E0): la matrice disegnata [[camera+0x164]+0x30] e le copie (es.
v["spidey"]) il gioco le riscrive da lì a ogni fotogramma (provato: scrivendo lì Spidey non si sposta). Il gioco poi lo
muove da lì con le sue collisioni.

- In aria (stato 3 swing, 4 caduta, 5 salto): velocità orizzontale misurata dagli spostamenti (dt dal contatore video),
  ammorbidita (V_aria); un calo improvviso sotto metà per un solo giro non conta (atterrando il gioco ferma Spidey per
  un fotogramma quando lo stato è ancora 5).
- Atterrando (stato 1 subito dopo l'aria): velocità voluta S = |V_aria| (max CAP), direzione = V_aria (John: forte come
  il momentum sui muri; la prima versione "V_aria - corsa" si notava appena).
- A terra con S > 0: spinta e = S - g, dove g = quanto lo muove il gioco da solo (velocità vera - spinta, ammorbidita:
  atterrando l'animazione quasi lo ferma, poi corre a ~8) -> la velocità vera resta S. S resta tutta per H_tieni, poi
  cala verso g (la corsa, o 0 se Spidey si ferma) con tau lenta (levetta tenuta, stessa direzione) o veloce (levetta lasciata o girato indietro);
  vicino alla corsa finisce. La direzione segue piano quella di Spidey (levetta). Contro un muro (velocità vera lungo la
  direzione < metà della spinta, dopo T_CONTROLLO) finisce subito. Qualsiasi altro stato (muri, palo, combattimenti
  speciali, filmati) = finisce.
- Acceso solo se il codice "$Landing momentum" scrive 1 in 817F07E0 (lo azzero io a ogni giro: codice spento = dopo
  20 giri niente, anche partendo da uno stato salvato col byte a 1).

Memoria 817F0700-07FF (libera: la camera usa 0100-05FF, l'HUD 0600-067F). Routine a MOMENTUM (dopo le costanti delle
camere 3800-3A4F, prima dei sensori di prova a 4000), scritta dal codice AR del programma della camera."""
import ppcasm as asm

# MESSO DA PARTE (John, 2026-10-09: "non mi convince tanto, ci sono diversi problemi"): fuori dall'app, dal programma
# della camera e dagli INI. Per riprenderlo: ATTIVO = True (torna la voce in Codici e la chiamata nel programma della
# camera), poi crea_codici_db.py + allinea_camera sugli INI (prove_gioco/mom_rigenera.sh) e rebuild dell'exe.
ATTIVO = True
# RIPRESO (John, 2026-10-10: "lo vorrei riprendere, prima mentre correva faceva un effetto strano, forse correva troppo
# veloce") come codice A SÉ (come il tuffo): routine in memoria scritta dal suo codice AR + un aggancio Gecko suo
# all'inizio dell'aggiornamento della camera del gioco (0x801A0B70, subito dopo quello del tuffo): va con qualsiasi
# camera, anche senza il codice Camera. Velocità più bassa: al massimo CAP 24 m/s (prima 50: a 35-40 m/s con
# l'animazione della corsa a 8 sembrava che pattinasse), tutta per 0,35 s, poi cala in ~1 s.
NEL_PROGRAMMA = False  # la vecchia chiamata dal programma della camera (cam_ps4): non più usata
AGGANCIO = 0x801A0B70  # li r4, 0 (r3 vivo: il gioco lo sta preparando; r0, r4-r12, f0-f13 liberi; LR già salvato)
ORIGINALE = 0x38800000

MOMENTUM = 0x817F3B00
BASE = 0x817F0000
FLAG = 0x7E0  # byte scritto a 1 dal codice "$Landing momentum"
NOME = "$Landing momentum (keep some swing speed when you land)"
NOME_AGGANCIO = "$Landing momentum hook (needed by Landing momentum)"
VECCHI = ["$Landing momentum (keep some swing speed when you land, needs the camera code)"]
RIGHE_CODICE = ["017F07E0 00000001"]  # (vecchio: il flag ora lo scrive l'aggancio)

# costanti (offset da 817F0000): nome, valore
K = {0x780: ("dt_vi", 1 / 60), 0x784: ("CORSA", 8.5), 0x788: ("CAP", 24.0), 0x78C: ("alfa_aria", 0.5),
     0x790: ("sterzo", 3.0), 0x794: ("inv_tau_lenta", 1 / 1.0), 0x798: ("inv_tau_veloce", 1 / 0.2),
     0x79C: ("E_MIN", 0.4), 0x7A0: ("levetta_min", 0.3), 0x7A4: ("mezzo", 0.5), 0x7A8: ("T_CONTROLLO", 0.25),
     0x7AC: ("uno", 1.0), 0x7B0: ("zero", 0.0), 0x7B4: ("dot_min", 0.3), 0x7B8: ("unoemezzo", 1.5),
     0x7BC: ("piccolo", 0.01), 0x7C0: ("un_quarto", 0.25), 0x7C4: ("H_tieni", 0.35), 0x7C8: ("G0", 4.0),
     0x7CC: ("G_MAX", 12.0), 0x7D0: ("alfa_g", 0.3)}
# variabili: 700/704 posizione prima (x, z), 708/70C V_aria, 710/714 direzione, 718 e (spinta), 71C tempo da terra,
# 728 S (velocità voluta, 0 = niente), 72C g (quanto lo muove il gioco da solo),
# 720 contatore video prima, 724 in aria (byte), 725 acceso (contatore), 726 posizione prima valida, 727 calo scartato


def _rsqrt(x, y, t):  # y = 1/sqrt(x) (stima + un passo di Newton), t = appoggio
    return f"""
    frsqrte {y}, {x}
    fmuls {t}, {y}, {y}
    fmuls {t}, {t}, {x}
    lfs f0, 0x7A4(r12)
    fmuls {t}, {t}, f0
    lfs f0, 0x7B8(r12)
    fsubs {t}, f0, {t}
    fmuls {y}, {y}, {t}
"""


def routine(v):
    """Funzione (r31 = oggetto camera, r12 qualsiasi; usa r0, r8-r12, f0-f13; torna con blr)."""
    vi = v["vi"]
    hi = lambda a: (a + 0x8000) >> 16 & 0xFFFF  # noqa: E731
    lo = lambda a: a & 0xFFFF  # noqa: E731
    return f"""
    lis r12, 0x817F
    lbz r9, {FLAG:#x}(r12)
    li r0, 0
    stb r0, {FLAG:#x}(r12)
    lbz r10, 0x725(r12)
    cmpwi r9, 0
    beq m_nouno
    li r10, 20
    b m_conta
m_nouno:
    cmpwi r10, 0
    beq m_spento
    addi r10, r10, -1
m_conta:
    stb r10, 0x725(r12)
    lwz r8, 0x164(r31)
    cmpwi r8, 0
    beq m_spento
    lwz r8, 0xC(r8)
    cmpwi r8, 0
    beq m_spento
    lis r11, {hi(vi):#x}
    lwz r11, {lo(vi):#x}(r11)
    lwz r10, 0x720(r12)
    stw r11, 0x720(r12)
    subf r11, r10, r11
    lbz r9, 0x726(r12)
    cmpwi r9, 0
    beq m_riparti
    cmpwi r11, 0
    ble m_fine
    cmpwi r11, 6
    bgt m_riparti
    xoris r11, r11, 0x8000
    stw r11, 0x7F4(r12)
    lis r11, 0x4330
    stw r11, 0x7F0(r12)
    lfd f12, 0x7F0(r12)
    lfd f13, 0x7D8(r12)
    fsub f12, f12, f13
    frsp f12, f12
    lfs f0, 0x780(r12)
    fmuls f12, f12, f0
    ; velocità orizzontale vera (spostamento da prima, spinta compresa)
    lfs f1, 0x30(r8)
    lfs f3, 0x38(r8)
    lfs f4, 0x700(r12)
    lfs f5, 0x704(r12)
    stfs f1, 0x700(r12)
    stfs f3, 0x704(r12)
    fsubs f4, f1, f4
    fsubs f5, f3, f5
    fdivs f4, f4, f12
    fdivs f5, f5, f12
    lis r9, 0x80AD
    lwz r0, 0x1A04(r9)
    cmpwi r0, 3
    beq m_aria
    cmpwi r0, 4
    beq m_aria
    cmpwi r0, 5
    beq m_aria
    cmpwi r0, 1
    bne m_zero
    lbz r9, 0x724(r12)
    cmpwi r9, 0
    beq m_terra
    ; appena atterrato: S (velocità voluta) = |V_aria| (max CAP), direzione = V_aria, g (corsa del gioco) = G0
    li r9, 0
    stb r9, 0x724(r12)
    lfs f6, 0x708(r12)
    lfs f7, 0x70C(r12)
    fmuls f8, f6, f6
    fmadds f8, f7, f7, f8
    lfs f0, 0x7AC(r12)
    fcmpu f8, f0
    blt m_zero
    {_rsqrt("f8", "f9", "f10")}
    fmuls f11, f8, f9
    lfs f0, 0x784(r12)
    lfs f1, 0x79C(r12)
    fadds f0, f0, f1
    fcmpu f11, f0
    ble m_zero
    lfs f0, 0x788(r12)
    fcmpu f11, f0
    ble m_cap
    fmr f11, f0
m_cap:
    fmuls f6, f6, f9
    fmuls f7, f7, f9
    stfs f6, 0x710(r12)
    stfs f7, 0x714(r12)
    stfs f11, 0x728(r12)
    lfs f0, 0x7C8(r12)
    stfs f0, 0x72C(r12)
    fsubs f0, f11, f0
    stfs f0, 0x718(r12)
    lfs f0, 0x7B0(r12)
    stfs f0, 0x71C(r12)
m_terra:
    lfs f13, 0x728(r12)
    lfs f0, 0x7B0(r12)
    fcmpu f13, f0
    ble m_fine
    lfs f10, 0x71C(r12)
    fadds f10, f10, f12
    stfs f10, 0x71C(r12)
    lfs f6, 0x710(r12)
    lfs f7, 0x714(r12)
    lfs f11, 0x718(r12)
    ; velocità vera lungo la direzione (spinta compresa)
    fmuls f8, f4, f6
    fmadds f8, f5, f7, f8
    ; contro un muro: velocità vera lungo la direzione < metà della spinta
    lfs f0, 0x7A8(r12)
    fcmpu f10, f0
    blt m_niente_muro
    lfs f0, 0x7A4(r12)
    fmuls f9, f11, f0
    fcmpu f8, f9
    blt m_zero
m_niente_muro:
    ; g = quanto lo muove il gioco da solo (velocità vera - spinta, tra 0 e G_MAX), ammorbidita: atterrando
    ; l'animazione quasi lo ferma, poi corre a ~8; la spinta è S - g, così la velocità vera resta S
    fsubs f9, f8, f11
    lfs f0, 0x7B0(r12)
    fcmpu f9, f0
    bge m_g1
    fmr f9, f0
m_g1:
    lfs f0, 0x7CC(r12)
    fcmpu f9, f0
    ble m_g2
    fmr f9, f0
m_g2:
    lfs f2, 0x72C(r12)
    fsubs f9, f9, f2
    lfs f0, 0x7D0(r12)
    fmadds f2, f9, f0, f2
    stfs f2, 0x72C(r12)
    ; la direzione segue piano quella di Spidey (avanti della matrice, orizzontale)
    lfs f8, 0x20(r8)
    lfs f9, 0x28(r8)
    fmuls f10, f8, f8
    fmadds f10, f9, f9, f10
    lfs f0, 0x7BC(r12)
    fcmpu f10, f0
    blt m_veloce
    {_rsqrt("f10", "f2", "f3")}
    fmuls f8, f8, f2
    fmuls f9, f9, f2
    fmuls f1, f8, f6
    fmadds f1, f9, f7, f1
    lfs f0, 0x790(r12)
    fmuls f3, f0, f12
    lfs f0, 0x7AC(r12)
    fcmpu f3, f0
    ble m_k
    fmr f3, f0
m_k:
    fsubs f10, f8, f6
    fmadds f6, f10, f3, f6
    fsubs f10, f9, f7
    fmadds f7, f10, f3, f7
    fmuls f10, f6, f6
    fmadds f10, f7, f7, f10
    lfs f0, 0x7BC(r12)
    fcmpu f10, f0
    blt m_zero
    {_rsqrt("f10", "f2", "f3")}
    fmuls f6, f6, f2
    fmuls f7, f7, f2
    stfs f6, 0x710(r12)
    stfs f7, 0x714(r12)
    ; girato indietro o levetta lasciata = cala in fretta; per i primi H secondi resta tutta; poi cala piano
    lfs f0, 0x7B4(r12)
    fcmpu f1, f0
    blt m_veloce
    lis r9, 0x80AD
    lfs f0, 0x19E4(r9)
    lfs f1, 0x7A0(r12)
    fcmpu f0, f1
    blt m_veloce
    lfs f1, 0x71C(r12)
    lfs f0, 0x7C4(r12)
    fcmpu f1, f0
    blt m_tieni
    lfs f0, 0x794(r12)
    b m_cala
m_tieni:
    lfs f0, 0x7B0(r12)
    b m_cala
m_veloce:
    lfs f0, 0x798(r12)
m_cala:
    fmuls f0, f0, f12
    lfs f1, 0x7AC(r12)
    fcmpu f0, f1
    ble m_c
    fmr f0, f1
m_c:
    ; S = g + (S - g) * (1 - x): cala verso quanto lo muove il gioco da solo (corsa ~8; levetta lasciata = 0: prima
    ; calava verso 8,5 e Spidey fermo scivolava)
    lfs f1, 0x72C(r12)
    fsubs f9, f13, f1
    fnmsubs f9, f9, f0, f9
    lfs f0, 0x79C(r12)
    fcmpu f9, f0
    blt m_zero
    fadds f13, f9, f1
    stfs f13, 0x728(r12)
    ; spinta e = S - g (mai negativa)
    lfs f2, 0x72C(r12)
    fsubs f11, f13, f2
    lfs f0, 0x7B0(r12)
    fcmpu f11, f0
    bge m_e
    fmr f11, f0
m_e:
    stfs f11, 0x718(r12)
    ; spinta: posizione += direzione * e * dt
    fmuls f10, f11, f12
    lfs f1, 0x30(r8)
    fmadds f1, f6, f10, f1
    stfs f1, 0x30(r8)
    lfs f3, 0x38(r8)
    fmadds f3, f7, f10, f3
    stfs f3, 0x38(r8)
    b m_fine
m_aria:
    li r9, 1
    stb r9, 0x724(r12)
    ; un calo improvviso (|v| < metà di V_aria) per UN solo giro non conta: nel fotogramma dell'atterraggio il gioco
    ; ferma Spidey un attimo quando lo stato è ancora 5 (V_aria si dimezzava proprio prima di servire). Dal secondo
    ; giro di fila conta (rallentamento vero: in cima allo swing la velocità scende da 30 a 10)
    lfs f6, 0x708(r12)
    lfs f7, 0x70C(r12)
    fmuls f8, f6, f6
    fmadds f8, f7, f7, f8
    lfs f0, 0x7C0(r12)
    fmuls f8, f8, f0
    fmuls f9, f4, f4
    fmadds f9, f5, f5, f9
    li r9, 0
    fcmpu f9, f8
    bge m_aria_ok
    lbz r9, 0x727(r12)
    cmpwi r9, 0
    li r9, 1
    stb r9, 0x727(r12)
    beq m_zero_e
    li r9, 0
m_aria_ok:
    stb r9, 0x727(r12)
    lfs f0, 0x78C(r12)
    fsubs f10, f4, f6
    fmadds f6, f10, f0, f6
    stfs f6, 0x708(r12)
    fsubs f10, f5, f7
    fmadds f7, f10, f0, f7
    stfs f7, 0x70C(r12)
    b m_zero_e
m_riparti:
    li r9, 1
    stb r9, 0x726(r12)
    lfs f1, 0x30(r8)
    stfs f1, 0x700(r12)
    lfs f3, 0x38(r8)
    stfs f3, 0x704(r12)
m_zero:
    li r9, 0
    stb r9, 0x724(r12)
m_zero_e:
    lfs f0, 0x7B0(r12)
    stfs f0, 0x718(r12)
    stfs f0, 0x728(r12)
    b m_fine
m_spento:
    li r9, 0
    stb r9, 0x726(r12)
    stb r9, 0x724(r12)
    lfs f0, 0x7B0(r12)
    stfs f0, 0x718(r12)
    stfs f0, 0x728(r12)
m_fine:
    blr
"""


def parole(v):
    w = asm.assembla(routine(v), MOMENTUM)
    assert MOMENTUM + 4 * len(w) <= 0x817F4000, "routine del momentum troppo lunga (tocca i sensori di prova a 817F4000)"
    return w


def righe_ar(v):
    """Righe AR del codice "Landing momentum": costanti (+ il doppio 0x4330000080000000 per int -> float a 7D8, prima
    preso dalle costanti della camera) + routine, la sua prima parola per ultima (l'aggancio la chiama solo se c'è)."""
    righe = [asm.scrivi32(BASE + o, asm.f32(x)) for o, (_, x) in sorted(K.items())]
    righe += [asm.scrivi32(BASE + 0x7D8, 0x43300000), asm.scrivi32(BASE + 0x7DC, 0x80000000)]
    w = parole(v)
    return righe + [asm.scrivi32(MOMENTUM + 4 * k, w[k]) for k in range(1, len(w))] + [asm.scrivi32(MOMENTUM, w[0])]


def codice_gecko():
    """Aggancio (uguale nelle 5 versioni): flag acceso (817F07E0 = 1, la routine lo azzera) e chiamata con mtlr/blrl se
    la routine c'è. r3 resta com'è (il gioco lo usa subito dopo)."""
    h, lo = (MOMENTUM >> 16), MOMENTUM & 0xFFFF
    return asm.c2(AGGANCIO, asm.assembla(f"""
    lis r12, 0x817F
    li r0, 1
    stb r0, {FLAG:#x}(r12)
    lis r12, {h:#x}
    ori r12, r12, {lo:#x}
    lwz r0, 0(r12)
    cmpwi r0, 0
    beq salta
    mtlr r12
    blrl
salta:
    .word {ORIGINALE:#x}
"""))


CHIAMA = f"    chiama {MOMENTUM:#x}\n    lis r12, 0x817F"
