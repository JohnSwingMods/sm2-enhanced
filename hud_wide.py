"""HUD in 16:9 senza stiratura (codice Gecko).

Il codice widescreen allarga solo il 3D: il gioco disegna l'interfaccia in uno schermo finto 640x448 che viene stirato
su tutta la larghezza 16:9 -> l'anello della vita, la minimappa e le scritte diventano ovali/larghe.

Come la disegna il gioco (stesso codice in tutte le versioni, ITA spostato di +0x70):
- ogni pezzo dell'interfaccia (PanelQuad) a ogni fotogramma finisce in una lista di disegno; la funzione 0x80307368 (ITA)
  manda alla scheda grafica i 4 vertici del pezzo (x, y, colore, u, v) leggendoli dalla voce della lista (r31);
- le scritte passano da 0x80305DDC (ITA): posizione (x, y) a +0x14/+0x18 della voce e scala (sx, sy) a +0x20/+0x24.

Il codice si aggancia in quei due punti e, in 16:9, stringe in orizzontale di k = (4/3) / aspetto (0.75) attorno a un
punto di ancoraggio: x' = a + (x - a) * k. Ancoraggio:
- in partita (modo dell'interfaccia = 1): pezzi col centro a x < 270 -> bordo sinistro (a = 0), x > 370 -> bordo destro
  (a = 640), il resto al centro (a = 320). Così l'HUD resta agli angoli dello schermo largo ma torna tondo. (Prima erano
  i terzi dello schermo, ma la minimappa è fatta di tessere separate tra x 385 e 617: quelle a sinistra finivano "al
  centro" e la mappa si spezzava);
- nei menu (modo != 1) tutto si stringe attorno al centro: il menu resta 4:3 al centro (proporzioni giuste); restano
  a tutto schermo solo gli sfondi larghi almeno 630;
- i pezzi larghi quasi tutto lo schermo (dissolvenze, bande nere, sfondi) non si toccano: devono coprire tutto;
- i segnalini che seguono un punto del mondo (es. il "?" della missione) hanno profondità grande (la distanza, es. 1074;
  l'HUD fisso sta a ~1): restano dove sono e si stringono solo attorno al loro centro (a = centro), se no l'ancoraggio
  li spostava di lato e li faceva saltare passando da una zona all'altra.
- mappa grande (Z + Start, VERSIONI "mappa_aperta"): i segnalini (stelle, $, ...: profondità 1.0) restano sopra i loro
  palazzi (a = centro del segnalino, o del gruppo per i riquadri fatti a pezzi; prima l'ancoraggio li spostava di
  50-90 pixel verso i bordi); le cornici
  (profondità < 1) col centro tra 200 e 440 vanno al centro (il riquadro della scheda scelta era spezzato: linee al
  centro, estremità ai bordi = "stirato"), le altre ai bordi (barra dello zoom, bussola, frecce « »); scritte: schede
  (profondità 20-26) e riga dei comandi in basso (y > 380) al centro, pannello di sinistra (centro < 140) a sinistra,
  nomi dei quartieri (profondità 1000) al loro posto.
In 4:3 (aspetto 1.333, nessun codice widescreen) non cambia niente.
DUE MODI (MODO_HUD, prima riga del codice, scelta in Grafica): 0 = SOLO L'HUD DI GIOCO (di base, idea di John: menu, mappa,
caricamenti e riquadri come 'CONTINUA?' restano stirati come nell'originale = sembrano fatti per il 16:9 e non c'è niente
da sistemare); 1 = tutto (le regole di menu e mappa qui sopra).
Nel modo 0 si tocca qualcosa SOLO se è stato disegnato un pezzo con la texture "i_igo_..." (anello della vita e bordo
della minimappa) negli ultimi 3 fotogrammi video (prova che l'HUD di gioco è a schermo): tutto quello che non lo disegna (menu, mappa, caricamenti, schermate mai viste) resta
originale per costruzione (_partita_solo_hud). Come si riconosce la texture
(registro: nome della texture a +0x38 dell'oggetto puntato da +0x60 del pezzo; in pausa solo pezzi senza texture e
"i_bar_fade", uno in alto a sinistra: per questo la posizione non bastava).

Uso: python hud_wide.py -> stampa il codice per ogni versione (righe Gecko)."""
import ppcasm as asm

NOME = "$HUD not stretched in 16:9"
# versione -> indirizzi: quad = lfsx della x nel giro dei 4 vertici, testo = ultimo lfs prima di costruire la scritta,
# aspetto = dove il codice widescreen scrive l'aspetto, ui = modo dell'interfaccia (1 in partita, 2 pausa, 0 titolo)
VERSIONI = {
    "GK2E52": {"quad": 0x803078F0, "testo": 0x80305EE4, "mappa": 0x8027A4D4, "aspetto": 0x804795A4,
               "ui": 0x804DCE2A, "pausa": 0x8056B9BB, "vi": 0x8056C4E0, "stato": 0x80AD1A04, "mappa_aperta": 0x8056B8EC},
    "GK2I52": {"quad": 0x80307960, "testo": 0x80305F54, "mappa": 0x8027A544, "aspetto": 0x8047962C,
               "ui": 0x804DCEAA, "pausa": 0x8056BA3B, "vi": 0x8056C560, "stato": 0x80AD1A04, "mappa_aperta": 0x8056B96C},
}
for _v in ("GK2P52", "GK2D52", "GK2F52"):  # stesso programma dell'USA
    VERSIONI[_v] = VERSIONI["GK2E52"]

LFSX_X = 0x7C1F4C2E  # lfsx f0, r31, r9 (istruzione originale del punto "quad")
LFS_Y = 0xC19F0018   # lfs f12, 0x18(r31) (istruzione originale del punto "testo")
FSUBS_Y = 0xEC401028  # fsubs f2, f0, f2 (istruzione originale del punto "mappa")
ANELLO_VI = 0x817F00D8  # contatore VI dell'ultimo disegno di un pezzo dell'HUD di gioco (texture i_igo_...), scritto da blocco_quad
MODO_HUD = 0x817F00BC  # 0 = solo l'HUD di gioco (menu, mappa, caricamenti e riquadri restano stirati come l'originale),
# 1 = tutto (anche menu e mappa stretti 4:3), 2 = niente (HUD originale stirato: alcuni elementi fatti a pezzi, come il
# riquadro "PARLA", con 0/1 si spezzavano). Lo scrive la prima riga del codice (riga_modo), l'app la cambia (Grafica).
RETT_MAPPA = 0x817F00E0  # rettangolo della minimappa già stretto (sinistra, alto, destra, basso), scritto da blocco_mappa


def _hl(ind):
    lo = ind & 0xFFFF
    return ((ind >> 16) + (1 if lo & 0x8000 else 0)) & 0xFFFF, (lo - 0x10000 if lo & 0x8000 else lo)


DEBUG = False  # prove dal vivo: il byte 0x817F00F8 spegne i controlli (bit 1 rettangolo, 2 GX, 4 partita)


def _salta_se(bit, rb, etichetta):
    if not DEBUG:
        return ""
    return f"""    lis {rb}, 0x817F
    lbz {rb}, 0xF8({rb})
    andi. {rb}, {rb}, {bit}
    bne {etichetta}
"""


def _conta(ra, rb, off):
    """(prove) contatore delle volte che passa di qui, in 0x817F00xx."""
    if not DEBUG:
        return ""
    return f"""    lis {ra}, 0x817F
    lwz {rb}, {off}({ra})
    addi {rb}, {rb}, 1
    stw {rb}, {off}({ra})
"""


def _schermo(ra, rb):
    """Salta a 'fine' se il gioco non sta disegnando sullo schermo intero: rettangolo di disegno ([r13-0x6DE8]+0x284,
    sinistra e destra) diverso da 0..639 = dentro la minimappa o dentro una texture (la mappa viene prima disegnata
    in una texture nascosta: se la stringessi lì, poi sullo schermo uscirebbe spostata). Stessa cosa se la finestra di
    disegno della scheda grafica non parte da sinistra (dati GX [r13-0x4DD8] +0x4F4 != 0): l'indicatore del giocatore
    nella minimappa viene disegnato così. (Non la larghezza: sulla USA lì resta 512 per tutto il fotogramma.)"""
    return _salta_se(1, rb, "no_rett") + f"""    lwz {ra}, -0x6de8(r13)
    lwz {rb}, 0x284({ra})
    cmpwi {rb}, 0
    bne fine
    lwz {rb}, 0x28C({ra})
    cmpwi {rb}, 639
    bne fine
no_rett:
""" + _salta_se(2, rb, "no_gx") + f"""    lwz {ra}, -0x4dd8(r13)
    lwz {rb}, 0x4F4({ra})
    cmpwi {rb}, 0
    bne fine
no_gx:
"""


def _costanti(r):
    """Costanti in mezzo al codice: bl le salta e lascia in LR il loro indirizzo (le funzioni agganciate hanno già
    salvato LR nel prologo)."""
    return f"""    bl dopo_costanti
    .float 1.3333334
    .float 320.0
    .float 540.0
    .float 740.0
    .float 600.0
    .float 1.34
    .float 2.0
    .float 0.5
    .float 2.0
    .float 630.0
    .float 200.0
    .float 150.0
    .float 0.9995
    .float 400.0
    .float 880.0
    .float 500.0
    .float 50.0
    .float 380.0
    .float 280.0
    .float 24.0
dopo_costanti:
    mflr {r}
"""


def _k(v, rt, ra, fa="f1", fk="f2"):
    """fk = k = (4/3) / aspetto (fa = registro di appoggio); se l'aspetto è <= 1.34 (niente 16:9) salta a 'fine'."""
    ah, al = _hl(v["aspetto"])
    return f"""    lis {rt}, {ah:#x}
    lfs {fa}, {al}({rt})
    lfs {fk}, 0x14({ra})
    fcmpu {fa}, {fk}
    blt fine
    lfs {fk}, 0({ra})
    fdivs {fk}, {fk}, {fa}
"""


def _partita(v, rt, rb):
    """rb = 1 in partita (pezzi ai bordi del 16:9), 2 nei menu (tutto stretto attorno al centro, menu 4:3 centrato).
    Il modo dell'interfaccia del gioco (v["ui"]: 1 in partita, 2 menu di pausa, 0 titolo, menu iniziali e caricamenti)
    cambia subito aprendo e chiudendo la pausa, ma in partita, sopra l'acqua e nel tuffo, salta per frazioni di secondo
    a 0 e a 2, e cadendo verso l'acqua resta a 0 per 2-3 secondi (l'HUD passava a intermittenza tra 4:3 e 16:9).
    Quindi: menu SUBITO solo se è 2 e il byte della pausa (v["pausa"], 1 anche nei riflessi, dove però il modo resta 1)
    è 1; altrimenti menu solo se Spidey non c'è (stato v["stato"] = -1: titolo; caricamenti e tuffo hanno uno stato) e il
    modo non è 1 da almeno 20 fotogrammi video (v["vi"], +60 al secondo anche nei caricamenti): a ogni disegno col modo
    1 scrivo la scadenza (contatore + 20) in 817F00F4.
    Prima di tutto: Spidey morto (stato -1) e anello della vita non disegnato da 3 fotogrammi (ANELLO_VI, lo segna
    blocco_quad) = riquadri come 'CONTINUA?' -> menu (centrati: prima i pezzi del riquadro andavano metà a sinistra e
    metà a destra). Mentre cade morendo l'HUD c'è ancora: resta in partita."""
    uh, ul = _hl(v["ui"]); ph, pl = _hl(v["pausa"]); vh, vl = _hl(v["vi"]); sh, sl = _hl(v["stato"])
    return _partita_solo_hud(v, rt, rb) + f"""pt_normale:
    lis {rt}, {sh:#x}
    lwz {rb}, {sl}({rt})
    cmpwi {rb}, -1
    bne con_spidey
    lis {rt}, {vh:#x}
    lwz {rb}, {vl}({rt})
    lis {rt}, 0x817F
    lwz {rt}, {ANELLO_VI & 0xFFFF:#x}({rt})
    addi {rt}, {rt}, 3
    cmpw {rb}, {rt}
    bgt modo_menu
con_spidey:
    lis {rt}, {uh:#x}
    lbz {rb}, {ul}({rt})
    cmpwi {rb}, 1
    bne modo_non1
    lis {rt}, {vh:#x}
    lwz {rb}, {vl}({rt})
    addi {rb}, {rb}, 20
    lis {rt}, 0x817F
    stw {rb}, 0xF4({rt})
    li {rb}, 1
    b modo_ok
modo_non1:
    cmpwi {rb}, 2
    bne modo_attesa
    lis {rt}, {ph:#x}
    lbz {rb}, {pl}({rt})
    cmpwi {rb}, 1
    beq modo_menu
modo_attesa:
    lis {rt}, {sh:#x}
    lwz {rb}, {sl}({rt})
    cmpwi {rb}, -1
    li {rb}, 1
    bne modo_ok
    lis {rt}, {vh:#x}
    lwz {rb}, {vl}({rt})
    lis {rt}, 0x817F
    lwz {rt}, 0xF4({rt})
    cmpw {rb}, {rt}
    li {rb}, 1
    blt modo_ok
modo_menu:
    li {rb}, 2
modo_ok:
"""


ANELLO_FOTOGRAMMI = 3  # modo "solo HUD": texture i_igo disegnata negli ultimi N fotogrammi video (50 ms) = HUD a schermo


def _partita_solo_hud(v, rt, rb):
    """Modo "solo HUD" (MODO_HUD = 0, quello di base): si tocca qualcosa SOLO con la prova che l'HUD di gioco è a
    schermo: l'anello della vita disegnato negli ultimi ANELLO_FOTOGRAMMI fotogrammi video (ANELLO_VI, scritto da
    blocco_quad per ogni pezzo in alto a sinistra), Spidey c'è (stato != -1) e non è il menu di pausa (modo
    dell'interfaccia 2 + pausa 1). Menu di pausa, mappa grande, caricamenti, 'CONTINUA?', titolo e schermate mai viste
    non disegnano l'anello -> restano come l'originale per costruzione (John: prima si capiva "quando è un menu" e
    quando quei segnali sbagliavano per un attimo il menu veniva stretto). Con l'HUD nascosto (LB) non c'è niente da
    sistemare. Nel modo 1 (tutto) resta la logica di sotto (pt_normale)."""
    uh, ul = _hl(v["ui"]); ph, pl = _hl(v["pausa"]); vh, vl = _hl(v["vi"]); sh, sl = _hl(v["stato"])
    return f"""    lis {rt}, 0x817F
    lbz {rb}, {MODO_HUD & 0xFFFF:#x}({rt})
    cmpwi {rb}, 2
    beq fine
    cmpwi {rb}, 0
    bne pt_normale
    lis {rt}, {sh:#x}
    lwz {rb}, {sl}({rt})
    cmpwi {rb}, -1
    beq modo_menu
    lis {rt}, {uh:#x}
    lbz {rb}, {ul}({rt})
    cmpwi {rb}, 2
    bne pt_non_pausa
    lis {rt}, {ph:#x}
    lbz {rb}, {pl}({rt})
    cmpwi {rb}, 1
    beq modo_menu
pt_non_pausa:
    lis {rt}, {vh:#x}
    lwz {rb}, {vl}({rt})
    lis {rt}, 0x817F
    lwz {rt}, {ANELLO_VI & 0xFFFF:#x}({rt})
    addi {rt}, {rt}, {ANELLO_FOTOGRAMMI}
    cmpw {rb}, {rt}
    bgt modo_menu
    li {rb}, 1
    b modo_ok
"""


def _mappa_chiusa(v, rt, etichetta):
    """Salta a etichetta se la mappa grande (Z + Start) è chiusa: byte v["mappa_aperta"] = 80 con la mappa aperta (da
    subito, anche dopo lo zoom e cambiando scheda, fino a fine dissolvenza), 10 in partita e nel menu di pausa (trovato
    confrontando la memoria; il puntatore 0x80497394 provato prima si svuota 4 s dopo l'apertura). In mappa il modo
    dell'interfaccia resta 1 (= partita)."""
    mh, ml = _hl(v["mappa_aperta"])
    return f"""    lis {rt}, {mh:#x}
    lbz {rt}, {ml}({rt})
    cmpwi {rt}, 80
    bne {etichetta}
"""


GRUPPO = 0x817F00A0  # segnalini della mappa: ancoraggio del gruppo (+0), riquadro x min/max y min/max (+4..+0x10), VI (+0x14),
# gruppi iniziati in questo fotogramma (+0x18)
CENTRI = 0x817F0600  # centro finale di ogni gruppo del fotogramma di prima (32 float; la camera usa 817F0500-059F)


def _gruppo_segnalino(v):
    """Segnalino della mappa grande (f8/f9 = x min/max, f7 = 2 * centro): si stringe attorno al proprio centro, ma i
    riquadri fatti a pezzi (il quadrato giallo del "$" = 9 pezzi) si aprivano in buchi se ogni pezzo usava il suo
    centro. Quindi: un pezzo che sta DENTRO il riquadro del gruppo di prima (2 di margine: anelli concentrici) o lo
    TOCCA di lato (sovrapposto al massimo 2 su un asse: pezzi di una cornice) nello stesso fotogramma usa l'ancoraggio
    del gruppo e lo allarga; se no apre un gruppo nuovo (due stelle vicine si sovrappongono in parte: restano separate,
    prima finivano una sopra l'altra). Ancoraggio del gruppo = il centro finale dello
    stesso gruppo (stesso numero d'ordine) nel fotogramma di prima, se è vicino (< 24); se no il centro del primo pezzo
    (l'angolo in alto a sinistra del riquadro: il "$" restava spostato dentro la cornice). Il codice passa 4 volte per pezzo
    (un vertice alla volta): dopo il primo il pezzo è già dentro il gruppo = stesso ancoraggio. Usa r3, r4, f1, f3-f6,
    f10, f11 (f2 = k)."""
    vh, vl = _hl(v["vi"]); g = GRUPPO & 0xFFFF
    return f"""    lfs f3, 4(r31)
    lfs f4, 0x18(r31)
    fsubs f10, f3, f4
    fsel f6, f10, f4, f3
    fsel f11, f10, f3, f4
    lfs f3, 0x2C(r31)
    lfs f4, 0x40(r31)
    fsubs f10, f3, f4
    fsel f1, f10, f4, f3
    fsel f3, f10, f3, f4
    fsubs f10, f6, f1
    fsel f6, f10, f1, f6
    fsubs f10, f11, f3
    fsel f11, f10, f11, f3
    lis r3, {vh:#x}
    lwz r4, {vl}(r3)
    lis r3, 0x817F
    lwz r3, {g + 0x14:#x}(r3)
    cmpw r4, r3
    lis r3, 0x817F
    stw r4, {g + 0x14:#x}(r3)
    bne q_fotogramma_nuovo
    lfs f1, 0x20(r12)
    lfs f3, {g + 4:#x}(r3)
    fsubs f10, f3, f1
    fcmpu f8, f10
    blt q_non_dentro
    lfs f3, {g + 8:#x}(r3)
    fadds f10, f3, f1
    fcmpu f9, f10
    bgt q_non_dentro
    lfs f3, {g + 0xC:#x}(r3)
    fsubs f10, f3, f1
    fcmpu f6, f10
    blt q_non_dentro
    lfs f3, {g + 0x10:#x}(r3)
    fadds f10, f3, f1
    fcmpu f11, f10
    ble q_unisci
q_non_dentro:
    lfs f3, {g + 8:#x}(r3)
    fsubs f10, f9, f3
    fsel f4, f10, f3, f9
    lfs f3, {g + 4:#x}(r3)
    fsubs f10, f8, f3
    fsel f3, f10, f8, f3
    fsubs f4, f4, f3
    lfs f3, {g + 0x10:#x}(r3)
    fsubs f10, f11, f3
    fsel f5, f10, f3, f11
    lfs f3, {g + 0xC:#x}(r3)
    fsubs f10, f6, f3
    fsel f3, f10, f6, f3
    fsubs f5, f5, f3
    fabs f10, f4
    fcmpu f10, f1
    bgt q_tocca_y
    fsubs f10, f10, f10
    fcmpu f5, f10
    bgt q_unisci
q_tocca_y:
    fabs f10, f5
    fcmpu f10, f1
    bgt q_gruppo_nuovo
    fsubs f10, f10, f10
    fcmpu f4, f10
    ble q_gruppo_nuovo
q_unisci:
    lfs f3, {g + 4:#x}(r3)
    fsubs f10, f8, f3
    fsel f3, f10, f3, f8
    stfs f3, {g + 4:#x}(r3)
    lfs f3, {g + 8:#x}(r3)
    fsubs f10, f9, f3
    fsel f3, f10, f9, f3
    stfs f3, {g + 8:#x}(r3)
    lfs f3, {g + 0xC:#x}(r3)
    fsubs f10, f6, f3
    fsel f3, f10, f3, f6
    stfs f3, {g + 0xC:#x}(r3)
    lfs f3, {g + 0x10:#x}(r3)
    fsubs f10, f11, f3
    fsel f3, f10, f11, f3
    stfs f3, {g + 0x10:#x}(r3)
    lfs f5, {g:#x}(r3)
    b trasforma
q_fotogramma_nuovo:
{_chiudi_gruppo("qf")}    li r4, 0
    stw r4, {g + 0x18:#x}(r3)
    b q_gruppo_inizia
q_gruppo_nuovo:
{_chiudi_gruppo("qg")}q_gruppo_inizia:
    stfs f8, {g + 4:#x}(r3)
    stfs f9, {g + 8:#x}(r3)
    stfs f6, {g + 0xC:#x}(r3)
    stfs f11, {g + 0x10:#x}(r3)
    lfs f5, 0x1C(r12)
    fmuls f5, f5, f7
    lwz r4, {g + 0x18:#x}(r3)
    addi r4, r4, 1
    stw r4, {g + 0x18:#x}(r3)
    cmpwi r4, 32
    bgt q_gruppo_proprio
    add r4, r4, r4
    add r4, r4, r4
    add r4, r4, r3
    lfs f3, {(CENTRI & 0xFFFF) - 4:#x}(r4)
    fsubs f10, f3, f5
    fabs f10, f10
    lfs f1, 0x4C(r12)
    fcmpu f10, f1
    bge q_gruppo_proprio
    fmr f5, f3
q_gruppo_proprio:
    stfs f5, {g:#x}(r3)
    b trasforma
"""


def _chiudi_gruppo(x):
    """Il gruppo di adesso è finito: il suo centro va in CENTRI[numero - 1] (r3 = 0x817F0000; usa r4, f3, f10)."""
    g = GRUPPO & 0xFFFF
    return f"""    lwz r4, {g + 0x18:#x}(r3)
    cmpwi r4, 1
    blt {x}_no
    cmpwi r4, 32
    bgt {x}_no
    add r4, r4, r4
    add r4, r4, r4
    add r4, r4, r3
    lfs f3, {g + 4:#x}(r3)
    lfs f10, {g + 8:#x}(r3)
    fadds f3, f3, f10
    lfs f10, 0x1C(r12)
    fmuls f3, f3, f10
    stfs f3, {(CENTRI & 0xFFFF) - 4:#x}(r4)
{x}_no:
"""


def _solo_hud(rt):
    """Modo "solo HUD" (MODO_HUD = 0): menu, mappa grande e riquadri restano come nel gioco originale (stirati)."""
    return f"""    lis {rt}, 0x817F
    lbz {rt}, {MODO_HUD & 0xFFFF:#x}({rt})
    cmpwi {rt}, 0
    beq fine
"""


def riga_modo(modo=0):
    """Riga Gecko (00 = scrivi un byte) che mette il modo in MODO_HUD a ogni fotogramma."""
    return f"{0x01000000 | (MODO_HUD & 0xFFFFFF):08X} {modo & 0xFF:08X}"


def _ancora(ra):
    """f5 = ancoraggio dato f7 = 2 * centro del pezzo: 0 (sinistra), 320 (centro) o 640 (destra)."""
    return f"""    lfs f5, 4({ra})
    lfs f10, 8({ra})
    fcmpu f7, f10
    bge non_sinistra
    fsubs f5, f5, f5
    b trasforma
non_sinistra:
    lfs f10, 0xC({ra})
    fcmpu f7, f10
    ble trasforma
    fadds f5, f5, f5
trasforma:
"""


def blocco_quad(v):
    """Pezzo dell'interfaccia: r31 = i 4 vertici (x a +0, +0x14, +0x28, +0x3C), f0 = x del vertice di adesso.
    Solo coi disegni a tutto schermo (vedi _schermo)."""
    return asm.assembla(f"""
    .word {LFSX_X:#x}
{_conta("r3", "r4", 0xFC)}{_schermo("r3", "r4")}{_partita(v, "r3", "r4")}{_costanti("r12")}
{_k(v, "r3", "r12")}
    lfs f3, 0(r31)
    lfs f4, 0x14(r31)
    lfs f5, 0x28(r31)
    lfs f6, 0x3C(r31)
    fsubs f7, f3, f4
    fsel f8, f7, f4, f3
    fsel f9, f7, f3, f4
    fsubs f7, f5, f6
    fsel f10, f7, f6, f5
    fsel f11, f7, f5, f6
    fsubs f7, f8, f10
    fsel f8, f7, f10, f8
    fsubs f7, f9, f11
    fsel f9, f7, f9, f11
    fsubs f7, f9, f8
    ; HUD di gioco a schermo: pezzo con la texture "i_igo_..." (in-game overlay: anello della vita e bordo della
    ; minimappa = "i_igo_gauge"; nome della texture a +0x38 dell'oggetto texture, puntato da +0x60 del pezzo). Segno il
    ; contatore VI di quando lo disegna, SEMPRE (anche fuori partita): nel modo "solo HUD" è la prova (vedi _partita).
    ; (Prima la POSIZIONE in alto a sinistra: nel menu di pausa c'è un pezzo senza texture proprio lì -> il menu
    ; veniva preso per partita e stretto.) Menu di pausa: nessuna texture i_igo (misurato: pezzi senza texture e
    ; "i_bar_fade"); mappa grande: c'è (icona di Spidey) ma la mappa ha il suo controllo.
    lwz r3, 0x60(r31)
    cmpwi r3, 0
    beq non_anello
    lwz r0, 0x38(r3)
    xoris r0, r0, 0x695F
    cmplwi r0, 0x6967
    bne non_anello
    lhz r0, 0x3C(r3)
    cmplwi r0, 0x6F5F
    bne non_anello
    lis r3, {_hl(v["vi"])[0]:#x}
    lwz r0, {_hl(v["vi"])[1]}(r3)
    lis r3, 0x817F
    stw r0, {ANELLO_VI & 0xFFFF:#x}(r3)
non_anello:
    cmpwi r4, 1
    beq in_partita
{_solo_hud("r3")}    lfs f10, 0x24(r12)
    fcmpu f7, f10
    bge fine
    lfs f5, 4(r12)
    b trasforma
in_partita:
    lfs f10, 0x10(r12)
    fcmpu f7, f10
    bge fine
{_mappa_chiusa(v, "r3", "q_non_mappa")}{_solo_hud("r3")}    fadds f7, f8, f9
    lfs f10, 0x50(r31)
    lfs f11, 0x30(r12)
    fcmpu f10, f11
    blt q_mappa_ui
{_gruppo_segnalino(v)}q_mappa_ui:
    lfs f5, 4(r12)
    lfs f10, 0x34(r12)
    fcmpu f7, f10
    bge q_mappa_non_sx
    fsubs f5, f5, f5
    b trasforma
q_mappa_non_sx:
    lfs f10, 0x38(r12)
    fcmpu f7, f10
    ble trasforma
    fadds f5, f5, f5
    b trasforma
q_non_mappa:
{_fuori_mappa("r3")}    fadds f7, f8, f9
    lfs f10, 0x50(r31)
    lfs f11, 0x18(r12)
    fcmpu f10, f11
    ble fisso
    lfs f5, 0x1C(r12)
    fmuls f5, f5, f7
    b trasforma
fisso:
{_ancora("r12")}
{_conta("r3", "r4", 0xEC)}    fsubs f3, f0, f5
    fmadds f0, f3, f2, f5
fine:
{_registro_quad(v) if REGISTRO else ""}""")


CAMPI_REGISTRO = [0, 4, 0x14, 0x18, 0x28, 0x2C, 0x3C, 0x40, 0xC, 0x10, 0x34, 0x38, 0x50]  # (prove) campi copiati


def _registro_quad(v):
    """(prove) Registro dei pezzi (solo al vertice 0, r9 = 0): 256 voci da 0x40 a 0x817F4000, indice a 0x817F7FF8.
    Voce = x/y dei 4 vertici (+0, +4, +0x14, +0x18, +0x28, +0x2C, +0x3C, +0x40), u/v dei vertici 0 e 2, profondità
    (+0x50), poi x del vertice 0 dopo il codice, ancoraggio (f5), modo (r4) e contatore VI."""
    vh, vl = _hl(v["vi"])
    campi = CAMPI_REGISTRO
    copia = "".join(f"    lwz r12, {o:#x}(r31)\n    stw r12, {4 * i:#x}(r3)\n" for i, o in enumerate(campi))
    return f"""    cmpwi r9, 0
    bne reg_fine
    lis r12, 0x817F
    lwz r3, 0x7FF8(r12)
    addi r3, r3, 1
    stw r3, 0x7FF8(r12)
    andi. r3, r3, 0xFF
""" + "    add r3, r3, r3\n" * 6 + f"""    add r3, r3, r12
    addi r3, r3, 0x4000
    stfs f0, 0x34(r3)
    stfs f5, 0x38(r3)
    stw r4, 0x30(r3)
{copia}    lis r12, {vh:#x}
    lwz r12, {vl}(r12)
    stw r12, 0x3C(r3)
reg_fine:
"""


def _subf(d, a, b):
    """subf rd, ra, rb (rd = rb - ra): l'assemblatore non la conosce."""
    return f"    .word {(31 << 26) | (d << 21) | (a << 16) | (b << 11) | (40 << 1):#x}\n"


def _or(a, s_, b):
    return f"    .word {(31 << 26) | (s_ << 21) | (a << 16) | (b << 11) | (444 << 1):#x}\n"


def _mulli(d, a, imm):
    return f"    .word {(7 << 26) | (d << 21) | (a << 16) | (imm & 0xFFFF):#x}\n"


def blocco_testo(v):
    """Scritta: f0 = x di INIZIO, f3 = scala x (già caricati), poi l'istruzione originale carica y in f12.
    - scritte disegnate nel mondo 3D (insegne dei negozi sui palazzi: x = y = 0, le piazza una matrice) non si toccano
      (prima si stringevano anche quelle);
    - l'ancoraggio si sceglie dal CENTRO della scritta, non dall'inizio: le scritte centrate (nome del quartiere,
      'CARICAMENTO') partono a sinistra di 270 e finivano ancorate al bordo sinistro = spostate a sinistra del centro.
      Larghezza = come la calcola il gioco (0x80305A7C): somma delle larghezze delle lettere (font +4 = tabella da 0x1C,
      larghezza intera a +0x18, prima lettera = font +0x14) e degli spazi (font +0xC), per la scala x; solo la prima
      riga; con codici di controllo (colore, scala: < 0x20) si torna al vecchio modo (centro = inizio).
    Registri liberi qui: r0, r3, r5-r7, r9, r11, r12 (r4, r8, r10, f4, f12, f31 servono dopo)."""
    return asm.assembla(f"""
    .word {LFS_Y:#x}
{_conta("r11", "r9", 0xF0)}{_schermo("r11", "r9")}{_partita(v, "r11", "r9")}{_costanti("r12")}
{_k(v, "r11", "r12")}
    lwz r11, 0x14(r31)
    lwz r3, 0x18(r31)
{_or(11, 11, 3)}    cmpwi r11, 0
    beq fine
    lfs f5, 4(r12)
    cmpwi r9, 1
    bne t_menu
    lwz r3, 0xC(r31)
    lwz r5, 0x10(r31)
    lwz r6, 4(r5)
    lwz r7, 0x14(r5)
    li r0, 0
lettera:
    lbz r9, 0(r3)
    addi r3, r3, 1
    cmpwi r9, 0
    beq misurata
    cmpwi r9, 0xA
    beq misurata
    cmpwi r9, 0x20
    beq spazio
    blt non_misurabile
{_subf(9, 7, 9)}{_mulli(9, 9, 0x1C)}    add r9, r9, r6
    lwz r9, 0x18(r9)
    add r0, r0, r9
    b lettera
spazio:
    lwz r9, 0xC(r5)
    add r0, r0, r9
    b lettera
misurata:
    lis r11, 0x817F
    lis r9, 0x4330
    stw r9, 0xD0(r11)
    stw r0, 0xD4(r11)
    lfd f1, 0xD0(r11)
    li r0, 0
    stw r0, 0xD4(r11)
    lfd f6, 0xD0(r11)
    fsub f1, f1, f6
    frsp f1, f1
    fmuls f1, f1, f3
    fadds f7, f0, f0
    fadds f7, f7, f1
    b misura_ok
non_misurabile:
    fadds f7, f0, f0
misura_ok:
{_mappa_chiusa(v, "r11", "t_non_mappa")}{_solo_hud("r11")}    lfs f10, 0x1C(r31)
    lfs f11, 0x3C(r12)
    fcmpu f10, f11
    bge t_mappa_proprio
    lfs f11, 0x18(r12)
    fcmpu f10, f11
    ble t_mappa_bordi
    lfs f11, 0x40(r12)
    fcmpu f10, f11
    blt t_mappa_centro
t_mappa_bordi:
    lfs f11, 0x44(r12)
    fcmpu f12, f11
    bgt t_mappa_centro
    lfs f11, 0x48(r12)
    fcmpu f7, f11
    bge t_mappa_centro
    fsubs f5, f5, f5
    b trasforma
t_mappa_centro:
    lfs f5, 4(r12)
    b trasforma
t_mappa_proprio:
    lfs f5, 0x1C(r12)
    fmuls f5, f5, f7
    b trasforma
t_non_mappa:
    lfs f10, 0x1C(r31)
    lfs f11, 0x18(r12)
    fcmpu f10, f11
    ble fisso
    lfs f5, 0x1C(r12)
    fmuls f5, f5, f7
    b trasforma
t_menu:
{_solo_hud("r11")}    b trasforma
fisso:
{_ancora("r12")}
    fsubs f6, f0, f5
    fmadds f0, f6, f2, f5
    fmuls f3, f3, f2
fine:
{_registro_testo(v) if REGISTRO else ""}""")


REGISTRO = False  # solo prove (prove_gioco/hud_registro.py): ogni scritta disegnata finisce in un registro circolare


def _registro_testo(v):
    """(prove) Registro delle scritte: 256 voci da 0x40 a 0x817F8000, indice a 0x817F7FFC. Voce = i primi 0x30 byte della
    voce del gioco (x originale a +0x14, scala a +0x20...), poi x e scala dopo il codice, 2 * centro misurato (f7; vale
    solo per le scritte misurate in partita) e il contatore VI."""
    vh, vl = _hl(v["vi"])
    copia = "".join(f"    lwz r12, {o:#x}(r31)\n    stw r12, {o:#x}(r11)\n" for o in range(0, 0x30, 4))
    return f"""    lis r12, 0x817F
    lwz r11, 0x7FFC(r12)
    addi r11, r11, 1
    stw r11, 0x7FFC(r12)
    andi. r11, r11, 0xFF
    add r11, r11, r11
    add r11, r11, r11
    add r11, r11, r11
    add r11, r11, r11
    add r11, r11, r11
    add r11, r11, r11
    add r11, r11, r12
    addi r11, r11, 0x4000
    addi r11, r11, 0x4000
    stfs f0, 0x30(r11)
    stfs f3, 0x34(r11)
    stfs f7, 0x38(r11)
{copia}    lis r12, {vh:#x}
    lwz r12, {vl}(r12)
    stw r12, 0x3C(r11)
"""


def blocco_mappa(v):
    """Minimappa: è una scena disegnata in un suo rettangolo (sinistra f1, alto f2, destra f3, basso f4 in pixel 640x480;
    centro 501, 335, raggio 116 x 87) passato a 0x80301BF0 subito dopo. Lo stringo verso il bordo destro come gli altri
    pezzi di destra e lo salvo in RETT_MAPPA. Il gioco calcola dal rettangolo anche i segnalini della minimappa
    (giocatore, obiettivi): finiscono già al posto giusto, quindi il punto "quad" non li tocca (vedi _fuori_mappa)."""
    rh, rl = _hl(RETT_MAPPA)
    return asm.assembla(f"""
    .word {FSUBS_Y:#x}
    lis r11, 0x817F
    lbz r11, {MODO_HUD & 0xFFFF:#x}(r11)
    cmpwi r11, 2
    beq fine
{_costanti("r12")}
{_k(v, "r11", "r12", "f7", "f8")}
    lfs f5, 4(r12)
    fadds f5, f5, f5
    fsubs f6, f1, f5
    fmadds f1, f6, f8, f5
    fsubs f6, f3, f5
    fmadds f3, f6, f8, f5
    lis r11, {rh:#x}
    stfs f1, {rl}(r11)
    stfs f2, {rl + 4}(r11)
    stfs f3, {rl + 8}(r11)
    stfs f4, {rl + 12}(r11)
    ; prospettiva della minimappa in 4:3: il gioco tiene fissa la larghezza e allarga l'altezza con l'aspetto (16:9 =
    ; 1.33 volte più alta): nel rettangolo stretto la mappa veniva alta e tagliata sotto guardando su o giù.
    ; 0x80301BF0 subito dopo ricalcola la prospettiva con questo aspetto ([r13-0x6DE8]+0x2D8, rimesso dal gioco a ogni
    ; fotogramma a 0x80300ACC).
    lfs f7, 0(r12)
    lwz r11, -0x6de8(r13)
    stfs f7, 0x2D8(r11)
fine:
""")


def _fuori_mappa(ry):
    """Salta a 'fine' se il pezzo (x da f8 a f9, y del primo vertice) sta dentro il rettangolo della minimappa salvato da
    blocco_mappa (con 2 pixel di margine): è un segnalino che il gioco ha già messo nel rettangolo stretto."""
    rh, rl = _hl(RETT_MAPPA)
    return f"""    lis {ry}, {rh:#x}
    lfs f10, {rl}({ry})
    lfs f11, 0x20(r12)
    fsubs f10, f10, f11
    fcmpu f8, f10
    blt fuori_mappa
    lfs f10, {rl + 8}({ry})
    fadds f10, f10, f11
    fcmpu f9, f10
    bgt fuori_mappa
    lfs f3, 4(r31)
    lfs f10, {rl + 4}({ry})
    fsubs f10, f10, f11
    fcmpu f3, f10
    blt fuori_mappa
    lfs f10, {rl + 12}({ry})
    fadds f10, f10, f11
    fcmpu f3, f10
    ble fine
fuori_mappa:
"""


def codice(ver, modo=0):
    v = VERSIONI[ver]
    return ([NOME, riga_modo(modo)] + asm.c2(v["quad"], blocco_quad(v)) + asm.c2(v["testo"], blocco_testo(v))
            + asm.c2(v["mappa"], blocco_mappa(v)))


def byte_gecko(ver):
    return 8 * (len(codice(ver)) - 1)


if __name__ == "__main__":
    for ver in VERSIONI:
        print(ver, byte_gecko(ver), "byte")
        print("\n".join(codice(ver)))
