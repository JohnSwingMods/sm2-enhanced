"""Camera stile Spider-Man PS4 (Gecko, tappa 2). Usa i ganci di cam_nostra.py (salva/rimetti la matrice del gioco).

Cosa fa (ogni fotogramma, dopo che il gioco ha calcolato la sua camera):
- levetta destra (C-stick): gira la camera e la alza/abbassa; lasciata, resta dov'è;
- rientro: dopo 30 fotogrammi senza levetta, se Spidey si muove, la camera torna piano dietro alla direzione di
  marcia (più svelta con la velocità);
- punto morbido (anti-pendolo): la camera segue un punto che insegue Spidey con un filtro (più lento in verticale)
  e non si allontana mai più di lim_h / lim_v da lui -> Spidey resta inquadrato senza il dondolio rigido;
- distanza D e altezza del punto guardato H per situazione (terra / aria / swing), con passaggi morbidi.
Stato (817F0200..): 200 init, 204/208 direzione orizzontale dello sguardo, 20C elevazione (rad, + = dall'alto),
210/214/218 punto morbido, 21C D, 220 H, 224 fotogrammi senza levetta, 228-230 Spidey prima, 234/238 velocità.
Le costanti (817F0144..) si scrivono UNA volta: dal vivo si cambiano con DME. Il programma (la logica) lo scrive un
codice AR a 817F0800 (codice_ar): nel Gecko restano solo costanti e agganci (spazio Gecko di Dolphin: ~3264 byte).

uso: python cam_ps4.py -> righe Gecko (ITA)."""
import os
import ppcasm as asm
import momentum
import prima
from cam_nostra import BASE, RIMETTI, VERSIONI, _rsqrt

PS4 = {  # offset: (nome, valore)
    0x144: ("D_salva", 0.6), 0x148: ("alfa_salva", 0.08),
    0x150: ("mezzo", 0.5), 0x154: ("unoemezzo", 1.5), 0x158: ("uno", 1.0), 0x15C: ("inizio_raggio", 0.25),
    0x160: ("k_yaw", -2.6 / 60 / 44), 0x164: ("k_pitch", -1.6 / 60 / 44),
    0x168: ("e_min", -0.45), 0x16C: ("e_max", 1.05),
    0x170: ("alfa_h", 0.35), 0x174: ("alfa_v", 0.2), 0x178: ("lim_h", 1.0), 0x17C: ("lim_v", 1.0),
    0x180: ("D_terra", 3.2), 0x184: ("H_terra", 0.45), 0x188: ("D_aria", 3.4), 0x18C: ("H_aria", 0.55),
    0x190: ("D_swing", 3.1), 0x194: ("H_swing", 0.45), 0x198: ("alfa_D", 0.05),
    0x19C: ("rientro", 0.07), 0x1A4: ("vel_min2", 0.0012),
    0x1AC: ("zona_morta", 6.0), 0x1B0: ("alfa_vel", 0.1), 0x1B4: ("sesto", 1 / 6), 0x1C8: ("zero", 0.0),
    0x1D0: ("k_vel_rientro", 0.06), 0x1D4: ("rientro_max", 0.3), 0x1D8: ("anticipo", 1.0), 0x1DC: ("anticipo_max", 0.6),
    0x1E0: ("e_terra", 0.22), 0x1E4: ("e_aria", 0.15), 0x1E8: ("alfa_e", 0.02), 0x1EC: ("margine", 0.5),
    0x1F0: ("alfa_muro", 0.08),
}
# prima persona (studiata coi dati registrati, 9000 campioni): la camera sta agli OCCHI, dall'osso della testa dello
# scheletro animato: [camera+0x164] = Spidey, [+0x134] = 60 ossa (matrici 4x4 nel mondo, 0x40 l'una), testa = osso 5
# (+0x140): riga x = giù della testa, riga z = indietro della testa, +0x30 posizione. Occhi = testa + avanti*A + su*H
# (A e H negativi perché moltiplicano le righe z e x). Sui muri la matrice del corpo non segue la posa: lo scheletro sì.
# Lo sguardo segue la direzione in cui vai e la levetta destra (come la moderna), NON la testa: in aria il gioco fa
# girare tutto il corpo e la vista girava con lui. In swing la mano della ragnatela sta ~60° sopra gli occhi: lo sguardo si alza (e negativo = in su) così
# braccia e ragnatela entrano nell'inquadratura. L'avanti della testa è -z.
# Blocco "una volta sola" suo (817F029C = 1): uno stato salvato col codice di prima non ha queste costanti.
PRIMA = {0x270: ("A_prima", -0.22), 0x274: ("H_prima", -0.06), 0x278: ("e_prima", 0.05), 0x280: ("e_prima_swing", -0.6),
         0x294: ("e_min_prima", -1.1), 0x298: ("alfa_e_prima", 0.06), 0x2AC: ("anticipo_prima", 1.0), 0x27C: ("fov_prima", 1.9199),
         0x288: ("A_trick", -0.32), 0x28C: ("vel_min2_prima", 0.03), 0x284: ("levetta_max_trick", 0.25),
         0x2D0: ("alfa_miscela", 0.22), 0x2E0: ("s_realistica", 0.9), 0x2E4: ("A_realistica", 0.16), 0x2B0: ("B_realistica", 0.08), 0x2B4: ("C_realistica", 0.25), 0x2BC: ("rollio_realistica", 0.35), 0x290: ("eps", 0.0001), 0x29C: ("s_realistica_swing", 0.45), 0x2C4: ("e_realistica_swing", -0.3), 0x2F8: ("D_realistica", 0.3), 0x2D8: ("imbardata_realistica", 0.4),
         0x2E8: ("cos_testa", 0.9801), 0x2EC: ("sin_testa", 0.1987), 0x2F4: ("alfa_testa", 0.35)}
# realistica: la testa di Spidey dritta guarda già ~18° in giù (misurato camminando: -13..-26°): la rotazione della testa
# si misura rispetto a quella posa, in parte (cos/sin_testa = 0.2 rad: con tutti i 18° correndo non si vedevano più
# piedi e braccia; senza, la vista guardava per terra).
# anticipo: la camera si aggiorna PRIMA che il gioco sposti Spidey nello stesso fotogramma -> agli occhi resterebbe indietro
# di uno spostamento (a 58 m/s in swing = 1,5 m!). Occhi += (Spidey - Spidey prima) * anticipo. (1.7 = troppo: avanti)
# FOV: in prima persona 110° (con lo sguardo alzato nello swing la mano della ragnatela, ~60° sopra gli occhi, entra
# nell'inquadratura); entrando salvo il FOV di adesso (817F02B8) e uscendo lo rimetto.
S = 0x300  # struttura per il controllo dei muri (raggio dal punto guardato alla camera), come la usa la camera del gioco
# raggio del gioco: prepara (802141D8), lancia (802153D8), chiudi (802148A0); globale passato in r6 (804BD34C)
VERSIONI["GK2I52"].update(tuffo=(0x801268B0, 0x800241D4, 0x801268F0, 0x800244DC, 0x804600C8, 0x804600F8), fov=0x8046A7C0, tasti=0x805546A0, stato=0x80AD1A04, raggio=(0x802141D8, 0x802153D8, 0x802148A0), raggio_g=0x804BD34C, vi=0x8056C560, levetta_x=0x802CB1E0,
                           croce_giu=0x802CB170, pausa=0x8056BA3B)
# USA (e UK/DE/FR: stesso programma): la camera e il raggio stanno agli STESSI indirizzi dell'ITA (confrontato main.dol);
# cambiano la posizione di Spidey, i tasti e il globale del raggio (-0x80). La camera si legge da r3: DE (oggetto camera
# spostato) va bene lo stesso.
for _g in ("GK2E52", "GK2P52", "GK2D52", "GK2F52"):
    VERSIONI[_g] = dict(VERSIONI["GK2I52"], spidey=0x80495F4C, tasti=0x80554620, raggio_g=0x804BD2CC, fov=0x8046A740, vi=0x8056C4E0, levetta_x=0x802CB170,
                        croce_giu=0x802CB100, pausa=0x8056B9BB)
    # tuffo a comando: funzioni del gioco agli stessi indirizzi dell'ITA (confrontato), stringa e costante -0x80
    VERSIONI[_g]["tuffo"] = (0x801268B0, 0x800241D4, 0x801268F0, 0x800244DC, 0x80460048, 0x80460078)
NOME = "$Camera: main and alternate (R3), modern / classic / original"
VECCHI = ["$Modern camera (PS4 style), R3 to switch modern/classic"]
# Due camere, R3 passa dall'una all'altra (817F0080 = 0 principale, 1 alternativa). Che camera è ognuna: byte 817F0084
# (principale) e 817F0085 (alternativa), scritti all'avvio e cambiati dal vivo dall'app (menu in gioco, Spider-Cam).
MODI = {"moderna": 0, "classica": 1, "originale": 2, "prima": 3, "cinematica": 4, "amazing": 5}  # classica = codice AR "Custom camera" (preset di
# Spider-Cam, nell'app "Migliorata"); prima = prima persona (stessa logica della moderna, camera sulla testa di Spidey)
MODI_BASE = ("moderna", "amazing")  # John 2026-10-10: le consigliate (prima moderna + originale)
# CINEMATICA (modo 4; era la prima "amazing", John: "bellissima, salviamola") e AMAZING (modo 5, come The Amazing
# Spider-Man 1 dal video che ha mandato John: molto più OVER THE SHOULDER, vicina, spalle, Spidey nel terzo sinistro):
# la moderna con un'altra regia, 817F05A0 = 1 cinematica / 2 amazing. Ogni fotogramma la serie di costanti della camera
# scelta (CIN a 817F3800, TASM a 817F3880, stessa disposizione) si copia in 817F3900 (quella che il programma legge);
# + spostamento di lato S (camera a destra di Spidey, come guardare oltre la sua spalla destra) a +0x40/+0x48/+0x50
# (terra/aria/swing, 0 nella cinematica), ammorbidito in 817F05BC; anche il raggio dei muri lo tiene in conto.
# +0x58: FOV in meno (TASM ha un'inquadratura più stretta: col FOV di John a 95° Spidey sembrava lontano). +0x44/4C/54:
# DERIVA = in TASM la spalla non è fissa: nello swing Spidey scivola verso il lato dove si muove (S = base - deriva *
# velocità laterale rispetto alla vista, max S_max +0x5C); a terra resta la spalla destra. In caduta (aria) camera più
# lontana (3.1) e un po' dall'alto: nei trick Spidey veniva tagliato (John). Spalla con le frecce: 817F05C0 (0 destra = di base, 1 sinistra; prima 0 sinistra,
# di base, 1 destra; la base S cambia segno). A terra quasi centrale (John: 0.22, deriva 0.3).
# Descrizione della cinematica: Più vicina e più bassa,
# nello swing quasi orizzontale (si vede il cielo); con la velocità il FOV si allarga e la camera si allontana un po'
# (boost b 0..1 da 12 a 39 m/s, ammorbidito); in aria si inclina nelle curve (rollio = quanto gira la direzione di
# marcia, solo in aria e solo veloce). Stato in 817F05A0.. (A0 attiva, A4 FOV base, A8/AC velocità prima, B0 boost,
# B4 ultimo FOV scritto, B8 rollio). Le costanti NON stanno nel Gecko (pieno): le scrive il codice AR del programma
# a 817F3800 (AMAZING_K), insieme alla logica.
AMAZING_K = {0x3800: ("D_terra_a", 2.5), 0x3804: ("H_terra_a", 0.7), 0x3808: ("D_aria_a", 2.7), 0x380C: ("H_aria_a", 0.5),
             0x3810: ("D_swing_a", 2.75), 0x3814: ("H_swing_a", 0.35), 0x3818: ("e_terra_a", 0.18), 0x381C: ("e_aria_a", -0.02),
             0x3820: ("v0_a", 0.2), 0x3824: ("inv_range_a", 1 / 0.45), 0x3828: ("fov_boost_a", 0.17), 0x382C: ("D_boost_a", 0.45),
             0x3830: ("alfa_boost_a", 0.015), 0x3834: ("k_rollio_a", 7.0), 0x3838: ("rollio_max_a", 0.14), 0x383C: ("alfa_rollio_a", 0.05)}
TASM_K = {0x3880: ("D_terra_t", 1.6), 0x3884: ("H_terra_t", 0.8), 0x3888: ("D_aria_t", 3.1), 0x388C: ("H_aria_t", 0.45),
          0x3890: ("D_swing_t", 2.5), 0x3894: ("H_swing_t", 0.5), 0x3898: ("e_terra_t", 0.1), 0x389C: ("e_aria_t", 0.05),
          0x38A0: ("v0_t", 0.2), 0x38A4: ("inv_range_t", 1 / 0.45), 0x38A8: ("fov_boost_t", 0.14), 0x38AC: ("D_boost_t", 0.35),
          0x38B0: ("alfa_boost_t", 0.015), 0x38B4: ("k_rollio_t", 5.0), 0x38B8: ("rollio_max_t", 0.25), 0x38BC: ("alfa_rollio_t", 0.05),
          0x38C0: ("S_terra_t", 0.22), 0x38C4: ("deriva_terra_t", 0.3), 0x38C8: ("S_aria_t", 0.0), 0x38CC: ("deriva_aria_t", 1.6),
          0x38D0: ("S_swing_t", 0.1), 0x38D4: ("deriva_swing_t", 1.6), 0x38D8: ("fov_delta_t", -0.2), 0x38DC: ("S_max_t", 0.9),
          0x38E0: ("k_tuffo_t", 0.55), 0x38E4: ("vy0_t", 9.0), 0x38E8: ("inv_vy_t", 1 / 21), 0x38EC: ("alfa_tuffo_t", 0.05),
          0x38F0: ("caduta_min_t", 6.0), 0x38F4: ("k_lat_t", 0.6)}
AMAZING_K.update({0x3860: ("k_tuffo_a", 0.5), 0x3864: ("vy0_a", 9.0), 0x3868: ("inv_vy_a", 1 / 21), 0x386C: ("alfa_tuffo_a", 0.05),
                  0x3870: ("caduta_min_a", 6.0), 0x3874: ("k_lat_a", 0.0)})
# MODERNA come Spider-Man PS4 (video mandato da John, guardato a fotogrammi): stessa D/H/e di prima (PS4 = costanti
# 0x180..), in più 1) con la velocità la camera si allontana e il FOV si allarga (boost come la cinematica, più leggero);
# 2) TUFFO: in caduta libera (stato 5) la camera sale e guarda giù lungo la caduta (angolo T in 817F05C8 verso
# k_tuffo * clamp((-vy - vy0) * inv_vy), ammorbidito alfa_tuffo; vy = spostamento verticale per fotogramma ammorbidito
# in 817F05C4; T si somma all'elevazione solo per la direzione). Niente spalla, niente rollio.
# 817F05A0 = 3 per la moderna (non in prima persona). Serie a 817F3980 (stessa disposizione, 28 parole).
PS4_K = {0x3980 + o - 0x180: (n + "_m", PS4[o][1]) for o, n in ((0x180, "D_terra"), (0x184, "H_terra"), (0x188, "D_aria"),
         (0x18C, "H_aria"), (0x190, "D_swing"), (0x194, "H_swing"))}
PS4_K.update({0x3998: ("e_terra_m", PS4[0x1E0][1]), 0x399C: ("e_aria_m", PS4[0x1E4][1]),
              0x39A0: ("v0_m", 0.2), 0x39A4: ("inv_range_m", 1 / 0.45), 0x39A8: ("fov_boost_m", 0.12), 0x39AC: ("D_boost_m", 0.7),
              0x39B0: ("alfa_boost_m", 0.015), 0x39B4: ("k_rollio_m", 0.0), 0x39B8: ("rollio_max_m", 0.08), 0x39BC: ("alfa_rollio_m", 0.05),
              0x39C0: ("S_terra_m", 0.0), 0x39C4: ("deriva_terra_m", 0.0), 0x39C8: ("S_aria_m", 0.0), 0x39CC: ("deriva_aria_m", 0.0),
              0x39D0: ("S_swing_m", 0.0), 0x39D4: ("deriva_swing_m", 0.0), 0x39D8: ("fov_delta_m", 0.0), 0x39DC: ("S_max_m", 0.0),
              0x39E0: ("k_tuffo_m", 0.55), 0x39E4: ("vy0_m", 9.0), 0x39E8: ("inv_vy_m", 1 / 21), 0x39EC: ("alfa_tuffo_m", 0.05),
              0x39F0: ("caduta_min_m", 6.0), 0x39F4: ("k_lat_m", 0.25)})
# picchiata vera (comune alle camere con serie): posa del tuffo e quanto cambia la camera
PICCH_K = {0x3A00: ("rad_min_posa", 0.3), 0x3A08: ("vy_posa", -10.0),
           0x3A0C: ("e_picchiata", 0.75), 0x3A10: ("D_picchiata", 0.6), 0x3A14: ("fov_picchiata", 0.2),
           0x3A28: ("sessanta", 60.0), 0x3A2C: ("spalla_sx", -0.6), 0x3A30: ("alfa_D_picchiata", 0.3),
           0x3A20: ("e_max_tot", 1.3), 0x3A34: ("alfa_tuffo_giu", 0.2), 0x3A38: ("alfa_D_tuffo", 0.5), 0x3A3C: ("alfa_picchiata_giu", 0.35), 0x3A40: ("memoria_picchiata", 0.95), 0x3A44: ("radice_comando", -0.6),
           0x3A18: ("alfa_picchiata", 0.2)}
K_ATTIVE = 0x3900  # copia della serie in uso (0x70 byte)
RIGA_MODI = 0x84


# Prima persona, come si muove la vista (byte 817F0088): 0 "stabile" (guarda dove vai), 1 "trick" (stabile, ma nei trick
# in aria con la levetta sinistra lasciata la vista fa il trick 1 a 1), 2 "realistica" (la vista è sempre la testa di
# Spidey, anche guidando: al disegno va la testa, ai comandi la vista stabile -> niente camera e Spidey che si inseguono).
VISTE = {"no": 0, "si": 1}  # prima persona: movimento della testa spento / acceso (prima.py)
OPZIONI_BASE = {"prima_vista": "no", "tuffo_l3": True, "picchiata": True}
# Tuffo (byte 817F0089, idea di John): bit 1 = niente tuffo con L3, bit 2 = niente camera della picchiata (il tuffo con
# L3 c'è anche con la camera classica e con l'originale: lì la picchiata non c'è comunque).


def valore_tuffo(opzioni=None):
    o = opzioni or {}
    # bit 1 (niente tuffo con L3) non più usato: il tuffo è un codice a sé (tuffo.py), acceso/spento nell'INI
    return 0 if o.get("picchiata", True) else 2


def valore_vista(opzioni=None):
    """Byte 817F0088: movimento della testa in prima persona (0 spento, 1 acceso). Le viste di prima (stabile / trick /
    realistica, prima_testa) non ci sono più: la prima persona è stata rifatta da zero (prima.py) e riparte spenta."""
    return VISTE.get((opzioni or {}).get("prima_vista"), 0)


def riga_opzioni(opzioni=None):  # 817F0088: vista della prima persona (VISTE); 817F0089: tuffo (valore_tuffo)
    return asm.scrivi32(BASE + 0x88, valore_vista(opzioni) << 24 | valore_tuffo(opzioni) << 16)


def riga_modi(modi=MODI_BASE):
    # byte 817F0086 = 1: "camere già scritte". Ha un suo "una volta sola" (non quello delle costanti): uno stato salvato
    # fatto col codice di prima ha le costanti già scritte ma qui 0 -> le camere vengono scritte lo stesso.
    return asm.scrivi32(BASE + RIGA_MODI, MODI[modi[0]] << 24 | MODI[modi[1]] << 16 | 0x100)


def _blocco(da, a, valori):
    """Gecko 06 (scrive una fila di byte): una riga ogni 8 byte invece di una riga per ogni numero. Dolphin ha poco
    spazio per i codici Gecko (~3264 byte con il suo codehandler): se il totale non ci sta NON carica il codice (in silenzio)."""
    dati = bytearray(a - da)
    for o, v in valori.items():
        dati[o - da:o - da + 4] = v.to_bytes(4, "big")
    dati += bytes(-len(dati) % 8)
    righe = [f"{0x06000000 | ((BASE + da) & 0x1FFFFFF):08X} {a - da:08X}"]
    return righe + [f"{dati[k:k + 4].hex().upper()} {dati[k + 4:k + 8].hex().upper()}" for k in range(0, len(dati), 8)]


def costanti(modi=MODI_BASE, opzioni=None):
    righe = ["217F01FC 00000000"]  # Gecko: solo se non ancora scritte (poi si regolano dal vivo)
    righe += _blocco(0x144, 0x200, {**{o: asm.f32(x) for o, (_, x) in PS4.items()},
                                    0x1B8: 0x43300000, 0x1BC: 0x80000000, 0x1FC: 1})  # (1B8/1BC: int -> float)
    righe += ["E2000001 00000000"]
    righe += [f"29{(BASE + RIGA_MODI + 2) & 0xFFFFFF:06X} 00000000", riga_modi(modi), riga_opzioni(opzioni),
              "E2000001 00000000"]  # se 817F0086 == 0
    righe += [f"21{(BASE + 0x2FC) & 0xFFFFFF:06X} 00000000"]  # (2FC: segno nuovo, mai usato prima negli stati salvati)
    righe += _blocco(0x270, 0x300, {**{o: asm.f32(x) for o, (_, x) in PRIMA.items()}, 0x2F0: 1, 0x2DC: 1, 0x2D4: 1, 0x2FC: 1}) + ["E2000001 00000000"]
    return righe


def _intfloat(dest):  # r11 (int con segno) -> float in dest (usa f13)
    return f"""
    xoris r11, r11, 0x8000
    stw r11, 0x1C4(r12)
    lis r11, 0x4330
    stw r11, 0x1C0(r12)
    lfd {dest}, 0x1C0(r12)
    lfd f13, 0x1B8(r12)
    fsub {dest}, {dest}, f13
    frsp {dest}, {dest}
"""


def _stick(off, dest):  # byte con segno della levetta -> float
    return f"""
    lbz r11, {off:#x}(r8)
    extsb r11, r11
    {_intfloat(dest)}
"""


def _segui(asse, alfa, lim):  # Ts += (T - Ts)*alfa, poi |T - Ts| <= lim  (T = f1/f2/f3)
    t = ("f1", "f2", "f3")[asse]
    o = 0x210 + 4 * asse
    return f"""
    lfs f4, {o:#x}(r12)
    lfs f5, {alfa:#x}(r12)
    fsubs f6, {t}, f4
    fmadds f4, f6, f5, f4
    lfs f5, {lim:#x}(r12)
    fsubs f6, {t}, f4
    fsubs f7, f6, f5
    fsubs f8, {t}, f5
    fsel f4, f7, f8, f4
    fneg f6, f6
    fsubs f7, f6, f5
    fadds f8, {t}, f5
    fsel f4, f7, f8, f4
    stfs f4, {o:#x}(r12)
"""



TESTA_PRIMA, COLLO_PRIMA, TESTA_VIVA = 0x500, 0x530, 0x560  # 817F0500.. (zona a zero, libera)
APPOGGIO_TESTA = 0x37E0  # appoggio per caricare la costante (817F37E0, libero: 37C0-37DF = scheletro.py)
TUFFO_RADICE = 0.3  # posa del tuffo: radice a testa in giù (come il tuffo della moderna, 817F05CC) - stato 5
TUFFO_ENTRA = -0.4  # prima persona: il tuffo parte appena il corpo inizia a ruotare in avanti (radice da -0.9 dritto a +0.8 a testa in giù)
TUFFO_ESCE = -0.65  # e finisce solo col corpo di nuovo quasi dritto
TUFFO_FP = 0x37EC  # quantità di tuffo della prima persona (0..1, float)
TUFFO_GIU = 1.2  # rad: quanto scende lo sguardo nel tuffo (col limite e_max_tot ~ 72°, come la picchiata)


def _tuffo_prima(v):
    """Prima persona: quantità di tuffo 817F37EC verso 1 se Spidey è nella posa del tuffo (radice oltre TUFFO_ENTRA, poi fino a
    TUFFO_ESCE: stati 4 e 5), se no verso 0 (un quarto per giro). Con le altre camere va a 0.
    Usa r11, f5-f8 (f1-f3 = punto appena salvato, f12 serve dopo)."""
    st = v["stato"]
    return f"""
    fsubs f6, f6, f6
    lbz r11, 0x87(r12)
    cmpwi r11, 0
    beq tfp_ok
    lis r11, {st >> 16:#x}
    ori r11, r11, {st & 0xFFFF:#x}
    lwz r11, 0(r11)
    cmpwi r11, 5
    beq tfp_aria
    cmpwi r11, 4
    bne tfp_ok
tfp_aria:
    ; per entrare TUFFO_ENTRA; già nel tuffo (quantità > metà) si resta fino a TUFFO_ESCE (corpo di nuovo dritto): la posa
    ; oscilla attorno alla soglia e la vista scendeva, si rialzava e riscendeva (John)
    lis r0, {asm.f32(TUFFO_ENTRA) >> 16:#x}
    ori r0, r0, {asm.f32(TUFFO_ENTRA) & 0xFFFF:#x}
    lfs f5, {TUFFO_FP:#x}(r12)
    lfs f7, 0x150(r12)
    fcmpu f5, f7
    ble tfp_soglia
    lis r0, {asm.f32(TUFFO_ESCE) >> 16:#x}
    ori r0, r0, {asm.f32(TUFFO_ESCE) & 0xFFFF:#x}
tfp_soglia:
    stw r0, {APPOGGIO_TESTA:#x}(r12)
    lfs f7, {APPOGGIO_TESTA:#x}(r12)
    lwz r11, 0x164(r31)
    lwz r11, 0x134(r11)
    lfs f5, 0x4(r11)
    fcmpu f5, f7
    ble tfp_ok
    lfs f6, 0x158(r12)
tfp_ok:
    lfs f5, {TUFFO_FP:#x}(r12)
    fsubs f7, f6, f5
    lfs f8, 0x15C(r12)
    fmadds f5, f7, f8, f5
    stfs f5, {TUFFO_FP:#x}(r12)
"""


TENUTA_PICCHIATA = 24  # fotogrammi video (60 al secondo: 0,4 s) di L3 tenuto per agganciare la picchiata
PARTENZA_PICCHIATA = 12  # prima di 0,2 s di L3 tenuto la camera non si muove (John: col solo tuffo la picchiata scattava per un attimo)


def _chiama_tuffo(v):
    # (2026-10-10) il tuffo con L3 è un codice a sé (tuffo.py, gira anche con la camera spenta): il programma della
    # camera non lo chiama più e legge solo le sue variabili (817F05D4-05D7)
    return ""
    if "tuffo" not in v:
        return ""
    return "    bl tuffo_comando\n    lis r12, 0x817F"


def _tuffo_comando(v):
    return ""  # vedi _chiama_tuffo: ora in tuffo.py
    if "tuffo" not in v:
        return ""
    pulisci, crea, anima, libera, nome, cost = v["tuffo"]
    pad = v["tasti"]
    pulizie = "".join(f"""    mr r3, r30
    li r4, {k:#x}
    chiama {pulisci:#x}
""" for k in (2, 0xA, 3))
    zeri = "".join(f"    stb r0, {o:#x}(r30)\n" for o in (0x1F03, 0x1ED1, 0x1EFC, 0x1EF9, 0x1EFA, 0x1EFB, 0x1F1E))
    # Il fronte di L3 diventa una RICHIESTA (817F05D7) che resta finché Spidey è in aria (stato 4/5): così vale
    # anche se Spidey non può tuffarsi in quell'istante. Stato 5 = subito. Stato 4 (John: alla fine della corsa sul
    # muro il gioco fa l'avvitamento e mette lo stato 4, 0x8014DF8C) = solo se non è già un tuffo comandato, sta
    # scendendo (817F05C4 < 0) e non è già a testa in giù (radice +0x04 < rad_min: tuffo dal bordo del gioco o
    # avvitamento a metà giro -> aspetta). I trick in aria (e l'avvitamento) il gioco non li fa interrompere:
    # il tuffo si vede appena finiscono (anche la ragnatela aspetta), e la camera aspetta con lui (vedi sotto).
    return f"""tuffo_comando:
    mflr r0
    stw r0, 4(r1)
    stwu r1, -0x40(r1)
    stw r30, 0x38(r1)
    lis r12, 0x817F
    lbz r9, 0x89(r12)
    andi. r9, r9, 1
    bne tc_annulla
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
    stb r10, 0x5D7(r12)
tc_richiesta:
    lis r30, 0x80AD
    ori r30, r30, 0x140
    lwz r0, 0x18C4(r30)
    cmpwi r0, 5
    beq tc_aria
    cmpwi r0, 4
    bne tc_annulla
    lbz r9, 0x5D6(r12)
    cmpwi r9, 0
    bne tc_annulla
    lfs f0, 0x5C4(r12)
    lfs f1, 0x1C8(r12)
    fcmpu f0, f1
    bge tc_fine
    lwz r9, 0x164(r31)
    cmpwi r9, 0
    beq tc_fine
    lwz r9, 0x134(r9)
    cmpwi r9, 0
    beq tc_fine
    lfs f0, 4(r9)
    lfs f1, 0x3A00(r12)
    fcmpu f0, f1
    bge tc_fine
tc_aria:
    lbz r9, 0x5D7(r12)
    cmpwi r9, 0
    beq tc_fine
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
    li r9, 0
    stb r9, 0x5D7(r12)
tc_fine:
    lwz r30, 0x38(r1)
    lwz r0, 0x44(r1)
    addi r1, r1, 0x40
    mtlr r0
    blr"""


# ATTACCATO AL MURO (John: "arrivato al bordo del palazzo si arrampica a vuoto finché non lasci la levetta; con la camera
# originale sale subito"). La camera del gioco sul muro (modalità 5) guarda IN SU lungo il muro: per il gioco levetta su =
# su, e al bordo scavalca. Le nostre guardano il muro da dietro: levetta su = dentro il muro; arrampicarsi va lo stesso, ma al
# bordo il "vuole salire?" fallisce (lasciando la levetta il gioco sale da solo). Registrato (prove_gioco/registra_bordo.py,
# bordo_analisi.py): camera originale av = (0.31, 0.95, 0.10) quasi in su, la nostra (0.95, -0.07, 0.30) orizzontale.
# Qui, con Spidey sul muro (stato 2) e muro verticale (|y| dell'asse su del corpo < 0.5: il soffitto ha 817F0558), il DISEGNO
# resta la nostra camera (aggancio VISTA: occhio/bersaglio/su in 817F03B0.., 817F008C = 1, se la prima persona non li ha già
# messi) e alla matrice che leggono i COMANDI ([camera+0x30]) do: avanti = (su del mondo + 0.5 * dentro il muro) normalizzato,
# destra = lungo il muro in orizzontale dalla parte della nostra destra, su = avanti x destra (destra x su = avanti, come le
# matrici del gioco). Il programma al giro dopo riparte dalla matrice del gioco (RIMETTI), quindi niente si accumula.
def _muro_comandi(v):
    st = v["stato"]
    righe = [f"""
    ; ---- attaccato al muro: comandi come la camera del gioco (in su lungo il muro), disegno = la nostra camera
    lis r9, {st >> 16:#x}
    ori r9, r9, {st & 0xFFFF:#x}
    lwz r9, 0(r9)
    cmpwi r9, 2
    bne muro_fine
    lwz r9, 0x164(r31)
    lwz r9, 0x30(r9)
    lfs f1, 0x10(r9)
    lfs f2, 0x14(r9)
    lfs f3, 0x18(r9)
    fabs f4, f2
    lfs f5, 0x150(r12)
    fcmpu f4, f5
    bge muro_fine
    lwz r10, 0x30(r31)
    lbz r11, 0x8C(r12)
    cmpwi r11, 0
    bne muro_comandi"""]
    for i in range(3):
        righe.append(f"""
    lfs f4, {0x30 + 4 * i:#x}(r10)
    stfs f4, {0x3B0 + 4 * i:#x}(r12)
    lfs f5, {0x20 + 4 * i:#x}(r10)
    fadds f4, f4, f5
    stfs f4, {0x3C0 + 4 * i:#x}(r12)
    lfs f5, {0x10 + 4 * i:#x}(r10)
    stfs f5, {0x3CC + 4 * i:#x}(r12)""")
    righe.append("""
    li r11, 1
    stb r11, 0x8C(r12)
muro_comandi:
    fmuls f4, f1, f1
    fmadds f4, f3, f3, f4
    frsqrte f4, f4
    fneg f4, f4
    fmuls f6, f1, f4
    fmuls f7, f3, f4
    lfs f5, 0x150(r12)
    fmuls f8, f6, f5
    fmuls f9, f7, f5
    lfs f10, 0x158(r12)
    fmuls f11, f8, f8
    fmadds f11, f9, f9, f11
    fadds f11, f11, f10
    frsqrte f11, f11
    fmuls f8, f8, f11
    fmuls f9, f9, f11
    fmr f10, f11
    fmr f12, f7
    fneg f13, f6
    lfs f4, 0x0(r10)
    lfs f5, 0x8(r10)
    fmuls f4, f12, f4
    fmadds f4, f13, f5, f4
    fsubs f5, f10, f10
    fcmpu f4, f5
    bge muro_destra_ok
    fneg f12, f12
    fneg f13, f13
muro_destra_ok:
    stfs f12, 0x0(r10)
    stfs f5, 0x4(r10)
    stfs f13, 0x8(r10)
    fmuls f4, f10, f13
    stfs f4, 0x10(r10)
    fmuls f4, f9, f12
    fnmsubs f4, f8, f13, f4
    stfs f4, 0x14(r10)
    fmuls f4, f10, f12
    fneg f4, f4
    stfs f4, 0x18(r10)
    stfs f8, 0x20(r10)
    stfs f10, 0x24(r10)
    stfs f9, 0x28(r10)
muro_fine:""")
    return "".join(righe)


def logica(v):
    s, pad, stato, fov, vi = v["spidey"], v["tasti"], v["stato"], v["fov"], v["vi"]
    r_prep, r_lancia, r_chiudi = v["raggio"]
    g = v["raggio_g"]
    return f"""
    mflr r0
    stw r0, 4(r1)
    stwu r1, -0x40(r1)
    stw r31, 0x3C(r1)
    mr r31, r3
    lis r12, 0x817F
    lbz r9, 0x8C(r12)
    stb r9, 0x8E(r12)
    li r9, 0
    stb r9, 0x8C(r12)
    stb r9, 0x558(r12)
    stw r31, 0x3BC(r12)
    ; prima persona (prima.py): costanti e piano vicino del gioco
{prima.INIZIO()}
{_chiama_tuffo(v)}
{momentum.CHIAMA if momentum.NEL_PROGRAMMA else ''}
    ; ---- R3 (= Z + giù nel profilo): camera principale <-> alternativa (817F0080: 0 principale, 1 alternativa;
    ; NON 817F0040: lì scrive il riempimento del codice camera). Il codice camera classico conta anche lui Z + giù
    ; (817F0010 dispari = valori originali): finché R3 è tenuto metto il suo "già contato" (817F0012 = 1) e il suo
    ; contatore lo decido io qui sotto, così R3 fa una cosa sola.
    lis r8, {pad >> 16:#x}
    ori r8, r8, {pad & 0xFFFF:#x}
    lhz r11, 0(r8)
    andi. r9, r11, 0x14
    cmpwi r9, 0x14
    bne r3_su
    li r9, 1
    stb r9, 0x12(r12)
    lbz r9, 0x81(r12)
    li r7, 12
    stb r7, 0x81(r12)
    cmpwi r9, 0
    bne r3_fatto
    ; col LOCK sui nemici (camera del gioco modalità 3, elenco +0x1F8, attuale +0x22C o richiesta +0x230) R3 non cambia
    ; camera: non si vedrebbe (la camera del lock è del gioco) e togliendo il lock ti ritrovavi l'altra (John)
    lwz r7, 0x1F8(r31)
    lwz r9, 0x22C(r31)
    cmpw r7, r9
    beq r3_fatto
    lwz r9, 0x230(r31)
    cmpw r7, r9
    beq r3_fatto
    lbz r9, 0x80(r12)
    xori r9, r9, 1
    stb r9, 0x80(r12)
    li r9, 0
    stw r9, 0x200(r12)
    b r3_fatto
r3_su:
    ; pausa di 12 aggiornamenti della camera (~0,3 s) dopo ogni pressione: contro i rimbalzi del tasto (con 40 = ~1 s
    ; il secondo R3 veloce veniva ignorato)
    lbz r9, 0x81(r12)
    cmpwi r9, 0
    beq r3_fatto
    addi r9, r9, -1
    stb r9, 0x81(r12)
r3_fatto:
    ; camera attiva: 0 moderna, 1 classica (nell'app "Migliorata"), 2 originale, 3 prima persona
    lbz r9, 0x80(r12)
    cmpwi r9, 0
    lbz r9, 0x84(r12)
    beq modo_letto
    lbz r9, 0x85(r12)
modo_letto:
    li r7, 0
    cmpwi r9, 2
    bne non_originale
    li r7, 1
non_originale:
    stb r7, 0x10(r12)
    ; prima persona (3): come la moderna, con 817F0087 = 1
    li r7, 0
    cmpwi r9, 3
    bne non_prima
    li r7, 1
    li r9, 0
non_prima:
    ; amazing (4): come la moderna (r9 = 0) con 817F05A0 = 1; entrando salvo il FOV (base), uscendo lo rimetto
    li r11, 0
    cmpwi r9, 4
    blt non_amaz_m
    addi r11, r9, -3
    li r9, 0
    b non_amaz
non_amaz_m:
    ; moderna (non prima persona): 817F05A0 = 3, serie PS4 (boost e tuffo)
    cmpwi r9, 0
    bne non_amaz
    cmpwi r7, 0
    bne non_amaz
    li r11, 3
non_amaz:
    lbz r10, 0x5A0(r12)
    stb r11, 0x5A0(r12)
    cmpwi r11, 0
    beq amaz_niente_copia
    ; serie di costanti in uso -> 817F3900 (cinematica 3800, amazing 3880)
    li r5, 0x3800
    cmpwi r11, 2
    bne amaz_non_tasm
    li r5, 0x3880
amaz_non_tasm:
    cmpwi r11, 3
    bne amaz_serie
    li r5, 0x3980
amaz_serie:
    add r5, r5, r12
    lwz r0, 0x0(r5)
    stw r0, 0x3900(r12)
    lwz r0, 0x4(r5)
    stw r0, 0x3904(r12)
    lwz r0, 0x8(r5)
    stw r0, 0x3908(r12)
    lwz r0, 0xc(r5)
    stw r0, 0x390c(r12)
    lwz r0, 0x10(r5)
    stw r0, 0x3910(r12)
    lwz r0, 0x14(r5)
    stw r0, 0x3914(r12)
    lwz r0, 0x18(r5)
    stw r0, 0x3918(r12)
    lwz r0, 0x1c(r5)
    stw r0, 0x391c(r12)
    lwz r0, 0x20(r5)
    stw r0, 0x3920(r12)
    lwz r0, 0x24(r5)
    stw r0, 0x3924(r12)
    lwz r0, 0x28(r5)
    stw r0, 0x3928(r12)
    lwz r0, 0x2c(r5)
    stw r0, 0x392c(r12)
    lwz r0, 0x30(r5)
    stw r0, 0x3930(r12)
    lwz r0, 0x34(r5)
    stw r0, 0x3934(r12)
    lwz r0, 0x38(r5)
    stw r0, 0x3938(r12)
    lwz r0, 0x3c(r5)
    stw r0, 0x393c(r12)
    lwz r0, 0x40(r5)
    stw r0, 0x3940(r12)
    lwz r0, 0x44(r5)
    stw r0, 0x3944(r12)
    lwz r0, 0x48(r5)
    stw r0, 0x3948(r12)
    lwz r0, 0x4c(r5)
    stw r0, 0x394c(r12)
    lwz r0, 0x50(r5)
    stw r0, 0x3950(r12)
    lwz r0, 0x54(r5)
    stw r0, 0x3954(r12)
    lwz r0, 0x58(r5)
    stw r0, 0x3958(r12)
    lwz r0, 0x5c(r5)
    stw r0, 0x395c(r12)
    lwz r0, 0x60(r5)
    stw r0, 0x3960(r12)
    lwz r0, 0x64(r5)
    stw r0, 0x3964(r12)
    lwz r0, 0x68(r5)
    stw r0, 0x3968(r12)
    lwz r0, 0x6c(r5)
    stw r0, 0x396c(r12)
    lwz r0, 0x70(r5)
    stw r0, 0x3970(r12)
    lwz r0, 0x74(r5)
    stw r0, 0x3974(r12)
    ; amazing: spalla scelta con le frecce (idea di John): destra da sola = camera a destra di Spidey (817F05C0 = 0, di
    ; base: la memoria parte a zero; John 2026-10-10 "preferisco la spalla destra"), sinistra da sola = a sinistra (1).
    ; Con Z (HUD) o sinistra+destra (LB) niente.
    cmpwi r11, 2
    bne amaz_lato_ok
    lis r5, {pad >> 16:#x}
    ori r5, r5, {pad & 0xFFFF:#x}
    lhz r0, 0(r5)
    andi. r0, r0, 0x13
    cmpwi r0, 1
    bne amaz_non_sx
    li r0, 1
    stb r0, 0x5C0(r12)
    b amaz_lato_ok
amaz_non_sx:
    cmpwi r0, 2
    bne amaz_lato_ok
    li r0, 0
    stb r0, 0x5C0(r12)
amaz_lato_ok:
amaz_niente_copia:
    cmpw r10, r11
    beq amaz_stesso
    cmpwi r11, 0
    beq amaz_esci
    cmpwi r10, 0
    bne amaz_stesso
    lis r10, {(fov + 0x8000) >> 16:#x}
    b amaz_entra
amaz_esci:
    lis r10, {(fov + 0x8000) >> 16:#x}
    lfs f0, 0x5A4(r12)
    stfs f0, {fov & 0xFFFF:#x}(r10)
    b amaz_stesso
amaz_entra:
    lfs f0, {fov & 0xFFFF:#x}(r10)
    stfs f0, 0x5A4(r12)
    stfs f0, 0x5B4(r12)
    li r10, 0
    stw r10, 0x5B0(r12)
    stw r10, 0x5B8(r12)
    stw r10, 0x5BC(r12)
    stw r10, 0x200(r12)
amaz_stesso:
    ; il gioco stringe il FOV fino a 1.2 rad (69°) quando la camera è vicina al pavimento e guarda in su (0x80229640:
    ; FOV = mix(FOV, 1.2, fwd_y / 0.4), acceso dal byte [r13-0x7778], letto solo lì, uguale in tutte le versioni):
    ; in prima persona col FOV a 110° alzando la visuale da terra sembrava uno zoom -> spento solo in prima persona
    xori r11, r7, 1
    stb r11, -0x7778(r13)
    lis r8, {(fov + 0x8000) >> 16:#x}
    lbz r11, 0x87(r12)
    stb r7, 0x87(r12)
    cmpw r11, r7
    beq stessa_vista
    li r11, 0
    stw r11, 0x200(r12)
    stw r11, 0x3A4(r12)
    stw r11, 0x2C0(r12)
    stb r11, {prima.G_PRONTI:#x}(r12)
    li r11, 1
    stb r11, 0x4FD(r12)
    cmpwi r7, 0
    beq fov_esci
    lfs f0, {fov & 0xFFFF:#x}(r8)
    stfs f0, 0x2B8(r12)
    lfs f0, 0x27C(r12)
    stfs f0, 0x4DC(r12)
    b stessa_vista
fov_esci:
    lfs f0, 0x2B8(r12)
    stfs f0, {fov & 0xFFFF:#x}(r8)
stessa_vista:
    cmpwi r9, 0
    bne classica
    ; solo con le camere "di gioco" del gioco (modalità 1-8: normale, manuale, swing, palo... + la 13: attaccato al muro con B; NON la 3 = lock): con le altre
    ; (filmati, script, cecchino...) lascio la sua e la prossima volta riparto da lì
    ; tranne la 3 (elenco +0x1F8) = camera del LOCK sui nemici (freccia giù / L3 / R3, misurato sullo stato di John coi
    ; teppisti): la camera del gioco inquadra il nemico agganciato, la nostra non lo sapeva fare (John: "il lock non funziona")
    lwz r9, 0x22C(r31)
    lwz r7, 0x1F8(r31)
    cmpw r7, r9
    beq modo_no
    addi r8, r31, 0x1F0
    li r11, 8
    mtctr r11
cerca_modo:
    lwz r7, 0(r8)
    cmpw r7, r9
    beq modo_ok
    addi r8, r8, 4
    bdnz cerca_modo
    lwz r7, 0x220(r31)
    cmpw r7, r9
    beq modo_ok
modo_no:
    li r9, 0
    stw r9, 0x200(r12)
    lbz r11, 0x5A0(r12)
    cmpwi r11, 0
    beq filmato_amaz_no
    lis r8, {(fov + 0x8000) >> 16:#x}
    lfs f0, 0x5A4(r12)
    stfs f0, {fov & 0xFFFF:#x}(r8)
    stfs f0, 0x5B4(r12)
filmato_amaz_no:
    ; filmati, cecchino...: in prima persona rimetto il FOV di prima (il 110° vale solo per la nostra vista)
    lbz r11, 0x87(r12)
    cmpwi r11, 0
    beq classica
    lis r8, {(fov + 0x8000) >> 16:#x}
    lfs f0, 0x2B8(r12)
    stfs f0, {fov & 0xFFFF:#x}(r8)
    b classica
modo_ok:
    ; amazing: FOV = base + boost * fov_boost_a (se qualcun altro ha cambiato il FOV, es. il menu, è la base nuova)
    lbz r11, 0x5A0(r12)
    cmpwi r11, 0
    beq amaz_fov_no
    lis r8, {(fov + 0x8000) >> 16:#x}
    lfs f0, {fov & 0xFFFF:#x}(r8)
    lfs f1, 0x5B4(r12)
    fcmpu f0, f1
    beq amaz_fov_nostro
    stfs f0, 0x5A4(r12)
amaz_fov_nostro:
    lfs f0, 0x5A4(r12)
    lfs f1, 0x5B0(r12)
    lfs f2, 0x3928(r12)
    fmadds f0, f1, f2, f0
    lfs f1, 0x3958(r12)
    fadds f0, f0, f1
    lfs f1, 0x5D0(r12)
    lfs f2, 0x3A14(r12)
    fmadds f0, f1, f2, f0
    stfs f0, {fov & 0xFFFF:#x}(r8)
    stfs f0, 0x5B4(r12)
amaz_fov_no:
    lbz r11, 0x87(r12)
    cmpwi r11, 0
    beq fov_ok
    ; attaccato al muro col tasto (stato di Spidey 2; la corsa sui muri è il 6): FOV più largo di C_realistica (0.25
    ; rad = +14°, idea di John: si vedono di più le mani che si arrampicano); passa piano (alfa_miscela per fotogramma)
    ; -> FOV della prima persona in 817F04DC (all'entrata in prima persona = fov_prima)
    lfs f0, 0x27C(r12)
    lis r7, {stato >> 16:#x}
    ori r7, r7, {stato & 0xFFFF:#x}
    lwz r7, 0(r7)
    cmpwi r7, 2
    bne fov_mira
    lfs f1, 0x2B4(r12)
    fadds f0, f0, f1
fov_mira:
    lfs f1, 0x4DC(r12)
    fsubs f0, f0, f1
    lfs f2, 0x2D0(r12)
    fmadds f0, f0, f2, f1
    stfs f0, 0x4DC(r12)
    lis r8, {(fov + 0x8000) >> 16:#x}
    stfs f0, {fov & 0xFFFF:#x}(r8)
fov_ok:
    lwz r10, 0x30(r31)
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
    lis r9, {s >> 16:#x}
    ori r9, r9, {s & 0xFFFF:#x}
    lfs f1, 0(r9)
    lfs f2, 4(r9)
    lfs f3, 8(r9)
    ; A TESTA IN GIÙ SOTTO UN SOFFITTO (asse su del corpo di Spidey verso il basso, y < -0.5): la sua posizione è il punto
    ; d'attacco, cioè SUL soffitto -> i raggi dei muri partivano dentro la lastra e la camera ci finiva dentro (John:
    ; si vedeva attraverso). Sposto il riferimento di 0.75 m lungo l'asse del corpo (verso la testa = sotto il soffitto);
    ; passa dal punto morbido qui sotto, quindi entra ed esce senza scatti. Non in prima persona (lì conta la testa).
    ; 817F0558 = 1 a testa in giù: l'elevazione non va sopra 0 (guardando dall'alto il soffitto spingeva la camera dentro
    ; il corpo di Spidey)
    li r11, 0
    stb r11, 0x558(r12)
    lbz r11, 0x87(r12)
    cmpwi r11, 0
    bne soff_corpo_no
    lis r11, {stato >> 16:#x}
    ori r11, r11, {stato & 0xFFFF:#x}
    lwz r11, 0(r11)
    cmpwi r11, 2
    bne soff_corpo_no
    lwz r11, 0x164(r31)
    cmpwi r11, 0
    bge soff_corpo_no
    lwz r11, 0x30(r11)
    cmpwi r11, 0
    bge soff_corpo_no
    lfs f7, 0x150(r12)
    lfs f5, 0x14(r11)
    fneg f6, f5
    fcmpu f6, f7
    ble soff_corpo_no
    fmadds f7, f7, f7, f7
    lfs f6, 0x10(r11)
    fmadds f1, f6, f7, f1
    fmadds f2, f5, f7, f2
    lfs f6, 0x18(r11)
    fmadds f3, f6, f7, f3
    li r11, 1
    stb r11, 0x558(r12)
soff_corpo_no:
    lfs f12, 0x150(r12)
    ; ---- prima volta: parto dalla camera del gioco
    lwz r11, 0x200(r12)
    cmpwi r11, 0
    bne pronto
    lfs f4, 0x20(r10)
    lfs f5, 0x28(r10)
    fmuls f7, f4, f4
    fmadds f7, f5, f5, f7
    {_rsqrt("f8", "f7", "f9")}
    fmuls f4, f4, f8
    fmuls f5, f5, f8
    stfs f4, 0x204(r12)
    stfs f5, 0x208(r12)
    lfs f4, 0x24(r10)
    fneg f4, f4
    stfs f4, 0x20C(r12)
    stfs f1, 0x210(r12)
    stfs f2, 0x214(r12)
    stfs f3, 0x218(r12)
    stfs f1, 0x228(r12)
    stfs f2, 0x22C(r12)
    stfs f3, 0x230(r12)
    lfs f4, 0x180(r12)
    stfs f4, 0x21C(r12)
    stfs f4, 0x23C(r12)
    lfs f4, 0x184(r12)
    stfs f4, 0x220(r12)
    li r11, 0
    stw r11, 0x224(r12)
    stw r11, 0x234(r12)
    stw r11, 0x238(r12)
    stw r11, 0x258(r12)
    li r11, 1
    stw r11, 0x200(r12)
pronto:
    ; ---- levetta destra: f9 = x, f10 = y ; contatore fotogrammi senza levetta
    lis r8, {pad >> 16:#x}
    ori r8, r8, {pad & 0xFFFF:#x}
    {_stick(4, "f9")}
    {_stick(5, "f10")}
    lfs f11, 0x1AC(r12)
    lfs f6, 0x1C8(r12)
    fabs f4, f9
    fsubs f4, f4, f11
    fabs f5, f10
    fsubs f5, f5, f11
    lwz r11, 0x224(r12)
    addi r11, r11, 1
    fcmpu f4, f6
    bge toccata
    fcmpu f5, f6
    bge toccata
    fmr f9, f6
    fmr f10, f6
    b dopo_tocco
toccata:
    li r11, 0
dopo_tocco:
    stw r11, 0x224(r12)
    ; giro orizzontale: a = x*k ; c = 1 - a*a/2 ; s = a
    lfs f4, 0x160(r12)
    fmuls f4, f9, f4
    ; camera al limite dello zoom contro un muro (flag 258, rifatto ogni fotogramma): la levetta che la spingerebbe
    ; ancora verso il muro non conta; nell'altra direzione si gira subito
    stfs f4, 0x260(r12)
    lwz r11, 0x258(r12)
    cmpwi r11, 0
    beq a_libera
    lfs f5, 0x25C(r12)
    fmuls f5, f5, f4
    lfs f6, 0x1C8(r12)
    fcmpu f5, f6
    ble a_libera
    fmr f4, f6
a_libera:
    fmuls f5, f4, f4
    lfs f7, 0x158(r12)
    fnmsubs f5, f5, f12, f7
    lfs f6, 0x204(r12)
    lfs f7, 0x208(r12)
    fmuls f8, f6, f5
    fnmsubs f8, f7, f4, f8
    fmuls f11, f6, f4
    fmadds f11, f7, f5, f11
    stfs f8, 0x204(r12)
    stfs f11, 0x208(r12)
    ; elevazione (con limiti)
    lfs f4, 0x164(r12)
    lfs f5, 0x20C(r12)
    fmadds f5, f10, f4, f5
    lfs f6, 0x168(r12)
    lbz r11, 0x87(r12)
    cmpwi r11, 0
    beq emin_ok
    lfs f6, 0x294(r12)
emin_ok:
    fsubs f7, f5, f6
    fsel f5, f7, f5, f6
    lfs f6, 0x16C(r12)
    fsubs f7, f6, f5
    fsel f5, f7, f5, f6
    ; a testa in giù sotto un soffitto (817F0558): sopra 0 l'elevazione si dimezza a ogni fotogramma (niente scatto
    ; entrando, e la levetta non la porta più su di un passo)
    lbz r11, 0x558(r12)
    cmpwi r11, 0
    beq e_soff_no
    lfs f6, 0x150(r12)
    fmuls f7, f5, f6
    fsel f5, f5, f7, f5
e_soff_no:
    stfs f5, 0x20C(r12)
    ; ---- velocità orizzontale smorzata (per fotogramma): f7, f8
    lfs f4, 0x228(r12)
    lfs f5, 0x230(r12)
    fsubs f4, f1, f4
    fsubs f5, f3, f5
    ; spostamento vero di questo fotogramma (anche in verticale), per l'anticipo della prima persona: 2A0..2A8
    stfs f4, 0x2A0(r12)
    stfs f5, 0x2A8(r12)
    lfs f6, 0x22C(r12)
    fsubs f6, f2, f6
    stfs f6, 0x2A4(r12)
    ; ammorbidito (per il tuffo della moderna): 817F05C4
    lfs f7, 0x5C4(r12)
    fsubs f9, f6, f7
    lfs f8, 0x1B0(r12)
    fmadds f7, f9, f8, f7
    stfs f7, 0x5C4(r12)
    ; TUFFO (serie delle camere, non in prima persona): angolo in più T (817F05C8) sommato all'elevazione quando si
    ; calcola la direzione; verso k_tuffo * clamp((-vy - vy0) * inv_vy) in caduta libera (stato 5), 0 altrimenti.
    ; A parte da e (che si muove solo andando avanti): vale anche cadendo dritti, e la levetta resta com'era.
    lfs f9, 0x1C8(r12)
    lbz r11, 0x87(r12)
    cmpwi r11, 0
    bne tuffo_zero
    lbz r11, 0x5A0(r12)
    cmpwi r11, 0
    beq tuffo_zero
    ; PICCHIATA VERA (John): L3 (freccia giù senza Z; prima LT) tenuto durante l'animazione del tuffo -> P (817F05D0) verso 1: camera più alta
    ; dietro le spalle che guarda giù lungo la caduta, più vicina, FOV più largo. Animazione del tuffo = posa dello
    ; scheletro: rotazione della testa (vedi sotto) con vy <= vy_posa per 12 fotogrammi
    ; di fila (817F05CC; nelle cadute coi trick la posa gira e il conto riparte). Misurato su 4 tuffi di John.
    li r10, 0
    lfs f10, 0x1C8(r12)
    lis r11, {stato >> 16:#x}
    ori r11, r11, {stato & 0xFFFF:#x}
    lwz r11, 0(r11)
    ; fuori dallo stato 4 il tuffo non è più "comandato con L3" (817F05D6); l'aggancio della picchiata (05D4) resta
    ; anche nello stato 5 (cadute a testa in giù), finisce alla ragnatela o a terra
    cmpwi r11, 4
    beq comandato_ok
    li r9, 0
    stb r9, 0x5D6(r12)
    cmpwi r11, 5
    beq comandato_ok
    stb r9, 0x5D4(r12)
comandato_ok:
    cmpwi r11, 5
    beq tuffo_aria
    ; stato 4 = buttato dal bordo di un palazzo senza saltare (il gioco fa il tuffo a testa in giù)
    cmpwi r11, 4
    bne tuffo_verso
tuffo_aria:
    ; vy = min(velocità verticale del gioco (m/s, Spidey +0x1710), spostamento ammorbidito * 60): nello stato 4 il
    ; gioco non la scrive (resta 0) e Spidey arriva a -160 m/s
    lis r11, 0x80AD
    lfs f6, 0x1850(r11)
    lfs f8, 0x5C4(r12)
    lfs f11, 0x3A28(r12)
    fmuls f8, f8, f11
    fsubs f11, f6, f8
    fsel f6, f11, f8, f6
    stfs f6, 0x5D8(r12)
    ; quanto: clamp((-vy - vy0) * inv); 0 se Spidey è sceso meno di caduta_min dal punto più alto del salto
    ; (+0x1C44: niente picchiata nei saltelli tra uno swing e l'altro)
    fneg f9, f6
    lfs f8, 0x3964(r12)
    fsubs f9, f9, f8
    lfs f8, 0x3968(r12)
    fmuls f9, f9, f8
    lfs f8, 0x1C8(r12)
    fsel f9, f9, f9, f8
    lfs f8, 0x158(r12)
    fsubs f11, f8, f9
    fsel f9, f11, f9, f8
    lfs f11, 0x1D84(r11)
    fsubs f11, f11, f2
    lfs f8, 0x3970(r12)
    fsubs f11, f11, f8
    lfs f8, 0x1C8(r12)
    fsel f9, f11, f9, f8
    lfs f8, 0x3960(r12)
    fmuls f9, f9, f8
    ; tuffo fatto partire da L3 (tuffo_comando): la picchiata vera parte subito, senza aspettare che l'animazione
    ; abbia girato Spidey a testa in giù (su PS4 la camera si muove appena premi L3).
    ; Solo MENTRE L3 è tenuto (John): un colpetto di L3 = tuffo senza la camera della picchiata.
    ; E solo quando Spidey ha iniziato a girarsi (radice +0x04 > radice_comando): durante un trick o l'avvitamento
    ; della corsa sul muro il gioco finisce prima quelli, e la camera cambiava senza il tuffo
    ; Tenuto per TENUTA_PICCHIATA fotogrammi video (contatore VI del gioco, +60 al secondo: il programma non gira a
    ; ritmo fisso) la picchiata si AGGANCIA e resta anche lasciando L3, fino alla ragnatela o a terra (John: tenerlo a
    ; lungo è scomodo). Prima di PARTENZA_PICCHIATA la camera non si muove: un colpetto (solo tuffo) non la tocca.
    ; 817F05D4: 0 niente, 1 sta contando (VI d'inizio in 817F05F8), 2 agganciata; azzerato quando parte il tuffo e
    ; fuori dallo stato 4; lasciato prima di agganciare torna a 0 (ripremendo riparte il conto).
    lbz r11, 0x5D6(r12)
    cmpwi r11, 0
    beq posa_vera
    li r10, 100
    lbz r9, 0x5D4(r12)
    lis r11, {pad >> 16:#x}
    ori r11, r11, {pad & 0xFFFF:#x}
    lhz r11, 0(r11)
    andi. r11, r11, 0x14
    cmpwi r11, 4
    bne cm_lasciato
    cmpwi r9, 2
    beq cm_ok
    lis r11, {(vi + 0x8000) >> 16:#x}
    lwz r11, {vi & 0xFFFF:#x}(r11)
    cmpwi r9, 1
    beq cm_conta
    stw r11, 0x5F8(r12)
    li r9, 1
    stb r9, 0x5D4(r12)
    b tuffo_verso
cm_conta:
    lwz r9, 0x5F8(r12)
    subf r9, r9, r11
    cmpwi r9, {TENUTA_PICCHIATA}
    blt cm_presto
    li r9, 2
    stb r9, 0x5D4(r12)
    b cm_ok
cm_presto:
    cmpwi r9, {PARTENZA_PICCHIATA}
    blt tuffo_verso
    b cm_ok
cm_lasciato:
    cmpwi r9, 2
    beq cm_ok
    li r9, 0
    stb r9, 0x5D4(r12)
    b tuffo_verso
cm_ok:
    lwz r11, 0x164(r31)
    cmpwi r11, 0
    beq tuffo_verso
    lwz r11, 0x134(r11)
    cmpwi r11, 0
    beq tuffo_verso
    lfs f6, 0x4(r11)
    lfs f8, 0x3A44(r12)
    fcmpu f6, f8
    blt tuffo_verso
    lfs f10, 0x158(r12)
    b tuffo_verso
posa_vera:
    ; tuffo NON fatto da L3 (buttato dal palazzo senza saltare, o caduta a testa in giù): anche qui L3 tenuto
    ; TENUTA_PICCHIATA fotogrammi aggancia la picchiata (John: lasciando L3 la camera tornava normale)
    lbz r9, 0x5D4(r12)
    cmpwi r9, 2
    bne pv_normale
    li r10, 100
    lfs f10, 0x158(r12)
    b tuffo_verso
pv_normale:
    lfs f8, 0x3A08(r12)
    fcmpu f6, f8
    bgt posa_no
    lwz r11, 0x164(r31)
    cmpwi r11, 0
    beq posa_no
    lwz r11, 0x134(r11)
    cmpwi r11, 0
    beq posa_no
    ; per le prove (letti da fuori): y delle righe di testa (5), radice (0) e osso 3 al momento della camera
    lfs f8, 0x164(r11)
    stfs f8, 0x5E0(r12)
    lfs f8, 0x144(r11)
    stfs f8, 0x5DC(r12)
    lfs f8, 0x4(r11)
    stfs f8, 0x5E4(r12)
    lfs f8, 0x14(r11)
    stfs f8, 0x5E8(r12)
    lfs f8, 0x24(r11)
    stfs f8, 0x5EC(r12)
    lfs f8, 0xC4(r11)
    stfs f8, 0x5F0(r12)
    lfs f8, 0xD4(r11)
    stfs f8, 0x5F4(r12)
    ; tuffo = A TESTA IN GIÙ: y della prima riga della radice (osso 0, +0x04) > rad_min (provato sul tetto: tuffo
    ; buttandosi dal bordo +0.5..+0.8, caduta in piedi dopo un salto -0.8..-0.9, salto caricato da fermo -0.9).
    ; La testa NON basta (uguale nei due casi) e le POSIZIONI delle ossa qui non sono quelle finali.
    lfs f6, 0x4(r11)
    lfs f8, 0x3A00(r12)
    fcmpu f6, f8
    blt posa_no
    lbz r10, 0x5CC(r12)
    addi r10, r10, 1
    cmpwi r10, 100
    ble posa_conta
    li r10, 100
posa_conta:
    cmpwi r10, 20
    blt tuffo_verso
    lis r11, {pad >> 16:#x}
    ori r11, r11, {pad & 0xFFFF:#x}
    lhz r11, 0(r11)
    andi. r11, r11, 0x14
    cmpwi r11, 4
    bne pv_lasciato
    lbz r9, 0x5D4(r12)
    lis r11, {(vi + 0x8000) >> 16:#x}
    lwz r11, {vi & 0xFFFF:#x}(r11)
    cmpwi r9, 1
    beq pv_conta
    stw r11, 0x5F8(r12)
    li r9, 1
    stb r9, 0x5D4(r12)
    b pv_si
pv_conta:
    lwz r9, 0x5F8(r12)
    subf r9, r9, r11
    cmpwi r9, {TENUTA_PICCHIATA}
    blt pv_si
    li r9, 2
    stb r9, 0x5D4(r12)
pv_si:
    lfs f10, 0x158(r12)
    b tuffo_verso
pv_lasciato:
    li r9, 0
    stb r9, 0x5D4(r12)
    b tuffo_verso
posa_no:
    li r10, 0
tuffo_verso:
    stb r10, 0x5CC(r12)
    lbz r11, 0x89(r12)
    andi. r11, r11, 2
    beq picchiata_si
    lfs f10, 0x1C8(r12)
picchiata_si:
    lfs f8, 0x5D0(r12)
    fsubs f6, f10, f8
    ; entra con alfa_picchiata, esce più in fretta (alfa_picchiata_giu: su PS4 alla ragnatela torna dietro in ~0,2 s)
    lfs f11, 0x3A18(r12)
    lfs f7, 0x3A3C(r12)
    fsel f11, f6, f11, f7
    fmadds f8, f6, f11, f8
    stfs f8, 0x5D0(r12)
    lfs f8, 0x5C8(r12)
    fsubs f6, f9, f8
    ; sale piano (alfa_tuffo), scende in fretta (alfa_tuffo_giu: su PS4 appena parte lo swing la camera torna dietro
    ; in ~0,2 s)
    lfs f9, 0x396C(r12)
    lfs f11, 0x3A34(r12)
    fsel f9, f6, f9, f11
    fmadds f9, f6, f9, f8
    stfs f9, 0x5C8(r12)
    b tuffo_fatto
tuffo_zero:
    stfs f9, 0x5C8(r12)
    stfs f9, 0x5D0(r12)
    li r10, 0
    stb r10, 0x5CC(r12)
tuffo_fatto:
    lfs f6, 0x1B0(r12)
    lfs f7, 0x234(r12)
    fsubs f9, f4, f7
    fmadds f7, f9, f6, f7
    stfs f7, 0x234(r12)
    lfs f8, 0x238(r12)
    fsubs f9, f5, f8
    fmadds f8, f9, f6, f8
    stfs f8, 0x238(r12)
    stfs f1, 0x228(r12)
    stfs f2, 0x22C(r12)
    stfs f3, 0x230(r12)
    ; ---- rientro dietro la direzione di marcia (più veloce quanto più vai veloce) + altezza che si rimette
    fmuls f9, f7, f7
    fmadds f9, f8, f8, f9
    lfs f5, 0x1A4(r12)
    lbz r11, 0x87(r12)
    cmpwi r11, 0
    beq soglia_ok
    lfs f5, 0x28C(r12)
soglia_ok:
    fcmpu f9, f5
    blt niente_rientro
    ; attesa (fotogrammi senza levetta) confrontata da intero: 30
    lwz r11, 0x224(r12)
    cmpwi r11, 30
    blt niente_rientro
    ; sul palo (stato 8) niente rientro: girando, la posizione di Spidey fa un cerchio attorno al palo e la camera
    ; inseguiva quella "direzione di marcia" girando piano piano (John)
    lis r11, {stato >> 16:#x}
    ori r11, r11, {stato & 0xFFFF:#x}
    lwz r11, 0(r11)
    cmpwi r11, 8
    beq niente_rientro
    {_rsqrt("f10", "f9", "f11")}
    ; velocità = v2 / sqrt(v2) ; passo = min(rientro + k*velocità, rientro_max)
    fmuls f11, f9, f10
    lfs f4, 0x19C(r12)
    lfs f5, 0x1D0(r12)
    fmadds f4, f11, f5, f4
    lfs f5, 0x1D4(r12)
    fsubs f6, f5, f4
    fsel f4, f6, f4, f5
    fmuls f7, f7, f10
    fmuls f8, f8, f10
    lfs f5, 0x204(r12)
    lfs f6, 0x208(r12)
    fsubs f9, f7, f5
    fmadds f5, f9, f4, f5
    fsubs f9, f8, f6
    fmadds f6, f9, f4, f6
    fmuls f9, f5, f5
    fmadds f9, f6, f6, f9
    {_rsqrt("f10", "f9", "f11")}
    fmuls f5, f5, f10
    fmuls f6, f6, f10
    stfs f5, 0x204(r12)
    stfs f6, 0x208(r12)
    ; altezza che si rimette: e += (e_def - e) * alfa_e   (e_def terra se a terra, aria altrimenti)
    lis r11, {stato >> 16:#x}
    ori r11, r11, {stato & 0xFFFF:#x}
    lwz r11, 0(r11)
    li r7, 0x1E0
    cmpwi r11, 1
    beq e_terra_ok
    li r7, 0x1E4
e_terra_ok:
    lbz r10, 0x5A0(r12)
    cmpwi r10, 0
    beq e_amaz_no
    addi r7, r7, {0x3918 - 0x1E0:#x}
e_amaz_no:
    lbz r9, 0x87(r12)
    cmpwi r9, 0
    beq e_scelta
    li r7, 0x278
    cmpwi r11, 3
    bne e_scelta
    li r7, 0x280
e_scelta:
    add r7, r7, r12
    lfs f4, 0(r7)
    lfs f5, 0x20C(r12)
    lfs f6, 0x1E8(r12)
    cmpwi r9, 0
    beq alfa_e_ok
    lfs f6, 0x298(r12)
alfa_e_ok:
    fsubs f7, f4, f5
    fmadds f5, f7, f6, f5
    stfs f5, 0x20C(r12)
niente_rientro:
    ; ---- amazing: boost di velocità (817F05B0) e rollio nelle curve (817F05B8)
    lbz r10, 0x5A0(r12)
    cmpwi r10, 0
    beq amaz_vel_no
    lfs f4, 0x234(r12)
    lfs f5, 0x238(r12)
    fmuls f6, f4, f4
    fmadds f6, f5, f5, f6
    lfs f7, 0x290(r12)
    fadds f6, f6, f7
    frsqrte f7, f6
    fmuls f8, f6, f7
    lfs f9, 0x3920(r12)
    fsubs f8, f8, f9
    lfs f9, 0x3924(r12)
    fmuls f8, f8, f9
    lfs f9, 0x1C8(r12)
    fsel f8, f8, f8, f9
    lfs f9, 0x158(r12)
    fsubs f10, f9, f8
    fsel f8, f10, f8, f9
    lfs f9, 0x5B0(r12)
    fsubs f10, f8, f9
    lfs f11, 0x3930(r12)
    fmadds f9, f10, f11, f9
    stfs f9, 0x5B0(r12)
    lfs f10, 0x5A8(r12)
    lfs f11, 0x5AC(r12)
    stfs f4, 0x5A8(r12)
    stfs f5, 0x5AC(r12)
    fmuls f10, f10, f5
    fnmsubs f10, f11, f4, f10
    fmuls f7, f7, f7
    fmuls f10, f10, f7
    lfs f11, 0x3934(r12)
    fmuls f10, f10, f11
    fmuls f10, f10, f9
    ; dondolio (TASM forte, PS4 leggero): inclinazione verso il lato dove Spidey si sposta rispetto alla vista
    ; (v_lat = vx*dz - vz*dx, positiva = verso destra dello schermo; destra in giù = s negativo)
    lfs f6, 0x208(r12)
    fmuls f6, f4, f6
    lfs f7, 0x204(r12)
    fnmsubs f6, f5, f7, f6
    lfs f7, 0x3974(r12)
    fnmsubs f10, f7, f6, f10
    lfs f11, 0x3938(r12)
    fsubs f7, f11, f10
    fsel f10, f7, f10, f11
    fneg f11, f11
    fsubs f7, f10, f11
    fsel f10, f7, f10, f11
    lis r11, {stato >> 16:#x}
    ori r11, r11, {stato & 0xFFFF:#x}
    lwz r11, 0(r11)
    cmpwi r11, 1
    beq rollio_zero
    cmpwi r11, 8
    bne rollio_aria
rollio_zero:
    fsubs f10, f10, f10
rollio_aria:
    lfs f11, 0x5B8(r12)
    fsubs f7, f10, f11
    lfs f6, 0x393C(r12)
    fmadds f11, f7, f6, f11
    stfs f11, 0x5B8(r12)
amaz_vel_no:
    ; ---- distanza e altezza secondo la situazione (1 terra, 8 palo -> terra; 3 swing; resto aria)
    lis r11, {stato >> 16:#x}
    ori r11, r11, {stato & 0xFFFF:#x}
    lwz r11, 0(r11)
    li r7, 0x180
    cmpwi r11, 3
    bne non_swing
    li r7, 0x190
    b scelto
non_swing:
    cmpwi r11, 1
    beq scelto
    cmpwi r11, 8
    beq scelto
    li r7, 0x188
scelto:
    lbz r10, 0x5A0(r12)
    cmpwi r10, 0
    beq dh_amaz_no
    addi r7, r7, {0x3900 - 0x180:#x}
dh_amaz_no:
    lbz r11, 0x87(r12)
    cmpwi r11, 0
    beq dh_ok
    lfs f4, 0x270(r12)
    stfs f4, 0x21C(r12)
    lfs f4, 0x1C8(r12)
    stfs f4, 0x220(r12)
    b dh_fatto
dh_ok:
    add r7, r7, r12
    lfs f4, 0(r7)
    lfs f5, 4(r7)
    lbz r10, 0x5A0(r12)
    cmpwi r10, 0
    beq dh_boost_no
    lfs f6, 0x5B0(r12)
    lfs f7, 0x392C(r12)
    fmadds f4, f6, f7, f4
    lfs f6, 0x5D0(r12)
    lfs f7, 0x3A10(r12)
    fmuls f6, f6, f7
    fnmsubs f4, f4, f6, f4
    lfs f6, 0x40(r7)
    lbz r10, 0x5C0(r12)
    cmpwi r10, 1
    bne lato_destro
    lfs f7, 0x3A2C(r12)
    fmuls f6, f6, f7
lato_destro:
    lfs f7, 0x44(r7)
    lfs f8, 0x234(r12)
    lfs f9, 0x208(r12)
    fmuls f8, f8, f9
    lfs f9, 0x238(r12)
    lfs f10, 0x204(r12)
    fnmsubs f8, f9, f10, f8
    fnmsubs f6, f7, f8, f6
    lfs f9, 0x395C(r12)
    fsubs f10, f9, f6
    fsel f6, f10, f6, f9
    fneg f9, f9
    fsubs f10, f6, f9
    fsel f6, f10, f6, f9
    lfs f7, 0x5BC(r12)
    fsubs f6, f6, f7
    lfs f8, 0x198(r12)
    fmadds f7, f6, f8, f7
    stfs f7, 0x5BC(r12)
dh_boost_no:
    lfs f6, 0x198(r12)
    ; in picchiata la distanza segue subito (alfa_D + P * alfa_D_picchiata): prima l'angolo arrivava e la camera
    ; restava lontana per un attimo
    ; memoria della picchiata (817F05FC = max(P, memoria * 0.95)): uscendo P cala in fretta e la distanza restava
    ; vicina; così la distanza segue svelta ancora per ~1 s
    lfs f7, 0x5D0(r12)
    lfs f8, 0x5FC(r12)
    lfs f9, 0x3A40(r12)
    fmuls f8, f8, f9
    fsubs f9, f7, f8
    fsel f8, f9, f7, f8
    stfs f8, 0x5FC(r12)
    lfs f7, 0x3A30(r12)
    fmadds f6, f8, f7, f6
    ; ... e anche col tuffo automatico T (uscendo dalla picchiata la distanza torna subito, come su PS4)
    lfs f7, 0x5C8(r12)
    lfs f8, 0x3A38(r12)
    fmadds f6, f7, f8, f6
    lfs f7, 0x21C(r12)
    fsubs f8, f4, f7
    fmadds f7, f8, f6, f7
    stfs f7, 0x21C(r12)
    lfs f9, 0x220(r12)
    fsubs f8, f5, f9
    fmadds f9, f8, f6, f9
    stfs f9, 0x220(r12)
dh_fatto:
    ; ---- punto morbido (anti-pendolo); in prima persona la camera sta attaccata alla testa
    lbz r11, 0x87(r12)
    cmpwi r11, 0
    beq morbido
    stfs f1, 0x210(r12)
    stfs f2, 0x214(r12)
    stfs f3, 0x218(r12)
    b morbido_fatto
morbido:
    {_segui(0, 0x170, 0x178)}
    {_segui(1, 0x174, 0x17C)}
    {_segui(2, 0x170, 0x178)}
morbido_fatto:
    ; ---- punto guardato = Ts + (0, H, 0) + anticipo (velocità * anticipo, al massimo anticipo_max per asse)
    lfs f1, 0x210(r12)
    lfs f2, 0x214(r12)
    lfs f3, 0x218(r12)
    lfs f9, 0x220(r12)
    fadds f2, f2, f9
{prima.PUNTO(v)}
anticipo:
    li r11, 1
    stb r11, 0x4FD(r12)
    lfs f4, 0x1D8(r12)
    lfs f5, 0x1DC(r12)
    lfs f6, 0x234(r12)
    fmuls f6, f6, f4
    fsubs f7, f5, f6
    fsel f6, f7, f6, f5
    fneg f8, f5
    fsubs f7, f6, f8
    fsel f6, f7, f6, f8
    fadds f1, f1, f6
    lfs f6, 0x238(r12)
    fmuls f6, f6, f4
    fsubs f7, f5, f6
    fsel f6, f7, f6, f5
    fsubs f7, f6, f8
    fsel f6, f7, f6, f8
    fadds f3, f3, f6
punto_fatto:
    stfs f1, 0x240(r12)
    stfs f2, 0x244(r12)
    stfs f3, 0x248(r12)
{_tuffo_prima(v)}
    ; ---- avanti = (dx*ce, -se, dz*ce) con ce ~ 1 - e^2/2, se ~ e - e^3/6   (e + tuffo T)
    lfs f4, 0x20C(r12)
    lfs f5, 0x5C8(r12)
    fadds f4, f4, f5
    lfs f5, 0x5D0(r12)
    lfs f6, 0x3A0C(r12)
    fmadds f4, f5, f6, f4
    ; prima persona nel tuffo: lo sguardo scende di TUFFO_GIU * quantità (817F37EC; 0 con le altre camere)
    lfs f5, {TUFFO_FP:#x}(r12)
    lis r11, {asm.f32(TUFFO_GIU) >> 16:#x}
    ori r11, r11, {asm.f32(TUFFO_GIU) & 0xFFFF:#x}
    stw r11, {APPOGGIO_TESTA:#x}(r12)
    lfs f6, {APPOGGIO_TESTA:#x}(r12)
    fmadds f4, f5, f6, f4
    ; al massimo e_max_tot (oltre ~1.4 rad l'approssimazione di ce va sotto zero e la camera si capovolgerebbe)
    lfs f5, 0x3A20(r12)
    fsubs f6, f5, f4
    fsel f4, f6, f4, f5
    fmuls f5, f4, f4
    lfs f7, 0x158(r12)
    fnmsubs f8, f5, f12, f7
    lfs f6, 0x1B4(r12)
    fmuls f9, f5, f6
    fnmsubs f9, f9, f7, f7
    fmuls f9, f9, f4
    lfs f4, 0x204(r12)
    lfs f5, 0x208(r12)
    fmuls f4, f4, f8
    fmuls f5, f5, f8
    fneg f6, f9
    fmuls f7, f4, f4
    fmadds f7, f6, f6, f7
    fmadds f7, f5, f5, f7
    {_rsqrt("f8", "f7", "f9")}
    fmuls f4, f4, f8
    fmuls f6, f6, f8
    fmuls f5, f5, f8
    stfs f4, 0x24C(r12)
    stfs f6, 0x250(r12)
    stfs f5, 0x254(r12)
miscela_fine:
    ; posizione voluta = punto - avanti*D (+ destra*S nell'amazing) -> raggio dal punto guardato alla posizione voluta
    lfs f9, 0x21C(r12)
    fnmsubs f10, f4, f9, f1
    fnmsubs f11, f6, f9, f2
    fnmsubs f7, f5, f9, f3
    lbz r11, 0x5A0(r12)
    cmpwi r11, 0
    beq voluta_ok
    fmuls f8, f4, f4
    fmadds f8, f5, f5, f8
    lfs f9, 0x290(r12)
    fadds f8, f8, f9
    frsqrte f8, f8
    lfs f9, 0x5BC(r12)
    fmuls f8, f8, f9
    fmadds f10, f5, f8, f10
    fnmsubs f7, f4, f8, f7
voluta_ok:
    lbz r11, 0x87(r12)
    cmpwi r11, 0
    bne senza_muri
    addi r9, r12, {S:#x}
    lfs f8, 0x15C(r12)
    fnmsubs f1, f4, f8, f1
    fnmsubs f2, f6, f8, f2
    fnmsubs f3, f5, f8, f3
    ; SOFFITTI (John: attaccato sotto un ponte, girando la visuale si vedeva attraverso il tetto): il punto guardato è
    ; Spidey + H in su, e a testa in giù sotto un soffitto finiva DENTRO il soffitto -> il raggio dei muri partiva da
    ; lì e non vedeva niente. Primo raggio dalla posizione di Spidey (Ts, 210) all'inizio del raggio: se tocca, punto
    ; guardato, inizio e posizione voluta scendono fino a metà strada fra Spidey e il punto toccato. Mai un raggio
    ; lungo zero (pianta il gioco): sotto 10 cm niente primo raggio.
    stfs f10, 0x540(r12)
    stfs f11, 0x544(r12)
    stfs f7, 0x548(r12)
    stfs f1, 0x54C(r12)
    stfs f2, 0x550(r12)
    stfs f3, 0x554(r12)
    lfs f8, 0x210(r12)
    lfs f9, 0x214(r12)
    lfs f12, 0x218(r12)
    fsubs f4, f1, f8
    fmuls f13, f4, f4
    fsubs f4, f2, f9
    fmadds f13, f4, f4, f13
    fsubs f4, f3, f12
    fmadds f13, f4, f4, f13
    lfs f6, 0x150(r12)
    fmuls f6, f6, f6
    fmuls f6, f6, f6
    fmuls f6, f6, f6
    fcmpu f13, f6
    blt soffitto_fatto
    stfs f8, 0(r9)
    stfs f9, 4(r9)
    stfs f12, 8(r9)
    stfs f1, 0xC(r9)
    stfs f2, 0x10(r9)
    stfs f3, 0x14(r9)
    stfs f8, 0x40(r9)
    stfs f9, 0x44(r9)
    stfs f12, 0x48(r9)
    stfs f1, 0x4C(r9)
    stfs f2, 0x50(r9)
    stfs f3, 0x54(r9)
    li r11, 0
    stw r11, 0x30(r9)
    stb r11, 0x34(r9)
    addi r3, r9, 0x40
    addi r4, r9, 0x4C
    lwz r5, 0xA70(r31)
    lis r6, {g >> 16:#x}
    ori r6, r6, {g & 0xFFFF:#x}
    chiama {r_prep:#x}
    lis r12, 0x817F
    stw r3, {S + 0x60:#x}(r12)
    addi r4, r12, {S:#x}
    li r5, 0
    li r6, 0
    li r7, 0
    chiama {r_lancia:#x}
    lis r12, 0x817F
    addi r3, r12, {S + 0x60:#x}
    chiama {r_chiudi:#x}
    lis r12, 0x817F
    lbz r11, {S + 0x34:#x}(r12)
    cmpwi r11, 0
    beq soffitto_fatto
    lfs f13, 0x150(r12)
    lfs f8, 0x210(r12)
    lfs f1, {S + 0x18:#x}(r12)
    fsubs f1, f1, f8
    fmadds f1, f1, f13, f8
    lfs f8, 0x214(r12)
    lfs f2, {S + 0x1C:#x}(r12)
    fsubs f2, f2, f8
    fmadds f2, f2, f13, f8
    lfs f8, 0x218(r12)
    lfs f3, {S + 0x20:#x}(r12)
    fsubs f3, f3, f8
    fmadds f3, f3, f13, f8
    ; spostamento = nuovo inizio - inizio: lo stesso al punto guardato (240) e alla posizione voluta (540)
    lfs f8, 0x54C(r12)
    fsubs f8, f1, f8
    lfs f9, 0x550(r12)
    fsubs f9, f2, f9
    lfs f12, 0x554(r12)
    fsubs f12, f3, f12
    stfs f1, 0x54C(r12)
    stfs f2, 0x550(r12)
    stfs f3, 0x554(r12)
    lfs f4, 0x240(r12)
    fadds f4, f4, f8
    stfs f4, 0x240(r12)
    lfs f4, 0x244(r12)
    fadds f4, f4, f9
    stfs f4, 0x244(r12)
    lfs f4, 0x248(r12)
    fadds f4, f4, f12
    stfs f4, 0x248(r12)
    lfs f4, 0x540(r12)
    fadds f4, f4, f8
    stfs f4, 0x540(r12)
    lfs f4, 0x544(r12)
    fadds f4, f4, f9
    stfs f4, 0x544(r12)
    lfs f4, 0x548(r12)
    fadds f4, f4, f12
    stfs f4, 0x548(r12)
soffitto_fatto:
    addi r9, r12, {S:#x}
    lfs f10, 0x540(r12)
    lfs f11, 0x544(r12)
    lfs f7, 0x548(r12)
    lfs f1, 0x54C(r12)
    lfs f2, 0x550(r12)
    lfs f3, 0x554(r12)
    stfs f1, 0(r9)
    stfs f2, 4(r9)
    stfs f3, 8(r9)
    stfs f10, 0xC(r9)
    stfs f11, 0x10(r9)
    stfs f7, 0x14(r9)
    stfs f1, 0x40(r9)
    stfs f2, 0x44(r9)
    stfs f3, 0x48(r9)
    stfs f10, 0x4C(r9)
    stfs f11, 0x50(r9)
    stfs f7, 0x54(r9)
    li r11, 0
    stw r11, 0x30(r9)
    stb r11, 0x34(r9)
    addi r3, r9, 0x40
    addi r4, r9, 0x4C
    lwz r5, 0xA70(r31)
    lis r6, {g >> 16:#x}
    ori r6, r6, {g & 0xFFFF:#x}
    chiama {r_prep:#x}
    lis r12, 0x817F
    stw r3, {S + 0x60:#x}(r12)
    addi r4, r12, {S:#x}
    li r5, 0
    li r6, 0
    li r7, 0
    chiama {r_lancia:#x}
    lis r12, 0x817F
    addi r3, r12, {S + 0x60:#x}
    chiama {r_chiudi:#x}
    lis r12, 0x817F
    lfs f12, 0x150(r12)
    ; distanza voluta: D, o (distanza del muro - margine) se il raggio ha toccato qualcosa
    lfs f9, 0x21C(r12)
    lwz r9, 0x258(r12)
    li r11, 0
    stw r11, 0x258(r12)
    lbz r11, {S + 0x34:#x}(r12)
    cmpwi r11, 0
    beq muro_fatto
    lfs f1, 0x240(r12)
    lfs f2, 0x244(r12)
    lfs f3, 0x248(r12)
    lfs f4, {S + 0x18:#x}(r12)
    lfs f5, {S + 0x1C:#x}(r12)
    lfs f6, {S + 0x20:#x}(r12)
    fsubs f4, f4, f1
    fsubs f5, f5, f2
    fsubs f6, f6, f3
    fmuls f7, f4, f4
    fmadds f7, f5, f5, f7
    fmadds f7, f6, f6, f7
    {_rsqrt("f8", "f7", "f10")}
    fmuls f7, f7, f8
    lfs f4, 0x1EC(r12)
    fsubs f7, f7, f4
    lfs f4, 0x144(r12)
    fcmpu f7, f4
    bge muro_largo
    ; muro troppo vicino (es. Spidey attaccato al muro e visuale girata verso il palazzo): zoom fino a D_salva, poi
    ; la levetta in quella direzione si blocca (flag 258). Se non tocchi la levetta (il muro si è avvicinato da solo)
    ; la camera si gira piano verso la direzione della camera del gioco, che sta sempre dal lato aperto.
    lfs f4, 0x144(r12)
    fsubs f5, f7, f4
    fsel f9, f5, f7, f4
    li r11, 1
    stw r11, 0x258(r12)
    cmpwi r9, 0
    bne senza_verso
    lfs f4, 0x260(r12)
    lfs f5, 0x1C8(r12)
    fcmpu f4, f5
    beq senza_verso
    stfs f4, 0x25C(r12)
senza_verso:
    lwz r11, 0x224(r12)
    cmpwi r11, 10
    blt muro_fatto
    lfs f4, 0x120(r12)
    lfs f5, 0x128(r12)
    fmuls f6, f4, f4
    fmadds f6, f5, f5, f6
    {_rsqrt("f8", "f6", "f10")}
    fmuls f4, f4, f8
    fmuls f5, f5, f8
    lfs f6, 0x148(r12)
    lfs f7, 0x204(r12)
    fsubs f10, f4, f7
    fmadds f7, f10, f6, f7
    lfs f8, 0x208(r12)
    fsubs f10, f5, f8
    fmadds f8, f10, f6, f8
    fmuls f10, f7, f7
    fmadds f10, f8, f8, f10
    {_rsqrt("f11", "f10", "f4")}
    fmuls f7, f7, f11
    fmuls f8, f8, f11
    stfs f7, 0x204(r12)
    stfs f8, 0x208(r12)
    lfs f4, 0x124(r12)
    fneg f4, f4
    lfs f5, 0x20C(r12)
    fsubs f10, f4, f5
    fmadds f5, f10, f6, f5
    stfs f5, 0x20C(r12)
    b muro_fatto
muro_largo:
    fsubs f5, f7, f9
    fsel f9, f5, f9, f7
muro_fatto:
    ; Dc: si avvicina subito, si riallontana piano
    lfs f4, 0x23C(r12)
    fsubs f5, f9, f4
    lfs f6, 0x1F0(r12)
    fmadds f6, f5, f6, f4
    fsel f4, f5, f6, f9
    stfs f4, 0x23C(r12)
    fmr f9, f4
    b metti_pos
senza_muri:
    ; prima persona (si arriva qui solo in prima persona): occhio = punto - avanti * D (D negativo = davanti alla testa)
    ; + la spinta dei cambi di posa (817F04EC, vedi il punto della prima persona); poi i muri come nella realistica: raggio
    ; del gioco da P a occhio + avanti * A, se tocca l'occhio si ferma A (16 cm) prima e mai a meno di A da P (prima
    ; nella stabile e nella trick nessun controllo: vicino ai muri la camera ci entrava). La realistica ha il suo (8C):
    ; qui è solo la vista dei comandi.
    lfs f9, 0x21C(r12)
    stfs f9, 0x4C8(r12)
    addi r9, r12, {S:#x}
    lfs f8, 0x2E4(r12)
    fsubs f8, f8, f9
    lfs f1, 0x240(r12)
    lfs f4, 0x24c(r12)
    fmadds f10, f4, f8, f1
    stfs f1, 0x0(r9)
    stfs f1, 0x40(r9)
    stfs f10, 0xc(r9)
    stfs f10, 0x4c(r9)
    lfs f1, 0x244(r12)
    lfs f4, 0x250(r12)
    fmadds f10, f4, f8, f1
    stfs f1, 0x4(r9)
    stfs f1, 0x44(r9)
    stfs f10, 0x10(r9)
    stfs f10, 0x50(r9)
    lfs f1, 0x248(r12)
    lfs f4, 0x254(r12)
    fmadds f10, f4, f8, f1
    stfs f1, 0x8(r9)
    stfs f1, 0x48(r9)
    stfs f10, 0x14(r9)
    stfs f10, 0x54(r9)
    li r11, 0
    stw r11, 0x30(r9)
    stb r11, 0x34(r9)
    addi r3, r9, 0x40
    addi r4, r9, 0x4C
    lwz r5, 0xA70(r31)
    lis r6, {g >> 16:#x}
    ori r6, r6, {g & 0xFFFF:#x}
    chiama {r_prep:#x}
    lis r12, 0x817F
    stw r3, {S + 0x60:#x}(r12)
    addi r4, r12, {S:#x}
    li r5, 0
    li r6, 0
    li r7, 0
    chiama {r_lancia:#x}
    lis r12, 0x817F
    addi r3, r12, {S + 0x60:#x}
    chiama {r_chiudi:#x}
    lis r12, 0x817F
    lfs f9, 0x4C8(r12)
    lbz r11, {S + 0x34:#x}(r12)
    cmpwi r11, 0
    beq senza_muri_fatto
    lfs f1, {S + 0x18:#x}(r12)
    lfs f2, 0x240(r12)
    fsubs f1, f1, f2
    fmuls f5, f1, f1
    lfs f1, {S + 0x1c:#x}(r12)
    lfs f2, 0x244(r12)
    fsubs f1, f1, f2
    fmadds f5, f1, f1, f5
    lfs f1, {S + 0x20:#x}(r12)
    lfs f2, 0x248(r12)
    fsubs f1, f1, f2
    fmadds f5, f1, f1, f5
    lfs f1, 0x290(r12)
    fadds f5, f5, f1
    frsqrte f1, f5
    fmuls f5, f5, f1
    lfs f1, 0x2E4(r12)
    fsubs f5, f5, f1
    fsubs f2, f5, f1
    fsel f5, f2, f5, f1
    fneg f5, f5
    fsubs f2, f9, f5
    fsel f9, f2, f9, f5
senza_muri_fatto:
    ; distanza dell'occhio: rientra subito, si riallontana piano (un quarto per fotogramma, 817F049C): sfiorando un muro
    ; il raggio tocca e non tocca a fotogrammi alterni
    fneg f1, f9
    lfs f2, 0x49C(r12)
    fsubs f3, f1, f2
    lfs f4, 0x15C(r12)
    fmadds f4, f3, f4, f2
    fsel f1, f3, f4, f1
    stfs f1, 0x49C(r12)
    fneg f9, f1
    stfs f9, 0x23C(r12)
metti_pos:
    lwz r10, 0x30(r31)
    lfs f1, 0x240(r12)
    lfs f2, 0x244(r12)
    lfs f3, 0x248(r12)
    lfs f4, 0x24C(r12)
    lfs f6, 0x250(r12)
    lfs f5, 0x254(r12)
    stfs f4, 0x20(r10)
    stfs f6, 0x24(r10)
    stfs f5, 0x28(r10)
    fnmsubs f10, f4, f9, f1
    fnmsubs f11, f6, f9, f2
    fnmsubs f7, f5, f9, f3
    lbz r11, 0x5A0(r12)
    cmpwi r11, 0
    beq pos_lato_ok
    lfs f0, 0x21C(r12)
    lfs f8, 0x290(r12)
    fadds f0, f0, f8
    fdivs f0, f9, f0
    lfs f8, 0x5BC(r12)
    fmuls f0, f0, f8
    fmuls f8, f4, f4
    fmadds f8, f5, f5, f8
    lfs f1, 0x290(r12)
    fadds f8, f8, f1
    frsqrte f8, f8
    fmuls f0, f0, f8
    fmadds f10, f5, f0, f10
    fnmsubs f7, f4, f0, f7
pos_lato_ok:
    stfs f10, 0x30(r10)
    stfs f11, 0x34(r10)
    stfs f7, 0x38(r10)
destra_std:
    ; destra = normalize(fz, 0, -fx) ; su = avanti x destra
    fmuls f7, f4, f4
    fmadds f7, f5, f5, f7
    {_rsqrt("f8", "f7", "f9")}
    fmuls f1, f5, f8
    fneg f3, f4
    fmuls f3, f3, f8
    stfs f1, 0x00(r10)
    li r11, 0
    stw r11, 0x04(r10)
    stfs f3, 0x08(r10)
    fmuls f7, f6, f3
    stfs f7, 0x10(r10)
    fmuls f7, f5, f1
    fnmsubs f7, f4, f3, f7
    stfs f7, 0x14(r10)
    fmuls f7, f6, f1
    fneg f7, f7
    stfs f7, 0x18(r10)
    ; rollio (prima persona: 817F3440 di prima.py; amazing: 817F05B8): destra' = destra*c + su*s, su' = su*c - destra*s,
    ; c = 1 - s^2/2
    lfs f9, {prima.ROLLIO:#x}(r12)
    lbz r11, 0x87(r12)
    cmpwi r11, 0
    bne rollio_applica
    lbz r11, 0x5A0(r12)
    cmpwi r11, 0
    beq uscita
    lfs f9, 0x5B8(r12)
rollio_applica:
    fmuls f0, f9, f9
    lfs f2, 0x150(r12)
    lfs f8, 0x158(r12)
    fnmsubs f0, f0, f2, f8
    lfs f1, 0x0(r10)
    lfs f2, 0x10(r10)
    fmuls f3, f1, f0
    fmadds f3, f2, f9, f3
    stfs f3, 0x0(r10)
    fmuls f3, f2, f0
    fnmsubs f3, f1, f9, f3
    stfs f3, 0x10(r10)
    lfs f1, 0x4(r10)
    lfs f2, 0x14(r10)
    fmuls f3, f1, f0
    fmadds f3, f2, f9, f3
    stfs f3, 0x4(r10)
    fmuls f3, f2, f0
    fnmsubs f3, f1, f9, f3
    stfs f3, 0x14(r10)
    lfs f1, 0x8(r10)
    lfs f2, 0x18(r10)
    fmuls f3, f1, f0
    fmadds f3, f2, f9, f3
    stfs f3, 0x8(r10)
    fmuls f3, f2, f0
    fnmsubs f3, f1, f9, f3
    stfs f3, 0x18(r10)
    ; prima persona con 'Movimento della testa': sguardi solo per il disegno (prima.py)
{prima.TESTA(v)}
{_muro_comandi(v)}
    b uscita
classica:
    li r9, 0
    stw r9, 0x140(r12)
    stw r9, 0x200(r12)
uscita:
    lwz r31, 0x3C(r1)
    addi r1, r1, 0x40
    lwz r0, 4(r1)
    mtlr r0
    blr
{_tuffo_comando(v)}
"""


LIMITE_BYTE = 3240  # spazio per i codici Gecko in Dolphin: 0x1800 byte - codehandler.bin (2880) = 3264, tengo un margine
# (3088 caricato, 3400 no). ATTENZIONE: un Dolphin con un codehandler.bin più grande lascia meno spazio.


PROGRAMMA = 0x817F0800  # qui il codice AR "$Camera program" scrive la logica (zona sempre a zero, verificata; era a
# 0x817F1000: spostato il 2026-10-10 per fare posto al controllo dei soffitti, 0800-0FFF non lo usava nessuno)
NOME_PROGRAMMA = "$Camera program (needed by the camera code)"
# Dolphin ha ~3264 byte per TUTTI i codici Gecko: la logica (~2,5 KB) non ci sta più insieme al resto. Il Gecko tiene solo
# costanti + 2 agganci; la logica la scrive in memoria un codice AR (nessun limite di lunghezza), sempre uguale (il JIT
# di Dolphin la compila una volta). L'aggancio salta al programma solo quando la sua PRIMA parola è già scritta: il
# codice AR la scrive per ultima.
# Prima persona realistica: la camera del gioco (che i comandi leggono per sapere dov'è "avanti") resta la vista stabile;
# alla vista del disegno, quando il gioco la imposta da una camera (0x801A1E48 -> lookAt 0x8022F5A4 con occhio, bersaglio,
# su), do invece la testa di Spidey: occhio = testa + giù*H + indietro*A_trick (A negativo = avanti), bersaglio = occhio
# + avanti (-z), su = -x. Li calcola il PROGRAMMA (all'aggiornamento della camera, come la trick) in 817F03B0 (occhio),
# 03C0 (bersaglio), 03CC (su): letta qui al disegno, la testa era di un altro fotogramma rispetto allo Spidey disegnato
# (in swing più di mezzo metro) e la camera usciva dalla testa, fino a vedersi la faccia. Solo se il programma ha messo
# 817F008C = 1 in questo fotogramma (prima persona realistica, camera di gioco) e solo per la camera su cui gira il
# programma (817F03BC).
VISTA = 0x801A2058  # bl lookAt dentro 0x801A1E48 (stesso indirizzo in tutte le versioni)
LOOKAT = 0x8022F5A4


def _vista_testa():
    return f"""
    lis r12, 0x817F
    lbz r11, 0x8C(r12)
    cmpwi r11, 0
    beq vista_gioco
    lwz r11, 0x3BC(r12)
    cmpw r11, r31
    bne vista_gioco
    addi r4, r12, 0x3B0
    addi r5, r12, 0x3C0
    addi r6, r12, 0x3CC
vista_gioco:
    lis r12, {LOOKAT >> 16:#x}
    ori r12, r12, {LOOKAT & 0xFFFF:#x}
    mtctr r12
    bctrl
"""


CHIAMA_PROGRAMMA = f"""
    lis r12, {PROGRAMMA >> 16:#x}
    lwz r11, {PROGRAMMA & 0xFFFF:#x}(r12)
    cmpwi r11, 0
    beq senza_programma
    mflr r0
    stwu r1, -0x10(r1)
    stw r0, 0x14(r1)
    ori r12, r12, {PROGRAMMA & 0xFFFF:#x}
    mtctr r12
    bctrl
    lwz r0, 0x14(r1)
    addi r1, r1, 0x10
    mtlr r0
senza_programma:
"""


def programma(ver="GK2I52"):
    """Parole della logica (funzione: torna con blr; r3 = oggetto camera)."""
    w = asm.assembla(logica(VERSIONI[ver]) + "\n    blr\n", PROGRAMMA)
    assert PROGRAMMA + 4 * len(w) <= BASE + prima.DATI, "programma camera troppo lungo: tocca i dati della prima persona"
    return w


def codice_ar(ver="GK2I52"):
    """Righe AR che scrivono il programma a PROGRAMMA: la prima parola per ultima (vedi CHIAMA_PROGRAMMA)."""
    w = programma(ver)
    righe = [asm.scrivi32(PROGRAMMA + 4 * k, w[k]) for k in range(1, len(w))]
    # momentum all'atterraggio (momentum.py): routine a parte, chiamata dal programma -> scritta prima della prima parola
    return righe + righe_extra(ver) + [asm.scrivi32(PROGRAMMA, w[0])]


def righe_extra(ver="GK2I52"):
    """Righe AR scritte insieme al programma (prima della sua prima parola): costanti delle camere
    e, se acceso, il momentum all'atterraggio (momentum.py)."""
    return righe_amazing() + (momentum.righe_ar(VERSIONI[ver]) if momentum.NEL_PROGRAMMA else [])


def righe_amazing():
    """Righe AR delle costanti della camera Amazing (817F3800..), scritte insieme al programma."""
    return [asm.scrivi32(BASE + o, asm.f32(x)) for o, (_, x) in sorted({**AMAZING_K, **TASM_K, **PS4_K, **PICCH_K}.items())]


def codice(ver="GK2I52", modi=MODI_BASE, opzioni=None):
    v = VERSIONI[ver]
    r = _codice(v, modi, opzioni)
    assert len(r) * 8 <= LIMITE_BYTE, f"codice camera troppo lungo: {len(r) * 8} byte (Dolphin non lo caricherebbe)"
    return r


# A TESTA IN GIÙ SOTTO UN SOFFITTO (817F0558, scritto dal programma solo con le camere nuove): il gioco gira destra/sinistra
# della levetta pensando a una camera CAPOVOLTA (la sua sul soffitto si capovolge come Spidey); la nostra resta dritta ->
# John: "premi sinistra e lui va a destra". Nella lettura della levetta sinistra X per Spidey (0x802CAFD8 ingresso 4, dopo la
# divisione "fdivs f1, f1, f12": ITA 0x802CB1E0, USA/UK/DE/FR 0x802CB170) la giro di segno. Avanti/indietro erano giusti.
def _levetta_soffitto(v):
    """C2 dopo "fdivs f1, f1, f12" nella lettura della levetta X per Spidey: inverte se il programma ha messo 817F0558
    (appeso al soffitto), ma solo se Spidey è ANCORA appeso (stato 2) e il gioco non è in pausa: se l'aggiornamento della
    camera non gira (pausa, mappa) il flag resterebbe a 1. Solo r9 (dopo c'è la chiamata al limite della levetta)."""
    st, pa = v["stato"], v["pausa"]
    return f"""
    fdivs f1, f1, f12
    lis r9, 0x817F
    lbz r9, 0x558(r9)
    cmpwi r9, 0
    beq lev_ok
    lis r9, {st >> 16:#x}
    ori r9, r9, {st & 0xFFFF:#x}
    lwz r9, 0(r9)
    cmpwi r9, 2
    bne lev_ok
    lis r9, {pa >> 16:#x}
    ori r9, r9, {pa & 0xFFFF:#x}
    lbz r9, 0(r9)
    cmpwi r9, 0
    bne lev_ok
    fneg f1, f1
lev_ok:
"""


# R3 = Z + giù nel profilo, ma il giù è anche il LOCK sui nemici. La funzione del gioco che legge i tasti per Spidey
# (0x802CAFD8, ingresso 1 = asse verticale della croce) controlla il giù con "andi. r0, r3, 4": lì con Z tenuto il giù
# non conta. I nostri codici leggono i tasti dalla memoria (805546A0 / 80554620): per loro R3 resta Z + giù. Sta nel
# codice della camera (prima era in quello del tuffo: spegnendo il tuffo R3 tornava a fare il lock).
CROCE_ORIGINALE = 0x70600004  # andi. r0, r3, 4
CROCE_GIU = f"""
    andi. r0, r3, 0x14
    cmpwi r0, 0x14
    bne croce_ok
    xori r3, r3, 4
croce_ok:
    .word {CROCE_ORIGINALE:#x}
"""


def _codice(v, modi, opzioni=None):
    return (costanti(modi, opzioni) + asm.c2(v["inizio"], asm.assembla(RIMETTI))
            + asm.c2(v["fine"], asm.assembla(CHIAMA_PROGRAMMA)) + asm.c2(VISTA, asm.assembla(_vista_testa()))
            + asm.c2(v["levetta_x"], asm.assembla(_levetta_soffitto(v))) + asm.c2(v["croce_giu"], asm.assembla(CROCE_GIU)))


if __name__ == "__main__":
    print("\n".join(codice()))
