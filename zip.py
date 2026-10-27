"""WEB ZIP CHE TIENE IL MOMENTUM (idea di John, 2026-10-10: "la spinta del web zip proporzionata alla velocità a cui eri
prima").

Il web zip (L + R in aria) è lo stato 9: il gioco tira Spidey verso il punto (piano, ~6-8 m/s) e alla fine lo lancia
(stato 5) a ~30 m/s, sempre uguale: venendo da uno swing veloce lo zip ti rallentava. Velocità del corpo fisico =
[[camera+0x164]+0xC] + 0x130 (la matrice fisica è a +0x0, posizione a +0x30; trovata confrontando la posizione vera con
la memoria dopo uno zip; uguale nelle versioni: stesso codice). Qui: velocità orizzontale prima dello zip V0 (ogni
fotogramma fuori dallo stato 9, 817F0574); appena lo zip finisce nello stato 5 (entro 6 fotogrammi, aspettando che il
gioco abbia messo la velocità del lancio L) la velocità orizzontale diventa T = L + K * V0 (K 0.4; provati 0.6, 0.5, 0.25 e 0.1) (al massimo CAP), stessa
direzione e stessa velocità verticale, e per 20 fotogrammi non scende sotto T (il gioco nei primi fotogrammi del lancio
la riportava alla sua). V0 = picco che cala piano: premendo L + R il gioco rallenta Spidey prima dello stato 9. Da fermo (V0 = 0) = zip normale.

Codice Gecko a sé con un aggancio all'inizio dell'aggiornamento della camera del gioco (0x801A0B78, dopo quelli del tuffo
e del momentum all'atterraggio; r31 = camera, r3/r4 vivi: li prepara il gioco per la bl dopo). Memoria 817F0570-057F (0570 stato prima, 0574 V0, 0578 fotogrammi rimasti, 0579 T calcolata, 057C T).
"""
import ppcasm as asm

NOME = "$Web zip keeps your momentum"
AGGANCIO = 0x801A0B78
ORIGINALE = 0x38A00088  # li r5, 0x88 (uguale nelle 5 versioni)
K, CAP = 0.4, 70.0  # John: 60% troppo, 10% troppo poco -> 50%; poi (2026-10-22, insieme al momentum sui muri) "troppo veloce" -> 25% max 50; 2026-10-23 "troppo poco" -> 40% max 70


def codice(ver="GK2I52"):
    return asm.c2(AGGANCIO, asm.assembla(f"""
    bl dopo_k
    .float {K}
    .float {CAP}
    .float 0.5
    .float 1.5
    .float 1.0
    .float 0.0001
    .float 0.98
dopo_k:
    mflr r8
    lis r12, 0x817F
    lwz r9, 0x164(r31)
    cmpwi r9, 0
    bge fine
    lwz r9, 0xC(r9)
    cmpwi r9, 0
    bge fine
    addi r9, r9, 0x130
    lis r10, 0x80AD
    lwz r10, 0x1A04(r10)
    lwz r11, 0x570(r12)
    stw r10, 0x570(r12)
    ; h = |velocità orizzontale| (f7)
    lfs f2, 0(r9)
    lfs f4, 8(r9)
    fmuls f5, f2, f2
    fmadds f5, f4, f4, f5
    fsubs f7, f7, f7
    lfs f0, 20(r8)
    fcmpu f5, f0
    blt h_ok
    frsqrte f6, f5
    fmuls f0, f6, f6
    fmuls f0, f0, f5
    lfs f1, 8(r8)
    fmuls f0, f0, f1
    lfs f1, 12(r8)
    fsubs f0, f1, f0
    fmuls f6, f6, f0
    fmuls f7, f5, f6
h_ok:
    cmpwi r10, 9
    beq fine
    lbz r0, 0x578(r12)
    cmpwi r0, 0
    bne attesa
    cmpwi r11, 9
    bne salva
    cmpwi r10, 5
    bne salva
    li r0, 30
    stb r0, 0x578(r12)
    li r5, 0
    stb r5, 0x579(r12)
attesa:
    cmpwi r10, 5
    bne annulla
    lfs f0, 16(r8)
    fcmpu f7, f0
    blt aspetta
    ; T (817F057C) = lancio del gioco + K * V0 (max CAP), calcolata la prima volta; poi per FINESTRA fotogrammi la
    ; velocità orizzontale non scende sotto T (il gioco nei primi fotogrammi del lancio la rimette alla sua)
    lbz r5, 0x579(r12)
    cmpwi r5, 0
    bne t_ok
    lfs f0, 0x574(r12)
    lfs f1, 0(r8)
    fmadds f8, f0, f1, f7
    lfs f1, 4(r8)
    fcmpu f8, f1
    ble cap_ok
    fmr f8, f1
cap_ok:
    stfs f8, 0x57C(r12)
    li r5, 1
    stb r5, 0x579(r12)
    li r0, 20
t_ok:
    lfs f8, 0x57C(r12)
    fcmpu f8, f7
    ble aspetta
    fdivs f8, f8, f7
    fmuls f2, f2, f8
    fmuls f4, f4, f8
    stfs f2, 0(r9)
    stfs f4, 8(r9)
aspetta:
    addi r0, r0, -1
    stb r0, 0x578(r12)
    cmpwi r0, 0
    bne fine
    li r5, 0
    stb r5, 0x579(r12)
    b fine
annulla:
    li r0, 0
    stb r0, 0x578(r12)
    stb r0, 0x579(r12)
salva:
    ; V0 = picco che cala piano (x 0.98 a fotogramma): premendo L + R il gioco rallenta Spidey per qualche fotogramma
    ; PRIMA dello stato 9 (misurato: 52 -> 31 m/s)
    lfs f0, 0x574(r12)
    lfs f1, 24(r8)
    fmuls f0, f0, f1
    fcmpu f7, f0
    bge salva_h
    fmr f7, f0
salva_h:
    stfs f7, 0x574(r12)
fine:
    .word {ORIGINALE:#x}
"""))


if __name__ == "__main__":
    print(len(codice()) * 8, "byte Gecko")
