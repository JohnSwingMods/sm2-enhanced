"""PRIMA PERSONA (rifatta da zero il 2026-10-16, piano "PIANO PRIMA PERSONA DA ZERO" in CLAUDE.md).

Pezzi del programma della camera (cam_ps4.logica) usati SOLO in prima persona (817F0087 = 1). Regole:
- DOVE GUARDA = la vista della camera moderna (levetta destra + rientro dietro la direzione di marcia + tuffo): mai la
  rotazione dell'osso della testa (in molte pose è inaffidabile: flip, capriole, palo).
- DOVE STA L'OCCHIO = il COLLO (osso 4: resta sempre attaccato al corpo, misurato) + un po' in su + un po' avanti lungo
  la vista, più lo spostamento di Spidey di un fotogramma: la camera legge lo scheletro del fotogramma prima di quello
  che viene disegnato (misurato con le sentinelle, fp_nuova/sent_fisica.py).
- NIENTE FACCIA E NIENTE CORPO DA DENTRO: in prima persona il piano vicino della vista principale passa da 0.1 a NEAR_FP
  (r13-0x773C: ITA 0x8056BBA4, USA 0x8056BB24; il gioco non lo riscrive): tutto quello che sta a meno di NEAR_FP
  dall'occhio non si disegna (testa, spalle), le mani sì.
- La camera non scrive MAI lo stato del gioco (scheletro, posizione, velocità).
- Opzione "Movimento della testa" (817F0088 = 1): TODO strato in più, sempre limitato e che torna al centro.

Costanti in 817F3400.. (DATI): le scrive il programma stesso quando la firma (817F3400) non è quella giusta, così nelle
prove si possono cambiare dal vivo con DME (il codice AR riscriverebbe ogni fotogramma)."""
import ppcasm as asm

NEAR_OFF = -0x773C  # piano vicino della vista principale, da r13 (uguale in tutte le versioni)
DATI = 0x3400  # da r12 = 0x817F0000
COSTANTI = {  # offset: (nome, valore)
    0x3404: ("k_pred", 0.0),       # spostamento di un fotogramma aggiunto al collo: 0 = la camera vede lo stesso scheletro
                                   # che si disegna (misurato: con 1 nei flip e nei salti l'occhio usciva dal corpo)
    0x3408: ("h_collo", 0.12),     # occhi sopra il collo (m)
    0x340C: ("near_fp", 0.3),      # piano vicino in prima persona
    0x3410: ("near_std", 0.1),     # piano vicino del gioco
    0x3414: ("avanti", 0.12),      # occhio davanti al collo lungo la vista (m)
    0x3418: ("spost_max", 2.0),    # spostamento di un fotogramma al massimo (per asse, m)
    0x341C: ("rollio_k", 0.25),    # rollio nello swing: rad per metro di spostamento laterale in un fotogramma
    0x3420: ("rollio_max", 0.07),  # rad (4°)
    0x3424: ("rollio_alfa", 0.08), # quanto in fretta ci arriva (per giro)
    0x3428: ("dist4m", 16.0),      # collo a più di 4 m (al quadrato) dalla posizione disegnata = scheletro non buono
    0x342C: ("min_petto", 0.0025), # petto-collo più corto di 5 cm (al quadrato) = direzione del corpo non buona
    0x3430: ("alfa_terra", 0.25),  # testa SPENTA, a terra: posizione del collo rispetto al corpo ammorbidita (niente
                                   # dondolio della corsa); in aria e con la testa accesa segue subito
    0x3434: ("g_veloce", 0.06),    # testa ACCESA: sguardi = rotazione della testa rispetto al corpo, filtrata veloce...
    0x3438: ("g_lento", 0.01),     # ...meno la stessa filtrata lenta (= la posa normale): torna sempre al centro
    0x343C: ("g_max", 0.07),       # sguardo al massimo prima della scala (rad, ~4°)
    0x3480: ("g_scala", 0.6),      # quanto dello sguardo della testa passa alla vista
    0x3488: ("g_passo", 0.004),    # lo sguardo cambia al massimo di tanto per giro (rad): niente scatti a ogni passo
    0x3484: ("testa_max", 0.0625), # osso della testa a più di 25 cm (al quadrato) dal collo = sbagliato (succede nei flip)
}
FIRMA = 0x3400
ROLLIO = 0x3440  # rollio attuale (float), letto all'uscita della matrice
OFFS = 0x3450  # collo - posizione disegnata ammorbidito (3 float)
G = 0x3460  # sguardi: veloce yaw/pitch (3460/64), lento (3468/6C), attuale (3470/74)
G_PRONTI = 0x3490  # byte: 0 = filtri degli sguardi da far partire dalla posa attuale (messo a 0 entrando in prima persona)
APPOGGIO = 0x34FC


def _firma():
    h = 0
    for o, (_, x) in sorted(COSTANTI.items()):
        h = (h * 31 + o * 7 + asm.f32(x)) & 0x7FFFFFFF
    return h | 0x10000  # mai 0 (memoria a zero = da scrivere)


def INIZIO():
    """All'inizio di ogni giro del programma (r12 = 0x817F0000): costanti se mancano, piano vicino del gioco (in prima
    persona PUNTO lo rimette a near_fp: vale l'ultimo scritto prima del disegno). Usa r10, r11, f0."""
    f = _firma()
    a = [f"    lwz r11, {FIRMA:#x}(r12)", f"    lis r10, {f >> 16:#x}", f"    ori r10, r10, {f & 0xFFFF:#x}",
         "    cmpw r11, r10", "    beq pp_costanti_ok"]
    for o, (_, x) in sorted(COSTANTI.items()):
        w = asm.f32(x)
        a += [f"    lis r11, {w >> 16:#x}", f"    ori r11, r11, {w & 0xFFFF:#x}", f"    stw r11, {o:#x}(r12)"]
    a += [f"    stw r10, {FIRMA:#x}(r12)", "    li r11, 0", f"    stw r11, {ROLLIO:#x}(r12)", "pp_costanti_ok:",
          f"    lfs f0, {_k('near_std'):#x}(r12)", f"    stfs f0, {NEAR_OFF}(r13)"]
    return "\n".join(a)


def _k(nome):
    return next(o for o, (n, _) in COSTANTI.items() if n == nome)


def PUNTO(v):
    """Al posto del punto guardato, in prima persona: f1-f3 = riferimento R (collo + spostamento + h_collo in su), poi
    'b punto_fatto'. Non in prima persona -> 'anticipo' (il punto normale). Scheletro non buono -> 'anticipo' anche in
    prima persona (817F008D = 0). D (817F021C) = -avanti: l'occhio sta 'avanti' metri davanti a R lungo la vista (il
    controllo dei muri, senza_muri, fa il raggio da R all'occhio). Rollio nello swing in 817F3440.
    Usa r8-r11, f4-f11 (f12 serve dopo)."""
    st = v["stato"]
    a = ["    lbz r11, 0x87(r12)", "    cmpwi r11, 0", "    beq anticipo",
         f"    lfs f4, {_k('near_fp'):#x}(r12)", f"    stfs f4, {NEAR_OFF}(r13)",
         f"    lfs f4, {_k('avanti'):#x}(r12)", "    fneg f4, f4", "    stfs f4, 0x21C(r12)",
         # scheletro buono? collo entro 4 m dalla posizione disegnata di Spidey
         "    lwz r9, 0x164(r31)", "    lwz r8, 0x30(r9)", "    lwz r9, 0x134(r9)"]
    for i in range(3):
        a += [f"    lfs f4, {0x130 + 4 * i:#x}(r9)", f"    lfs f5, {0x30 + 4 * i:#x}(r8)", "    fsubs f4, f4, f5",
              "    fmuls f7, f4, f4" if i == 0 else "    fmadds f7, f4, f4, f7"]
    a += [f"    lfs f4, {_k('dist4m'):#x}(r12)", "    li r11, 0", "    fcmpu f7, f4", "    bge pp_ossa", "    li r11, 1",
          "pp_ossa:", "    stb r11, 0x8D(r12)", "    cmpwi r11, 0", "    beq anticipo",
          # R = collo + spostamento * k_pred (ogni asse al massimo spost_max) + h_collo in su
          f"    lfs f4, {_k('k_pred'):#x}(r12)", f"    lfs f8, {_k('spost_max'):#x}(r12)", "    fneg f10, f8"]
    # testa spenta e a terra (stato 1): offset collo - posizione disegnata ammorbidito (alfa_terra), se no subito (1)
    a += [f"    lis r11, {st >> 16:#x}", f"    ori r11, r11, {st & 0xFFFF:#x}", "    lwz r11, 0(r11)",
          "    lfs f9, 0x158(r12)", "    cmpwi r11, 1", "    bne pp_alfa", "    lbz r11, 0x88(r12)", "    cmpwi r11, 0",
          "    bne pp_alfa", f"    lfs f9, {_k('alfa_terra'):#x}(r12)", "pp_alfa:",
          # appena entrati in prima persona (817F04FD = 1, messo all'entrata): niente ammorbidimento dal valore vecchio
          "    lbz r11, 0x4FD(r12)", "    cmpwi r11, 0", "    beq pp_alfa_ok", "    li r11, 0", "    stb r11, 0x4FD(r12)",
          "    lfs f9, 0x158(r12)", "pp_alfa_ok:"]
    for i in range(3):
        a += [f"    lfs f5, {0x2A0 + 4 * i:#x}(r12)", "    fsubs f6, f5, f8", "    fsel f5, f6, f8, f5",
              "    fsubs f6, f5, f10", "    fsel f5, f6, f5, f10",
              f"    lfs f6, {0x130 + 4 * i:#x}(r9)", f"    lfs f7, {0x30 + 4 * i:#x}(r8)", "    fsubs f6, f6, f7",
              f"    lfs f11, {OFFS + 4 * i:#x}(r12)", "    fsubs f6, f6, f11", "    fmadds f11, f6, f9, f11",
              f"    stfs f11, {OFFS + 4 * i:#x}(r12)", f"    fadds f{1 + i}, f7, f11", f"    fmadds f{1 + i}, f5, f4, f{1 + i}"]
    # + h_collo lungo il corpo: direzione petto (osso 3) -> collo, NON il cielo: nei flip e nelle capriole la testa gira
    # col corpo e l'occhio sopra il collo "verso il cielo" finiva fuori dalla testa (si vedeva la maschera da fuori).
    # Petto e collo troppo vicini (< 5 cm) = verso il cielo
    for i in range(3):
        a += [f"    lfs f{5 + i}, {0x130 + 4 * i:#x}(r9)", f"    lfs f4, {0xF0 + 4 * i:#x}(r9)", f"    fsubs f{5 + i}, f{5 + i}, f4"]
    a += ["    fmuls f8, f5, f5", "    fmadds f8, f6, f6, f8", "    fmadds f8, f7, f7, f8",
          f"    lfs f4, {_k('min_petto'):#x}(r12)", "    fcmpu f8, f4", "    bge pp_su_corpo",
          "    fsubs f5, f5, f5", "    fsubs f7, f7, f7", "    lfs f6, 0x158(r12)", "    fmr f8, f6",
          "pp_su_corpo:", "    frsqrte f8, f8", f"    lfs f4, {_k('h_collo'):#x}(r12)", "    fmuls f8, f8, f4",
          "    fmadds f1, f5, f8, f1", "    fmadds f2, f6, f8, f2", "    fmadds f3, f7, f8, f3"]
    # rollio nello swing (stato 3): verso -rollio_k * spostamento laterale (destra della vista = (dz, -dx)), limitato
    a += ["    fsubs f9, f9, f9",
          f"    lis r11, {st >> 16:#x}", f"    ori r11, r11, {st & 0xFFFF:#x}", "    lwz r11, 0(r11)",
          "    cmpwi r11, 3", "    bne pp_rollio",
          "    lfs f4, 0x2A0(r12)", "    lfs f5, 0x2A8(r12)", "    lfs f6, 0x208(r12)", "    lfs f7, 0x204(r12)",
          "    fmuls f9, f4, f6", "    fnmsubs f9, f5, f7, f9",
          f"    lfs f4, {_k('rollio_k'):#x}(r12)", "    fmuls f9, f9, f4", "    fneg f9, f9",
          f"    lfs f8, {_k('rollio_max'):#x}(r12)", "    fneg f10, f8",
          "    fsubs f6, f9, f8", "    fsel f9, f6, f8, f9", "    fsubs f6, f9, f10", "    fsel f9, f6, f9, f10",
          "pp_rollio:", f"    lfs f4, {ROLLIO:#x}(r12)", "    fsubs f9, f9, f4", f"    lfs f5, {_k('rollio_alfa'):#x}(r12)",
          "    fmadds f9, f9, f5, f4", f"    stfs f9, {ROLLIO:#x}(r12)",
          "    b punto_fatto"]
    return "\n".join(a)


def TESTA(v):
    """Alla fine della matrice (r10 = matrice della camera, righe destra/su/avanti/posizione), solo in prima persona con
    "Movimento della testa" acceso (817F0088 = 1) e scheletro buono: sguardi della testa SOLO PER IL DISEGNO (i comandi
    restano sulla vista pulita) -> occhio/bersaglio/su in 817F03B0/03C0/03CC e 817F008C = 1 (aggancio VISTA in cam_ps4).
    Sguardo = rotazione della testa rispetto al corpo (avanti della testa = -riga z dell'osso 5, sulle righe destra e su
    del corpo), filtrata veloce MENO filtrata lenta (la posa normale): sempre limitato a g_max e torna al centro da solo.
    Solo a terra (1) e nello swing (3): nelle acrobazie la rotazione della testa non è affidabile -> lo sguardo torna a 0.
    Testa a più di 25 cm dal collo = osso sbagliato -> 0. Usa r8, r9, r11, f0-f11."""
    st = v["stato"]
    a = ["    lbz r11, 0x87(r12)", "    cmpwi r11, 0", "    beq pt_fine", "    lbz r11, 0x88(r12)", "    cmpwi r11, 0",
         "    beq pt_fine", "    lbz r11, 0x8D(r12)", "    cmpwi r11, 0", "    beq pt_fine",
         "    fsubs f1, f1, f1", "    fsubs f2, f2, f2",
         f"    lis r11, {st >> 16:#x}", f"    ori r11, r11, {st & 0xFFFF:#x}", "    lwz r11, 0(r11)",
         "    cmpwi r11, 1", "    beq pt_si", "    cmpwi r11, 3", "    bne pt_bersaglio", "pt_si:",
         "    lwz r9, 0x164(r31)", "    lwz r8, 0x30(r9)", "    lwz r9, 0x134(r9)"]
    for i in range(3):
        a += [f"    lfs f4, {0x170 + 4 * i:#x}(r9)", f"    lfs f5, {0x130 + 4 * i:#x}(r9)", "    fsubs f4, f4, f5",
              "    fmuls f7, f4, f4" if i == 0 else "    fmadds f7, f4, f4, f7"]
    a += [f"    lfs f4, {_k('testa_max'):#x}(r12)", "    fcmpu f7, f4", "    bgt pt_bersaglio"]
    # avanti della testa = -(riga z), poi sulle righe destra (0x00) e su (0x10) del corpo
    for j, (dest, riga) in enumerate((("f1", 0x00), ("f2", 0x10))):
        a += [f"    lfs f4, 0x160(r9)", f"    lfs f5, {riga:#x}(r8)", f"    fmuls {dest}, f4, f5",
              f"    lfs f4, 0x164(r9)", f"    lfs f5, {riga + 4:#x}(r8)", f"    fmadds {dest}, f4, f5, {dest}",
              f"    lfs f4, 0x168(r9)", f"    lfs f5, {riga + 8:#x}(r8)", f"    fmadds {dest}, f4, f5, {dest}",
              f"    fneg {dest}, {dest}"]
    # appena entrati (o dopo uno stato salvato con altri valori): veloce = lento = posa attuale, se no lo sguardo partiva
    # al massimo e ci restava qualche secondo
    a += ["pt_bersaglio:", f"    lbz r11, {G_PRONTI:#x}(r12)", "    cmpwi r11, 0", "    bne pt_pronti", "    li r11, 1",
          f"    stb r11, {G_PRONTI:#x}(r12)", f"    stfs f1, {G:#x}(r12)", f"    stfs f2, {G + 4:#x}(r12)",
          f"    stfs f1, {G + 8:#x}(r12)", f"    stfs f2, {G + 12:#x}(r12)", "pt_pronti:"]
    # veloce/lento per yaw (f1) e pitch (f2); sguardo = veloce - lento, limitato
    a += [f"    lfs f8, {_k('g_veloce'):#x}(r12)", f"    lfs f9, {_k('g_lento'):#x}(r12)", f"    lfs f10, {_k('g_max'):#x}(r12)",
          "    fneg f11, f10"]
    for i, f in enumerate(("f1", "f2")):
        a += [f"    lfs f4, {G + 4 * i:#x}(r12)", f"    fsubs f5, {f}, f4", "    fmadds f4, f5, f8, f4", f"    stfs f4, {G + 4 * i:#x}(r12)",
              f"    lfs f6, {G + 8 + 4 * i:#x}(r12)", f"    fsubs f5, {f}, f6", "    fmadds f6, f5, f9, f6", f"    stfs f6, {G + 8 + 4 * i:#x}(r12)",
              f"    fsubs {f}, f4, f6", f"    fsubs f5, {f}, f10", f"    fsel {f}, f5, f10, {f}", f"    fsubs f5, {f}, f11", f"    fsel {f}, f5, {f}, f11",
              f"    lfs f5, {_k('g_scala'):#x}(r12)", f"    fmuls {f}, {f}, f5",
              f"    lfs f6, {G + 0x10 + 4 * i:#x}(r12)", f"    fsubs {f}, {f}, f6", f"    lfs f5, {_k('g_passo'):#x}(r12)",
              f"    fsubs f7, {f}, f5", f"    fsel {f}, f7, f5, {f}", "    fneg f5, f5", f"    fsubs f7, {f}, f5", f"    fsel {f}, f7, {f}, f5",
              f"    fadds {f}, {f}, f6", f"    stfs {f}, {G + 0x10 + 4 * i:#x}(r12)"]
    # occhio = posizione della matrice; bersaglio = occhio + avanti + destra*yaw + su*pitch; su = su della matrice
    for i in range(3):
        a += [f"    lfs f4, {0x30 + 4 * i:#x}(r10)", f"    stfs f4, {0x3B0 + 4 * i:#x}(r12)",
              f"    lfs f5, {0x20 + 4 * i:#x}(r10)", "    fadds f4, f4, f5",
              f"    lfs f5, {0x00 + 4 * i:#x}(r10)", "    fmadds f4, f5, f1, f4",
              f"    lfs f5, {0x10 + 4 * i:#x}(r10)", "    fmadds f4, f5, f2, f4", f"    stfs f4, {0x3C0 + 4 * i:#x}(r12)",
              f"    lfs f5, {0x10 + 4 * i:#x}(r10)", f"    stfs f5, {0x3CC + 4 * i:#x}(r12)"]
    a += ["    li r11, 1", "    stb r11, 0x8C(r12)", "pt_fine:"]
    return chr(10).join(a)


# (prove) righe AR che rimettono le costanti di base: python -c "import prima; prima.stampa()"
def stampa():
    for o, (n, x) in sorted(COSTANTI.items()):
        print(f"{0x817F0000 + o:08X} {n} = {x}")
