"""HUD 16:9 per ELEMENTI, con la logica IN MEMORIA (come il programma della camera).

Perché (John, 2026-10-09): col codice di prima (hud_wide.py, tutto Gecko) ogni PEZZO dell'interfaccia andava al bordo
sinistro, al centro o al bordo destro secondo dove stava: gli elementi fatti di più pezzi si spezzavano (riquadro
"PARLA": X a sinistra, barra al centro, "?" a destra), gli indicatori che si muovono saltavano da una zona all'altra
(scatti, puntavano storti) e lo spazio dei codici Gecko di Dolphin era finito (~3264 byte per tutti; HUD 2500).
John: "l'HUD sono barra della vita, minimappa, i punti, barre delle vite dei boss o delle macchine, le barre degli
inseguimenti: il resto può restare allargato".

STRUTTURA. Nel Gecko solo 3 agganci (stessi punti di hud_wide): "quad" (x di un vertice di un pezzo: r31 = voce, r9 =
vertice*0x14 nell'ordine 0, 0x14, 0x3C, 0x28, f0 = x), "testo" (f0 = x di inizio, f3 = scala x, f12 = y), "mappa"
(rettangolo della minimappa f1..f4). L'aggancio esegue l'istruzione originale e, se il programma c'è (parola a PROG,
scritta per ultima dal codice AR), lo chiama con mtlr + blrl (CTR NO: nel punto "quad" il gioco conta i 4 vertici con
CTR / bdnz). Il programma salva in memoria l'indirizzo di ritorno e i registri che il gioco usa ancora (quad: r5-r11;
testo: r4-r11 e f4 f8 f9 f13; mappa: r3-r5 r10; i liberi sono quelli che usava hud_wide in quel punto).
ATTENZIONE PowerPC: "addi rX, r0, n" vale n (r0 come sorgente = zero): mai addi/lwz/stw con base r0.

LOGICA (solo in 16:9, solo in partita con l'HUD a schermo = pezzo con texture "i_igo_..." negli ultimi 3 fotogrammi
video, non mappa grande; solo disegni a schermo intero; mai i pezzi col centro entro 30
pixel dal rettangolo della minimappa già stretta, che il gioco calcola da quel rettangolo, spillo rosso compreso):
- ELEMENTI: pezzi e scritte disegnati di seguito che si toccano (6 pixel di margine) formano un elemento (il gioco
  disegna ogni elemento pezzo dopo pezzo: registro). Ogni elemento usa la decisione presa sull'elemento INTERO al
  fotogramma prima (l'elemento di prima che tocca il suo primo pezzo): centro < 270 -> bordo sinistro (x' = x*k), > 370
  -> bordo destro (x' = 640 + (x - 640)*k), in mezzo -> centrato (x' = 320 + (x - 320)*k), k = (4/3) / aspetto.
- NON si toccano (restano come nel gioco, allargati ma interi e allineati al 3D): elementi larghi più di 300 (riquadri
  come "PARLA", sfondi), elementi che si spostano di lato (segnalini che seguono il mondo: centro che cambia di più di
  0,75 fra due fotogrammi -> fermi per 30 fotogrammi).
- Elemento senza un elemento di prima che contiene il suo primo pezzo: quello di prima più simile che lo TOCCA (margine
  14: l'anello che trema dopo un colpo); se non c'è nemmeno quello, decisione PROVVISORIA dal pezzo (bordo oltre
  180 / 460, centro in mezzo; prima restava stirato il primo fotogramma). Un pezzo con texture non entra mai in un
  elemento-segnalino che tocca soltanto (il "?" sopra un civile si portava via il riquadro "PARLA").
- "In partita" contato in fotogrammi DEL GIOCO (D_FR), non in VI: in combattimento il gioco rallenta e i pezzi
  disegnati prima dell'anello tornavano 4:3 per un fotogramma.
- Minimappa: il suo rettangolo si stringe verso il bordo destro (e la sua prospettiva torna 4:3, vedi hud_wide).

REGISTRO (prove): byte 817F06E0 bit 1 = pezzi a 0x817F4000 (256 voci da 0x40, indice DATI+0), bit 2 = scritte a
0x817F8000 (128 voci da 0x80, indice DATI+4); numero d'ordine comune DATI+8 (pezzi +0x34, scritte +0x78); nei pezzi la
x del vertice 0 DOPO il codice a +0x3C, nelle scritte x e scala dopo il codice a +0x70/+0x74."""
import ppcasm as asm
import hud_wide

PROG = 0x817FCA00  # programma (zona a zero, dopo i dati che finiscono a C900; sensori di prova 4000-DFFF, routine del teletrasporto E000)
DATI = 0x817FC000  # dati del programma (registri salvati, elementi del fotogramma di adesso e di prima)
FLAG = 0x817F06E0
REG_Q, REG_T = 0x817F4000, 0x817F8000
NOME_PROG = "$HUD program (needed by the 16:9 HUD)"
MAX_EL = 32
# dati (offset da DATI)
D_IND_Q, D_IND_T, D_ORD = 0x000, 0x004, 0x008
D_SALVA_Q, D_SALVA_M, D_SALVA_T, D_SALVA_TF = 0x010, 0x030, 0x040, 0x060
D_VI, D_N, D_NP, D_QA, D_QOK, D_K, D_RVI, D_RETT, D_TMP, D_ANELLO, D_RIT = (0x080, 0x084, 0x088, 0x08C, 0x090, 0x094,
                                                                            0x098, 0x0A0, 0x0B0, 0x0C0, 0x0C4)
D_SEQ, D_ULT = 0x0DC, 0x0E0  # contatore di TUTTI i pezzi/scritte/minimappa disegnati e quello dell'ultimo raggruppato: si
# uniscono solo pezzi davvero consecutivi (la minimappa, scartata, separava l'anello dai segnalini: scartandola senza
# contarla un "?" che passava sopra l'anello veniva unito all'anello, che poi restava stirato per un minuto)
D_PT = 0x0E4  # (prove) esito dell'ultimo controllo "in partita": 1 sì, 2 pausa (modo 2 + byte pausa), 3 anello vecchio, 0 mappa
# FOTOGRAMMI DEL GIOCO (non VI): in combattimento il gioco rallenta e un fotogramma può durare 3-4 VI -> "anello negli
# ultimi 3 VI" falliva per i pezzi disegnati PRIMA dell'anello (HUD in 4:3 per un fotogramma). D_FR = numero del
# fotogramma (cambia quando cambia il VI fra due disegni), D_FVI = suo VI, D_ANELLO = fotogramma dell'ultimo anello,
# D_AVI = suo VI, D_AP = byte pausa in quel momento, D_RALL = 1 se nel fotogramma finito c'era l'anello col byte pausa
# a 1 (riflessi: i pezzi disegnati prima dell'anello non sono il menu), D_CONTEX = 1 pezzo con texture (non segnalino)
D_FR, D_FVI, D_AVI, D_RALL, D_AP, D_CONTEX = 0x0E8, 0x0EC, 0x0F0, 0x0F4, 0x0F8, 0x0B8
# INIZIO DEL FOTOGRAMMA = la maschera della minimappa ("minimapmask", primo pezzo di ogni fotogramma in partita), non il
# cambio del VI: sul PC di John (gioco lento) il VI cambiava A METÀ dei disegni dell'interfaccia e il riquadro "PARLA"
# veniva spezzato in due elementi (uno "mosso" a ogni fotogramma = stirato: foto di John). Senza minimappa da MM_VI VI
# si torna al cambio del VI. D_ISMM = il pezzo di adesso è la maschera, D_MMVI = VI dell'ultima maschera.
D_ISMM, D_MMVI = 0x0BC, 0x0FC
MM_VI = 8
# HUD NASCOSTO (codice "HUD on/off", 817F0014 dispari) e il gioco lo rimette per UN fotogramma (dopo i filmati, es.
# tuffo in acqua, o chiudendo la mappa: il codice AR lo rinasconde solo al giro dopo). In quel fotogramma l'anello c'è
# (= "in partita"): pezzi, scritte, segnalini del mondo (John: con un indicatore vicino compariva lui per un fotogramma)
# e minimappa vanno fuori dallo schermo (x = C_VIA), tranne le dissolvenze. Da nascosto il gioco di suo non disegna l'anello: "in partita" falso e niente cambia.
# D_HIDQ = il pezzo di adesso va nascosto, D_TIPO = tipo dell'elemento (2 = segnalino), messo da elemento.
D_HIDQ, D_TIPO = 0x09C, 0x00C
HUD_STATO = 0x817F0014
# FOTO DELLA MAPPA (menu in gioco > Viaggio, mappa di tutta la città fatta dall'app): byte != 0 = TUTTI i pezzi e le
# scritte fuori dallo schermo (icone, nomi dei quartieri, cornici della mappa grande): nelle foto resta solo la città.
# 2 = mappa 3D: tutto via TRANNE l'icona di Spidey (texture i_igo_, l'unica i_igo nella mappa grande).
# Lo accende/spegne l'app (core.MappaCitta) solo durante il giro fotografico; memoria a zero a ogni avvio.
FOTO = 0x817FF1F0
D_MONDO = 0x0D8  # 1 = il pezzo di adesso è un segnalino del mondo (texture in MONDO): il suo elemento non si tocca mai
D_CUR, D_PREV = 0x100, 0x500
# texture dei segnalini che seguono il mondo (primi 4 caratteri): non si toccano mai, e nemmeno l'elemento che toccano
# (da fermi sembravano elementi fissi e venivano spostati; muovendosi tornavano al loro posto = scatti). Dai nomi in
# memoria: i_poi_01/02, i_asset_circle/offscreen, i_icon_* (civili, obiettivi), i_goto_*, i_3d_bonus_icons, i_special_icon,
# i_spline_path, i_line_goal_0, i_web_reticle_*.
MONDO = ["i_po", "i_as", "i_ic", "i_go", "i_3d", "i_sp", "i_li", "i_we"]
# elemento (0x20): +0 x0, +4 x1, +8 y0, +C y1, +10 ancoraggio (float), +14 da sistemare (0/1), +18 centro di prima
# (float, 1e9 = non c'era), +1C fotogrammi di "mosso" rimasti
SOGLIA_SX, SOGLIA_DX, LARGO, MARGINE, MOSSO, TENUTA_MOSSO, ALT_TESTO = 270.0, 370.0, 300.0, 6.0, 0.75, 30, 18.0
ANELLO_FOTOGRAMMI = 3  # fotogrammi del gioco
ANELLO_VI = 20  # e comunque non più di 20 VI (schermo nero lungo e poi caricamento: i fotogrammi senza disegni non contano)


def _hl(a):
    return hud_wide._hl(a)


COSTANTI = [("c_43", 1.3333334), ("c_134", 1.34), ("c_sx", SOGLIA_SX), ("c_dx", SOGLIA_DX), ("c_320", 320.0),
            ("c_640", 640.0), ("c_largo", LARGO), ("c_marg", MARGINE), ("c_mosso", MOSSO), ("c_mezzo", 0.5),
            ("c_alt", ALT_TESTO), ("c_niente", 1e9), ("c_2", 2.0), ("c_630", 630.0), ("c_bordo_mappa", 30.0),
            ("c_psx", 180.0), ("c_pdx", 460.0), ("c_marg2", 14.0), ("c_alto", 170.0), ("c_via", -5000.0)]
C = {n: 4 * i for i, (n, _) in enumerate(COSTANTI)}  # offset dentro la tabella (r11 = tabella, presa con bl)


def _costanti(x):
    return (f"    bl dopo_costanti_{x}\n" + "".join(f"    .float {v}\n" for _, v in COSTANTI)
            + f"dopo_costanti_{x}:\n    mflr r11\n")


def _dati(r="r10"):
    h, l = _hl(DATI)
    return f"    lis {r}, {h:#x}\n    addi {r}, {r}, {l}\n"


def _partita(v, x, pausa=True):
    """r3 = 1 se in partita con l'HUD a schermo, se no 0. Usa r3, r4, r5; r10 = DATI. Lo stato di Spidey NO (stordito
    vale -1 per un secondo). Titolo, caricamenti e "CONTINUA?" non disegnano l'anello: anello negli ultimi
    ANELLO_FOTOGRAMMI fotogrammi DEL GIOCO (e ANELLO_VI VI); la mappa grande lo disegna (icona di Spidey): byte suo.
    Menu di pausa: il byte pausa va a 1 subito all'apertura (il modo dell'interfaccia dopo qualche fotogramma) e
    l'anello non c'è più -> byte pausa 1 e anello non disegnato in QUESTO fotogramma = menu, tranne se nel fotogramma
    prima c'erano anello e byte pausa 1 (riflessi: il byte pausa vale 1 e l'anello arriva DOPO alcuni pezzi, es. il
    riquadro "PARLA"). Per il rettangolo della minimappa (pausa=False) niente controllo della pausa."""
    ph, pl = _hl(v["pausa"]); vh, vl = _hl(v["vi"]); mh, ml = _hl(v["mappa_aperta"])
    controllo_pausa = f"""    lis r4, {ph:#x}
    lbz r4, {pl}(r4)
    cmpwi r4, 1
    bne pt_np_{x}
    lwz r4, {D_FR}(r10)
    lwz r5, {D_ANELLO}(r10)
    cmpw r4, r5
    beq pt_np_{x}
    lwz r4, {D_RALL}(r10)
    cmpwi r4, 1
    beq pt_np_{x}
    li r3, 2
    b pt_fatto_{x}
""" if pausa else ""
    # minimappa: col byte pausa a 0 è partita anche se l'anello non è ancora passato (chiudendo il menu di pausa il
    # rettangolo arriva PRIMA dell'anello, che mancava da tanti fotogrammi: minimappa stirata per un fotogramma)
    minimappa = f"""    lis r4, {ph:#x}
    lbz r4, {pl}(r4)
    cmpwi r4, 0
    li r3, 1
    beq pt_fatto_{x}
""" if not pausa else ""
    return f"""    li r3, 0
    lis r4, {mh:#x}
    lbz r4, {ml}(r4)
    cmpwi r4, 80
    beq pt_fatto_{x}
{controllo_pausa}{minimappa}pt_np_{x}:
    li r3, 3
    lwz r4, {D_FR}(r10)
    lwz r5, {D_ANELLO}(r10)
    addi r5, r5, {ANELLO_FOTOGRAMMI}
    cmpw r4, r5
    bgt pt_fatto_{x}
    lis r4, {vh:#x}
    lwz r4, {vl}(r4)
    lwz r5, {D_AVI}(r10)
    addi r5, r5, {ANELLO_VI}
    cmpw r4, r5
    bgt pt_fatto_{x}
    li r3, 1
pt_fatto_{x}:
    stw r3, {D_PT}(r10)
    cmpwi r3, 1
    li r3, 1
    beq pt_si_{x}
    li r3, 0
pt_si_{x}:
"""


def _fotogramma(v, x):
    """Fotogramma nuovo del gioco -> D_FR + 1 e D_RALL (vedi D_FR). Inizio = maschera della minimappa (D_ISMM, vedi D_MMVI);
    senza minimappa da MM_VI VI, il cambio del VI. Usa r3-r5; r10 = DATI."""
    vh, vl = _hl(v["vi"])
    return f"""    lis r4, {vh:#x}
    lwz r4, {vl}(r4)
    lwz r5, {D_ISMM}(r10)
    cmpwi r5, 0
    beq fg_nomm_{x}
    stw r4, {D_MMVI}(r10)
    b fg_nuovo_{x}
fg_nomm_{x}:
    lwz r5, {D_MMVI}(r10)
    addi r5, r5, {MM_VI}
    cmpw r4, r5
    ble fg_ok_{x}
    lwz r5, {D_FVI}(r10)
    cmpw r4, r5
    beq fg_ok_{x}
fg_nuovo_{x}:
    stw r4, {D_FVI}(r10)
    lwz r5, {D_FR}(r10)
    lwz r3, {D_ANELLO}(r10)
    li r4, 0
    cmpw r3, r5
    bne fg_r_{x}
    lwz r3, {D_AP}(r10)
    cmpwi r3, 1
    bne fg_r_{x}
    li r4, 1
fg_r_{x}:
    stw r4, {D_RALL}(r10)
    addi r5, r5, 1
    stw r5, {D_FR}(r10)
fg_ok_{x}:
"""


def _schermo(salta):
    """Salta se il gioco non disegna sullo schermo intero (rettangolo 0..639 e finestra GX da 0). Usa r4, r5."""
    return f"""    lwz r4, -0x6de8(r13)
    lwz r5, 0x284(r4)
    cmpwi r5, 0
    bne {salta}
    lwz r5, 0x28C(r4)
    cmpwi r5, 639
    bne {salta}
    lwz r4, -0x4dd8(r13)
    lwz r5, 0x4F4(r4)
    cmpwi r5, 0
    bne {salta}
"""


def _k(v, salta):
    """f2 = k = (4/3) / aspetto; se l'aspetto è <= 1.34 (niente 16:9) salta. Usa r4, f1; r11 = costanti."""
    ah, al = _hl(v["aspetto"])
    return f"""    lis r4, {ah:#x}
    lfs f1, {al}(r4)
    lfs f2, {C['c_134']}(r11)
    fcmpu f1, f2
    blt {salta}
    lfs f2, {C['c_43']}(r11)
    fdivs f2, f2, f1
"""


def _per32(r):
    return "".join(f"    add {r}, {r}, {r}\n" for _ in range(5))


def _elemento(v):
    """Sottoprogramma 'elemento' (bl): f8..f9 = x del pezzo, f6..f7 = y, DATI+D_MONDO = 0 pezzo qualsiasi, 1 segnalino del
    mondo, 2 HUD sicuro (texture i_igo_); r10 = DATI, r11 = costanti. Torna con r4 = 1 se va sistemato e f5 =
    ancoraggio. Elemento: +0x14 = 0 non si tocca / 1 si sistema / 2 segnalino del mondo; +0x1C = fotogrammi di "mosso"
    rimasti, -1 = HUD sicuro (mai "mosso": l'anello trema quando Spidey prende un colpo). I segnalini formano sempre
    un elemento a parte (il "?" verde comparso accanto all'anello lo univa all'anello e l'anello tornava stirato).
    Fotogramma nuovo (contatore VI cambiato) = decide gli elementi finiti (sull'elemento intero) e li passa in PREV.
    Usa r3-r9, f1, f5, f10, f11, f13 (f2 = k e f6-f9 restano)."""
    vh, vl = _hl(v["vi"])
    sovrapposto = lambda r, no: f"""    lfs f10, 0({r})
    fsubs f10, f10, f13
    fcmpu f9, f10
    blt {no}
    lfs f10, 4({r})
    fadds f10, f10, f13
    fcmpu f8, f10
    bgt {no}
    lfs f10, 8({r})
    fsubs f10, f10, f13
    fcmpu f7, f10
    blt {no}
    lfs f10, 0xC({r})
    fadds f10, f10, f13
    fcmpu f6, f10
    bgt {no}
"""
    ancora = lambda dest, x: f"""    lfs {dest}, {C['c_320']}(r11)
    lfs f10, {C['c_sx']}(r11)
    fcmpu f1, f10
    bge anc_non_sx_{x}
    fsubs {dest}, {dest}, {dest}
    b anc_ok_{x}
anc_non_sx_{x}:
    lfs f10, {C['c_dx']}(r11)
    fcmpu f1, f10
    ble anc_ok_{x}
    lfs {dest}, {C['c_640']}(r11)
anc_ok_{x}:
"""
    return f"""elemento:
    lwz r4, {D_FR}(r10)
    lwz r5, {D_VI}(r10)
    cmpw r4, r5
    beq el_stesso
    stw r4, {D_VI}(r10)
    ; ---- fotogramma nuovo: decisione per ogni elemento finito, poi CUR -> PREV
    lwz r6, {D_N}(r10)
    stw r6, {D_NP}(r10)
    addi r7, r10, {D_CUR}
    addi r8, r10, {D_PREV}
el_decidi:
    cmpwi r6, 0
    beq el_decisi
    lfs f10, 0(r7)
    lfs f11, 4(r7)
    fsubs f13, f11, f10
    fadds f1, f10, f11
    lfs f10, {C['c_mezzo']}(r11)
    fmuls f1, f1, f10
    lwz r3, 0x14(r7)
    lwz r9, 0x1C(r7)
    cmpwi r3, 2
    beq el_scelto
    cmpwi r9, -1
    beq el_mov_ok
    lfs f10, 0x18(r7)
    lfs f11, {C['c_niente']}(r11)
    fcmpu f10, f11
    beq el_fermo
    fsubs f10, f1, f10
    fabs f10, f10
    lfs f11, {C['c_mosso']}(r11)
    fcmpu f10, f11
    ble el_fermo
    li r9, {TENUTA_MOSSO}
    b el_mov_ok
el_fermo:
    cmpwi r9, 0
    ble el_mov_ok
    addi r9, r9, -1
el_mov_ok:
    li r3, 0
    lfs f11, {C['c_largo']}(r11)
    fcmpu f13, f11
    bgt el_scelto
    cmpwi r9, 0
    bgt el_scelto
    li r3, 1
el_scelto:
    stw r9, 0x1C(r8)
    stw r3, 0x14(r8)
{ancora("f5", "d")}    stfs f5, 0x10(r8)
    lfs f10, 0(r7)
    stfs f10, 0(r8)
    lfs f10, 4(r7)
    stfs f10, 4(r8)
    lfs f10, 8(r7)
    stfs f10, 8(r8)
    lfs f10, 0xC(r7)
    stfs f10, 0xC(r8)
    stfs f1, 0x18(r8)
    addi r7, r7, 0x20
    addi r8, r8, 0x20
    addi r6, r6, -1
    b el_decidi
el_decisi:
    ; ---- un elemento tutto DENTRO un altro più largo prende la sua decisione (la X del tasto e la scritta "PARLA"
    ; disegnate dopo l'anello facevano elemento a sé: la X, a sinistra del centro, andava al bordo sinistro e si
    ; staccava dal riquadro centrato)
    lwz r6, {D_NP}(r10)
    addi r7, r10, {D_PREV}
el_dentro_i:
    cmpwi r6, 0
    beq el_dentro_fine
    lwz r9, {D_NP}(r10)
    addi r8, r10, {D_PREV}
    lfs f13, {C['c_2']}(r11)
el_dentro_j:
    cmpwi r9, 0
    beq el_dentro_i_dopo
    cmpw r8, r7
    beq el_dentro_j_dopo
    lfs f10, 0(r8)
    fsubs f10, f10, f13
    lfs f11, 0(r7)
    fcmpu f11, f10
    blt el_dentro_j_dopo
    lfs f10, 4(r8)
    fadds f10, f10, f13
    lfs f11, 4(r7)
    fcmpu f11, f10
    bgt el_dentro_j_dopo
    lfs f10, 8(r8)
    fsubs f10, f10, f13
    lfs f11, 8(r7)
    fcmpu f11, f10
    blt el_dentro_j_dopo
    lfs f10, 0xC(r8)
    fadds f10, f10, f13
    lfs f11, 0xC(r7)
    fcmpu f11, f10
    bgt el_dentro_j_dopo
    ; j più largo di i (se no due elementi uguali si scambierebbero la decisione)
    lfs f10, 4(r8)
    lfs f11, 0(r8)
    fsubs f10, f10, f11
    lfs f11, 4(r7)
    lfs f1, 0(r7)
    fsubs f11, f11, f1
    fcmpu f10, f11
    ble el_dentro_j_dopo
    lwz r4, 0x14(r8)
    stw r4, 0x14(r7)
    lfs f10, 0x10(r8)
    stfs f10, 0x10(r7)
    b el_dentro_i_dopo
el_dentro_j_dopo:
    addi r8, r8, 0x20
    addi r9, r9, -1
    b el_dentro_j
el_dentro_i_dopo:
    addi r7, r7, 0x20
    addi r6, r6, -1
    b el_dentro_i
el_dentro_fine:
    li r4, 0
    stw r4, {D_N}(r10)
    b el_nuovo
el_stesso:
    ; ---- il pezzo segue SUBITO l'ultimo raggruppato e tocca il suo elemento? allora ne fa parte
    lwz r6, {D_N}(r10)
    cmpwi r6, 0
    beq el_nuovo
    lwz r4, {D_SEQ}(r10)
    lwz r5, {D_ULT}(r10)
    addi r5, r5, 1
    cmpw r4, r5
    bne el_nuovo
    addi r6, r6, -1
{_per32("r6")}    addi r7, r10, {D_CUR}
    add r7, r7, r6
    lwz r5, {D_MONDO}(r10)
    lwz r3, 0x14(r7)
    ; HUD sicuro (anello, cerchi dei segnalini) mai dentro un elemento-segnalino già fatto (i cerchi vengono prima della
    ; loro icona): l'anello disegnato subito dopo un "?" che gli sta sopra diventava "segnalino" e restava stirato
    cmpwi r5, 2
    bne el_unisci_a
    cmpwi r3, 2
    beq el_nuovo
el_unisci_a:
    ; segnalino in un elemento non-segnalino: solo se ci sta DENTRO (l'icona dentro il suo cerchio), non se lo tocca.
    ; E viceversa un pezzo con texture (non segnalino) in un elemento-segnalino: solo se ci sta dentro (il "?" sopra un
    ; civile disegnato subito prima del riquadro "PARLA" e che lo toccava se lo portava via: riquadro stirato)
    cmpwi r5, 1
    beq el_unisci_seg
    cmpwi r3, 2
    bne el_unisci_b
    lwz r4, {D_CONTEX}(r10)
    cmpwi r4, 1
    bne el_unisci_b
    b el_unisci_dentro
el_unisci_seg:
    cmpwi r3, 2
    beq el_unisci_b
el_unisci_dentro:
    lfs f13, {C['c_2']}(r11)
    lfs f10, 0(r7)
    fsubs f10, f10, f13
    fcmpu f8, f10
    blt el_nuovo
    lfs f10, 4(r7)
    fadds f10, f10, f13
    fcmpu f9, f10
    bgt el_nuovo
    lfs f10, 8(r7)
    fsubs f10, f10, f13
    fcmpu f6, f10
    blt el_nuovo
    lfs f10, 0xC(r7)
    fadds f10, f10, f13
    fcmpu f7, f10
    bgt el_nuovo
el_unisci_b:
    lfs f13, {C['c_marg']}(r11)
{sovrapposto("r7", "el_nuovo")}    lfs f10, 0(r7)
    fsubs f11, f8, f10
    fsel f10, f11, f10, f8
    stfs f10, 0(r7)
    lfs f10, 4(r7)
    fsubs f11, f9, f10
    fsel f10, f11, f9, f10
    stfs f10, 4(r7)
    lfs f10, 8(r7)
    fsubs f11, f6, f10
    fsel f10, f11, f10, f6
    stfs f10, 8(r7)
    lfs f10, 0xC(r7)
    fsubs f11, f7, f10
    fsel f10, f11, f7, f10
    stfs f10, 0xC(r7)
    b el_tipo
el_nuovo:
    ; ---- elemento nuovo: riquadro = il pezzo; decisione dall'elemento di prima (non segnalino) che lo tocca
    lwz r6, {D_N}(r10)
    cmpwi r6, {MAX_EL}
    bge el_pieno
    addi r4, r6, 1
    stw r4, {D_N}(r10)
{_per32("r6")}    addi r7, r10, {D_CUR}
    add r7, r7, r6
    stfs f8, 0(r7)
    stfs f9, 4(r7)
    stfs f6, 8(r7)
    stfs f7, 0xC(r7)
    li r4, 0
    stw r4, 0x14(r7)
    stw r4, 0x1C(r7)
    lfs f5, {C['c_niente']}(r11)
    stfs f5, 0x18(r7)
    lwz r5, {D_MONDO}(r10)
el_cerca_via:
    ; elemento di prima più simile (somma delle differenze dei 4 lati) fra quelli che CONTENGONO il pezzo (prima bastava
    ; toccarlo: i pezzi nuovi del menu di pausa sopra l'anello ne prendevano la decisione e venivano stretti)
    lwz r6, {D_NP}(r10)
    addi r8, r10, {D_PREV}
    lfs f13, {C['c_marg']}(r11)
    lfs f11, {C['c_niente']}(r11)
    li r3, 0
el_cerca:
    cmpwi r6, 0
    beq el_cercato
    lfs f10, 0(r8)
    fsubs f10, f10, f13
    fcmpu f8, f10
    blt el_cerca_dopo
    lfs f10, 4(r8)
    fadds f10, f10, f13
    fcmpu f9, f10
    bgt el_cerca_dopo
    lfs f10, 8(r8)
    fsubs f10, f10, f13
    fcmpu f6, f10
    blt el_cerca_dopo
    lfs f10, 0xC(r8)
    fadds f10, f10, f13
    fcmpu f7, f10
    bgt el_cerca_dopo
    lfs f10, 0(r8)
    fsubs f10, f10, f8
    fabs f1, f10
    lfs f10, 4(r8)
    fsubs f10, f10, f9
    fabs f10, f10
    fadds f1, f1, f10
    lfs f10, 8(r8)
    fsubs f10, f10, f6
    fabs f10, f10
    fadds f1, f1, f10
    lfs f10, 0xC(r8)
    fsubs f10, f10, f7
    fabs f10, f10
    fadds f1, f1, f10
    fcmpu f1, f11
    bge el_cerca_dopo
    fmr f11, f1
    mr r3, r8
el_cerca_dopo:
    addi r8, r8, 0x20
    addi r6, r6, -1
    b el_cerca
el_cercato:
    cmpwi r3, 0
    bne el_eredita
    ; nessuno lo contiene: il più simile fra quelli che lo TOCCANO (margine 14). L'anello che trema quando Spidey prende
    ; un colpo si sposta di più del margine: era "nuovo" e tornava stirato per un fotogramma (John: "in combattimento
    ; per frame singoli si rimette in 4:3"); un segnalino che si muove portava il suo cerchio a una decisione nuova
    lwz r6, {D_NP}(r10)
    addi r8, r10, {D_PREV}
    lfs f13, {C['c_marg2']}(r11)
    lfs f11, {C['c_niente']}(r11)
el_cerca2:
    cmpwi r6, 0
    beq el_cercato2
    lfs f10, 4(r8)
    fadds f10, f10, f13
    fcmpu f8, f10
    bgt el_cerca2_dopo
    lfs f10, 0(r8)
    fsubs f10, f10, f13
    fcmpu f9, f10
    blt el_cerca2_dopo
    lfs f10, 0xC(r8)
    fadds f10, f10, f13
    fcmpu f6, f10
    bgt el_cerca2_dopo
    lfs f10, 8(r8)
    fsubs f10, f10, f13
    fcmpu f7, f10
    blt el_cerca2_dopo
    ; un pezzo qualsiasi non prende la decisione di un segnalino solo perché lo tocca (riquadro "PARLA" che compare
    ; sotto il "?": resterebbe stirato il primo fotogramma)
    lwz r4, 0x14(r8)
    cmpwi r4, 2
    bne el_cerca2_tipo_ok
    cmpwi r5, 0
    beq el_cerca2_dopo
el_cerca2_tipo_ok:
    lfs f10, 0(r8)
    fsubs f10, f10, f8
    fabs f1, f10
    lfs f10, 4(r8)
    fsubs f10, f10, f9
    fabs f10, f10
    fadds f1, f1, f10
    lfs f10, 8(r8)
    fsubs f10, f10, f6
    fabs f10, f10
    fadds f1, f1, f10
    lfs f10, 0xC(r8)
    fsubs f10, f10, f7
    fabs f10, f10
    fadds f1, f1, f10
    fcmpu f1, f11
    bge el_cerca2_dopo
    fmr f11, f1
    mr r3, r8
el_cerca2_dopo:
    addi r8, r8, 0x20
    addi r6, r6, -1
    b el_cerca2
el_cercato2:
    cmpwi r3, 0
    bne el_eredita
    ; HUD sicuro (i_igo a sinistra) nuovo: decisione provvisoria solo nella zona dell'anello (in alto a sinistra); i
    ; cerchi dei segnalini (stessa texture) appena comparsi restano com'è
    cmpwi r5, 2
    bne el_prov
    fadds f1, f8, f9
    lfs f10, {C['c_mezzo']}(r11)
    fmuls f1, f1, f10
    lfs f10, {C['c_psx']}(r11)
    fcmpu f1, f10
    bge el_tipo
    fadds f1, f6, f7
    lfs f10, {C['c_mezzo']}(r11)
    fmuls f1, f1, f10
    lfs f10, {C['c_alto']}(r11)
    fcmpu f1, f10
    bge el_tipo
el_prov:
    ; nessun elemento di prima: decisione PROVVISORIA dal pezzo (prima restava stirato il primo fotogramma, e così
    ; anche ogni fotogramma un elemento che cresce o sale): stretto verso il bordo se il pezzo sta oltre 180 / 460,
    ; centrato in mezzo; largo più di LARGO = non si tocca
    fsubs f13, f9, f8
    lfs f11, {C['c_largo']}(r11)
    fcmpu f13, f11
    bgt el_tipo
    fadds f1, f8, f9
    lfs f10, {C['c_mezzo']}(r11)
    fmuls f1, f1, f10
    lfs f5, {C['c_320']}(r11)
    lfs f10, {C['c_psx']}(r11)
    fcmpu f1, f10
    bge el_prov_non_sx
    fsubs f5, f5, f5
    b el_prov_ok
el_prov_non_sx:
    lfs f10, {C['c_pdx']}(r11)
    fcmpu f1, f10
    ble el_prov_ok
    lfs f5, {C['c_640']}(r11)
el_prov_ok:
    stfs f5, 0x10(r7)
    li r4, 1
    stw r4, 0x14(r7)
    b el_tipo
el_eredita:
    lwz r4, 0x14(r3)
    stw r4, 0x14(r7)
    lfs f10, 0x10(r3)
    stfs f10, 0x10(r7)
    lfs f10, 0x18(r3)
    stfs f10, 0x18(r7)
    lwz r4, 0x1C(r3)
    stw r4, 0x1C(r7)
el_tipo:
    ; il pezzo di adesso: segnalino -> tutto l'elemento resta com'è (2); HUD sicuro -> mai "mosso" (-1)
    cmpwi r5, 1
    bne el_tipo_hud
    li r4, 2
    stw r4, 0x14(r7)
    b el_fine
el_tipo_hud:
    cmpwi r5, 2
    bne el_fine
    lwz r4, 0x14(r7)
    cmpwi r4, 2
    beq el_fine
    li r4, -1
    stw r4, 0x1C(r7)
el_fine:
    lwz r4, {D_SEQ}(r10)
    stw r4, {D_ULT}(r10)
    li r4, 0
    lwz r3, 0x14(r7)
    cmpwi r3, 1
    bne el_ritorno
    li r4, 1
el_ritorno:
    stw r3, {D_TIPO}(r10)
    lfs f5, 0x10(r7)
    blr
el_pieno:
    li r4, 0
    stw r4, {D_TIPO}(r10)
    blr
"""


def _mondo(rn, rt, x):
    """r0 = 1 se i primi 4 caratteri del nome (in rn) sono di un segnalino del mondo (MONDO). Usa rt."""
    s = ""
    for i, p in enumerate(MONDO):
        w = int.from_bytes(p.encode(), "big")
        s += f"""    lis {rt}, {w >> 16:#x}
    ori {rt}, {rt}, {w & 0xFFFF:#x}
    cmpw {rn}, {rt}
    beq mondo_si_{x}
"""
    return s + f"""    b mondo_fine_{x}
mondo_si_{x}:
    li r0, 1
mondo_fine_{x}:
"""


DEBUG = False  # (prove) segnaposto: DATI+0xD0 = punto raggiunto nella routine delle scritte, +0xD4 contatore


def _punto(n):
    if not DEBUG:
        return ""
    return f"""    lis r12, {_hl(DATI)[0]:#x}
    addi r12, r12, {_hl(DATI)[1]}
    li r0, {n}
    stw r0, 0xD0(r12)
"""


def _salva(regs, off, fregs=(), foff=0):
    s = "".join(f"    stw r{r}, {off + 4 * i:#x}(r12)\n" for i, r in enumerate(regs))
    return s + "".join(f"    stfd f{f}, {foff + 8 * i:#x}(r12)\n" for i, f in enumerate(fregs))


def _rimetti(regs, off, fregs=(), foff=0):
    s = "".join(f"    lwz r{r}, {off + 4 * i:#x}(r12)\n" for i, r in enumerate(regs))
    return s + "".join(f"    lfd f{f}, {foff + 8 * i:#x}(r12)\n" for i, f in enumerate(fregs))


def _base12():
    h, l = _hl(DATI)
    return f"    lis r12, {h:#x}\n    addi r12, r12, {l}\n"


def _ingresso_quad(v):
    """Pezzo: f0 = x del vertice. Al vertice 0 decide (elemento) e lo ricorda per gli altri 3 vertici."""
    vh, vl = _hl(v["vi"])
    return f"""ingresso_quad:
{_base12()}    mflr r0
    stw r0, {D_RIT}(r12)
{_salva(range(5, 12), D_SALVA_Q)}{_dati()}{_costanti("q")}    cmpwi r9, 0
    bne q_fg_fatto
    li r0, 0
    lwz r3, 0x60(r31)
    cmpwi r3, 0
    beq q_mm_ok
    lwz r4, 0x38(r3)
    lis r5, 0x6D69
    ori r5, r5, 0x6E69
    cmpw r4, r5
    bne q_mm_ok
    lwz r4, 0x3C(r3)
    lis r5, 0x6D61
    ori r5, r5, 0x706D
    cmpw r4, r5
    bne q_mm_ok
    li r0, 1
q_mm_ok:
    stw r0, {D_ISMM}(r10)
{_fotogramma(v, "q")}q_fg_fatto:
    ; texture "i_igo_..." = HUD di gioco a schermo (sempre, anche fuori partita: è la prova)
    lwz r3, 0x60(r31)
    cmpwi r3, 0
    beq q_non_igo
    lwz r0, 0x38(r3)
    lis r4, 0x695F
    ori r4, r4, 0x6967
    cmpw r0, r4
    bne q_non_igo
    lhz r0, 0x3C(r3)
    cmplwi r0, 0x6F5F
    bne q_non_igo
    lis r4, {vh:#x}
    lwz r0, {vl}(r4)
    stw r0, {D_AVI}(r10)
    lwz r0, {D_FR}(r10)
    stw r0, {D_ANELLO}(r10)
    lis r4, {_hl(v["pausa"])[0]:#x}
    lbz r0, {_hl(v["pausa"])[1]}(r4)
    stw r0, {D_AP}(r10)
q_non_igo:
    cmpwi r9, 0
    bne q_altri_vertici
    li r0, 0
    stw r0, {D_QOK}(r10)
    stw r0, {D_HIDQ}(r10)
    lwz r3, {D_SEQ}(r10)
    addi r3, r3, 1
    stw r3, {D_SEQ}(r10)

{_k(v, "q_fine")}{_schermo("q_fine")}{_partita(v, "q")}    cmpwi r3, 0
    beq q_fine
    ; HUD nascosto dal codice HUD on/off? (vedi D_HIDQ)
    lis r4, {HUD_STATO >> 16:#x}
    lbz r4, {HUD_STATO & 0xFFFF:#x}(r4)
    andi. r4, r4, 1
    stw r4, {D_HIDQ}(r10)
    ; riquadro del pezzo: f8..f9 x, f6..f7 y
    lfs f3, 0(r31)
    lfs f4, 0x14(r31)
    fsubs f7, f3, f4
    fsel f8, f7, f4, f3
    fsel f9, f7, f3, f4
    lfs f3, 0x28(r31)
    lfs f4, 0x3C(r31)
    fsubs f7, f3, f4
    fsel f10, f7, f4, f3
    fsel f11, f7, f3, f4
    fsubs f7, f8, f10
    fsel f8, f7, f10, f8
    fsubs f7, f9, f11
    fsel f9, f7, f9, f11
    lfs f3, 4(r31)
    lfs f4, 0x18(r31)
    fsubs f7, f3, f4
    fsel f6, f7, f4, f3
    fsel f11, f7, f3, f4
    lfs f3, 0x2C(r31)
    lfs f4, 0x40(r31)
    fsubs f7, f3, f4
    fsel f10, f7, f4, f3
    fsel f3, f7, f3, f4
    fsubs f7, f6, f10
    fsel f6, f7, f10, f6
    fsubs f7, f11, f3
    fsel f7, f7, f11, f3
    ; dentro la minimappa stretta (disegnata in questo fotogramma o in quello prima, fotogrammi del gioco) = al suo posto
    lwz r4, {D_FR}(r10)
    lwz r5, {D_RVI}(r10)
    addi r5, r5, 1
    cmpw r4, r5
    bgt q_non_mappa
    ; centro del pezzo entro 30 pixel dal rettangolo: lo spillo rosso in cima alla minimappa gira attorno al bordo e
    ; ne esce un po' (con "tutto dentro" a volte veniva stretto e a volte no = salti di 11 pixel)
    fadds f1, f8, f9
    lfs f10, {C['c_mezzo']}(r11)
    fmuls f1, f1, f10
    fadds f3, f6, f7
    fmuls f3, f3, f10
    lfs f13, {C['c_bordo_mappa']}(r11)
    lfs f10, {D_RETT}(r10)
    fsubs f10, f10, f13
    fcmpu f1, f10
    blt q_non_mappa
    lfs f10, {D_RETT + 8}(r10)
    fadds f10, f10, f13
    fcmpu f1, f10
    bgt q_non_mappa
    lfs f10, {D_RETT + 4}(r10)
    fsubs f10, f10, f13
    fcmpu f3, f10
    blt q_non_mappa
    lfs f10, {D_RETT + 12}(r10)
    fadds f10, f10, f13
    fcmpu f3, f10
    ble q_fine
q_non_mappa:
    ; pezzi larghi quasi tutto lo schermo (dissolvenze): mai
    fsubs f10, f9, f8
    lfs f11, {C['c_630']}(r11)
    fcmpu f10, f11
    bge q_largo
    ; segnalino del mondo?
    li r0, 0
    stw r0, {D_CONTEX}(r10)
    lwz r3, 0x60(r31)
    cmpwi r3, 0
    beq q_mondo_ok
    li r0, 1
    stw r0, {D_CONTEX}(r10)
    li r0, 0
    lwz r3, 0x38(r3)
{_mondo("r3", "r4", "q")}    lis r4, 0x695F
    ori r4, r4, 0x6967
    cmpw r3, r4
    bne q_mondo_ok
    ; i_igo nella metà destra = minimappa (bordo, spillo rosso che le gira attorno a ~150 pixel dal centro): il gioco li
    ; calcola dal rettangolo già stretto -> mai; a sinistra (anello della vita) = HUD sicuro
    fadds f1, f8, f9
    lfs f10, {C['c_mezzo']}(r11)
    fmuls f1, f1, f10
    lfs f10, {C['c_320']}(r11)
    fcmpu f1, f10
    bgt q_fine
    li r0, 2
q_mondo_ok:
    stw r0, {D_MONDO}(r10)
    bl elemento
    stw r4, {D_QOK}(r10)
    stfs f5, {D_QA}(r10)
    stfs f2, {D_K}(r10)
    b q_altri_vertici
q_largo:
    li r0, 0
    stw r0, {D_HIDQ}(r10)
    b q_fine
q_altri_vertici:
    lwz r0, {D_QOK}(r10)
    cmpwi r0, 0
    beq q_fine
    lfs f5, {D_QA}(r10)
    lfs f2, {D_K}(r10)
    fsubs f3, f0, f5
    fmadds f0, f3, f2, f5
q_fine:
    lwz r0, {D_HIDQ}(r10)
    lis r3, {_hl(FOTO)[0]:#x}
    lbz r3, {_hl(FOTO)[1]}(r3)
    ; FOTO = 2 (mappa 3D): resta solo l'icona di Spidey (texture "i_igo_..."): la disegna il gioco nello stesso
    ; fotogramma della città, quindi è perfettamente ferma sul punto (il segnalino dell'app, una finestra sopra, tremava)
    cmpwi r3, 2
    bne q_foto_or
    lwz r4, 0x60(r31)
    cmpwi r4, 0
    beq q_foto_or
    lwz r4, 0x38(r4)
    addis r4, r4, -0x695F
    cmpwi r4, 0x6967
    bne q_foto_or
    li r3, 0
q_foto_or:
{hud_wide._or(0, 0, 3)}    cmpwi r0, 0
    beq q_hid_no
    lfs f0, {C['c_via']}(r11)
q_hid_no:
{_registro_quad(v)}{_base12()}{_rimetti(range(5, 12), D_SALVA_Q)}    lwz r0, {D_RIT}(r12)
    mtlr r0
    blr
"""


def _ingresso_testo(v):
    """Scritta: f0 = x di inizio, f3 = scala x, f12 = y. Larghezza come la misura il gioco (vedi hud_wide.blocco_testo)."""
    return f"""ingresso_testo:
{_base12()}    mflr r0
    stw r0, {D_RIT + 4}(r12)
{_salva(range(4, 12), D_SALVA_T, (4, 8, 9, 13), D_SALVA_TF)}{_punto(1)}{_dati()}    li r3, 0
    stw r3, {D_ISMM}(r10)
{_fotogramma(v, "t")}    lwz r3, {D_SEQ}(r10)
    addi r3, r3, 1
    stw r3, {D_SEQ}(r10)
{_costanti("t")}
{_k(v, "t_fine")}{_schermo("t_fine")}{_partita(v, "t")}    cmpwi r3, 0
    beq t_fine
    ; scritte nel mondo 3D (insegne: x = y = 0, le piazza una matrice): mai
    lwz r4, 0x14(r31)
    lwz r5, 0x18(r31)
{hud_wide._or(4, 4, 5)}    cmpwi r4, 0
    beq t_fine
    ; larghezza (prima riga): lettere (font +4 tabella da 0x1C, larghezza intera +0x18, prima lettera font +0x14) e
    ; spazi (font +0xC), per la scala x; con codici di controllo (< 0x20) larghezza 0
{_punto(2)}    lwz r3, 0xC(r31)
    lwz r5, 0x10(r31)
    lwz r6, 4(r5)
    lwz r7, 0x14(r5)
    li r4, 0
t_lettera:
    lbz r9, 0(r3)
    addi r3, r3, 1
    cmpwi r9, 0
    beq t_misurata
    cmpwi r9, 0xA
    beq t_misurata
    cmpwi r9, 0x20
    beq t_spazio
    blt t_non_misurabile
    subf r9, r7, r9
{hud_wide._mulli(9, 9, 0x1C)}    add r9, r9, r6
    lwz r9, 0x18(r9)
    add r4, r4, r9
    b t_lettera
t_spazio:
    lwz r9, 0xC(r5)
    add r4, r4, r9
    b t_lettera
t_non_misurabile:
    li r4, 0
t_misurata:
    lis r9, 0x4330
    stw r9, {D_TMP}(r10)
    stw r4, {D_TMP + 4}(r10)
    lfd f1, {D_TMP}(r10)
    li r4, 0
    stw r4, {D_TMP + 4}(r10)
    lfd f5, {D_TMP}(r10)
    fsub f1, f1, f5
    frsp f1, f1
    fmuls f1, f1, f3
    fmr f8, f0
    fadds f9, f0, f1
    fmr f6, f12
    lfs f7, {C['c_alt']}(r11)
    fadds f7, f12, f7
{_punto(3)}    li r0, 0
    stw r0, {D_MONDO}(r10)
    stw r0, {D_CONTEX}(r10)
    bl elemento
{_punto(4)}
    ; HUD nascosto (vedi D_HIDQ): la scritta fuori dallo schermo
    lis r3, {HUD_STATO >> 16:#x}
    lbz r3, {HUD_STATO & 0xFFFF:#x}(r3)
    andi. r3, r3, 1
    beq t_hid_no
    lfs f0, {C['c_via']}(r11)
    b t_fine
t_hid_no:
    cmpwi r4, 0
    beq t_fine
    fsubs f1, f0, f5
    fmadds f0, f1, f2, f5
    fmuls f3, f3, f2
t_fine:
    lis r3, {_hl(FOTO)[0]:#x}
    lbz r3, {_hl(FOTO)[1]}(r3)
    cmpwi r3, 0
    beq t_foto_no
    lfs f0, {C['c_via']}(r11)
t_foto_no:
{_punto(5)}{_registro_testo(v)}{_base12()}{_rimetti(range(4, 12), D_SALVA_T, (4, 8, 9, 13), D_SALVA_TF)}    lwz r0, {D_RIT + 4}(r12)
    mtlr r0
    blr
"""


def _ingresso_mappa(v):
    """Rettangolo della minimappa (f1 sinistra, f2 alto, f3 destra, f4 basso, pixel 640x480): verso il bordo destro e
    prospettiva 4:3 (vedi hud_wide.blocco_mappa). Solo in partita con l'HUD. Usa r11, r12, f5-f8 (salvo r3-r5, r10)."""
    ah, al = _hl(v["aspetto"])
    vh, vl = _hl(v["vi"])
    return f"""ingresso_mappa:
{_base12()}    mflr r11
    stw r11, {D_RIT + 8}(r12)
    stw r3, {D_SALVA_M}(r12)
    stw r4, {D_SALVA_M + 4}(r12)
    stw r5, {D_SALVA_M + 8}(r12)
    stw r10, {D_SALVA_M + 0xC}(r12)
{_dati()}    li r3, 0
    stw r3, {D_ISMM}(r10)
{_fotogramma(v, "m")}    lwz r3, {D_SEQ}(r10)
    addi r3, r3, 1
    stw r3, {D_SEQ}(r10)
{_costanti("m")}
    lis r3, {ah:#x}
    lfs f6, {al}(r3)
    lfs f5, {C['c_134']}(r11)
    fcmpu f6, f5
    blt m_fine
    lfs f5, {C['c_43']}(r11)
    fdivs f8, f5, f6
{_partita(v, "m", pausa=False)}    cmpwi r3, 0
    beq m_fine
    lfs f5, {C['c_640']}(r11)
    fsubs f6, f1, f5
    fmadds f1, f6, f8, f5
    fsubs f6, f3, f5
    fmadds f3, f6, f8, f5
    ; HUD nascosto (vedi D_HIDQ): minimappa fuori dallo schermo (bordo e spillo li calcola il gioco da qui)
    lis r3, {HUD_STATO >> 16:#x}
    lbz r3, {HUD_STATO & 0xFFFF:#x}(r3)
    andi. r3, r3, 1
    beq m_hid_no
    fsubs f6, f3, f1
    lfs f1, {C['c_via']}(r11)
    fadds f3, f1, f6
m_hid_no:
    stfs f1, {D_RETT}(r10)
    stfs f2, {D_RETT + 4}(r10)
    stfs f3, {D_RETT + 8}(r10)
    stfs f4, {D_RETT + 12}(r10)
    lwz r3, {D_FR}(r10)
    stw r3, {D_RVI}(r10)
    lfs f7, {C['c_43']}(r11)
    lwz r3, -0x6de8(r13)
    stfs f7, 0x2D8(r3)
m_fine:
{_base12()}    lwz r3, {D_SALVA_M}(r12)
    lwz r4, {D_SALVA_M + 4}(r12)
    lwz r5, {D_SALVA_M + 8}(r12)
    lwz r10, {D_SALVA_M + 0xC}(r12)
    lwz r11, {D_RIT + 8}(r12)
    mtlr r11
    blr
"""


def _registro_quad(v):
    """(prove) bit 1 di FLAG: il pezzo (al vertice 0) nel registro. Usa r0, r3, r4, r10."""
    vh, vl = _hl(v["vi"])
    campi = [0, 4, 0x14, 0x18, 0x28, 0x2C, 0x3C, 0x40, 0x50]
    copia = "".join(f"    lwz r0, {o:#x}(r31)\n    stw r0, {4 * i:#x}(r3)\n" for i, o in enumerate(campi))
    fh, fl = _hl(FLAG)
    return f"""    lis r4, {fh:#x}
    lbz r0, {fl}(r4)
    andi. r0, r0, 1
    beq rq_fine
    cmpwi r9, 0
    bne rq_fine
{_dati()}    lwz r3, {D_IND_Q}(r10)
    addi r3, r3, 1
    stw r3, {D_IND_Q}(r10)
    andi. r3, r3, 0xFF
""" + "    add r3, r3, r3\n" * 6 + f"""    lis r4, {REG_Q >> 16:#x}
    ori r4, r4, {REG_Q & 0xFFFF:#x}
    add r3, r3, r4
{copia}    lwz r0, {D_PT}(r10)
    stb r0, 0x24(r3)
    lis r4, {_hl(v["ui"])[0]:#x}
    lbz r0, {_hl(v["ui"])[1]}(r4)
    stb r0, 0x25(r3)
    lis r4, {_hl(v["pausa"])[0]:#x}
    lbz r0, {_hl(v["pausa"])[1]}(r4)
    stb r0, 0x26(r3)
    lwz r4, 0x60(r31)
    li r0, 0
    stw r0, 0x28(r3)
    stw r0, 0x2C(r3)
    stw r0, 0x30(r3)
    cmpwi r4, 0
    beq rq_senza
    lwz r0, 0x38(r4)
    stw r0, 0x28(r3)
    lwz r0, 0x3C(r4)
    stw r0, 0x2C(r3)
    lwz r0, 0x40(r4)
    stw r0, 0x30(r3)
rq_senza:
    lwz r4, {D_ORD}(r10)
    addi r4, r4, 1
    stw r4, {D_ORD}(r10)
    stw r4, 0x34(r3)
    lis r4, {vh:#x}
    lwz r0, {vl}(r4)
    stw r0, 0x38(r3)
    stfs f0, 0x3C(r3)
rq_fine:
"""


def _registro_testo(v):
    """(prove) bit 2 di FLAG: la scritta nel registro (voce da r31-0x20, testo, x e scala DOPO il codice)."""
    vh, vl = _hl(v["vi"])
    copia = "".join(f"    lwz r0, {o - 0x20:#x}(r31)\n    stw r0, {o:#x}(r3)\n" for o in range(0, 0x60, 4))
    fh, fl = _hl(FLAG)
    return f"""    lis r4, {fh:#x}
    lbz r0, {fl}(r4)
    andi. r0, r0, 2
    beq rt_fine
{_dati()}    lwz r3, {D_IND_T}(r10)
    addi r3, r3, 1
    stw r3, {D_IND_T}(r10)
    andi. r3, r3, 0x7F
""" + "    add r3, r3, r3\n" * 7 + f"""    lis r4, {REG_T >> 16:#x}
    ori r4, r4, {REG_T & 0xFFFF:#x}
    add r3, r3, r4
{copia}    li r0, 0
    stw r0, 0x60(r3)
    stw r0, 0x64(r3)
    stw r0, 0x68(r3)
    stw r0, 0x6C(r3)
    lwz r5, 0xC(r31)
    lis r6, 0x8000
    cmplw r5, r6
    blt rt_senza
    lis r6, 0x8180
    cmplw r5, r6
    bge rt_senza
    lwz r0, 0(r5)
    stw r0, 0x60(r3)
    lwz r0, 4(r5)
    stw r0, 0x64(r3)
    lwz r0, 8(r5)
    stw r0, 0x68(r3)
    lwz r0, 12(r5)
    stw r0, 0x6C(r3)
rt_senza:
    stfs f0, 0x70(r3)
    stfs f3, 0x74(r3)
    lwz r4, {D_ORD}(r10)
    addi r4, r4, 1
    stw r4, {D_ORD}(r10)
    stw r4, 0x78(r3)
    lis r4, {vh:#x}
    lwz r0, {vl}(r4)
    stw r0, 0x7C(r3)
rt_fine:
"""


def _testo(v):
    return ("    .word 1\n" + _ingresso_quad(v) + _ingresso_testo(v) + _ingresso_mappa(v) + _elemento(v))


def _controlla_dati():
    """Nessun campo dei dati sopra un altro (D_MONDO stava su D_RIT+4: la routine delle scritte tornava a 0 e il gioco
    si piantava)."""
    campi = [(D_IND_Q, 4), (D_IND_T, 4), (D_ORD, 4), (D_SALVA_Q, 28), (D_SALVA_M, 16), (D_SALVA_T, 32), (D_SALVA_TF, 32),
             (D_VI, 4), (D_N, 4), (D_NP, 4), (D_QA, 4), (D_QOK, 4), (D_K, 4), (D_RVI, 4), (D_RETT, 16), (D_TMP, 8),
             (D_ANELLO, 4), (D_RIT, 12), (0xD0, 8), (D_MONDO, 4), (D_SEQ, 4), (D_ULT, 4), (D_PT, 4), (D_FR, 4), (D_FVI, 4),
             (D_AVI, 4), (D_RALL, 4), (D_AP, 4), (D_CONTEX, 4), (D_ISMM, 4), (D_MMVI, 4), (D_HIDQ, 4), (D_TIPO, 4), (D_CUR, 0x20 * MAX_EL),
             (D_PREV, 0x20 * MAX_EL)]
    occ = {}
    for o, n in campi:
        for b in range(o, o + n):
            assert b not in occ, f"dati HUD sovrapposti a {b:#x}: {occ[b]:#x} e {o:#x}"
            occ[b] = o
    assert max(occ) < PROG - DATI, "dati HUD dentro il programma"


def programma(ver="GK2I52"):
    """(parole, etichette) del programma a PROG. La prima parola (a PROG) è la parola "presente"."""
    _controlla_dati()
    w, et = asm.assembla(_testo(hud_wide.VERSIONI[ver]), PROG, etichette=True)
    assert PROG + 4 * len(w) <= 0x817FE000, f"programma HUD troppo lungo ({4 * len(w)} byte): tocca la routine del teletrasporto a 817FE000"
    return w, et


ORIG = {"quad": hud_wide.LFSX_X, "testo": hud_wide.LFS_Y, "mappa": hud_wide.FSUBS_Y}
TEMP = {"quad": "r3", "testo": "r11", "mappa": "r11"}  # registro libero per il controllo "programma presente"


def aggancio(nome, ver="GK2I52"):
    """Codice del C2: istruzione originale + chiamata (mtlr/blrl) alla routine se il programma c'è."""
    t = TEMP[nome]
    a = programma(ver)[1]["ingresso_" + nome]
    ph, pl = _hl(PROG)
    return asm.assembla(f"""
    .word {ORIG[nome]:#x}
    lis r12, {ph:#x}
    lwz {t}, {pl}(r12)
    cmpwi {t}, 0
    beq salta
    lis r12, {a >> 16:#x}
    ori r12, r12, {a & 0xFFFF:#x}
    mtlr r12
    blrl
salta:
""")


def codice_ar(ver="GK2I52"):
    """Righe AR che scrivono il programma; la parola di "presente" (PROG) per ultima."""
    w = programma(ver)[0]
    return [asm.scrivi32(PROG + 4 * k, w[k]) for k in range(1, len(w))] + [asm.scrivi32(PROG, w[0])]


def codice(ver="GK2I52"):
    """Righe Gecko: i 3 agganci (nome in testa, come hud_wide.codice)."""
    v = hud_wide.VERSIONI[ver]
    return ([hud_wide.NOME] + asm.c2(v["quad"], aggancio("quad", ver)) + asm.c2(v["testo"], aggancio("testo", ver))
            + asm.c2(v["mappa"], aggancio("mappa", ver)))


if __name__ == "__main__":
    for g in ("GK2I52", "GK2E52"):
        w, et = programma(g)
        print(g, "Gecko", (len(codice(g)) - 1) * 8, "byte; programma", len(w) * 4, "byte,", len(codice_ar(g)), "righe AR;",
              {k: hex(v) for k, v in et.items() if k.startswith("ingresso")})
