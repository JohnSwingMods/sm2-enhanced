"""CORSA SUL MURO CHE TIENE LA VELOCITÀ (pezzo nascosto di "Momentum pieno sui muri", codici_db "muro_aggancio").

L'inizio della corsa sul muro (0x8014C7D4) tiene la velocità che avevi (velocità del corpo fisico, almeno
WALLSPRINT_INITIAL_VELOCITY 14,4) solo se lo stato di prima (+0x18C0, uguale allo stato del fotogramma prima) è 5 (in aria)
o 3 (swing); con gli altri riparte da 14,4. John:
- "faccio il tuffo con L3, corro su un muro durante l'animazione e si perde tutto il momentum" (tuffo = stato 4);
- "esco dalla corsa sul muro in modo naturale quando finisce il muro e nello stesso salto atterro in un'altra corsa sul
  muro: la seconda perde tutto il momentum" (fine della corsa = stato 4, avvitamento WALLSPRINT_FALL).
Qui ogni stato da 0 a 5 conta come 5: la corsa parte da max(velocità che avevi, 14,4) -> mai più lenta di prima (da terra
o attaccato al muro la velocità è sotto 14,4: uguale a prima). Restano com'erano 6 (corsa sul muro), 7, 8 (palo).
Prima (22am) era nel codice del tuffo e valeva solo durante un tuffo comandato. Stesso indirizzo nelle 5 versioni.

CORSA SUL MURO DI FILA (John: "finisce il muro, voglio fare un'altra corsa sul muro e molte volte non la attiva: si attacca
al muro come premendo B"): la corsa sul muro parte solo se il tempo da quando è finita l'ultima (+0x1E38) supera una soglia
(+0x1E48, NO_WALLSPRINT_TIMEOUT_INTERVAL). Il gioco la mette a 0,7 s quando la corsa finisce con l'avvitamento
(0x8014DFD0) e in un altro caso di uscita dal muro (0x8014D95C): entro 0,7 s niente corsa, solo l'aggancio al muro (stato
2). Qui in quei due punti la soglia diventa SOGLIA (0,1 s). Stessi indirizzi nelle 5 versioni (cambia solo la costante
del gioco, che non uso: la mia sta nel codice; r9 era la base delle costanti, libero; CR e LR non servono più lì).
"""
import ppcasm as asm

MURO = 0x8014C80C  # cmpwi r10, 5 (r9 libero: riscritto dopo la bl che segue; il CR lo usa il beq a 0x8014C818)
MURO_ORIGINALE = 0x2C0A0005
NOME = "$Wallsprint momentum hook (needed by Wallsprint keeps all swing momentum)"
SOGLIA_PUNTI = (0x8014DFD0, 0x8014D95C)  # stfs f0, 0x1e48(r31)
SOGLIA = 0.1
# NIENTE VELOCITÀ IN PIÙ DURANTE LA CORSA (John: "correndo sui muri a volte acquisisco ancora più velocità di quella con
# cui sono entrato"): a ogni fotogramma (0x8014EB80) il gioco prende la velocità lungo il muro, la taglia a
# WALLSPRINT_VELOCITY_CAP (+0x1E40; col "Momentum pieno sui muri" 999 = niente tetto) e toglie DAMPENING * dt (col
# "Corsa sui muri infinita" 0, e anche la gravità del muro 0): niente la frena e le spinte (levetta, discesa) si sommano.
# Qui la velocità d'ingresso (0x8014C93C riceve in f1 la velocità di partenza) va in 817F055C e diventa il tetto della
# corsa (0x8014EC1C: tetto = min(+0x1E40, ingresso); ingresso < 1 = non scritto, es. stato salvato = tetto del gioco).
# Ma la "velocità che avevi" contava anche la CADUTA: cadendo forte (dopo la fine di una corsa, un tuffo) e partendo con la
# corsa VERSO L'ALTO, i 50-70 m/s di caduta diventavano velocità in salita (John: "più veloce di quando sono entrato").
# Qui: la velocità prima della corsa (0x8014C858: f1 vx, f0 vy, f12 vz) va in 817F0580; finito l'avvio della corsa
# (0x8014C894) se la corsa va IN SU (vy della corsa, Spidey +0x1DC4, > 0) e prima stavi cadendo, la sua velocità
# (+0x1DC0..C8) scende alla velocità orizzontale che avevi (almeno WALLSPRINT_INITIAL_VELOCITY +0x6F0); in giù la caduta
# resta (corri giù per il muro alla velocità della caduta, come prima).
VERTICALE = 0x8014C858
FINE_AVVIO = 0x8014C894  # addi r9, r31, 0x18c0 (r9, r12, f0-f13, LR, CR liberi: subito dopo una bl)
FINE_AVVIO_ORIGINALE = 0x393F18C0
INGRESSO = 0x8014C93C  # stwu r1, -0x38(r1) (inizio funzione: r12 libero)
INGRESSO_ORIGINALE = 0x9421FFC8
TETTO = 0x8014EC1C  # lfs f0, 0x1e40(r30) (dopo una bl: r12, f12, f13, LR e CR liberi)
# TETTO FISSO della corsa sul muro (John 2026-10-22: col momentum pieno sui muri e quello del web zip "l'esperienza è
# diventata troppo veloce"): oltre al tetto = velocità d'ingresso, mai più di CAP_MURO (m/s; la corsa normale parte da 14,4)
# 2026-10-23 John: 32 e 45 troppo poco ("quando swingo forte vado come un pazzo"): ora il tetto segue la velocità d'ingresso,
# un po' più bassa (x FATTORE_MURO, mai sotto la partenza normale +0x6F0), con CAP_MURO solo come sicurezza
FATTORE_MURO = 0.85
CAP_MURO = 80.0


def _soglia():
    return asm.assembla(f"""
    bl dopo
    .float {SOGLIA}
dopo:
    mflr r9
    lfs f0, 0(r9)
    stfs f0, 0x1e48(r31)
""")


def _ingresso():
    # la funzione la chiamano in 4 punti: solo i due dell'avvio della corsa (ritorno a 0x8014C87C / 0x8014C88C) scrivono il
    # tetto. Gli altri due (0x8014BEAC ricalcolo, 0x8014E4CC fine della sterzata) la richiamano a corsa avviata con la
    # velocità di ADESSO: il tetto scendeva e girando in giù la corsa non tornava più alla velocità d'ingresso.
    return asm.assembla(f"""
    mflr r12
    li32 r0, 0x8014C87C
    cmplw r12, r0
    beq ing_si
    li32 r0, 0x8014C88C
    cmplw r12, r0
    bne ing_no
ing_si:
    lis r12, 0x817F
    stfs f1, 0x55C(r12)
ing_no:
    .word {INGRESSO_ORIGINALE:#x}
""")


def _verticale():
    return asm.assembla("""
    lis r12, 0x817F
    stfs f1, 0x580(r12)
    stfs f0, 0x584(r12)
    stfs f12, 0x588(r12)
    fmuls f0, f0, f0
""")


def _fine_avvio():
    rs = lambda x, y: f"""    frsqrte {y}, {x}
    fmuls f10, {y}, {y}
    fmuls f10, f10, {x}
    lfs f9, 0(r12)
    fmuls f10, f10, f9
    lfs f9, 4(r12)
    fsubs f10, f9, f10
    fmuls {y}, {y}, f10
"""
    return asm.assembla(f"""
    bl dopo
    .float 0.5
    .float 1.5
dopo:
    mflr r12
    lis r9, 0x817F
    fsubs f11, f11, f11
    lfs f0, 0x1DC4(r31)
    fcmpu f0, f11
    ble fine
    lfs f2, 0x584(r9)
    fcmpu f2, f11
    bge fine
    ; orizzontale di prima (f5), almeno la velocità iniziale del gioco
    lfs f3, 0x580(r9)
    lfs f4, 0x588(r9)
    fmuls f5, f3, f3
    fmadds f5, f4, f4, f5
{rs("f5", "f6")}    fmuls f5, f5, f6
    lfs f6, 0x6F0(r31)
    fcmpu f5, f6
    bge oriz_ok
    fmr f5, f6
oriz_ok:
    ; velocità della corsa (f7)
    lfs f2, 0x1DC0(r31)
    lfs f4, 0x1DC8(r31)
    fmuls f7, f2, f2
    fmadds f7, f0, f0, f7
    fmadds f7, f4, f4, f7
{rs("f7", "f8")}    fmuls f7, f7, f8
    fcmpu f5, f7
    bge fine
    fmuls f8, f5, f8
    fmuls f2, f2, f8
    fmuls f0, f0, f8
    fmuls f4, f4, f8
    stfs f2, 0x1DC0(r31)
    stfs f0, 0x1DC4(r31)
    stfs f4, 0x1DC8(r31)
    stfs f5, 0x55C(r9)
fine:
    .word {FINE_AVVIO_ORIGINALE:#x}
""")


def _tetto():
    return asm.assembla(f"""
    lfs f0, 0x1e40(r30)
    lis r12, 0x817F
    lfs f13, 0x55C(r12)
    bl dopo
    .float 1.0
    .float {CAP_MURO}
    .float {FATTORE_MURO}
dopo:
    mflr r12
    lfs f12, 0(r12)
    fcmpu f13, f12
    blt tetto_fisso
    lfs f12, 8(r12)
    fmuls f13, f13, f12
    lfs f12, 0x6F0(r30)
    fcmpu f13, f12
    bge ingresso_ok
    fmr f13, f12
ingresso_ok:
    fcmpu f13, f0
    bge tetto_fisso
    fmr f0, f13
tetto_fisso:
    lfs f12, 4(r12)
    fcmpu f0, f12
    ble fine
    fmr f0, f12
fine:
""")


def codice():
    return (sum((asm.c2(a, _soglia()) for a in SOGLIA_PUNTI), []) + asm.c2(VERTICALE, _verticale()) + asm.c2(FINE_AVVIO, _fine_avvio())
            + asm.c2(INGRESSO, _ingresso()) + asm.c2(TETTO, _tetto())
            + asm.c2(MURO, asm.assembla(f"""
    cmplwi r10, 5
    bgt muro_orig
    li r10, 5
muro_orig:
    .word {MURO_ORIGINALE:#x}
""")))


if __name__ == "__main__":
    print(codice())
