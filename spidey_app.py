"""App unica "SM2 Enhanced" (prima "Spider-Man 2 · Definitive Edition") (pywebview: finestra con grafica HTML, motore Edge WebView2).
Per ora: schermata Skin (costume principale, alternativo, ragnatele) con anteprima 3D. Logica in app_core.py."""
import functools
import hashlib
import json
import math
import subprocess
import base64
import shutil
import os
import sys
import threading
import time
import traceback
from pathlib import Path

import webview

import app_core as core
CAM_PROGRAMMA = 0x817F0800  # = cam_ps4.PROGRAMMA (prima parola del programma della camera: != 0 = codice AR in funzione)
RITARDO_SEGNI = 0.033  # s: segnalini della mappa 3D in ritardo come l'immagine mostrata (misurato, vedi filo_segni)


def risorsa(nome):
    return Path(getattr(sys, "_MEIPASS", Path(__file__).parent)) / nome


def protetto(fn):
    """Ogni chiamata dalla pagina: gli errori finiscono nel log e tornano alla pagina come {"errore": ...}."""
    @functools.wraps(fn)
    def dentro(*a, **kw):
        t0 = time.perf_counter()
        try:
            return fn(*a, **kw)
        except Exception as e:  # noqa: BLE001
            core.log_errore(traceback.format_exc())
            return {"errore": f"{type(e).__name__}: {e}"}
        finally:
            if _TEMPI:  # (prove) SPIDEY_TEMPI=<file>: quanto ci mette ogni chiamata dalla pagina
                with open(_TEMPI, "a", encoding="utf-8") as f:
                    f.write(f"{time.time():.2f}\t{(time.perf_counter() - t0) * 1000:.0f}\t{fn.__name__}\n")
    return dentro


_TEMPI = os.environ.get("SPIDEY_TEMPI")


def _con_chiavi(nodo):
    if nodo["path"]:
        nodo["k"] = core._chiave(str(core.tex(nodo["path"], core.CORPO)))
    for f in nodo["figli"]:
        _con_chiavi(f)
    return nodo


DOWNLOAD = {}  # nome file -> {"stato": "scarico"|"finito"|"errore", "byte", "totale", "file"} (finestra ModDB)
SCARICHI = core.CONF_DIR / "scarichi_in_corso.json"  # {file: byte attesi}: se l'app si chiude a metà, al riavvio li pulisco


def _scarichi(cambia=None):
    import json as _j
    try:
        d = _j.loads(SCARICHI.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        d = {}
    if cambia:
        cambia(d)
        SCARICHI.parent.mkdir(parents=True, exist_ok=True)
        SCARICHI.write_text(_j.dumps(d), encoding="utf-8")
    return d


def _togli_scaricato_male(file):
    """File di un download non finito o rovinato: via (non deve restare in Download)."""
    try:
        Path(file).unlink(missing_ok=True)
    except OSError:
        pass
    _scarichi(lambda d: d.pop(str(file), None))


def pulisci_scarichi_interrotti():
    """All'avvio: i download lasciati a metà (app chiusa mentre scaricava) se non sono completi si cancellano."""
    for f, atteso in list(_scarichi().items()):
        p = Path(f)
        if p.is_file() and atteso and p.stat().st_size == atteso:
            _scarichi(lambda d: d.pop(f, None))  # era finito davvero
        else:
            _togli_scaricato_male(f)


def _scarica_in_download(self, sender, args):
    """Download dalla finestra ModDB: niente finestra "Salva con nome", il file va dritto in Download e
    l'avanzamento finisce in DOWNLOAD (lo legge la pagina dell'installer). Se il download si interrompe (finestra
    chiusa, rete) il pezzo scaricato si cancella subito."""
    import re
    nome = os.path.basename(str(args.ResultFilePath))
    nome = re.sub(r" \(\d+\)(?=\.[^.]+$)", "", nome)  # il browser propone "file (1).zip" se c'è già: nome vero
    atteso = next((c["byte"] for c in core.carica_moddb()["file"] if c["file"] == nome), 0)
    import time
    gia = DOWNLOAD.get(nome) or {}
    if gia.get("stato") == "scarico" and time.time() - gia.get("quando", 0) < 30:
        # lo stesso file sta già scaricando (es. hai cliccato "download" mentre partiva da solo): il secondo lo annullo,
        # se no due download scriverebbero insieme e resterebbero due copie
        args.Cancel = True
        return
    dest = core.cartella_download() / nome
    n = 1
    while dest.exists():
        if atteso and dest.stat().st_size != atteso:  # un pezzo rimasto da un tentativo di prima: lo sostituisco
            try:
                dest.unlink()
                break
            except OSError:
                pass
        dest = core.cartella_download() / f"{Path(nome).stem} ({n}){Path(nome).suffix}"  # quello buono resta: "file (1).zip"
        n += 1
    args.ResultFilePath = str(dest)
    args.Handled = True
    op = args.DownloadOperation
    DOWNLOAD[nome] = {"stato": "scarico", "byte": 0, "totale": 0, "file": str(dest), "quando": time.time()}
    _scarichi(lambda d: d.__setitem__(str(dest), atteso))

    def avanza(s, e):
        DOWNLOAD[nome].update(byte=int(s.BytesReceived), totale=int(s.TotalBytesToReceive or 0), quando=time.time())

    def stato(s, e):
        st = str(s.State)
        DOWNLOAD[nome]["stato"] = "finito" if st == "Completed" else "errore" if st == "Interrupted" else "scarico"
        if st == "Interrupted":
            threading.Timer(1.0, _togli_scaricato_male, args=(dest,)).start()  # il browser lo rilascia un attimo dopo
        elif st == "Completed":
            _scarichi(lambda d: d.pop(str(dest), None))
    op.BytesReceivedChanged += avanza
    op.StateChanged += stato


class LavoroInstaller:
    """Libreria poi installazione in Dolphin, come un lavoro solo (per la barra di avanzamento)."""

    def __init__(self, *passi):
        self.passi, self.i, self.finito, self.errore, self.annulla = list(passi), 0, False, None, False

    def esegui(self):
        for self.i, p in enumerate(self.passi):
            p.esegui()
            if p.errore or p.annulla:
                self.errore = p.errore
                break
        self.finito = True

    def stato(self):
        p = self.passi[self.i]
        st = p.stato()
        st.update(passo=self.i, passi=len(self.passi), finito=self.finito, errore=self.errore, installer=True)
        return st


def _log_avviso(testo):
    f = os.environ.get("SPIDEY_LOG_AVVISO")
    if f:
        import time
        with open(f, "a", encoding="utf-8") as x:
            x.write(f"{time.strftime('%H:%M:%S')} {testo}" + chr(10))


def _albero_menu(n):
    """Albero delle varianti di una skin, leggero, per il personalizzatore del menu: n = nome, d = di base, p = percorso
    (None = cartella che contiene solo altre varianti), f = figli."""
    return {"n": n["nome"], "d": bool(n.get("default")), "p": n.get("path"), "f": [_albero_menu(x) for x in n.get("figli", [])]}


class Api:
    def __init__(self):
        self._finestra = None
        self._conf = core.carica_config()
        import app_cam
        for k, campo in (("cam_ultimi", "preset_chiave"), ("menu_cam", "preset")):  # preset pronto rinominato o tolto -> la migliorata
            v = self._conf.get(k).get(campo) if isinstance(self._conf.get(k), dict) else None
            if isinstance(v, str) and v.startswith("f:") and v[2:] not in app_cam.PRESET_FISSI:
                self._conf[k][campo] = "f:migliorata"
        self._voci = None
        self._ragnatele = None
        self._lock = threading.Lock()
        self._cam = None
        self._cam_vivo, self._cam_vivo_lock = None, threading.Lock()  # dove sta il codice camera dentro Dolphin (ar_vivo)
        self._peso_tex = None
        self._tex_voci = None
        self._aggiunta = None
        self._lavoro = None
        self._ins = None  # installazione in corso (skin / HUD / texture)
        self._trascina_ok = False
        self._fin_moddb = {}  # finestre ModDB aperte, una per pacchetto: si possono scaricare più cose insieme
        self._moddb_chiusa = set()
        self._giochi = None  # {ID: disco} trovati tra i giochi di Dolphin (cercati una volta)
        self._orig_provati, self._orig_in_corso, self._orig_ram = set(), False, 0.0  # costume originale dal gioco
        # foto e dati degli stati salvati: un filo che guarda la cartella StateSaves mentre gira il gioco
        self._guardia = core.GuardiaStati(lambda: core.trova_dolphin(self._conf),
                                          lambda: core.trova_exe_dolphin(self._conf, core.trova_dolphin(self._conf)))
        threading.Thread(target=self._guardia.esegui, daemon=True).start()
        threading.Thread(target=self._riaccendi_camera, daemon=True).start()  # codice camera rimasto spento da Spider-Cam
        self._menu, self._menu_aperto, self._menu_gioco = None, False, None
        self._menu_lock = threading.Lock()  # aprire / chiudere uno alla volta (premendo LB + RB di fila si accavallavano)
        self._pad_app, self._pad_app_lock = None, threading.Lock()  # pad letti per la pagina (pad_leggi)
        self._menu_fin_lock = threading.Lock()  # una finestra del menu sola (preparazione e primo LB + RB insieme)
        self._riavvio_lock = threading.Lock()  # un riavvio del gioco alla volta (due A di fila = due Dolphin)
        self._hud_snap = None  # stato dell'HUD (817F0014) prima di premere LB: il menu lo rimette com'era
        self._avvio_lock = threading.Lock()  # installer / export: un avvio alla volta (doppio clic = due lavori)
        self._dme_lock = core.DME_LOCK  # la memoria di Dolphin si legge da un filo alla volta (vedi core.DME_LOCK)
        # (questi due dopo gli attributi del menu e il lucchetto della memoria: li usano)
        threading.Thread(target=self._sorveglia_sopra, daemon=True).start()  # finestra del gioco sempre in primo piano
        self._codici_pronti = threading.Event()  # stati salvati aggiornati ai codici di adesso (vedi _sorveglia_codici)
        self._codici_pronti.set()
        threading.Thread(target=self._sorveglia_codici, daemon=True).start()  # stati salvati coi codici Gecko vecchi
        threading.Thread(target=self._sorveglia_camere, daemon=True).start()  # camere nel gioco = quelle scelte
        self._ora_vivo, self._ora_ini, self._ora_timer = None, None, None  # menu in gioco > Cielo
        self._ora_lock = threading.Lock()  # (ora scelta dal menu e ora tenuta ferma da _sorveglia_ora: una scrittura alla volta)
        self._mappa_punto, self._viaggio_prima, self._viaggio_esito = None, None, None  # menu in gioco > Viaggio
        self._viaggio_lock = threading.Lock()
        self._mappa_lavoro = None  # giro fotografico della mappa della città in corso: {fase, n, tot}
        threading.Thread(target=self._sorveglia_ora, daemon=True).start()  # tempo fermato dal menu, col gioco aperto
        if os.environ.get("SPIDEY_REGIA_FILE"):  # (solo riprese/prove: comandi da un file, vedi _regia_file)
            threading.Thread(target=self._regia_file, daemon=True).start()
        threading.Thread(target=self._sorveglia_ragnatele, daemon=True).start()  # ragnatele che seguono il costume
        threading.Thread(target=self._sorveglia_pad, daemon=True).start()  # LB + RB in gioco = menu
        threading.Thread(target=self._sorveglia_linee, daemon=True).start()  # Opzioni > Controller: linee fino ai tasti
        threading.Thread(target=self._aggiorna_disegno, daemon=True).start()  # disegno del controller della versione di prima
        threading.Thread(target=self._correggi_texture, daemon=True).start()  # nostre correzioni a texture del gioco
        threading.Thread(target=pulisci_scarichi_interrotti, daemon=True).start()  # download lasciati a metà
        self._ultima = None  # ultima versione di Dolphin sul sito (per avvisare degli aggiornamenti)
        threading.Thread(target=lambda: setattr(self, "_ultima", core.ultima_dolphin()), daemon=True).start()
        self._ultima_app = None  # versione nuova dell'app (manifesto online, vedi core.ultima_app)
        self._agg = None  # download della versione nuova in corso (core.AggiornaApp)
        threading.Thread(target=lambda: setattr(self, "_ultima_app", self._leggi_ultima_app()), daemon=True).start()

    # ------------------------------------------------------------ dati
    def _catalogo(self, forza=False):
        with self._lock:
            if self._voci is None or forza:
                pack = core.trova_pack(self._conf)
                self._voci = [dict(v, albero=_con_chiavi(v["albero"]), k=core._chiave(str(core.tex(v["default"], core.CORPO))))
                              for v in core.catalogo_skin(pack)] if pack else []
                self._ragnatele = core.catalogo_ragnatele(pack) if pack else []
            return self._voci, self._ragnatele

    @protetto
    def stato(self):
        dolphin = core.trova_dolphin(self._conf)
        pack = core.trova_pack(self._conf)
        voci, rag = self._catalogo()
        if dolphin and self._dal_disco_manca():  # modello 3D e costume originale dal disco: subito, qualunque sia la pagina
            self._tutti_giochi(dolphin)
        return {
            "versione": core.VERSIONE_APP, "aggiornata": _APPENA_AGGIORNATA, "patreon": core.PATREON_URL,
            "lingua": self._conf.get("lingua") or core.lingua_sistema(),
            "dolphin": str(dolphin) if dolphin else None,
            "pack": core.corto(pack) if pack else None,
            "da_zero": core.DA_ZERO, "base_prova": str(core.BASE_PROVA),
            "cartelle": [core.NOMI_VERSIONE[g] for g in core.versioni_texture(dolphin)] if dolphin else [],
            "dolphin_aperto": bool(core.exe_dolphin_aperti()),
            "skin": voci, "ragnatele": rag, "alt_spento": self._alt_spento(dolphin), "preferite": self._preferite(),
        }

    PREFERITE_BASE = ["Collezione/RAIMI_2004", "Collezione/RAIMI_BLACK_SUIT"]  # i costumi del film: in testa da subito

    def _preferite(self):
        """Costumi preferiti. Di base (e una volta, per chi aveva già dei preferiti) Raimi 2004 e Raimi Black Suit in testa."""
        if not self._conf.get("pref_base_v1"):
            pref = self._conf.get("skin_preferite", [])
            self._conf["skin_preferite"] = [x for x in self.PREFERITE_BASE if x not in pref] + pref
            self._conf["pref_base_v1"] = True
            core.scrivi_config(self._conf)
        return self._conf.get("skin_preferite", [])

    def _alt_spento(self, dolphin):
        """Versioni con i codici ma col "Cambio costume" spento: lì il costume alternativo in gioco non si può usare."""
        if not dolphin:
            return []
        nome = next((c["nome_ini"] for c in core.carica_codici_db() if c["id"] == "skin"), None)
        dischi = self._tutti_giochi(dolphin)  # solo le versioni che si possono giocare: un INI rimasto di una versione
        # senza disco (es. USA su un PC che ha solo il disco ITA) non deve far comparire l'avviso
        out = []
        for g, n in core.NOMI_VERSIONE.items():
            if dischi and g not in dischi:
                continue
            ini = Path(dolphin) / "GameSettings" / f"{g}.ini"
            if ini.is_file():
                st = core.leggi_codici_ini(ini)
                if st["presenti"] and nome not in st["attivi"]:
                    out.append(n)
        return out

    @protetto
    def installate(self):
        dolphin = core.trova_dolphin(self._conf)
        if not dolphin:
            return None
        voci, rag = self._catalogo()
        return self._installate(dolphin, voci, rag)

    def _installate(self, dolphin, voci, rag):
        """core.installate + ragnatele del costume alternativo. Mentre in gioco c'è il costume alternativo in Dolphin ci
        sono le sue ragnatele (rag_messe): quelle principali sono quelle ricordate (rag_pri)."""
        ins = core.installate(dolphin, voci, rag or [])
        c = self._conf
        if c.get("rag_messe") and c.get("rag_pri"):
            ins["ragnatele"] = c["rag_pri"]
        elif ins.get("ragnatele") not in (None, "?") and c.get("rag_pri") != ins["ragnatele"]:
            c["rag_pri"] = ins["ragnatele"]
            core.scrivi_config(c)
        ins["ragnatele_alt"] = c.get("rag_alt") or "uguali"
        return ins

    def _sorveglia_ragnatele(self):
        """Ragnatele che seguono il costume: col costume alternativo in gioco metto le sue ragnatele (rag_alt), col
        principale quelle principali (rag_pri). Gioco chiuso: rimetto le principali. rag_messe = ragnatele alternative
        che ci sono adesso nei file di Dolphin (None = ci sono le principali)."""
        import time
        while True:
            time.sleep(0.4)
            try:
                c = self._conf
                alt, pri, messe = c.get("rag_alt"), c.get("rag_pri"), c.get("rag_messe")
                attivo = bool(alt and pri and alt != pri)
                if not attivo and not messe:
                    time.sleep(1.5)
                    continue
                vuoi = pri
                if attivo and core.gioco_in_corso():
                    with self._dme_lock:
                        dme = core.aggancia_dme()
                        st = core.costume_alternativo(dme) if dme else None
                    if st is None:
                        continue  # texture non ancora in memoria (caricamento): non tocco niente
                    vuoi = alt if st else pri
                if vuoi == (messe or pri):
                    continue
                self._rag_metti(vuoi)
                c["rag_messe"] = None if vuoi == pri else vuoi
                core.scrivi_config(c)
                self._log_menu(f"ragnatele -> {vuoi} ({'alternative' if c['rag_messe'] else 'principali'})")
            except Exception as e:  # noqa: BLE001 - il filo non deve fermarsi
                core.log_errore(f"ragnatele alternative: {e!r}")
                time.sleep(3)

    def _rag_metti(self, rid):
        """Ragnatele `rid` in Dolphin riscrivendo i file (vedi core.scambia_ragnatele); i file che non ha restano quelli
        delle principali."""
        dolphin = core.trova_dolphin(self._conf)
        _, rag = self._catalogo()
        per = {r["id"]: r["path"] for r in rag or []}
        if not dolphin or not per.get(rid):
            return 0
        return core.scambia_ragnatele(dolphin, per[rid], per.get(self._conf.get("rag_pri")))

    def log_js(self, testo):
        core.log_errore("JS: " + str(testo))
        print("JS:", testo, flush=True)

    @protetto
    def dolphin_aperto(self):
        return bool(core.exe_dolphin_aperti())

    @protetto
    def texture(self, cartella, larg=1024, alt=512):
        return core.immagine64(str(core.tex(cartella, core.CORPO)), larg, alt)

    @protetto
    def miniature(self, chiavi):
        out = {}
        for k in chiavi:
            f = core.CACHE / "mini" / f"{k}.png"
            if f.exists():
                out[k] = "data:image/png;base64," + __import__("base64").b64encode(f.read_bytes()).decode()
        return out

    @protetto
    def salva_miniatura(self, k, dataurl):
        import base64
        f = core.CACHE / "mini" / f"{k}.png"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(base64.b64decode(dataurl.split(",", 1)[1]))
        return True

    @protetto
    def ragnatela_filo(self, rid):
        """Texture del filo della ragnatela (PNG con trasparenza) per vederla in 3D; None = originali del gioco."""
        _, rag = self._catalogo()
        r = next((x for x in rag if x["id"] == rid), None)
        return core.filo_ragnatela(r["path"]) if r and r["path"] else None

    @protetto
    def ragnatela_img(self, rid):
        _, rag = self._catalogo()
        r = next((x for x in rag if x["id"] == rid), None)
        return core.anteprima_ragnatele(r["path"]) if r and r["path"] else None

    # ------------------------------------------------------------ codici
    @protetto
    def codici_stato(self):
        dolphin = core.trova_dolphin(self._conf)
        db = core.carica_codici_db()
        giochi = self._tutti_giochi(dolphin) if dolphin else {}
        versioni = []
        for gid, nome in core.NOMI_VERSIONE.items():
            ini = Path(dolphin) / "GameSettings" / f"{gid}.ini" if dolphin else None
            if ini and ini.exists():
                core.aggiorna_codici_vecchi(ini, gid)  # codici nostri rifatti: il vecchio diventa il nuovo
                core.allinea_camera(ini, gid, self._cam_modi(), self._conf.get("cam_opzioni"))  # camera classica + Gecko = una voce sola
            stato = core.leggi_codici_ini(ini) if ini and ini.exists() else None
            versioni.append({"id": gid, "nome": nome, "pal": gid in core.PAL, "installata": bool(stato and (stato["presenti"] or stato["patch_attive"])),
                             "disco": gid in giochi,
                             "attivi": sorted(stato["attivi"]) if stato else [],
                             "patch60": any("60Hz" in x for x in stato["patch_attive"]) if stato else False})
        codici = [{k: v for k, v in c.items() if k != "versioni"} | {"versioni": sorted(c["versioni"])} for c in db + self._miei()
                  if not c.get("parte_di")]
        for c in codici:  # pezzi nascosti (Gecko della camera e dell'HUD 16:9, programma della camera): scritti sulla scheda
            c["pezzi"] = [{"titolo": x["titolo"], "tipo": "Gecko" if x.get("tipo") == "gecko" else "AR"}
                          for x in db if x.get("parte_di") == c["id"]]
        return {"versioni": versioni, "codici": codici, "dolphin_aperto": bool(core.exe_dolphin_aperti()),
                "tutte": self._conf.get("codici_tutte")}

    @protetto
    def menu_ora_stato(self):
        """Menu in gioco > Cielo: ora del gioco adesso e se il tempo è fermo (scelto ora dall'app o dal codice nell'INI)."""
        gid = core.gioco_in_corso()
        if not gid or gid == "?":
            return {"gioco": False, "sec": None, "fermo": False}
        v = self._ora_vivo if self._ora_vivo and self._ora_vivo["gid"] == gid else None
        letto = core.ora_leggi(gid)
        if v:
            fermo = v["fermo"]
        else:
            dolphin = core.trova_dolphin(self._conf)
            fermo = bool(dolphin) and core.ora_valore(Path(dolphin) / "GameSettings" / f"{gid}.ini") is not None
            if letto and letto[1]:  # parola SPENTO già messa (es. app riaperta col gioco aperto): il codice non scrive
                fermo = False
        sec = v["sec"] if v and v["fermo"] else letto[0] if letto else None
        return {"gioco": bool(letto), "sec": sec, "fermo": fermo}

    @protetto
    def menu_ora_vista(self):
        """Menu in gioco > Cielo: la finestra del gioco adesso (JPEG base64 piccolo) per il riquadro "nel gioco"."""
        g = core.finestra_gioco()
        try:
            return core.foto_finestra(g, 420) if g else None
        except Exception:  # noqa: BLE001
            return None

    @protetto
    def menu_ora_imposta(self, sec, fermo):
        """Menu in gioco > Cielo: ora scelta (subito nel cielo) e tempo fermo o no. Fermo = codice negli INI di tutte le
        versioni (vale dalla prossima partita, anche senza l'app); che scorre = codice tolto. Intanto, col gioco aperto,
        l'ora la tiene ferma l'app (_sorveglia_ora): il codice già caricato in Dolphin non si può cambiare."""
        sec = None if sec is None else int(sec) % 86400
        gid = core.gioco_in_corso()
        if gid and gid != "?":
            with self._ora_lock:
                self._ora_vivo = {"gid": gid, "sec": sec, "fermo": bool(fermo), "scrivi": True}
                core.ora_scrivi(gid, sec)
        self._ora_ini = (sec if fermo else None)
        if self._ora_timer:  # negli INI una volta sola, quando smetti di scorrere (ogni scrittura fa un backup)
            self._ora_timer.cancel()
        self._ora_timer = threading.Timer(1.5, self._ora_negli_ini)
        self._ora_timer.daemon = True
        self._ora_timer.start()
        return {"ok": True}

    # ---------------------------------------------------------------- menu in gioco > Mondo > Viaggio (teletrasporto)
    def _gid_partita(self):
        gid = core.gioco_in_corso()
        if not gid or gid == "?":
            return None
        try:
            return gid if core.Viaggio(gid).stato() > 0 else None  # -1 = titolo, caricamento, morte
        except Exception:  # noqa: BLE001
            return None

    @protetto
    def menu_viaggio_stato(self):
        """Punto della mappa ricordato, posti salvati, se si può tornare indietro, esito dell'ultimo viaggio (una volta)."""
        gid = self._gid_partita()
        esito, self._viaggio_esito = self._viaggio_esito, None
        try:
            aperta = bool(gid) and core.Viaggio(gid).centro_mappa() is not None
        except Exception:  # noqa: BLE001
            aperta = False
        m = self._mappa_punto if aperta and self._mappa_punto and self._mappa_punto["gid"] == gid else None
        spidey = None
        ora = core.ora_leggi(gid) if gid else None
        if gid:
            try:
                p = core.Viaggio(gid).posizione()
                spidey = [round(p[0], 1), round(p[2], 1)]
            except Exception:  # noqa: BLE001
                spidey = None
        return {"gioco": bool(gid), "esito": esito, "mappa_aperta": aperta,
                "mappa": {"x": round(m["x"]), "z": round(m["z"]), "fa": round(time.time() - m["quando"])} if m else None,
                "posti": [{"foto": p.get("foto"), "quando": p.get("quando"), "x": p.get("x"), "z": p.get("z"), "nome": p.get("nome")}
                          for p in self._conf.get("posti", [])],
                "indietro": bool(self._viaggio_prima and self._viaggio_prima["gid"] == gid),
                "spidey": spidey, "citta": self._mappa_geo(), "creando": self._mappa_lavoro,
                "ora": ora[0] if ora else None}  # ora del gioco: di notte l'esploratore mostra la mappa fatta di notte

    # ------------------------------------------------ mappa di tutta la città (mappa_citta.py)
    def _mappa_cartella(self):
        return core.CONF_DIR / "mappa_citta"  # quadrati t_x_y.jpg, panoramica.jpg, piccola.jpg, mappa.json

    def _mappa_geo(self):
        """Geometria della mappa della città se c'è (pixel della mappa intera = J . (x, z) + O), se no None."""
        f = self._mappa_cartella() / "mappa.json"
        try:
            if f.is_file():
                import mappa_citta
                geo = json.loads(f.read_text(encoding="utf-8"))
                if geo.get("versione") == mappa_citta.VERSIONE:
                    return geo
        except Exception:  # noqa: BLE001
            pass
        return None

    @protetto
    def menu_mappa_immagine(self, grande=False, strato="t"):
        """La mappa della città in base64 (grande = la panoramica, se no l'anteprima; strato t giorno, a alba, s tramonto,
        n notte)."""
        import base64
        c = self._mappa_cartella()
        strato = strato if strato in ("a", "s", "n") else "t"
        f = c / (("panoramica" if grande else "piccola") + ("" if strato == "t" else "_" + strato) + ".jpg")
        if not f.is_file():
            f = c / ("panoramica.jpg" if grande else "piccola.jpg")
        if not f.is_file():
            return None
        return base64.b64encode(f.read_bytes()).decode()

    @protetto
    def menu_mappa_tassello(self, tx, ty, strato="t"):
        """Un quadrato della mappa a piena risoluzione (esploratore zoomato), base64."""
        import base64
        strato = strato if strato in ("a", "s", "n") else "t"
        f = self._mappa_cartella() / f"{strato}_{int(tx)}_{int(ty)}.jpg"
        return base64.b64encode(f.read_bytes()).decode() if f.is_file() else None

    @protetto
    def menu_mappa_mare(self, strato="t"):
        """Il mare ripetibile di uno strato (esploratore: continua oltre il bordo della mappa): {b64, colore} (colore medio:
        da lontano, dove la mappa è la panoramica rimpicciolita e liscia, la trama piena sembrava più chiara) o None."""
        import base64
        from PIL import Image, ImageStat
        strato = strato if strato in ("a", "s", "n") else "t"
        f = self._mappa_cartella() / ("mare" + ("" if strato == "t" else "_" + strato) + ".jpg")
        if not f.is_file():
            return None
        with Image.open(f) as im:
            colore = "#%02x%02x%02x" % tuple(round(v) for v in ImageStat.Stat(im.convert("RGB")).mean)
        return {"b64": base64.b64encode(f.read_bytes()).decode(), "colore": colore}

    # ore del giro fotografico: giro intero di giorno e di notte; all'alba e al tramonto solo una foto campione (dallo
    # stesso punto di una foto di giorno: la cucitura ne ricava i colori di tutta la mappa)
    _MAPPA_ORE = (("giorno", 12 * 3600), ("alba", 6 * 3600 + 2700), ("tramonto", 18 * 3600), ("notte", 23 * 3600))
    _MAPPA_CAMPIONE = (-500.0, 100.0)  # parco, laghi, palazzi e strade: buono per i colori

    @protetto
    def menu_mappa_crea(self):
        """Giro fotografico (mappa_citta.Giro), DUE volte: a mezzogiorno e di notte (la luce della mappa del gioco è quella
        dell'ora in cui la apri: con la mappa aperta il gioco è fermo). Per ogni giro: ora del cielo scritta a mappa chiusa,
        apre la mappa (F15), foto dall'alto con le icone nascoste, chiude. Poi rimette l'ora e cuce i due strati. Il menu
        resta aperto con l'avanzamento (le foto della finestra del gioco vengono pulite anche col menu sopra)."""
        gid = self._gid_partita()
        if not gid:
            return {"errore": "gioco"}
        if self._mappa_lavoro or not self._viaggio_lock.acquire(blocking=False):
            return {"errore": "occupato"}

        def via():
            import mappa_citta
            v = core.Viaggio(gid)
            esito = "ok"
            ora0, t0 = core.ora_leggi(gid), time.time()
            tmp = core.CONF_DIR / "_mappa_tmp"
            try:
                self._mappa_lavoro = {"fase": "apro", "n": 0, "tot": 0}
                self._menu_js("mcAvanza()")
                # A del pad ancora giù: F15 porta davanti il gioco e Spidey saltava (John)
                self._aspetta_rilascio(3.0)
                aperta_prima = v.mappa_aperta()
                giri, aspetto, campioni = [], None, {}
                for fase, sec in self._MAPPA_ORE:
                    if v.mappa_aperta() and not v.chiudi_mappa(dopo_tasto=self._menu_sopra):
                        raise RuntimeError("mappa rimasta aperta")
                    fine = time.time() + 1.8  # il cielo e la luce cambiano col gioco che gira (mappa chiusa)
                    while time.time() < fine:
                        core.ora_scrivi(gid, sec)
                        time.sleep(0.1)
                    if not v.apri_mappa(dopo_tasto=self._menu_sopra):
                        esito = "apri"  # profilo senza F15 (gioco avviato da Dolphin): la mappa va aperta a mano (Select)
                        return
                    time.sleep(1.0)
                    notte = fase == "notte"
                    if fase in ("alba", "tramonto"):
                        self._mappa_lavoro = {"fase": "luce", "n": 0, "tot": 0}
                        self._menu_js("mcAvanza()")
                        f = mappa_citta.Giro(gid, tmp / fase).esegui(punti=[self._MAPPA_CAMPIONE])[0]
                        campioni["a" if fase == "alba" else "s"] = f[0][4]
                        continue

                    def avanza(n, tot, notte=notte):
                        self._mappa_lavoro = {"fase": "foto", "n": n, "tot": tot, "notte": notte}
                        self._menu_js("mcAvanza()")
                    g = mappa_citta.Giro(gid, tmp / fase, avanza)
                    fatti, r, aspetto, _, _ = g.esegui()
                    giri.append((fatti, r))
                    if fase == "giorno":  # campione di giorno dallo stesso punto di quelli di alba e tramonto
                        f = mappa_citta.Giro(gid, tmp / "campione").esegui(punti=[self._MAPPA_CAMPIONE])[0]
                        campioni["t"] = f[0][4]
                if not aperta_prima:
                    v.chiudi_mappa(dopo_tasto=self._menu_sopra)
                self._mappa_ora_rimetti(gid, ora0, t0)
                ora0 = None

                ultimo = [-1]

                def cucio(n, tot):  # al menu solo quando cambia la percentuale
                    pc = int(100 * n / max(1, tot))
                    if pc != ultimo[0]:
                        ultimo[0] = pc
                        self._mappa_lavoro = {"fase": "cucio", "n": pc, "tot": 100}
                        self._menu_js("mcAvanza()")
                cucio(0, 1)
                nuova = core.CONF_DIR / "_mappa_nuova"
                shutil.rmtree(nuova, ignore_errors=True)
                mappa_citta.cuci(giri, aspetto, nuova, cucio, campioni=campioni if len(campioni) == 3 else None)
                dest = self._mappa_cartella()
                shutil.rmtree(dest, ignore_errors=True)
                nuova.rename(dest)
                for vecchio in ("mappa_citta.jpg", "mappa_citta.json", "mappa_citta_piccola.jpg"):  # mappa v1/v2
                    try:
                        (core.CONF_DIR / vecchio).unlink()
                    except OSError:
                        pass
                self._log_menu(f"mappa della città fatta ({sum(len(f) for f, _ in giri)} foto)")
            except Exception as e:  # noqa: BLE001
                esito = "errore" if "interrotto" not in str(e) else "interrotto"
                core.log_errore(f"mappa della città: {e!r}")
            finally:
                if ora0:
                    self._mappa_ora_rimetti(gid, ora0, t0)
                shutil.rmtree(tmp, ignore_errors=True)
                self._mappa_lavoro = None
                self._viaggio_lock.release()
                self._menu_js(f"mcFine({json.dumps(esito)})")
        threading.Thread(target=via, daemon=True).start()
        return {"ok": True}

    def _mappa_ora_rimetti(self, gid, ora0, t0):
        """Dopo il giro: l'ora di prima (più il tempo passato, il gioco corre ~48 volte il tempo vero) e la parola SPENTO
        com'era. Se il tempo è fermato dal menu ci pensa _sorveglia_ora (lo riscrive lui)."""
        if not ora0:
            return
        sec, spento = ora0
        v = self._ora_vivo
        if v and v.get("gid") == gid and v.get("fermo"):
            v["scrivi"] = True
            return
        core.ora_scrivi(gid, sec + (time.time() - t0) * 48, spento=spento)

    @protetto
    def menu_viaggio_vai(self, cosa, i=None, x=None, z=None, occhio=None, dopo=None, da=None, coperto=False):
        """cosa = "mappa" (sopra il punto al centro della mappa), "posto" (posto salvato i) o "indietro" (dove eri prima
        dell'ultimo viaggio). Chiude il menu (così lo vedi arrivare) e lo porta lì. occhio = (x, y, z) da dove si guardava
        il punto (vista 3D: si arriva su quello che c'era al centro dello schermo). da = dove era DAVVERO Spidey (vista 3D:
        intanto la telecamera lo ha portato a 520 m sotto di sé; "torna dov'eri" e "acqua" lo rimettevano lassù = morto).
        coperto = il velo sopra il gioco c'è già (dalla mappa 3D)."""
        gid = self._gid_partita()
        if not gid:
            return {"errore": "gioco"}
        v = core.Viaggio(gid)
        occhio_dato = tuple(float(c) for c in occhio) if occhio else None
        terra = occhio = None  # "punto": dalla mappa della città, lì c'è terra? e da dove è stata fatta la foto
        if cosa == "mappa":
            m = self._mappa_punto
            if not m or m["gid"] != gid or v.centro_mappa() is None:
                return {"errore": "mappa"}
            dove = (m["x"], None, m["z"])
        elif cosa == "punto":  # punto scelto sulla mappa della città
            if x is None or z is None:
                return {"errore": "cosa"}
            dove = (float(x), None, float(z))
            geo = self._mappa_geo()
            if geo:  # la mappa dice se lì c'è terra: lontano la città si carica piano, il raggio aspetta di più
                import mappa_citta
                terra = mappa_citta.terra(self._mappa_cartella(), geo, float(x), float(z))
                occhio = mappa_citta.occhio(geo, float(x), float(z))  # foto in prospettiva: raggio da dove è stata fatta
            occhio = occhio_dato or occhio
            if occhio_dato and terra is None:  # dalla mappa 3D senza mappa della città: quello che vedevi c'era; se il
                terra = True  # raggio non lo trova subito (città lontana che si carica) caduta protetta, non "acqua"
        elif cosa == "posto":
            posti = self._conf.get("posti", [])
            if i is None or not 0 <= int(i) < len(posti):
                return {"errore": "posto"}
            p = posti[int(i)]
            dove = (p["x"], p["y"], p["z"])
            if p.get("y") is None and p.get("occhio"):  # salvato dalla mappa 3D: punto col raggio da dove si guardava
                occhio = tuple(p["occhio"])
                terra = True  # (lì c'era qualcosa: se lontano si carica piano, si aspetta di più invece di dire "acqua")
        elif cosa == "indietro":
            p = self._viaggio_prima
            if not p or p["gid"] != gid:
                return {"errore": "indietro"}
            dove = (p["x"], p["y"], p["z"])
        else:
            return {"errore": "cosa"}
        if not self._viaggio_lock.acquire(blocking=False):
            return {"errore": "occupato"}

        def via():
            # VELO sopra tutto il gioco (la foto del gioco che si sfoca, poi quella del posto) mentre Spidey si sposta, la
            # mappa del gioco si chiude e la città si carica (John: "si vede che si teletrasporta e poi carica tutto"); a
            # fine viaggio torna a fuoco sul gioco e il menu si chiude. Se non arriva (acqua, mappa rimasta aperta) il velo
            # si toglie e il menu resta aperto con l'avviso.
            esito, altezza = "errore", None
            try:
                qui = tuple(da) if da else v.posizione()
                self._menu_js("vgInViaggio(true)")
                if not coperto:
                    self._copri("su", testo="vg_in_viaggio", gioco=True)
                    if cosa == "posto" and posti[int(i)].get("foto"):  # la foto del posto, sfocata, mentre lo raggiungi
                        time.sleep(0.25)
                        self._copri("cambia", img=posti[int(i)]["foto"])
                self._aspetta_rilascio(3.0)  # A ancora giù: chiudendo la mappa (F14 porta davanti il gioco) Spidey salterebbe
                esito = v.vai(dove[0], dove[2], dove[1], dopo_tasto=self._menu_sopra, terra=terra, occhio=occhio, prima=qui)
                if esito == "ok" and getattr(v, "arrivo", None) and cosa == "punto":
                    altezza = round(v.arrivo[1])  # nel menu "Arrivato a 214 m": quanto era alto il palazzo
                if esito not in ("acqua", "mappa"):
                    self._viaggio_prima = {"gid": gid, "x": qui[0], "y": qui[1], "z": qui[2]}
                    self._mappa_punto = None  # punto usato: la prossima volta si riparte dalla mappa
                    time.sleep(0.6)  # la camera raggiunge Spidey sul tetto
                self._log_menu(f"viaggio {cosa} -> {esito} ({dove[0]:.0f}, {dove[2]:.0f})")
            except Exception as e:  # noqa: BLE001
                core.log_errore(f"viaggio: {e!r}")
            finally:
                if dopo:  # (vista 3D: icone della mappa di nuovo visibili, a mappa chiusa)
                    try:
                        dopo()
                    except Exception as e:  # noqa: BLE001
                        core.log_errore(f"viaggio, dopo: {e!r}")
                self._m3_passaggio = 0  # (fine del passaggio mappa 3D -> viaggio)
                self._viaggio_lock.release()
            self._menu_js(f"vgInViaggio(false, {json.dumps(esito)}, {json.dumps(altezza)})")
            if esito not in ("acqua", "mappa", "errore"):
                if altezza is not None:  # sul velo: "Arrivato a 214 m d'altezza" (quanto era alto il palazzo)
                    self._copri("cambia", testo="vg_arrivato_terra" if altezza < 4 else "vg_arrivato", args=[altezza], sub="", ok=True)
                    time.sleep(1.1)
                self._copri("giu", gioco=True, poi="chiudi")
            else:
                self._copri("giu", gioco=True, poi=None)
        threading.Thread(target=via, daemon=True).start()
        return {"ok": True}

    @protetto
    def menu_mappa3d(self):
        """Mappa 3D della città (mappa3d.py, al posto della mappa piatta): apre la mappa del gioco (se è chiusa), la sua
        telecamera parte dall'alto e si comanda con le levette mentre il menu è una barra in basso; al centro il mirino,
        sopra i posti salvati e "tu" i segnalini. Comandi dalla pagina (menu_mappa3d_comando): Y = posto salvato dopo
        (la telecamera ci vola), X = salva qui, L3/R3 = dall'alto. Finisce con menu_mappa3d_fine (A = vai: al posto scelto
        o dove c'è il mirino; B = esci), chiudendo il menu o la mappa."""
        gid = self._gid_partita()
        if not gid:
            return {"errore": "gioco"}
        if self._mappa_lavoro or getattr(self, "_m3", None) or not self._viaggio_lock.acquire(blocking=False):
            return {"errore": "occupato"}
        self._m3 = {"fine": None, "cmd": [], "scelto": None}

        def via():
            import cam_ps4
            import mappa3d
            import hud_ram
            v, vista, esito, dove = core.Viaggio(gid), None, "errore", None
            coperto = foto_fatta = False
            try:
                self._menu_js("m3Stato('apro')")
                self._aspetta_rilascio(3.0)  # A ancora giù: F15 porta davanti il gioco
                if self._m3["fine"] is not None:  # B mentre si apriva
                    esito = "esci"
                    return
                # VELO sopra tutto il gioco finché la vista 3D non è pronta dall'alto (John: "si vede che prima passa dalla
                # mappa normale"): sotto, la mappa che si apre (icone già nascoste), la telecamera che vola, la foto
                # dell'anteprima e l'icona di Spidey ritagliata (che così non "lampeggia" più davanti a te)
                self._copri("su", testo="m3_apro", gioco=True)
                coperto = True
                time.sleep(0.4)
                with core.DME_LOCK:
                    v._dme().write_byte(hud_ram.FOTO, 1)
                if not v.mappa_aperta() and not v.apri_mappa(dopo_tasto=self._menu_sopra):
                    esito = "apri"
                    return
                time.sleep(0.6)
                vista = mappa3d.Vista3D(v)
                try:
                    vista.entra()
                except RuntimeError as e:  # mappa rimasta in uno stato strano (es. app chiusa a metà): la riapro e riprovo
                    if "telecamera" not in str(e) or not v.chiudi_mappa(dopo_tasto=self._menu_sopra):
                        raise
                    time.sleep(0.8)
                    if not v.apri_mappa(dopo_tasto=self._menu_sopra):
                        raise
                    time.sleep(0.6)
                    vista = mappa3d.Vista3D(v)
                    vista.entra()
                self._m3["vista"] = vista  # (per chiudere l'app con la vista aperta)
                self._m3_segni_prepara()
                time.sleep(0.3)  # il gioco disegna la vista dall'alto
                try:  # anteprima della pagina Viaggio e icona di Spidey (per la freccia sul bordo), sotto il velo
                    foto_fatta = vista.foto()
                    if vista.icona_spidey():
                        self._m3_frecce_icona()
                except Exception as e:  # noqa: BLE001
                    core.log_errore(f"mappa 3d, foto: {e!r}")
                if self._m3["fine"] is None:
                    self._copri("giu", gioco=True, poi="barra")  # a fuoco sulla vista 3D, poi la barra
                    coperto = False
                self._m3_info()
                # MOVIMENTO A RITMO DEL GIOCO (teletrasporto.EST, modo 2): a ogni scatto del contatore video lo stato per
                # quello scatto e quanto cambia in uno scatto; il gioco, costruendo la vista, si calcola da solo dove sta
                # in quel momento. Prima scrivevo ~500 volte al secondo la posizione per il mio orologio, ma con la mappa il
                # gioco disegna 19-40 fotogrammi al secondo e legge in momenti irregolari = passi diversi a ogni fotogramma
                # (John: "ancora troppo tremolio"; misurato 92 passi irregolari su 354). Senza il codice nuovo nel gioco
                # (avviato prima) resta il modo vecchio.
                import mappa3d as m3
                t_ultimo = t_pronta = time.perf_counter()
                vi_ind = cam_ps4.VERSIONI[gid]["vi"]

                m3s = self._m3  # (i fili guardano QUESTA apertura: riaprendo, quelli vecchi si fermano)

                def filo_segni():  # mirino, segnalini e controlli a parte: muovere finestre o parlare con la pagina
                    controllo = time.perf_counter()  # (aspetta la risposta) non deve fermare la telecamera
                    foto, cam_prima, segni_t, tentativi = foto_fatta, None, 0.0, 0
                    storia = []  # (quando, telecamera disegnata) degli ultimi fotogrammi
                    ritardo = float(os.environ.get("SPIDEY_M3_RITARDO", RITARDO_SEGNI))
                    while m3s["fine"] is None:
                      try:
                        time.sleep(0.004)
                        if not foto and tentativi < 5 and time.perf_counter() - t_pronta > 0.8:  # dall'alto: anteprima
                            tentativi += 1  # della pagina Viaggio (e parte disegnata per i segnalini)
                            try:
                                foto = vista.foto()
                            except Exception as e:  # noqa: BLE001
                                core.log_errore(f"mappa 3d, foto: {e!r}")
                        if m3s["fine"] is not None:
                            break
                        self._mirino3d(True)
                        # segnalini mossi a ogni fotogramma DISEGNATO e con la sua telecamera (prima ogni 33 ms col mio
                        # stato, che non è quello che si vede: "il ping fa movimenti strani")
                        try:
                            with core.DME_LOCK:
                                cam_letta = m3.vista_disegnata(v._dme(), gid)
                        except Exception:  # noqa: BLE001
                            cam_letta = None
                        # l'immagine che si vede è qualche millisecondo indietro rispetto alla telecamera in memoria
                        # (Dolphin la disegna e la mostra dopo): uso quella di RITARDO_SEGNI fa, se no muovendo la vista
                        # i segnalini tremavano rispetto alla città (John)
                        adesso = time.perf_counter()
                        if not storia or storia[-1][1] != cam_letta:
                            storia.append((adesso, cam_letta))
                        while len(storia) > 1 and storia[1][0] <= adesso - ritardo:
                            storia.pop(0)
                        cam = storia[0][1]
                        if cam != cam_prima or time.perf_counter() - segni_t > 0.25:
                            cam_prima, segni_t = cam, time.perf_counter()
                            self._m3_segni(vista, cam)
                        if time.perf_counter() - controllo > 0.5:  # menu chiuso (LB + RB) o mappa chiusa da chi gioca
                            controllo = time.perf_counter()
                            if not self._menu_aperto or not v.mappa_aperta():
                                if m3s["fine"] is None:
                                    m3s["fine"] = "esci"
                                break
                            if getattr(self, "_menu_modo", None) != "barra":  # qualcuno ha rimesso il menu normale
                                self.menu_compatto("barra")
                            self._menu_js("m3Tieni()")
                      except Exception as e:  # noqa: BLE001  (un errore non deve fermare mirino e controlli)
                        core.log_errore(f"mappa 3d, segnalini: {e!r}")
                        time.sleep(0.2)

                def filo_bussola():  # bussola della barra: dove sta il nord del gioco (-x) sullo schermo
                    ultimo = None
                    while m3s["fine"] is None:
                        time.sleep(0.05)
                        try:
                            a = vista.ora["a"]
                            an = math.atan2(-math.sin(a), -math.cos(a))  # destra = (sin a, -cos a), su = (cos a, sin a)
                            if ultimo is None or abs(math.remainder(an - ultimo, 2 * math.pi)) > 0.02:
                                ultimo = an
                                self._menu_js(f"m3Bussola({an:.4f})")
                        except Exception:  # noqa: BLE001
                            pass
                fili = [threading.Thread(target=f, daemon=True) for f in (filo_segni, filo_bussola)]
                for f in fili:
                    f.start()
                switch = sys.getswitchinterval()
                sys.setswitchinterval(0.001)  # il filo della telecamera riprende la parola più spesso (rimesso uscendo)
                giri_dt, tempi = [], {"passo": 0.0}
                vi_prima, errori = None, 0
                while self._m3["fine"] is None:
                  try:  # una lettura/scrittura fallita per un attimo non deve chiudere tutto a metà (John: mappa bloccata)
                    if vista.modo == 2:  # aspetto lo scatto del contatore video (il gioco legge 0-15 ms dopo)
                        time.sleep(0.0005)
                        with core.DME_LOCK:
                            vi = v._dme().read_word(vi_ind)
                        if vi == vi_prima:
                            continue
                        scatti = 1 if vi_prima is None else max(1, min(6, (vi - vi_prima) & 0xFFFFFFFF))
                        vi_prima = vi
                    else:
                        time.sleep(0.002)
                    ora = time.perf_counter()
                    dt, t_ultimo = min(0.1, ora - t_ultimo), ora
                    giri_dt.append(dt)
                    alto = False
                    while self._m3["cmd"]:
                        c = self._m3["cmd"].pop(0)
                        if c == "alto":
                            alto = True
                        elif c in ("posto", "posto-"):
                            self._m3_posto(vista, -1 if c == "posto-" else 1)
                        elif c == "salva":  # (foto e segnalini nuovi sono lenti: la telecamera non deve fermarsi)
                            threading.Thread(target=self._m3_salva, args=(vista,), daemon=True).start()
                    (sx, sy), (dx, dy), incl = self._m3_levette()
                    if self._m3["scelto"] is not None and (abs(sx) > 0.18 or abs(sy) > 0.18):
                        self._m3["scelto"] = None  # mosso a mano: A va dove c'è il mirino
                        self._m3_info()
                    t1 = time.perf_counter()
                    if vista.modo == 2:  # tempo del gioco: 1/60 di secondo per scatto
                        for k in range(scatti):
                            vista.passo(1 / 60, sx, sy, dx, dy, incl, alto and k == 0)
                        e1, t1_ = vista.prevedi(1 / 60, sx, sy, dx, dy, incl)
                        vista.scrivi_est(vi, e1, t1_)
                    else:
                        vista.passo(dt, sx, sy, dx, dy, incl, alto)
                        vista.scrivi()
                    vista.segui()
                    tempi["passo"] = max(tempi["passo"], time.perf_counter() - t1)
                  except Exception as e:  # noqa: BLE001
                    errori += 1
                    if errori == 1:
                        core.log_errore(f"vista 3d, giro: {e!r}")
                    if errori > 60:  # ~3 s di fila: il gioco non risponde più (chiuso?)
                        raise
                    vi_prima = None
                    time.sleep(0.05)
                    continue
                  errori = 0
                esito = self._m3["fine"]
                if giri_dt:
                    g = sorted(giri_dt)
                    self._log_menu(f"vista 3d (modo {vista.modo}) giri: {len(g)} in {sum(g):.1f} s, mediana {g[len(g) // 2] * 1000:.1f} ms, p95 "
                                   f"{g[int(len(g) * .95)] * 1000:.1f} ms, max {g[-1] * 1000:.0f} ms, >20 ms: "
                                   f"{sum(1 for x in g if x > 0.02)}; passo max {tempi['passo'] * 1000:.0f} ms")
                if esito in ("vai", "esci"):  # velo anche all'uscita: mappa che si chiude e Spidey rimesso non si vedono
                    for f in fili:
                        f.join(1.0)
                    self._mirino3d(False)  # (finestre sopra a tutto: sopra al velo resterebbero)
                    self._m3_segni(None)
                    self._copri("su", testo="vg_in_viaggio" if esito == "vai" else "", gioco=True)
                    coperto = True
                    time.sleep(0.4)
                if esito == "vai":
                    i = self._m3["scelto"]
                    dove = ("posto", i, None) if i is not None else ("punto", (vista.tx, vista.tz), vista.occhio())
                    try:  # anteprima nuova della pagina Viaggio: dall'alto sopra la destinazione (John: riaprendo c'era
                        # ancora la zona di prima); un attimo prima di partire, con la mappa ancora aperta, sotto il velo
                        p = self._conf.get("posti", [])[i] if i is not None else {"x": vista.tx, "z": vista.tz}
                        self._m3_foto_arrivo(vista, p["x"], p["z"], vi_ind)
                        import base64
                        self._copri("cambia", img=base64.b64encode(mappa3d.ANTEPRIMA.read_bytes()).decode())  # dove vai
                    except Exception as e:  # noqa: BLE001
                        core.log_errore(f"vista 3d, foto d'arrivo: {e!r}")
            except Exception as e:  # noqa: BLE001
                core.log_errore(f"vista 3d: {e!r}")
            finally:
                try:
                    sys.setswitchinterval(switch)
                except NameError:
                    pass
                if self._m3:
                    self._m3["fine"] = self._m3.get("fine") or esito  # ferma il filo dei segnalini
                for f in locals().get("fili", []):  # (se no un segnalino rimesso a metà restava sullo schermo)
                    f.join(1.0)
                self._mirino3d(False)
                self._m3_segni(None)
                if dove:  # tra la fine della vista e il viaggio la mappa è ancora aperta con le icone nascoste: la
                    self._m3_passaggio = time.time() + 20  # pulizia di _sorveglia_ora non deve rimetterle (lo azzera il viaggio)
                try:
                    if vista:
                        if dove is None:  # B ancora giù: chiudendo la mappa (F14 porta davanti il gioco) arriverebbe a Spidey
                            self._aspetta_rilascio(3.0)
                        vista.esci(rimetti_spidey=dove is None, dopo_tasto=self._menu_sopra)
                    elif not dove:  # chiusa prima di essere pronta: icone (nascoste aprendo) di nuovo visibili
                        with core.DME_LOCK:
                            v._dme().write_byte(hud_ram.FOTO, 0)
                except Exception as e:  # noqa: BLE001
                    core.log_errore(f"vista 3d, uscita: {e!r}")
                self._m3 = None
                self._viaggio_lock.release()
                self._menu_js(f"m3Stato('fine', {json.dumps(esito)})")
                if coperto and not dove:  # di nuovo a fuoco sul gioco (la camera è tornata su Spidey), menu normale
                    time.sleep(0.2 if vista else 0.0)
                    self._copri("giu", gioco=True, poi=None)
                elif not dove:
                    self.menu_compatto(None)
            self._log_menu(f"vista 3d -> {esito}")
            if dove:  # (icone e "su" del gioco rimessi a viaggio finito; il velo lo toglie il viaggio)
                if dove[0] == "posto":
                    r = self.menu_viaggio_vai("posto", dove[1], dopo=vista.icone_visibili, da=vista.pos0, coperto=True)
                else:  # come un punto della mappa della città, col raggio da dove guardavi
                    r = self.menu_viaggio_vai("punto", None, dove[1][0], dove[1][1], occhio=list(dove[2]), dopo=vista.icone_visibili,
                                              da=vista.pos0, coperto=True)
                if not r or r.get("errore"):
                    self._m3_passaggio = 0
                    vista.icone_visibili()
                    self._copri("giu", gioco=True, poi=None)
        threading.Thread(target=via, daemon=True).start()
        return {"ok": True}

    def _m3_foto_arrivo(self, vista, x, z, vi_ind):
        """La telecamera della mappa vola dall'alto sopra (x, z) (~0,6 s, com'è all'apertura) e fotografa l'anteprima."""
        import mappa3d as m3
        w = vista.voluta
        w.update(x=x, z=z, p=m3.P_MAX, d=m3.D_INIZIO, a=vista.a0 + round((w["a"] - vista.a0) / (2 * math.pi)) * 2 * math.pi)
        t0 = t_ultimo = time.perf_counter()
        vi_prima = None
        while time.perf_counter() - t0 < 0.75:
            if vista.modo == 2:
                time.sleep(0.0005)
                with core.DME_LOCK:
                    vi = vista.v._dme().read_word(vi_ind)
                if vi == vi_prima:
                    continue
                scatti = 1 if vi_prima is None else max(1, min(6, (vi - vi_prima) & 0xFFFFFFFF))
                vi_prima = vi
                for _ in range(scatti):
                    vista.passo(1 / 60, 0, 0, 0, 0)
                e1, t1 = vista.prevedi(1 / 60, 0, 0, 0, 0)
                vista.scrivi_est(vi, e1, t1)
            else:
                time.sleep(0.004)
                ora = time.perf_counter()
                vista.passo(min(0.1, ora - t_ultimo), 0, 0, 0, 0)
                t_ultimo = ora
                vista.scrivi()
            vista.segui()
        time.sleep(0.15)  # il gioco disegna l'ultima posizione
        vista.foto()

    @protetto
    def menu_mappa3d_fine(self, vai=False):
        m = getattr(self, "_m3", None)
        if m and m["fine"] is None:
            m["fine"] = "vai" if vai else "esci"
        return True

    @protetto
    def menu_mappa3d_comando(self, cosa):
        """Dalla pagina: "posto" / "posto-" (posto salvato dopo / prima), "salva" (salva qui), "alto" (di nuovo dall'alto)."""
        m = getattr(self, "_m3", None)
        if m and cosa in ("posto", "posto-", "salva", "alto"):
            m["cmd"].append(cosa)
        return True

    @protetto
    def menu_mappa3d_finto(self, sx=0, sy=0, dx=0, dy=0, incl=0, secondi=1.0):
        """Solo per le prove (senza pad): levette e inclinazione (LT/RT) finte per qualche secondo."""
        self._m3_finto = ((float(sx), float(sy)), (float(dx), float(dy)), float(incl), time.time() + float(secondi))
        return True

    @protetto
    def menu_mappa3d_anteprima(self):
        """Anteprima della mappa 3D (foto dall'alto fatta all'ultima apertura) per la pagina Viaggio: {img, quando} o None."""
        import base64
        import mappa3d
        f = mappa3d.ANTEPRIMA
        if not f.is_file():
            return None
        r = {"img": base64.b64encode(f.read_bytes()).decode(), "quando": int(f.stat().st_mtime), "tu": None}
        gid = self._gid_partita()
        if gid:  # dove sei ADESSO nella foto (John: "mi sono spostato e l'anteprima non si era aggiornata")
            try:
                pos = core.Viaggio(gid).posizione()
                r["tu"] = mappa3d.proietta_anteprima(*pos) if pos else None
            except Exception:  # noqa: BLE001
                pass
        return r

    def _m3_info(self):
        posti = self._conf.get("posti", [])
        m = self._m3
        i = m["scelto"] if m else None
        nome = posti[i].get("nome") if i is not None and i < len(posti) else None
        self._menu_js(f"m3Info({json.dumps({'posto': None if i is None else len(posti) - i, 'tot': len(posti), 'nome': nome})})")

    def _m3_posto(self, vista, passo):
        """Y: la telecamera vola al posto salvato dopo (nell'ordine dei numeri: 1, 2, 3...)."""
        posti = self._conf.get("posti", [])
        if not posti:
            self._menu_js("toast(t('m3_nessun_posto'))")
            return
        i = self._m3["scelto"]
        # numero mostrato = quanti - indice: il posto col numero dopo è l'indice prima
        i = len(posti) - 1 if i is None else (i - passo) % len(posti)
        self._m3["scelto"] = i
        vista.vola_a(posti[i]["x"], posti[i]["z"])
        self._m3_info()

    def _m3_salva(self, vista):
        """X: salva il punto sotto il mirino tra i posti (col raggio da dove guardi: andandoci si arriva su quello che si
        vedeva, come i punti della mappa della città)."""
        g = core.finestra_gioco()
        try:
            foto = core.foto_finestra(g, 320) if g else None
        except Exception:  # noqa: BLE001
            foto = None
        posti = self._conf.setdefault("posti", [])
        if not self._m3:
            return
        posti.insert(0, {"x": round(vista.tx, 2), "y": None, "z": round(vista.tz, 2),
                         "occhio": [round(c, 2) for c in vista.occhio()], "foto": foto, "quando": time.strftime("%Y-%m-%d %H:%M")})
        del posti[24:]
        core.scrivi_config(self._conf)
        m = self._m3
        if m and m["scelto"] is not None:
            m["scelto"] = min(m["scelto"] + 1, len(posti) - 1)
        self._m3_segni_prepara()
        self._menu_js(f"toast(t('m3_salvato', {len(posti)}))")
        self._m3_info()

    def _rett_gioco(self, vista):
        """Origine (pixel veri) della parte interna della finestra del gioco e scala foto -> schermo, o None."""
        import ctypes
        from ctypes import wintypes
        g = core.finestra_gioco()
        dim = getattr(vista, "foto_dim", None)
        if not g or not dim:
            return None
        u = ctypes.windll.user32
        prima = u.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))
        try:
            r, pt = wintypes.RECT(), wintypes.POINT(0, 0)
            u.GetClientRect(g, ctypes.byref(r))
            u.ClientToScreen(g, ctypes.byref(pt))
        finally:
            u.SetThreadDpiAwarenessContext(ctypes.c_void_p(prima))
        if u.IsIconic(g) or r.right - r.left < 200:
            return None
        return pt.x, pt.y, (r.right - r.left) / dim[0], (r.bottom - r.top) / dim[1]

    def _m3_alza(self):
        for m in [getattr(self, "_mirino_3d", None)] + list(getattr(self, "_segni", {}).values()):
            try:
                if m:
                    m.alza()
            except Exception:  # noqa: BLE001
                pass

    def _m3_segni_prepara(self):
        """Segnalini (finestre trasparenti, mirino.py) per i posti salvati e per "tu": fatti prima, così non rallentano."""
        import mirino
        self._segni = getattr(self, "_segni", {})
        posti = self._conf.get("posti", [])
        tu = {"it": "Tu", "en": "You", "de": "Du", "fr": "Toi", "es": "Tú"}.get(self._conf.get("lingua") or core.lingua_sistema(), "You")
        voluti = [(tu, (226, 54, 54))] + [(str(n), c) for n in range(1, len(posti) + 1) for c in ((45, 110, 235), (232, 170, 20))]
        for k in voluti:
            if k not in self._segni:
                self._segni[k] = mirino.Mirino(immagine=mirino._segnalino(*k))
        for i in range(24):  # "tu" fuori dallo schermo: freccia sul bordo verso di te, una ogni 15°
            k = ("freccia", tu, i)
            if k not in self._segni:
                self._segni[k] = mirino.Mirino(immagine=mirino._freccia(tu, (226, 54, 54), i * math.pi / 12))
        self._segni_tu = tu
        self._m3_frecce_icona()

    def _m3_frecce_icona(self):
        """Frecce sul bordo con l'icona di Spidey del gioco (mappa3d.ICONA, ritagliata all'apertura): rifatte se l'icona
        è cambiata (es. altra risoluzione del gioco)."""
        import hashlib
        import mappa3d
        import mirino
        from PIL import Image
        try:
            dati = mappa3d.ICONA.read_bytes()
        except OSError:
            return
        firma = hashlib.md5(dati).hexdigest()
        if getattr(self, "_ficona_firma", None) == firma:
            return
        try:
            ic = Image.open(mappa3d.ICONA)
            ic.load()
        except Exception:  # noqa: BLE001
            return
        vecchie = [k for k in self._segni if k[0] == "ficona"]
        for k in vecchie:  # (finestre vecchie: nascoste e lasciate andare)
            try:
                self._segni.pop(k).nascondi()
            except Exception:  # noqa: BLE001
                pass
        lato = None
        for i in range(24):
            im = mirino._freccia_icona(ic, i * math.pi / 12, lato)
            lato = im.width
            self._segni[("ficona", i)] = mirino.Mirino(immagine=im)
        self._ficona_firma, self._ficona_lato = firma, lato

    def _m3_segni(self, vista, cam=None):
        """Segnalini sopra la vista 3D (vista None = tutti via); cam = telecamera del fotogramma disegnato."""
        segni = getattr(self, "_segni", {})
        mostra = {}
        try:
            rett = self._rett_gioco(vista) if vista else None
            if rett:
                posti = self._conf.get("posti", [])
                scelto = self._m3["scelto"] if self._m3 else None
                for i, p in enumerate(posti):
                    k = (str(len(posti) - i), (232, 170, 20) if i == scelto else (45, 110, 235))
                    xy = vista.schermo(p["x"], p["y"] if p.get("y") is not None else 0.0, p["z"], rett, cam)
                    if xy and k in segni:
                        mostra[k] = xy
                k = (getattr(self, "_segni_tu", "Tu"), (226, 54, 54))
                xy = vista.schermo(vista.pos0[0], vista.pos0[1], vista.pos0[2], rett, cam)
                if xy and k in segni and vista.modo != 2:  # nel modo 2 c'è l'icona di Spidey del gioco (ferma sul punto)
                    mostra[k] = xy
                elif not xy:  # fuori dallo schermo: la freccia sul bordo che punta verso dove sei (quadrata: centro)
                    b = vista.bordo(vista.pos0[0], vista.pos0[1], vista.pos0[2], rett, cam)
                    if b:
                        (bx, by), ang = b
                        i = round(ang / (math.pi / 12)) % 24
                        if ("ficona", i) in segni and vista.modo == 2:  # con l'icona di Spidey del gioco (John)
                            mostra[("ficona", i)] = (bx, by + getattr(self, "_ficona_lato", 74) / 2)
                        elif ("freccia", k[0], i) in segni:
                            mostra[("freccia", k[0], i)] = (bx, by + 37)
            for k, m in list(segni.items()):  # (_m3_segni_prepara può aggiungerne intanto)
                if k in mostra:
                    m.mostra(*mostra[k])
                else:
                    m.nascondi()
        except Exception as e:  # noqa: BLE001
            core.log_errore(f"segnalini 3d: {e!r}")

    def _m3_levette(self):
        f = getattr(self, "_m3_finto", None)
        if f and time.time() < f[3]:
            return f[0], f[1], f[2]
        sin, des = getattr(self, "_pad_levette", ((0.0, 0.0), (0.0, 0.0)))
        if time.time() - getattr(self, "_pad_quando", 0) > 0.3:  # pad muto (staccato): fermo
            sin = des = (0.0, 0.0)
        b = getattr(self, "_pad_bits", 0)
        return sin, des, (1 if b & 0x20000 else 0) - (1 if b & 0x10000 else 0)  # RT verso l'orizzonte, LT dall'alto

    def _centro_gioco(self):
        """Centro della parte disegnata della finestra del gioco (pixel veri), o None (ridotta a icona / non c'è)."""
        import ctypes
        from ctypes import wintypes
        g = core.finestra_gioco()
        if not g:
            return None
        u = ctypes.windll.user32
        prima = u.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))
        try:
            r, pt = wintypes.RECT(), wintypes.POINT(0, 0)
            u.GetClientRect(g, ctypes.byref(r))
            u.ClientToScreen(g, ctypes.byref(pt))
        finally:
            u.SetThreadDpiAwarenessContext(ctypes.c_void_p(prima))
        if u.IsIconic(g) or r.right - r.left < 200:
            return None
        return pt.x + (r.right - r.left) // 2, pt.y + (r.bottom - r.top) // 2

    def _mirino3d(self, si):
        """Mirino al centro del gioco nella vista 3D (il punto dove si arriva con A); aggiornato ogni ~0,3 s."""
        try:
            if not si:
                if getattr(self, "_mirino_3d", None):
                    self._mirino_3d.nascondi()
                self._mirino_3d_quando = 0
                return
            if time.time() - getattr(self, "_mirino_3d_quando", 0) < 0.3:
                return
            self._mirino_3d_quando = time.time()
            import mirino
            if not getattr(self, "_mirino_3d", None):
                testo = {"it": "A · Vai qui", "en": "A · Go here", "de": "A · Hierhin", "fr": "A · Aller ici",
                         "es": "A · Ir aquí"}.get(self._conf.get("lingua") or core.lingua_sistema(), "A · Go here")
                self._mirino_3d = mirino.Mirino(testo)
            c = self._centro_gioco()
            if c:
                self._mirino_3d.mostra(*c)
            else:
                self._mirino_3d.nascondi()
        except Exception as e:  # noqa: BLE001
            core.log_errore(f"mirino 3d: {e!r}")

    @protetto
    def menu_viaggio_salva(self):
        """Salva il posto dove sei adesso (con una foto del gioco) tra i "tuoi posti" (al massimo 24: via il più vecchio)."""
        gid = self._gid_partita()
        if not gid:
            return {"errore": "gioco"}
        p = core.Viaggio(gid).posizione()
        foto = None
        try:
            g = core.finestra_gioco()
            foto = core.foto_finestra(g, 320) if g else None
        except Exception:  # noqa: BLE001
            foto = None
        posti = self._conf.setdefault("posti", [])
        posti.insert(0, {"x": round(p[0], 2), "y": round(p[1], 2), "z": round(p[2], 2), "foto": foto,
                         "quando": time.strftime("%Y-%m-%d %H:%M")})
        del posti[24:]
        core.scrivi_config(self._conf)
        return {"ok": True}

    @protetto
    def menu_viaggio_rinomina(self, i, nome):
        """Nome di un posto salvato (vuoto = torna "Posto n")."""
        posti = self._conf.get("posti", [])
        if 0 <= int(i) < len(posti):
            nome = " ".join(str(nome or "").split())[:32]
            if nome:
                posti[int(i)]["nome"] = nome
            else:
                posti[int(i)].pop("nome", None)
            core.scrivi_config(self._conf)
        return {"ok": True}

    @protetto
    def menu_tastiera(self):
        """La finestra del menu in primo piano (per scrivere: aperto col pad, la tastiera può essere ancora del gioco)."""
        import ctypes
        w = ctypes.windll.user32.FindWindowW(None, TITOLO_MENU)
        if w and self._menu_aperto:
            core._davanti(w)
        return True

    @protetto
    def menu_viaggio_togli(self, i):
        posti = self._conf.get("posti", [])
        if 0 <= int(i) < len(posti):
            del posti[int(i)]
            core.scrivi_config(self._conf)
        return {"ok": True}

    def _ora_negli_ini(self):
        dolphin = core.trova_dolphin(self._conf)
        if not dolphin:
            return
        for g in core.NOMI_VERSIONE:
            try:
                core.imposta_ora(Path(dolphin) / "GameSettings" / f"{g}.ini", g, self._ora_ini)
            except Exception as e:  # noqa: BLE001
                core.log_errore(f"ora negli INI: {e!r}")

    def _sorveglia_ora(self):
        """Tempo fermato dal menu col gioco aperto: l'app riscrive l'ora (il gioco la fa correre ~48 volte il tempo vero);
        ora cambiata col tempo che scorre: una scrittura sola. Gioco chiuso o cambiato = si smette."""
        controllato, gid_mappa, gid_quando, mappa_da = 0, None, 0, None
        mappa_ok = False
        errore_t = 0
        while True:
            time.sleep(0.25)
            try:  # un errore non deve fermare per sempre ora ferma, mirino e pulizia della mappa
                if time.time() - gid_quando > 2:  # quale gioco gira (ogni 2 s: elenco delle finestre)
                    gid_quando, gid_mappa = time.time(), core.gioco_in_corso()
                if gid_mappa and gid_mappa != "?":  # mappa del gioco aperta: mi ricordo il punto al centro (menu > Mondo > Viaggio)
                    try:  # (solo a mappa aperta da 1,2 s e telecamera in quota: aprendo/chiudendo vola verso un punto fuori città)
                        c = core.Viaggio(gid_mappa).centro_mappa()
                        mappa_da = (mappa_da or time.time()) if c else None
                        mappa_ok = bool(c and c[1] >= 499 and time.time() - mappa_da > 1.2)
                        fermo = self._menu_aperto or (getattr(self, "_pad_bits", 0) & 0x0300)  # LB/RB tenuti o menu aperto
                        # il primo punto di questa apertura della mappa lo prendo anche col menu già aperto (John: aprendo
                        # subito il menu bisognava muovere il cursore perché comparisse "vai al punto della mappa")
                        mp = self._mappa_punto
                        nuovo = not mp or mp.get("gid") != gid_mappa or mp.get("quando", 0) < mappa_da
                        proprio = getattr(self, "_m3", None) or self._mappa_lavoro  # la telecamera la muove l'app
                        if mappa_ok and (not fermo or nuovo) and not proprio:  # (LB = sinistra+destra della croce: aprendo
                            self._mappa_punto = {"gid": gid_mappa, "x": c[0], "z": c[2], "quando": time.time()}  # il menu
                            # la mappa scivolava: col menu aperto il punto non cambia più)
                    except Exception:  # noqa: BLE001
                        mappa_ok = False
                else:
                    mappa_ok = False
                if gid_mappa and gid_mappa != "?" and time.time() - getattr(self, "_foto_controllo", 0) > 3:
                    self._foto_controllo = time.time()  # icone della mappa (e pezzi dell'HUD) nascoste rimaste da un giro o da
                    if not self._mappa_lavoro and not getattr(self, "_m3", None) and not self._viaggio_lock.locked() and \
                            time.time() > getattr(self, "_m3_passaggio", 0):  # (vista 3D interrotta)
                        try:
                            import hud_ram
                            with core.DME_LOCK:
                                dme = core.Viaggio(gid_mappa)._dme()
                                if dme.read_byte(hud_ram.FOTO):  # (1 foto, 2 mappa 3D)
                                    dme.write_byte(hud_ram.FOTO, 0)
                                    core.log_errore("icone della mappa rimaste nascoste: rimesse")
                                import teletrasporto
                                if dme.read_word(teletrasporto.SU3D_ATTIVA):
                                    dme.write_word(teletrasporto.SU3D_ATTIVA, 0)
                                import mappa3d  # limiti di distanza della città tolti da una vista 3D interrotta
                                if mappa3d.DISTANZE_FILE.is_file():
                                    d3 = json.loads(mappa3d.DISTANZE_FILE.read_text(encoding="utf-8"))
                                    if d3.get("gid") == gid_mappa:
                                        mappa3d.rimetti_distanze(dme, d3.get("valori", {}))
                                        core.log_errore("limiti di distanza della città rimasti tolti: rimessi")
                        except Exception:  # noqa: BLE001
                            pass
                v = self._ora_vivo
                if not v and time.time() - controllato > 5:  # app riaperta col gioco aperto dopo aver fermato il tempo dal menu:
                    controllato = time.time()  # la parola SPENTO zittisce il codice dell'INI, quindi l'ora la riprendo a tenere io
                    gid = core.gioco_in_corso()
                    letto = core.ora_leggi(gid) if gid and gid != "?" else None
                    dolphin = core.trova_dolphin(self._conf) if letto and letto[1] else None
                    sec = core.ora_valore(Path(dolphin) / "GameSettings" / f"{gid}.ini") if dolphin else None
                    if sec is not None:
                        self._ora_vivo = v = {"gid": gid, "sec": sec, "fermo": True, "scrivi": True}
                if not v:
                    continue
                if core.gioco_in_corso() != v["gid"]:
                    self._ora_vivo = None
                    continue
                if (v["fermo"] or v["scrivi"]) and not self._mappa_lavoro:  # (giro della mappa: lì è mezzogiorno)
                    with self._ora_lock:  # (intanto il menu può aver scelto un'altra ora: scrivevo quella vecchia e
                        v = self._ora_vivo  # tenendo premuto l'ora tornava indietro per un attimo)
                        if v and (v["fermo"] or v["scrivi"]) and core.ora_scrivi(v["gid"], v["sec"]):
                            v["scrivi"] = False
            except Exception as e:  # noqa: BLE001
                if time.time() - errore_t > 60:
                    errore_t = time.time()
                    core.log_errore(f"sorveglia ora: {e!r}")

    @protetto
    def hd_accendi(self):
        """Launcher: le texture HD sono installate ma spente (HiresTextures) -> accese negli INI di quelle versioni."""
        dolphin = core.trova_dolphin(self._conf)
        if not dolphin:
            return {"errore": "dolphin"}
        fatti = []
        for gid, m in core.mod_versioni(dolphin).items():
            if m.get("hd_spente"):
                core.accendi_hd(Path(dolphin) / "GameSettings" / f"{gid}.ini")
                fatti.append(core.NOMI_VERSIONE[gid])
        return {"fatti": fatti, "dolphin_aperto": bool(core.exe_dolphin_aperti())}

    @protetto
    def codici_essenziali(self):
        """Senza la mod grafica: mette nelle versioni che hai i codici essenziali (lo stesso INI che usa l'installer: 60 fps,
        camera, niente blur, widescreen, cambio skin, HUD, patch 60 Hz per le PAL e le impostazioni di John). Se poi installi
        la mod, l'installer trova i codici con gli stessi nomi e non li tocca."""
        dolphin = core.trova_dolphin(self._conf)
        if not dolphin:
            return {"errore": "dolphin"}
        fatti = []
        oc = core.OC_CPU.get(self._conf.get("grafica_cpu") or core.processore()["livello"])
        for gid in self._tutti_giochi(dolphin):
            if core.prepara_ini(dolphin, gid, self._conf, self._cam_modi(), self._conf.get("cam_opzioni"), oc):
                fatti.append(core.NOMI_VERSIONE[gid])
        return {"fatti": fatti, "dolphin_aperto": bool(core.exe_dolphin_aperti())}

    def _versione_modello(self, dolphin, escludi):
        """La versione da cui copiare (launcher, "Come ITA"): l'ultima giocata se è pronta, se no quella con più codici."""
        mod = core.mod_versioni(dolphin)
        pronte = [g for g in self._tutti_giochi(dolphin) if g != escludi and mod.get(g, {}).get("ini")]
        if not pronte:
            return None
        ult = self._conf.get("ultima_versione")
        if ult in pronte:
            return ult
        return max(pronte, key=lambda g: (mod[g].get("texture", False), mod[g].get("codici", 0)))

    @protetto
    def versione_allinea(self, gid, da=None):
        """Launcher: porta una versione appena aggiunta alla pari di un'altra (su un PC di prova c'era solo ITA:
        aggiunta la USA per il video non c'era modo di averla uguale). Texture (collegamento <ID>.txt nella cartella delle
        texture), INI pronto (prepara_ini: patch 60 Hz, camera, profilo del pad), gli stessi codici accesi/spenti, la stessa
        grafica, la stessa camera classica (quella salvata) e la stessa ora del giorno. I codici sono scritti con le righe
        della versione di destinazione (gli indirizzi cambiano tra le versioni: le righe non si copiano)."""
        import app_cam
        dolphin = core.trova_dolphin(self._conf)
        if not dolphin:
            return {"errore": "dolphin"}
        D = Path(dolphin)
        da = da or self._versione_modello(dolphin, gid)
        if not da or da == gid:
            return {"errore": "nessuna versione da copiare"}
        src, dest = D / "GameSettings" / f"{da}.ini", D / "GameSettings" / f"{gid}.ini"
        # 1. texture: la cartella che usa la versione modello vale anche per questa
        base = D / "Load" / "Textures"
        if da in core.versioni_texture(D) and gid not in core.versioni_texture(D):
            cart = next((c for c in core.cartelle_texture(D) if c.is_dir() and (c.name == da or (c / f"{da}.txt").exists())), None)
            if cart:
                (cart / f"{gid}.txt").write_text("", encoding="utf-8")
        # 2. INI pronto per giocare con la mod
        oc = core.OC_CPU.get(self._conf.get("grafica_cpu") or core.processore()["livello"])
        if not core.prepara_ini(D, gid, self._conf, self._cam_modi(), self._conf.get("cam_opzioni"), oc):
            return {"errore": "ini"}
        # 3. stessi codici accesi e spenti (solo quelli che esistono in tutte e due le versioni)
        db = core.carica_codici_db() + self._miei()
        att_da, att_qui = core.leggi_codici_ini(src)["attivi"], core.leggi_codici_ini(dest)["attivi"]
        stati = {}
        for c in db:
            if c.get("parte_di") or gid not in c.get("versioni", {}) or da not in c.get("versioni", {}):
                continue
            on = c["nome_ini"] in att_da
            if on != (c["nome_ini"] in att_qui):
                stati[c["id"]] = on
        if stati:
            r = self.codici_applica([gid], stati)
            if isinstance(r, dict) and r.get("errore"):
                return r
        # 4. stessa grafica (le righe di GRAFICA scritte nell'INI della versione modello)
        ini_da = core.leggi_ini(src)
        valori = {(sez, chiave): ini_da[sez][chiave] for sez, chiave, _t, _s in core.GRAFICA.values()
                  if chiave in ini_da.get(sez, {})}
        if valori:
            core.backup_file(dest, "GameSettings")
            core.scrivi_ini_valori(dest, valori)
        # 5. stessa camera classica (i valori salvati: le righe AR sono diverse per ogni versione) e stessa ora
        cs = self._conf.get("cam_salvata")
        if cs and cs.get("valori"):
            try:
                app_cam.salva(D, cs["valori"], cs.get("fov", 95), gid)
            except Exception as e:  # noqa: BLE001
                core.log_errore(f"versione_allinea, camera: {e!r}")
        sec = core.ora_valore(src)
        if sec != core.ora_valore(dest):
            core.imposta_ora(dest, gid, sec)
        # 6. il salvataggio (convertito per questa versione); con Dolphin aperto no: la memory card la sta usando lui.
        # Se lì c'è già un salvataggio diverso non lo sovrascrivo: la pagina chiede (salvataggio_copia con forza)
        aperto = bool(core.exe_dolphin_aperti())
        fd = core.file_salvataggio(D, gid)
        if aperto:
            salv = "dolphin"
        elif fd.is_file() and core.file_salvataggio(D, da).is_file() and not core.stessi_dati_salvataggio(D, da, gid):
            salv = "chiedi"
        else:
            salv = core.copia_salvataggio(D, da, gid)
        self._giochi = None
        return {"ok": True, "da": core.NOMI_VERSIONE[da], "a": core.NOMI_VERSIONE[gid], "codici": len(stati),
                "salvataggio": salv, "dolphin_aperto": aperto, "gid": gid, "da_gid": da,
                "salv_qui": core.leggi_salvataggio(fd) if salv == "chiedi" else None,
                "salv_da": core.leggi_salvataggio(core.file_salvataggio(D, da)) if salv == "chiedi" else None}

    @protetto
    def salvataggi_stato(self):
        """Gestore dei salvataggi (scheda "Salvataggi" del launcher): per ogni versione (col disco o col file) le caselle
        del salvataggio della memory card A con nome, percentuale, tempo, punti eroe, data."""
        dolphin = core.trova_dolphin(self._conf)
        if not dolphin:
            return {"errore": "dolphin"}
        giochi = self._tutti_giochi(dolphin)
        out = []
        for gid in core.ID_GIOCO:
            f = core.file_salvataggio(dolphin, gid)
            if gid in giochi or f.is_file():
                out.append({"gid": gid, "nome": core.NOMI_VERSIONE[gid], "disco": gid in giochi, "file": str(f) if f.is_file() else None,
                            "slot": core.leggi_salvataggio(f)})
        return {"versioni": out, "dolphin_aperto": bool(core.exe_dolphin_aperti())}

    @protetto
    def salvataggio_copia(self, da, a, forza=False):
        """Copia il salvataggio di una versione in un'altra (convertito). Se lì ce n'è già uno diverso e non è forza:
        {"chiedi": ...} senza toccare niente. Il salvataggio sostituito va nei backup."""
        dolphin = core.trova_dolphin(self._conf)
        if not dolphin:
            return {"errore": "dolphin"}
        if core.exe_dolphin_aperti():
            return {"errore": "salv_dolphin_aperto"}
        fd = core.file_salvataggio(dolphin, a)
        if not forza and fd.is_file() and not core.stessi_dati_salvataggio(dolphin, da, a):
            return {"chiedi": True, "salv_qui": core.leggi_salvataggio(fd),
                    "salv_da": core.leggi_salvataggio(core.file_salvataggio(dolphin, da))}
        return {"esito": core.copia_salvataggio(dolphin, da, a)}

    @protetto
    def codici_applica(self, gids, stati):
        """gids = versioni da modificare; stati = {id codice: True/False} (solo quelli cambiati)."""
        dolphin = core.trova_dolphin(self._conf)
        if not dolphin:
            return {"errore": "dolphin"}
        db = {c["id"]: c for c in core.carica_codici_db() + self._miei()}
        stati = dict(stati)
        for cid, on in list(stati.items()):  # pezzi di un altro codice (camera classica + Gecko): insieme a lui
            for c in db.values():
                if c.get("parte_di") == cid:
                    stati[c["id"]] = on
        if stati.get("widescreen") and "aspetto_43" in db:  # widescreen riacceso a mano: via il "4:3" di Grafica
            stati["aspetto_43"] = False
        if any(on and db[cid].get("esclusivo") == "ora" for cid, on in stati.items()) and "ora_fissa" in db:
            stati["ora_fissa"] = False  # un orario fisso di Codici al posto dell'ora precisa del menu > Cielo
        fatti, saltati = [], []
        for gid in gids:
            ini = Path(dolphin) / "GameSettings" / f"{gid}.ini"
            if not ini.exists():
                continue
            accendi, spegni = [], []
            for cid, on in stati.items():
                c = db[cid]
                if on:
                    if gid in c["versioni"]:
                        accendi.append((c["nome_ini"], c["versioni"][gid]))
                    else:
                        saltati.append(f"{c['titolo']['en']} ({core.NOMI_VERSIONE[gid]})")
                else:
                    spegni.append((c["nome_ini"], c["livello"] in ("facile", "difficile", "divertimento", "miei", "ora")))
            core.backup_file(ini, "GameSettings")
            core.scrivi_codici_ini(ini, accendi, spegni)
            core.allinea_camera(ini, gid, self._cam_modi(), self._conf.get("cam_opzioni"))
            core.spegni_di_serie(dolphin, core.trova_exe_dolphin(self._conf, dolphin), gid)
            fatti.append(core.NOMI_VERSIONE[gid])
        return {"fatti": fatti, "saltati": saltati, "dolphin_aperto": bool(core.exe_dolphin_aperti())}

    # codici aggiunti dall'utente (salvati in config.json, scritti negli INI come gli altri)
    def _miei(self):
        return [{"id": c["id"], "livello": "miei", "titolo": {"en": c["nome"]}, "desc": {"en": ""}, "nome_ini": "$" + c["nome"],
                 "versioni": {g: c["righe"] for g in c["versioni"]}, "conflitti": [], "tasti": None, "righe_n": len(c["righe"])}
                for c in self._conf.get("codici_miei", [])]

    @protetto
    def codice_aggiungi(self, nome, testo, gids):
        import re
        nome = " ".join(nome.replace("$", "").split())
        righe = []
        for n, r in enumerate(testo.splitlines(), 1):
            r = r.strip()
            if not r:
                continue
            if r.startswith("$") and not nome:  # incollato col nome in testa, come negli INI
                nome = " ".join(r[1:].split())
                continue
            if re.fullmatch(r"[0-9A-Za-z]{4}-[0-9A-Za-z]{4}-[0-9A-Za-z]{5}", r):
                return {"errore": "criptato"}
            if not re.fullmatch(r"[0-9A-Fa-f]{8}\s+[0-9A-Fa-f]{8}", r):
                return {"errore": "riga", "n": n, "riga": r[:40]}
            righe.append(" ".join(r.upper().split()))
        if not righe:
            return {"errore": "vuoto"}
        if not nome:
            return {"errore": "nome"}
        if not gids:
            return {"errore": "vers"}
        usati = {c["nome_ini"].lower() for c in core.carica_codici_db() + self._miei()}
        dolphin = core.trova_dolphin(self._conf)
        for g in core.NOMI_VERSIONE:
            ini = Path(dolphin) / "GameSettings" / f"{g}.ini" if dolphin else None
            if ini and ini.exists():
                usati |= {x.lower() for x in core.leggi_codici_ini(ini)["presenti"]}
        if "$" + nome.lower() in usati:
            return {"errore": "usato"}
        import time
        cid = f"mio_{int(time.time() * 1000)}"
        self._conf.setdefault("codici_miei", []).append({"id": cid, "nome": nome, "righe": righe, "versioni": list(gids)})
        core.scrivi_config(self._conf)
        return {"id": cid, "nome": nome}

    @protetto
    def codice_elimina(self, cid):
        c = next((x for x in self._conf.get("codici_miei", []) if x["id"] == cid), None)
        if not c:
            return False
        dolphin = core.trova_dolphin(self._conf)
        for g in core.NOMI_VERSIONE:
            ini = Path(dolphin) / "GameSettings" / f"{g}.ini" if dolphin else None
            if ini and ini.exists() and "$" + c["nome"] in core.leggi_codici_ini(ini)["presenti"]:
                core.backup_file(ini, "GameSettings")
                core.scrivi_codici_ini(ini, [], [("$" + c["nome"], True)])
        self._conf["codici_miei"] = [x for x in self._conf["codici_miei"] if x["id"] != cid]
        core.scrivi_config(self._conf)
        return True

    # ------------------------------------------------------------ HUD e tasti
    @protetto
    def hud_stato(self):
        pack = core.trova_pack(self._conf)
        dolphin = core.trova_dolphin(self._conf)
        hud = core.catalogo_hud(pack) if pack else []
        tasti = core.catalogo_tasti(pack) if pack else []
        inst = core.installate_hud(dolphin, hud, tasti) if dolphin else {"hud": None, "tasti": None}
        disegni = core.catalogo_disegni()
        inst["disegno"] = None  # disegno del controller (Opzioni > Controller) che c'è adesso in Dolphin
        if dolphin and disegni:
            f = core.tex(core.cartelle_texture(dolphin)[0], core.TASTI_FILE[1])
            h = core.md5_file(f) if f else None
            d = next((x for x in disegni if h and core.md5_file(x["path"]) == h), None)
            inst["disegno"] = {"id": d["id"], "fam": d["fam"]} if d else None
        scelti = {fam: (core.disegno_per("PlayStation" if fam == "ps" else "XBOX", self._conf.get("disegno_controller", {})) or {}).get("id")
                  for fam in ("xbox", "ps")}
        return {"hud": hud, "tasti": tasti, "inst": inst, "disegni": disegni, "disegni_scelti": scelti}

    @protetto
    def disegno_anteprima(self, did, larg=900):
        """Miniatura (larg piccola) = il controller; grande = come apparirà nel gioco, con scritte e linee messe dall'app
        (linee_gioco.anteprima, scritte nella lingua dell'app)."""
        d = next((x for x in core.catalogo_disegni() if x["id"] == did), None)
        if not d:
            return None
        j = Path(d["path"]).with_suffix(".json")
        if larg < 600 or not j.is_file():
            return core.anteprima_png(d["path"], larg, fondo=(26, 34, 56, 255))
        import base64
        import linee_gioco as lg
        from PIL import Image
        lingua = self._conf.get("lingua") or core.lingua_sistema()
        f = core.CACHE / "img" / f"disegno_{did}_{lingua}_{int(j.stat().st_mtime)}_{int(Path(d['path']).stat().st_mtime)}_{larg}.jpg"
        if not f.exists():
            img, _ = lg.anteprima(Image.open(d["path"]), json.loads(j.read_text(encoding="utf-8")), lg.SCRITTE.get(lingua, lg.SCRITTE["en"]))
            img.thumbnail((larg, larg), Image.LANCZOS)
            f.parent.mkdir(parents=True, exist_ok=True)
            img.convert("RGB").save(f, quality=90)
        return "data:image/jpeg;base64," + base64.b64encode(f.read_bytes()).decode()

    @protetto
    def hud_anteprima(self, tipo, cartella, larg=900):
        pack = core.trova_pack(self._conf)
        if tipo == "hud":
            f = core._sorgente_hud(pack, cartella, core.HUD_FILE[0])
        else:
            f = core.tex(cartella, core.TASTI_FILE[0])
        return core.anteprima_png(f, larg) if f else None

    @protetto
    def hud_pezzi(self, cartella):
        """Le altre due texture della HUD (da dove arrivano: la HUD stessa o quella di base)."""
        pack = core.trova_pack(self._conf)
        out = []
        for n in core.HUD_FILE[1:]:
            f = core._sorgente_hud(pack, cartella, n)
            if f:
                out.append({"img": core.anteprima_png(f, 360), "base": core.HUD_BASE in str(f)})
        return out

    @protetto
    def hud_applica(self, scelte):
        dolphin = core.trova_dolphin(self._conf)
        pack = core.trova_pack(self._conf)
        if not dolphin:
            return {"errore": "dolphin"}
        ins = self._ins = core.Installazione(dolphin)  # la pagina ne segue l'avanzamento
        if scelte.get("hud"):
            ins.hud(pack, scelte["hud"])
        tasti = scelte.get("tasti")
        if scelte.get("disegno"):  # {famiglia: id}: si ricorda per famiglia e rimette i tasti col disegno nuovo
            self._conf.setdefault("disegno_controller", {}).update(scelte["disegno"])
            core.scrivi_config(self._conf)
            if not tasti and dolphin:
                inst = core.installate_hud(dolphin, [], core.catalogo_tasti(pack) if pack else []).get("tasti")
                tasti = inst["path"] if inst else None
        if tasti:
            ins.tasti(pack, tasti, self._conf.get("disegno_controller", {}))
            if scelte.get("tasti") and pack:  # ricordo la scelta per la sua famiglia: i tasti automatici rimettono questa
                lc = Path(pack) / "Layout Controller"
                voce = next((c for c in core.catalogo_tasti(pack) if Path(tasti) == lc / c["id"] or lc / c["id"] in Path(tasti).parents), None)
                if voce:
                    self._conf.setdefault("tasti_fam", {})[core.famiglia_tasti(voce["id"])] = voce["id"]
                    core.scrivi_config(self._conf)
        ris = ins.esegui()
        ris["dolphin_aperto"] = bool(core.exe_dolphin_aperti())
        return ris

    # ------------------------------------------------------------ grafica (impostazioni di Dolphin per il gioco)
    @protetto
    def grafica_stato(self):
        import psutil
        dolphin = core.trova_dolphin(self._conf)
        if not dolphin:
            return {"errore": "dolphin"}
        vers = [g for g in core.NOMI_VERSIONE if (Path(dolphin) / "GameSettings" / f"{g}.ini").exists()] or ["GK2E52"]
        tutti = {g: core.grafica_valori(dolphin, g) for g in vers}
        primo = tutti[vers[0]]
        if self._peso_tex is None:
            pack = core.trova_pack(self._conf)
            self._peso_tex = core.peso_texture(dolphin, core.file_protetti(pack) if pack else frozenset())
        # messaggi di Dolphin: è un'impostazione generale di Dolphin (Dolphin.ini [Interface]); l'app la passa a ogni avvio
        # schermo intero = scelta dell'app (come nel launcher), passata a Dolphin a ogni avvio
        # 30 fps = codice $60fps spento in tutte le versioni installate (è lo stesso interruttore della pagina Codici)
        fps30 = not any("$60fps" in core.leggi_codici_ini(Path(dolphin) / "GameSettings" / f"{g}.ini")["attivi"] for g in vers)
        # HUD 16:9: solo l'HUD di gioco (di base) o tutto (anche menu e mappa): riga del codice HUD (prima versione che ce l'ha)
        return {"valori": dict(primo, intero=bool(self._conf.get("gioca_intero", True)), bordi=bool(self._conf.get("schermo_senza_bordi", True)), osd=bool(self._conf.get("notifiche_dolphin", False)), fps30=fps30),
                "avanzata": self._conf.get("grafica_avanzata"),
                "mac": core.MAC_BASE | self._conf.get("grafica_mac", {}),
                "versioni": [core.NOMI_VERSIONE[g] for g in vers],
                "diverse": any(v != primo for v in tutti.values()),
                "proprie": (proprie := any(core.grafica_proprie(dolphin, g) for g in vers)),
                # "usa Dolphin" acceso solo se scelto dall'utente (e nel gioco non sono state riscritte impostazioni)
                "globali": bool(self._conf.get("grafica_globali")) and not proprie,
                "peso_tex": self._peso_tex[0], "peso_dds": self._peso_tex[1], "ram": psutil.virtual_memory().total,
                "comp": self._comp_info(dolphin),
                "android": core.ANDROID_BASE | self._conf.get("grafica_android", {}),
                "arm": __import__("platform").machine().upper() in ("ARM64", "AARCH64"),
                "cpu": core.processore(), "cpu_scelta": self._conf.get("grafica_cpu"), "oc_cpu": core.OC_CPU,
                "dolphin_aperto": bool(core.exe_dolphin_aperti())}

    @protetto
    def grafica_mac_salva(self, valori):
        """Impostazioni grafiche per lo zip Mac (non toccano questo PC)."""
        self._conf["grafica_mac"] = {k: v for k, v in valori.items() if k in core.MAC_BASE}
        core.scrivi_config(self._conf)
        return True

    # ------------------------------------------------------------ menu in gioco (LB + RB)
    TASTI_MENU = {0x0001: "su", 0x0002: "giu", 0x0004: "sx", 0x0008: "dx", 0x1000: "a", 0x2000: "b", 0x4000: "x", 0x8000: "y",
                  0x0100: "lb", 0x0200: "rb", 0x0010: "start", 0x0020: "select", 0x0040: "l3", 0x0080: "r3",
                  0x10000: "lt", 0x20000: "rt"}  # grilletti: bit finti (XInput li dà come valori 0-255)

    def _sorveglia_pad(self):
        """Legge il pad (XInput, + PlayStation/Switch Pro col joystick di Windows) mentre gioca Spider-Man 2: LB + RB apre/chiude il menu; col menu aperto i tasti lo
        comandano (su/giù/sx/dx anche con lo stick, tenuti premuti si ripetono)."""
        import ctypes
        import time

        class ST(ctypes.Structure):
            _fields_ = [("pkt", ctypes.c_uint32), ("b", ctypes.c_uint16), ("lt", ctypes.c_ubyte), ("rt", ctypes.c_ubyte),
                        ("lx", ctypes.c_short), ("ly", ctypes.c_short), ("rx", ctypes.c_short), ("ry", ctypes.c_short)]
        try:
            xi = ctypes.windll.xinput1_4
        except OSError:
            return
        prima, tenuto, gioco, quando, hud_quando, ripetuti, stick_vivo = 0, {}, None, 0.0, 0.0, {}, False
        sin_vivo, pad_log, errore_pad, xbox_visto = False, 0, False, False
        dorsali = {}  # LB/RB premuti col menu aperto: valgono al RILASCIO, se intanto non è arrivato anche l'altro (LB+RB)
        import app_controller
        ps = self._pad_ps = app_controller.PadWinmm()  # pad PlayStation / Switch Pro (non sono XInput): stessi tasti del pad Xbox
        hidpad = self._pad_hid = app_controller.PadHid()  # tutti gli altri gamepad (Stadia, generici), letti come dispositivi HID
        while True:
            try:
                ora = time.time()
                if ora - quando > 1:  # il gioco c'è? (controllo leggero, una volta al secondo)
                    quando = ora
                    gioco = core.finestra_gioco() if core.exe_dolphin_aperti() else None
                    if os.environ.get("SPIDEY_MENU_PROVA"):  # per provare il menu senza il gioco
                        gioco = gioco or self._finestra and ctypes.windll.user32.FindWindowW(None, TITOLO)
                    if not gioco and self._menu_aperto and self._menu_lock.acquire(blocking=False):
                        try:  # gioco chiuso col menu aperto (sotto il lucchetto: non deve accavallarsi con un'apertura)
                            self._menu_chiudi(normale=False)
                        finally:
                            self._menu_lock.release()
                if not gioco:
                    prima = 0
                    self._menu_preparato = False  # al prossimo avvio del gioco lo ripreparo (dati aggiornati)
                    time.sleep(0.5)
                    continue
                if not getattr(self, "_menu_preparato", False):  # gioco appena comparso: preparo il menu (nascosto)
                    self._menu_preparato = True
                    threading.Thread(target=self._menu_prepara, daemon=True).start()
                    pad_log = ora + 4  # tra poco scrivo nel menu.log quali pad vedo (PS5 dall'amico: menu che non si apriva)
                if pad_log and ora >= pad_log:
                    pad_log = 0
                    try:
                        vis = [f"{p['tipo']}:{p['nome']}" + (f" {p['vid']}:{p['pid']}" if p.get("vid") else "") for p in app_controller.pad_collegati()]
                        self._log_menu(f"pad visti: {', '.join(vis) or 'nessuno'} | letti: xinput={int(xbox_visto)} "
                                       f"winmm={[d['nome'] for d in ps.dispositivi]} hid={[d['nome'] for d in hidpad.dispositivi]}")
                    except Exception as e:  # noqa: BLE001
                        self._log_menu(f"pad visti: errore {e!r}")
                b, xbox_visto, destro, sinistro = 0, False, (0.0, 0.0), (0.0, 0.0)
                for i in range(4):
                    st = ST()
                    if xi.XInputGetState(i, ctypes.byref(st)) == 0:
                        xbox_visto = True
                        b |= st.b
                        if abs(st.rx) + abs(st.ry) > 1000:
                            destro = (st.rx / 32768, -st.ry / 32768)  # su = negativo, come gli altri pad
                        if abs(st.lx) + abs(st.ly) > 1000:
                            sinistro = (st.lx / 32768, -st.ly / 32768)
                        b |= (0x0001 if st.ly > 20000 else 0) | (0x0002 if st.ly < -20000 else 0) | \
                             (0x0004 if st.lx < -20000 else 0) | (0x0008 if st.lx > 20000 else 0) | \
                             (0x10000 if st.lt > 140 else 0) | (0x20000 if st.rt > 140 else 0)
                try:
                    b |= ps.bottoni(con_xbox=xbox_visto) | hidpad.bottoni(con_xbox=xbox_visto)
                    for d in (ps.destro, hidpad.destro):
                        if abs(d[0]) + abs(d[1]) > abs(destro[0]) + abs(destro[1]):
                            destro = d
                    for d in (ps.sinistro, hidpad.sinistro):
                        if abs(d[0]) + abs(d[1]) > abs(sinistro[0]) + abs(sinistro[1]):
                            sinistro = d
                except Exception as e:  # noqa: BLE001 - un pad strano non deve fermare gli altri (ma lo scrivo, una volta)
                    if not errore_pad:
                        errore_pad = True
                        self._log_menu(f"pad PlayStation/HID: errore {e!r}")
                self._pad_bits, self._pad_quando = b, ora  # per _aspetta_rilascio (un solo lettore dei pad: questo filo)
                self._pad_levette = (sinistro, destro)  # per la vista 3D della città (la legge il suo filo)
                combo = 0x0100 | 0x0200
                if not self._menu_aperto and not b & combo and ora - hud_quando > 0.2:  # HUD com'è adesso (LB non premuto)
                    hud_quando = ora
                    self._hud_snap = self._hud_leggi()
                if b & combo == combo and prima & combo != combo:
                    dorsali.clear()  # era LB+RB: il primo dorsale arrivato da solo non deve cambiare sezione
                    if not self._menu_lock.locked():  # sta già aprendo o chiudendo: la pressione in più non conta
                        threading.Thread(target=self._menu_cambia, args=(gioco,), daemon=True).start()
                elif self._menu_aperto and b & combo != combo:
                    for bit, nome in self.TASTI_MENU.items():
                        if bit in (0x0100, 0x0200):  # (John, chiudendo con LB+RB il menu saltava un attimo su un'altra
                            if b & bit and not prima & bit:  # sezione: i due dorsali quasi mai arrivano nella stessa lettura)
                                dorsali[bit] = True
                            elif not b & bit and prima & bit and dorsali.pop(bit, False):
                                self._menu_js(f"menuTasto('{nome}')")
                            continue
                        if b & bit and not prima & bit:
                            tenuto[bit], ripetuti[bit] = ora + 0.38, 0
                            self._menu_js(f"menuTasto('{nome}')")
                        elif b & bit and bit in (1, 2, 4, 8) and ora >= tenuto.get(bit, 9e9):
                            # tenendo premuto si va sempre più veloci (per scorrere lunghe liste di skin)
                            ripetuti[bit] = ripetuti.get(bit, 0) + 1
                            tenuto[bit] = ora + (0.11 if ripetuti[bit] < 5 else 0.06 if ripetuti[bit] < 14 else 0.035)
                            self._menu_js(f"menuTasto('{nome}', {ripetuti[bit]})")
                    # stick destro: gira (x) e avvicina/allontana (y) lo Spidey 3D, come col mouse
                    vivo = abs(destro[0]) > 0.22 or abs(destro[1]) > 0.22
                    if vivo or stick_vivo:
                        dx = destro[0] if abs(destro[0]) > 0.22 else 0.0
                        dy = destro[1] if abs(destro[1]) > 0.22 else 0.0
                        self._menu_js(f"menuStick({dx:.3f}, {dy:.3f})")
                    stick_vivo = vivo
                    # stick sinistro analogico (la mappa della città lo usa per muoversi fluida; le frecce restano per il resto)
                    vivo = abs(sinistro[0]) > 0.25 or abs(sinistro[1]) > 0.25
                    if vivo or sin_vivo:
                        dx = sinistro[0] if abs(sinistro[0]) > 0.25 else 0.0
                        dy = sinistro[1] if abs(sinistro[1]) > 0.25 else 0.0
                        self._menu_js(f"menuStickL({dx:.3f}, {dy:.3f})")
                    sin_vivo = vivo
                prima = b
                time.sleep(0.03)
            except Exception:  # noqa: BLE001 - il filo non deve fermarsi (ma l'errore si scrive: LB+RB morto senza traccia)
                if time.time() - getattr(self, "_pad_errore_t", 0) > 60:
                    self._pad_errore_t = time.time()
                    core.log_errore("filo del pad: " + traceback.format_exc())
                time.sleep(1)

    def _correggi_texture(self):
        """Le correzioni di core.CORREZIONI_TEXTURE anche nelle librerie e nei Dolphin già installati (una volta per elenco)."""
        try:
            firma = ",".join(core.CORREZIONI_TEXTURE)
            if self._conf.get("correzioni_tex") == firma:
                return
            n = core.correggi_texture(core.trova_pack(self._conf), core.trova_dolphin(self._conf))
            if n:
                core.log_errore(f"correzioni alle texture messe: {n} file")
            self._conf["correzioni_tex"] = firma
            core.scrivi_config(self._conf)
        except Exception as e:  # noqa: BLE001
            core.log_errore(f"correggi texture: {e!r}")

    def _aggiorna_disegno(self):
        try:
            d = core.aggiorna_disegno_vecchio(core.trova_dolphin(self._conf))
            if d:
                core.log_errore(f"disegno del controller aggiornato alla versione nuova: {d}")
        except Exception as e:  # noqa: BLE001
            core.log_errore(f"aggiorna disegno: {e!r}")

    def _dati_disegno(self, cache):
        """Il disegno del controller installato in Dolphin e i suoi dati per le linee (contenuti/Controller/disegni/
        <id>.json, fatti da crea_disegni_controller.py). (id, dati); (None, None) = non è uno dei nostri (es. il 360 di
        RE): linee come l'originale del gioco. L'MD5 si ricalcola solo se il file cambia."""
        dolphin = core.trova_dolphin(self._conf)
        f = core.tex(core.cartelle_texture(dolphin)[0], core.TASTI_FILE[1]) if dolphin else None
        if not f:  # per un attimo non c'è (si sta installando un disegno): tengo quello di prima
            return cache.get("id"), cache.get("dati")
        st = f.stat()
        firma = (str(f), st.st_mtime, st.st_size)
        if cache.get("firma") == firma:
            return cache["id"], cache["dati"]
        disegni = core.catalogo_disegni()
        firma_cat = tuple((d["id"], Path(d["path"]).stat().st_mtime) for d in disegni)
        if cache.get("firma_cat") != firma_cat:  # disegni cambiati (es. aggiornati): MD5 da rifare
            cache["md5"], cache["firma_cat"] = {d["id"]: core.md5_file(d["path"]) for d in disegni}, firma_cat
        h = core.md5_file(f)
        d = next((x for x in disegni if cache["md5"].get(x["id"]) == h), None)
        dati = None
        if d:
            try:
                dati = json.loads(Path(d["path"]).with_suffix(".json").read_text(encoding="utf-8"))
            except (OSError, ValueError):
                dati = None
        cache.update(firma=firma, id=d["id"] if d and dati else None, dati=dati)
        return cache["id"], cache["dati"]

    def _sorveglia_linee(self):
        """Col menu di pausa aperto: le linee gialle e le scritte di Opzioni > Controller vanno ai tasti del disegno del
        controller installato (linee_gioco.py: le cerca nella memoria per posizione e le sposta). Leggero: ogni 0,7 s;
        quando è già tutto a posto controlla solo che le linee siano ancora lì."""
        import time
        import linee_gioco as lg
        ap = lg.Applicatore(core.CONF_DIR / "linee_gioco.json")
        cache, attesa, fatte = {}, 0.0, {}
        while True:
            time.sleep(0.7)
            try:
                gid = core.gioco_in_corso()
                if not gid or gid == "?":
                    ap.pezzi, ap.chiave, attesa = None, None, 0.0
                    continue
                if time.time() < attesa or self._in_partita(gid) != 0:  # in partita: il pannello delle opzioni non c'è
                    continue
                did, dati = self._dati_disegno(cache)
                chiave = did or "originale"
                with self._dme_lock:  # trovare linee e scritte: veloce (la memoria serve anche al menu e al pad)
                    dme = core.aggancia_dme()
                    trovate = bool(dme) and ap.trova(dme)
                    larg = ap.larghezze(dme) if trovate and ap.chiave != chiave else None
                if not trovate:
                    attesa = time.time() + 3  # schermata non trovata (es. titolo): riprovo tra un po'
                    continue
                if ap.chiave == chiave:
                    continue
                # la disposizione (qualche secondo di calcolo) fuori dal blocco, e ricordata per la prossima volta
                k = f"{chiave}|{sorted((n, round(v)) for n, v in larg.items())}|{sorted(ap.righe_testo.items())}|{cache.get('firma')}"
                if k not in fatte:
                    fatte[k] = lg.disposizione(dati["tasti"], larg, {int(a): b for a, b in dati.get("sagoma", {}).items()},
                                               dict(ap.righe_testo)) if dati else lg.disposizione_originale()
                with self._dme_lock:
                    dme = core.aggancia_dme()
                    if dme and ap.trova(dme):
                        ap.scrivi(dme, chiave, fatte[k])
            except Exception as e:  # noqa: BLE001 - il filo non deve fermarsi
                core.log_errore(f"linee del controller: {e!r}")
                time.sleep(5)

    def _menu_js(self, codice):
        try:
            if self._menu:
                self._menu.evaluate_js(codice)
        except Exception:  # noqa: BLE001
            pass

    def _menu_finestra(self):
        """La finestra del menu, creata una volta sola, e la sua pagina pronta (anche se la sta creando un altro filo: LB + RB
        mentre _menu_prepara aspetta la pagina mostrava un menu vuoto, e a volte nascevano due finestre)."""
        import time  # ?v= cambia a ogni avvio: WebView2 teneva una copia vecchia di menu.html (pagina nuova, script vecchio)
        with self._menu_fin_lock:
            if self._menu is None:
                self._menu_pronto = False
                self._menu = webview.create_window(TITOLO_MENU, url=str(risorsa("app_web") / "menu.html") + f"?v={int(time.time())}", js_api=self,
                                                   width=1040, height=640, x=-20000, y=-20000,  # fuori schermo: creandola pywebview la mostra per un attimo (lampo sul gioco)
                                                   frameless=True, on_top=True, hidden=True, resizable=False,
                                                   background_color="#0b0e16", focus=True, easy_drag=False)
        for _ in range(160):  # la pagina deve essere pronta prima di mostrarla
            if self._menu_pronto:
                break
            time.sleep(0.05)
        return self._menu

    def _fuoco_al_gioco(self):
        """Ridà il fuoco al gioco se ce l'ha una finestra NOSTRA (app, menu nascosto, avviso) o nessuna: Dolphin dà i tasti
        del pad solo alla finestra attiva, e creare la finestra del menu (o l'avviso) a volte gliela toglieva -> John doveva
        cliccare col mouse prima di premere Start. Se sei passato a un altro programma, non lo tocco."""
        import ctypes
        from ctypes import wintypes
        if self._menu_aperto:
            return
        h = core.finestra_gioco()
        if not h:
            return
        u = ctypes.windll.user32
        fg = u.GetForegroundWindow()
        if fg == h:
            return
        pid = wintypes.DWORD(0)
        if fg:
            u.GetWindowThreadProcessId(fg, ctypes.byref(pid))
        if not fg or pid.value == os.getpid():
            core._davanti(h)

    def _menu_prepara(self):
        """Appena compare il gioco: crea la finestra del menu (nascosta) e ci disegna dentro le skin, così il primo LB + RB
        la mostra subito (prima: finestra, pagina e modello 3D si caricavano solo lì, qualche secondo). Poi, in sottofondo,
        prepara le texture delle anteprime 3D che mancano nella cache (la prima volta ogni costume andava convertito)."""
        import time
        try:
            time.sleep(3)  # lascio partire il gioco
            if self._menu_aperto or self._menu_lock.locked():
                return
            self._menu_finestra()
            self._menu_js("menuPrepara()")
            time.sleep(0.5)
            self._fuoco_al_gioco()  # creare la finestra del menu poteva rubare il fuoco al gioco
            voci, _ = self._catalogo()
            for v in voci:
                if self._menu_aperto:
                    time.sleep(2)
                try:
                    core.immagine64(str(core.tex(v["default"], core.CORPO)), 1024, 512)
                except Exception:  # noqa: BLE001
                    pass
                time.sleep(0.05)
        except Exception as e:  # noqa: BLE001
            core.log_errore(f"menu: preparazione non riuscita: {e!r}")

    def _mini_menu(self, k):
        """Miniatura per il menu in gioco: WebP piccolo dalla miniatura PNG dell'app (30 KB -> ~6 KB: 73 skin erano 2,7 MB
        da passare alla pagina a ogni apertura). Cache in cache/mini_menu, rifatta se il PNG è più nuovo."""
        for kk in (k + "_idle3", k + "_b3", k + "_idle2", k):
            f = core.CACHE / "mini" / f"{kk}.png"
            if f.exists():
                w = core.CACHE / "mini_menu" / f"{kk}.webp"
                try:
                    if not w.exists() or w.stat().st_mtime < f.stat().st_mtime:
                        from PIL import Image
                        w.parent.mkdir(parents=True, exist_ok=True)
                        Image.open(f).save(w, "WEBP", quality=82, method=4)
                    return "data:image/webp;base64," + __import__("base64").b64encode(w.read_bytes()).decode()
                except Exception:  # noqa: BLE001
                    return "data:image/png;base64," + __import__("base64").b64encode(f.read_bytes()).decode()
        return None

    @protetto
    def menu_pronto(self):
        self._menu_pronto = True
        return True

    def menu_mostrami(self):
        """La pagina ha finito di ridisegnarsi per l'apertura (menuApri): adesso il menu si può mostrare (prima si vedeva un
        attimo com'era alla chiusura precedente: altra sezione, forma a barra)."""
        ev = getattr(self, "_menu_disegnato", None)
        if ev:
            ev.set()
        return True

    def _hud_db(self, gid):
        """Righe del codice HUD acceso nella versione (None se spento / niente memoria)."""
        dolphin = core.trova_dolphin(self._conf)
        db = next((c for c in core.carica_codici_db() if c["id"] == "hud"), None)
        if not dolphin or not db or not gid or db["nome_ini"] not in core.leggi_codici_ini(Path(dolphin) / "GameSettings" / f"{gid}.ini")["attivi"]:
            return None
        return db["versioni"].get(gid)

    def _hud_leggi(self):
        """Byte di stato dell'HUD (817F0014, dispari = nascosto), solo se la memoria è già agganciata (leggero)."""
        try:
            import dolphin_memory_engine as dme
            with self._dme_lock:
                return dme.read_byte(0x817F0014) if core.aggancia_dme() else None
        except Exception:  # noqa: BLE001
            return None

    def _hud_correggi(self, gid):
        """Se premendo LB + RB l'HUD è scattato (LB tenuto un attimo prima di RB), lo rimetto com'era prima di LB."""
        try:
            snap = self._hud_snap
            righe = self._hud_db(gid) if snap is not None else None
            if not righe:
                return
            import dolphin_memory_engine as dme
            with self._dme_lock:
                if not core.aggancia_dme():
                    return
                ora = dme.read_byte(0x817F0014)
                if (ora ^ snap) & 1 == 0:
                    return
                dme.write_byte(0x817F0014, snap)
                if not snap & 1:  # torna visibile: il codice non lo riscrive, rimetto io i due byte dell'HUD (ultime 2 righe)
                    for r in righe[-2:]:
                        dme.write_byte(0x80000000 | (int(r.split()[0], 16) & 0x01FFFFFF), 0)
            self._log_menu(f"hud rimesso com'era ({snap & 1})")
        except Exception:  # noqa: BLE001 - è solo un ritocco
            pass

    def _log_menu(self, testo):
        """menu.log in AppData: cosa è successo col menu (per capire eventuali problemi segnalati)."""
        try:
            import time
            f = core.CONF_DIR / "menu.log"
            righe = f.read_text(encoding="utf-8").splitlines()[-300:] if f.exists() else []
            righe.append(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {testo}")
            f.write_text(chr(10).join(righe) + chr(10), encoding="utf-8")
        except OSError:
            pass

    # modo dell'interfaccia del gioco: 1 = in partita (anche riflessi e dopo un tuffo), 2 = menu di pausa, 0 = titolo e
    # caricamenti (il vecchio byte "in partita" restava a 0 dopo un tuffo). UK/DE/FR = USA. Vedi core.RIGHE_PARTITA.
    IN_PARTITA = {"GK2E52": 0x804DCE2A, "GK2P52": 0x804DCE2A, "GK2D52": 0x804DCE2A, "GK2F52": 0x804DCE2A, "GK2I52": 0x804DCEAA}

    def _in_partita(self, gid):
        """1 = in partita, 0 = in un menu del gioco, None = non lo so (memoria non agganciata). Sopra l'acqua il modo salta
        per un attimo a 0/2: se non legge 1 riprova un paio di volte."""
        try:
            import time
            import dolphin_memory_engine as dme
            with self._dme_lock:
                if not core.aggancia_dme() or gid not in self.IN_PARTITA:
                    return None
                for _ in range(3):
                    if dme.read_byte(self.IN_PARTITA[gid]) == 1:
                        return 1
                    time.sleep(0.006)
                return 0
        except Exception:  # noqa: BLE001
            return None

    def _menu_cambia(self, gioco):
        """LB + RB: apre o chiude. Uno alla volta: mentre apre/chiude le altre pressioni non contano."""
        if not self._menu_lock.acquire(blocking=False):
            return
        try:
            if self._menu_aperto:
                self._menu_chiudi()
            else:
                self._menu_apri(gioco)
        finally:
            self._menu_lock.release()

    def _aspetta_rilascio(self, max_s=1.5):
        """Aspetta che i tasti del pad (B, LB, RB, A...) siano lasciati: tornando al gioco con un tasto giù, il gioco lo vedrebbe.
        Vale per tutti i pad: Xbox (XInput), PlayStation/Switch (joystick di Windows), Stadia e generici (HID)."""
        import ctypes
        import time
        try:
            xi = ctypes.windll.xinput1_4
        except OSError:
            return
        buf = (ctypes.c_ubyte * 16)()
        fine = time.time() + max_s
        while time.time() < fine:
            giu = 0
            for i in range(4):
                if xi.XInputGetState(i, buf) == 0:
                    giu |= buf[4] | buf[5] << 8
            if time.time() - getattr(self, "_pad_quando", 0) < 0.2:  # pad non Xbox: i tasti letti dal filo del pad
                giu |= getattr(self, "_pad_bits", 0)
            if not giu & 0xFFF0:  # tutti i tasti (non la croce: lì finiscono anche gli stick dei pad non Xbox)
                return
            time.sleep(0.03)

    def _menu_apri(self, gioco):
        if self._menu_aperto or self._riavvio_lock.locked():  # durante un riavvio il menu non si riapre
            return
        try:
            self._menu_apri_davvero(gioco)
        except Exception as e:  # noqa: BLE001 - finestra non creata/mostrata: il menu resta chiuso (se no LB+RB va a vuoto)
            self._menu_aperto = False
            self._log_menu(f"apertura non riuscita: {e!r}")
            core.log_errore(f"menu: apertura non riuscita: {e!r}")

    def _menu_apri_davvero(self, gioco):
        self._menu_aperto = True
        gid = core.gioco_in_corso()
        self._menu_gioco = gioco
        # niente pausa: quella di Dolphin (F10) in dual core blocca Spider-Man 2, quella del gioco (Start) con RB tenuto
        # (= Z) apriva la mappa. Il gioco continua sotto al menu; col menu davanti Dolphin non riceve i tasti del pad.
        self._menu_modo = None  # si riapre sempre con la forma normale (la pagina decide poi se serve la barra)
        self._log_menu(f"aperto {gid}")
        self._cam_cerca_presto(gid)
        if gid and gid != "?":
            self._hud_correggi(gid)
        m = self._menu_finestra()
        try:  # mappa del gioco aperta: il menu si apre direttamente su Mondo > Viaggio (il punto è quello del mirino)
            gid = core.gioco_in_corso()
            if gid and gid != "?" and core.Viaggio(gid).centro_mappa() is not None:
                self._menu_js("window.apriViaggio = true")
        except Exception:  # noqa: BLE001
            pass
        import ctypes
        import time
        u = ctypes.windll.user32
        self._menu_disegnato = threading.Event()
        self._menu_js("menuApri(true)")
        w = u.FindWindowW(None, TITOLO_MENU)  # (trova anche la finestra nascosta)
        if w:  # misura e posto giusti PRIMA di mostrarla (prima per un attimo aveva la forma di prima, es. la barra)
            self._menu_posiziona(w, gioco, mostra=False)
        self._menu_disegnato.wait(0.6)  # e la pagina già ridisegnata (se non risponde la mostro lo stesso)
        m.show()
        for _ in range(40):
            w = u.FindWindowW(None, TITOLO_MENU)
            if w:
                break
            time.sleep(0.05)
        if w:
            self._menu_posiziona(w, gioco)
            core._davanti(w)
            threading.Thread(target=self._menu_segui, args=(w,), daemon=True).start()

    def _menu_rett(self, gioco):
        """Dove va il menu: dentro la finestra del gioco (parte disegnata), centrato, sempre nelle stesse proporzioni,
        così sembra un pezzo del gioco. Gioco piccolo = menu che ne occupa di più (resta leggibile). Pixel veri."""
        import ctypes
        from ctypes import wintypes
        u = ctypes.windll.user32
        r = wintypes.RECT()
        u.GetClientRect(gioco, ctypes.byref(r))
        pt = wintypes.POINT(0, 0)
        u.ClientToScreen(gioco, ctypes.byref(pt))
        cw, ch = r.right - r.left, r.bottom - r.top
        if cw < 200 or ch < 150:  # ridotto a icona o non ancora pronto: centro del monitor
            mon, _ = core._monitor(gioco)
            pt.x, pt.y, cw, ch = mon.left, mon.top, mon.right - mon.left, mon.bottom - mon.top
        modo = getattr(self, "_menu_modo", None)
        if modo == "copri":  # velo dei passaggi (mappa 3D, viaggio): tutta la parte disegnata del gioco
            return pt.x, pt.y, cw, ch
        if modo == "barra":  # regolazione camera stile TV: una barra in basso, il gioco si vede tutto
            w = cw * 0.74
            h = w * 150 / 1040
            return pt.x + (cw - int(w)) // 2, pt.y + ch - int(h) - int(ch * 0.04), int(w), int(h)
        quota = min(0.94, 0.70 + max(0, 1600 - cw) / 1600 * 0.5)
        A = 1040 / 640
        w = cw * quota
        h = w / A
        if h > ch * 0.92:
            h = ch * 0.92
            w = h * A
        w, h = int(w), int(h)
        return pt.x + (cw - w) // 2, pt.y + (ch - h) // 2, w, h

    def _menu_posiziona(self, w, gioco, mostra=True):
        import ctypes
        from ctypes import wintypes
        u = ctypes.windll.user32
        u.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))  # pixel veri anche con lo zoom di Windows
        u.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint]
        x, y, larg, alt = self._menu_rett(gioco)
        u.SetWindowPos(w, wintypes.HWND(-1), x, y, larg, alt, 0x0010 | (0x0040 if mostra else 0))  # sopra a tutto, senza rubare il fuoco
        u.SetWindowPos(gioco, w, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010)  # il gioco subito sotto al menu
        return (x, y, larg, alt)

    def _menu_segui(self, w):
        """Col menu aperto: se la finestra del gioco si sposta, cambia misura o va/esce dallo schermo intero (Alt+Invio),
        il menu la segue; e resta sopra di lei."""
        import ctypes
        import time
        u = ctypes.windll.user32
        u.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))
        ultimo, giro, via = None, 0, False
        while self._menu_aperto:
            time.sleep(0.15)
            g = core.finestra_gioco() or self._menu_gioco
            if not g or not self._menu_aperto:
                continue
            giro += 1
            try:
                r = core._rett(g)
                if u.IsIconic(g) or r.left <= -30000:  # gioco ridotto a icona: il menu sparisce con lui
                    if not via:
                        via = True
                        u.ShowWindow(w, 0)
                    continue
                if via:  # gioco riaperto: il menu torna sopra di lui, con la sua misura
                    via, ultimo = False, None
                    self._menu_posiziona(w, g)
                    u.ShowWindow(w, 4)  # SW_SHOWNOACTIVATE
                if giro % 2 == 0 and self._menu_domande(w):  # Esc -> "Vuoi interrompere?" di Dolphin: va sopra al menu
                    continue
                r = self._menu_rett(g)
                if r != ultimo or giro % 6 == 0:  # misura cambiata, o comunque ogni ~1 s ricontrollo chi sta sopra
                    ultimo = self._menu_posiziona(w, g)
                    if getattr(self, "_m3", None):  # mappa 3D: mirino e segnalini di nuovo sopra (il gioco, rimesso
                        self._m3_alza()  # subito sotto al menu, li copriva fino al giro dopo = il mirino lampeggiava)
            except Exception:  # noqa: BLE001
                pass

    def _menu_domande(self, w):
        """Finestrelle di Dolphin aperte col menu (la conferma di Esc, impostazioni...): le metto SOPRA al menu e davanti,
        se no restano sotto e non si possono cliccare. True = ce n'è almeno una (intanto il menu non si rialza)."""
        import ctypes
        from ctypes import wintypes
        u = ctypes.windll.user32
        u.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint]
        domande = [h for h, t in core.finestre_dolphin() if t.strip() and " | " not in t and not t.strip().startswith("Dolphin")]
        viste = getattr(self, "_domande_viste", set())
        for h in domande:
            prima = u.GetWindow(h, 3)  # GW_HWNDPREV: se sopra c'è qualcosa (il menu), la rialzo
            if prima or u.GetForegroundWindow() != h:
                u.SetWindowPos(h, wintypes.HWND(-1), 0, 0, 0, 0, 0x0001 | 0x0002)
                if h not in viste:  # davanti una volta sola: con due finestrelle se lo rubavano a turno (Alt finti a raffica)
                    core._davanti(h)
        self._domande_viste = set(domande)
        return bool(domande)

    def _menu_chiudi(self, normale=True):
        """normale = chiuso da te (B, LB+RB): aspetta che lasci i tasti e controlla poi che il gioco riparta bene;
        False = il gioco non c'è più."""
        if not self._menu_aperto:
            return
        import ctypes
        import time
        gioco = core.finestra_gioco() or self._menu_gioco
        gid = core.gioco_in_corso()
        if getattr(self, "_cam_ant", None):  # anteprima della camera del gioco ancora attiva: rimetto la camera di prima
            self.menu_cam_anteprima(False)
        # Il gioco non è in pausa: finché il menu è davanti Dolphin ignora il pad. Aspetto che B (o LB+RB...) sia
        # lasciato PRIMA di ridare il primo piano al gioco, se no a Spidey arriva anche quel tasto (B = animazione).
        if normale and gid and gid != "?":
            self._aspetta_rilascio()
        if gioco:  # il menu (davanti) passa il primo piano al gioco PRIMA di sparire: se no Dolphin ignora il pad
            ctypes.windll.user32.SetForegroundWindow(gioco)
        self._menu_nascondi()
        if normale and gid and gid != "?" and not os.environ.get("SPIDEY_MENU_PROVA"):
            self._log_menu(f"chiuso {gid}")
            threading.Thread(target=self._dopo_chiusura, args=(gid,), daemon=True).start()

    def _menu_nascondi(self):
        """Nasconde il menu (chiusura, carica stato, esci, riavvio) e ferma i timer della pagina (musica, camera, Spidey
        che gira: lavoravano anche a menu nascosto, rubando CPU a Dolphin)."""
        self._menu_aperto = False
        self._menu_js("menuChiuso()")
        try:
            self._menu.hide()
        except Exception:  # noqa: BLE001
            pass

    def _dopo_chiusura(self, gid):
        """Dopo aver chiuso il menu, per qualche secondo: il gioco ha il primo piano (senza, Dolphin ignora il pad e
        sembra bloccato)? l'immagine si muove? Dolphin risponde? Scritto nel menu.log, e se il gioco ha perso il primo
        piano glielo ridò."""
        import base64
        import ctypes
        import io
        import time
        from PIL import Image, ImageChops, ImageStat
        u = ctypes.windll.user32
        prima, righe = None, []
        for n in range(4):
            time.sleep(1.0)
            if self._menu_aperto:
                return
            g = core.finestra_gioco()
            if not g:
                return
            fg = u.GetForegroundWindow()
            buf = ctypes.create_unicode_buffer(200)
            u.GetWindowTextW(fg, buf, 200)
            chi = "gioco" if fg == g else (buf.value or "?")[:40]
            foto = core.foto_finestra(g, 160)
            im = Image.open(io.BytesIO(base64.b64decode(foto))).convert("L") if foto else None
            moto = None
            if im is not None and prima is not None and im.size == prima.size:
                moto = round(ImageStat.Stat(ImageChops.difference(im, prima)).mean[0], 2)
            prima = im
            righe.append(f"{chi}/{'appeso' if u.IsHungAppWindow(g) else 'ok'}/{moto}")
            pid, pid_g = ctypes.c_ulong(), ctypes.c_ulong()
            u.GetWindowThreadProcessId(fg, ctypes.byref(pid))
            u.GetWindowThreadProcessId(g, ctypes.byref(pid_g))
            domanda = pid.value == pid_g.value and buf.value and " | " not in buf.value and not buf.value.startswith("Dolphin")
            if fg != g and n >= 1 and not domanda and (not fg or pid.value in (os.getpid(), pid_g.value)):  # (una finestrella
                # di Dolphin, es. "Vuoi fermare?" dopo Esc, si tiene il primo piano: se no Invio/Esc non le arrivano)
                core._davanti(g)  # primo piano rimasto a noi o a Dolphin: senza, il pad non arriverebbe al gioco
        self._log_menu(f"dopo la chiusura (primo piano/risponde/movimento immagine): {' '.join(righe)}")

    @protetto
    def menu_chiudi(self):
        def via():
            if self._menu_lock.acquire(timeout=8):
                try:
                    self._menu_chiudi()
                finally:
                    self._menu_lock.release()
        threading.Thread(target=via, daemon=True).start()
        return True

    @protetto
    def menu_compatto(self, modo):
        """Forma del menu: None = normale, "barra" = barra in basso (camera regolata stile TV, col gioco tutto visibile),
        "copri" = sopra tutto il gioco (velo dei passaggi: _copri)."""
        modo = modo if modo in ("barra", "copri") else None
        if getattr(self, "_menu_modo", None) == modo:
            return True
        self._menu_modo = modo
        import ctypes
        w, g = ctypes.windll.user32.FindWindowW(None, TITOLO_MENU), core.finestra_gioco() or self._menu_gioco
        if w and g and self._menu_aperto:
            self._menu_posiziona(w, g)
        return True

    def _copri(self, stato, testo=None, sub=None, args=None, gioco=False, img=None, ok=False, fermo=False, poi=None):
        """Velo sopra TUTTO il gioco nei passaggi (John: "si vede la mappa normale prima di quella 3D", "si vede che si
        teletrasporta e poi carica tutto"): "su" = la foto del gioco di adesso che si sfoca (il menu diventa grande come
        il gioco), "cambia" = un'altra foto sfocata in dissolvenza, "giu" = la foto del gioco di adesso che torna a fuoco,
        poi poi = None (menu normale), "barra" o "chiudi". testo/sub = chiavi dei testi (args per {0}); gioco = la foto
        è quella del gioco adesso (PrintWindow: anche col menu sopra)."""
        import time
        if gioco:
            try:
                g = core.finestra_gioco()
                img = core.foto_finestra(g, 1280) if g else None
            except Exception:  # noqa: BLE001
                img = None
        o = {"stato": stato, "img": img, "ok": ok, "fermo": fermo}
        if os.environ.get("SPIDEY_LOG_COPRI"):
            self._log_menu(f"copri {stato} img={bool(img)} t={time.perf_counter():.2f}")
        for k, v in (("testo", testo), ("sub", sub)):
            if v is not None:
                o[k] = v
        if args:
            o["args"] = list(args)
        if stato == "su":
            self._menu_js(f"copri({json.dumps(o)})")
            self.menu_compatto("copri")
            return
        self._menu_js(f"copri({json.dumps(o)})")
        if stato != "giu":
            return
        time.sleep(0.42)  # di nuovo a fuoco
        if poi == "chiudi":
            if self._menu_lock.acquire(timeout=8):
                try:
                    self._menu_chiudi()
                finally:
                    self._menu_lock.release()
            return
        self.menu_compatto(poi)
        self._menu_js("copri({stato: 'via'})" + ("; m3Stato('pronta')" if poi == "barra" else ""))

    @protetto
    def menu_schermo_intero(self):
        """Alt+Invio col menu aperto: lo giro al gioco (schermo intero <-> finestra); il menu si risistema da solo."""
        def via():
            import time
            self._aspetta_rilascio()  # Alt+Invio porta davanti il gioco: con A ancora premuto Spidey salterebbe
            core.schermo_intero_al_volo()
            time.sleep(0.5)
            self._menu_sopra()
        threading.Thread(target=via, daemon=True).start()
        return True

    def _regia_file(self):
        """SOLO PER LE RIPRESE DEL VIDEO E LE PROVE (variabile d'ambiente SPIDEY_REGIA_FILE = file di comandi): ogni riga nuova
        è un comando, eseguito in ordine: "menu:<JS>" nel menu in gioco, "app:<JS>" nella finestra dell'app, "py:<codice>"
        Python con self. Il risultato (o l'errore) va in una riga del file .out accanto."""
        import time
        f = Path(os.environ["SPIDEY_REGIA_FILE"])
        out = f.with_suffix(".out")
        letto = f.stat().st_size if f.exists() else 0
        while True:
            time.sleep(0.02)
            try:
                if not f.exists() or f.stat().st_size <= letto:
                    if f.exists() and f.stat().st_size < letto:
                        letto = 0
                    continue
                with open(f, "rb") as h:
                    h.seek(letto)
                    blocco = h.read()
                fine = blocco.rfind(b"\n")
                if fine < 0:
                    continue
                letto += fine + 1
                for riga in blocco[:fine].decode("utf-8").splitlines():
                    riga = riga.strip()
                    if not riga:
                        continue
                    tipo, _, codice = riga.partition(":")
                    try:
                        if tipo == "menu":
                            r = self._menu_js(codice)
                        elif tipo == "app":
                            r = self._finestra.evaluate_js(codice)
                        else:
                            ambiente = {"self": self, "core": core, "time": time}
                            exec(compile(codice, "<regia>", "exec"), ambiente)
                            r = ambiente.get("r")
                        esito = f"ok {r!r}"[:400]
                    except Exception as e:  # noqa: BLE001
                        esito = f"errore {e!r}"[:400]
                    with open(out, "a", encoding="utf-8") as h:
                        h.write(esito.replace("\n", " ") + "\n")
            except Exception:  # noqa: BLE001
                time.sleep(0.5)

    @protetto
    def menu_apri_prova(self, gioco=False):
        """Solo per provare: apre il menu come se avessi premuto LB + RB (sul gioco vero o, senza, sulla finestra dell'app)."""
        g = core.finestra_gioco() if gioco else __import__("ctypes").windll.user32.FindWindowW(None, TITOLO)

        def via():
            import time
            self._menu_apri(g)
            for k in filter(None, os.environ.get("SPIDEY_MENU_TASTI", "").split(",")):  # tasti finti, per le foto di prova
                time.sleep(0.7)
                self._menu_js(k[3:] if k.startswith("js:") else f"menuTasto('{k}')")  # "js:..." = JavaScript nel menu
        threading.Thread(target=via, daemon=True).start()
        return True

    def _comandi_gioco(self, dolphin):
        """Quali righe mostrare nei comandi del menu in gioco (come la finestra Comandi dell'app): tuffo, FOV e camera
        moderna dai codici della versione in gioco, spalla ←/→ se una delle camere è la Amazing."""
        gid = core.gioco_in_corso()
        m = (core.mod_versioni(dolphin) if dolphin else {}).get(gid) or {}
        return {"tuffo": bool(m.get("tuffo")), "fov": bool(m.get("fov")), "moderna": bool(m.get("cam_moderna")),
                "amazing": bool(m.get("cam_moderna")) and "amazing" in self._cam_modi()}

    @protetto
    def menu_stato(self):
        """Per il menu: lingua, skin (con miniature), quelle in uso, avviso sul cambio costume, tasti della Play."""
        voci, rag = self._catalogo()
        dolphin = core.trova_dolphin(self._conf)
        mini = {v["id"]: self._mini_menu(v["k"]) for v in voci}
        inst = self._installate(dolphin, voci, rag or []) if dolphin and voci else {}
        tasti = None  # layout dei tasti a schermo installato (HUD e tasti): PlayStation -> il menu mostra i tasti della Play
        try:
            pack = core.trova_pack(self._conf)
            tasti = (core.installate_hud(dolphin, [], core.catalogo_tasti(pack)).get("tasti") or {}).get("id") if pack and dolphin else None
        except Exception:  # noqa: BLE001
            pass
        ps = bool(os.environ.get("SPIDEY_MENU_PS")) or bool(tasti) and any(x in tasti.upper() for x in ("PLAYSTATION", "PS2", "PS3", "PS4", "PS5"))
        return {"lingua": self._conf.get("lingua") or core.lingua_sistema(), "tasti_ps": ps,
                "partita": f"{self._pid_dolphin()}:{core.gioco_in_corso()}",  # gioco riaperto = il menu riparte dalle skin
                "preferite": self._preferite(),
                "skin": [{"id": v["id"], "nome": v["nome"], "gruppo": v["gruppo"], "crediti": v.get("crediti"), "path": v["default"],
                          "mini": mini.get(v["id"]), "nvar": v.get("varianti", 1),
                          "albero": _albero_menu(v["albero"]) if v.get("varianti", 1) > 1 else None} for v in voci],
                "primaria_path": (inst.get("primaria") or {}).get("path"), "alternativa_path": (inst.get("alternativa") or {}).get("path"),
                "ragnatele": [{"id": r["id"], "nome": r["nome"], "file": r["file"]} for r in rag or []], "ragnatela": inst.get("ragnatele"),
                "ragnatela_alt": inst.get("ragnatele_alt", "uguali"),
                "primaria": (inst.get("primaria") or {}).get("id"), "alternativa": (inst.get("alternativa") or {}).get("id"),
                "alt_spento": self._alt_spento(dolphin), "pad": self._pad(), "versione": core.gioco_in_corso(),
                "comandi": self._comandi_gioco(dolphin)}

    @protetto
    def menu_musica(self, cmd="info"):
        """Musica del menu: info (titolo, artista, stato, tempo), foto (copertina), play / next / prev."""
        if cmd not in ("info", "foto", "play", "next", "prev", "vol", "vol+", "vol-"):
            return {"errore": "comando"}
        if os.environ.get("SPIDEY_MUSICA_FINTA"):  # per provare la grafica senza niente in riproduzione
            if cmd == "foto":
                return {"foto": core.immagine64(str(risorsa("spidey_app.ico")), 300, 300).split(",", 1)[1], "tipo": "image/png"}
            if cmd.startswith("vol"):
                self._vol_finto = max(0.0, min(1.0, getattr(self, "_vol_finto", 0.6) + {"vol+": 0.05, "vol-": -0.05}.get(cmd, 0)))
                return {"vol": self._vol_finto}
            return {"sessione": True, "app": "Spotify.exe", "app_nome": "Spotify", "titolo": "Spider-Man 2 Main Theme", "artista": "Danny Elfman",
                    "stato": "Playing", "pos": 74, "durata": 215, "foto": True}
        if not hasattr(self, "_musica"):
            self._musica = core.Musica()
        r = self._musica.comando(cmd, attesa=12 if cmd == "info" else 6)
        if r.get("app"):  # nome leggibile: "Spotify.exe", "SpotifyAB.SpotifyMusic_zpdnekdrzrea0!Spotify", "msedge"...
            import re
            a = re.sub(r"_[a-z0-9]{13}$", "", r["app"].split("!")[0].split("\\")[-1].replace(".exe", ""))
            noti = [("spotify", "Spotify"), ("msedge", "Microsoft Edge"), ("chrome", "Google Chrome"), ("firefox", "Firefox"),
                    ("opera", "Opera"), ("brave", "Brave"), ("vlc", "VLC"), ("zunemusic", "Windows Media Player"),
                    ("mediaplayer", "Windows Media Player"), ("applemusic", "Apple Music"), ("itunes", "iTunes"),
                    ("deezer", "Deezer"), ("tidal", "TIDAL"), ("amazonmusic", "Amazon Music"), ("youtube", "YouTube Music"),
                    ("foobar", "foobar2000"), ("musicbee", "MusicBee")]
            r["app_nome"] = next((n for k, n in noti if k in r["app"].lower()), a.split(".")[-1])
        if cmd == "foto" and r.get("foto"):  # copertina rimpicciolita (Spotify la dà 640x640, ~300 KB)
            try:
                import base64
                import io
                from PIL import Image
                im = Image.open(io.BytesIO(base64.b64decode(r["foto"]))).convert("RGB")
                im.thumbnail((360, 360))
                b = io.BytesIO()
                im.save(b, "JPEG", quality=88)
                r = {"foto": base64.b64encode(b.getvalue()).decode(), "tipo": "image/jpeg"}
            except Exception:  # noqa: BLE001
                pass
        return r

    @protetto
    def menu_codici(self):
        """Codici della versione che sta girando, con acceso/spento (per la scheda Codici del menu)."""
        gid = core.gioco_in_corso()
        dolphin = core.trova_dolphin(self._conf)
        if not dolphin or not gid or gid == "?":
            return {"errore": "gioco"}
        ini = Path(dolphin) / "GameSettings" / f"{gid}.ini"
        st = core.leggi_codici_ini(ini) if ini.is_file() else {"attivi": set()}
        lista = [c for c in core.carica_codici_db() + self._miei() if gid in c["versioni"] and not c.get("parte_di")
                 and c.get("livello") != "ora"]  # l'ora del giorno sta nella sezione Cielo (cambia subito, senza riavvio)
        return {"gid": gid, "stato1": self._stato1_c_e(gid), "codici": [{"id": c["id"], "titolo": c.get("titolo"), "desc": c.get("desc"), "livello": c.get("livello", "miei"),
                                        "tasti": c.get("tasti"), "esclusivo": c.get("esclusivo"), "conflitti": c.get("conflitti", []),
                                        "attivo": c["nome_ini"] in st["attivi"]} for c in lista]}

    @protetto
    def menu_codici_applica(self, stati, stato1=False):
        """stati = {id: acceso}: scrive i codici e riavvia il gioco da capo (i codici partono solo all'avvio); stato1 =
        poi carica lo stato 1 (aggiornato ai codici nuovi dall'app prima di caricarlo, vedi _sorveglia_codici)."""
        threading.Thread(target=self._menu_riavvia, args=(dict(stati), True, bool(stato1)), daemon=True).start()
        return True

    def _stato1_c_e(self, gid):
        """C'è lo stato 1 di questa versione e Dolphin lo può caricare (stesso formato)?"""
        dolphin = core.trova_dolphin(self._conf)
        if not dolphin or not gid or gid == "?":
            return False
        s = next((x for x in (self.gioca_stati(gid) or {}).get("stati", []) if x["n"] == 1), None)
        return bool(s and s.get("compatibile") is not False)

    @protetto
    def stato1_c_e(self):
        """Pagina Codici: per offrire "Riavvia dallo stato 1" dopo aver cambiato i codici col gioco aperto."""
        return self._stato1_c_e(core.gioco_in_corso())

    def _chiudi_dolphin(self):
        """Chiude il gioco e Dolphin: WM_CLOSE, la sua conferma (Invio = Sì), e se non basta lo chiudo io."""
        import ctypes
        import time
        u = ctypes.windll.user32
        core.chiudi_gioco()
        for i in range(60):
            time.sleep(0.25)
            if not core.exe_dolphin_aperti(fresco=True):
                return True
            fin = core.finestre_dolphin()
            for h, tit in fin:
                tit = tit.strip()
                if tit and " | " not in tit and not tit.startswith("Dolphin"):  # la domanda "Vuoi fermare l'emulazione?"
                    u.SetForegroundWindow(h)
                    u.keybd_event(0x0D, 0x1C, 0, 0)
                    u.keybd_event(0x0D, 0x1C, 0x0002, 0)
            if i == 16 and not any(" | " in t for _, t in fin):  # gioco fermato ma Dolphin aperto (senza "Solo il gioco")
                for h, tit in fin:
                    u.PostMessageW(h, 0x0010, 0, 0)
        import psutil
        for p in psutil.process_iter(["name", "exe"]):
            if core.e_dolphin(p.info.get("name")):  # non DolphinMemoryEngine / DolphinTool
                if core.DA_ZERO and core.BASE_PROVA not in Path(p.info.get("exe") or ".").parents:
                    continue  # prova da zero: mai il Dolphin vero
                try:
                    p.kill()
                except Exception:  # noqa: BLE001
                    pass
        time.sleep(1)
        return not core.exe_dolphin_aperti()

    @protetto
    def riavvia_gioco(self, stato1=False):
        """Pagina Codici: codici già scritti, riavvio il gioco in corso da capo (stato1 = poi carica lo stato 1)."""
        threading.Thread(target=self._menu_riavvia, args=({}, False, bool(stato1)), daemon=True).start()
        return True

    @protetto
    def skin_preferita(self, sid, si):
        """Costumi preferiti (pagina Skin e menu in gioco)."""
        pref = [x for x in self._preferite() if x != sid]
        if si:
            pref.insert(0, sid)
        self._conf["skin_preferite"] = pref
        core.scrivi_config(self._conf)
        return pref

    def _menu_riavvia(self, stati, scrivi=True, stato1=False):
        """Codici cambiati (dal menu o dalla pagina Codici): li scrive e riavvia il gioco da capo, nello stesso modo
        (schermo intero o finestra). (Il "riprendi da dove sei" con uno stato salvato temporaneo è stato tolto: i codici
        spenti restavano attivi nella memoria salvata.) stato1 (idea di John) = riparte e carica lo stato 1 come "Parti
        dallo stato 1" del launcher: prima di caricarlo l'app gli rimette dentro i codici nuovi (stati_codici)."""
        import time
        if not self._riavvio_lock.acquire(blocking=False):  # già in corso (secondo A, o la pagina Codici insieme al menu)
            self._menu_js("menuCodiciPasso('errore')")  # (se no la finestrella "riavvio?" restava con la rotella)
            return
        nascosto = False
        try:
            gid = core.gioco_in_corso()
            dolphin = core.trova_dolphin(self._conf)
            if not gid or gid == "?" or not dolphin:
                self._menu_js("menuCodiciPasso('errore')")
                return
            intero = bool((core.stato_finestra_gioco() or {}).get("intero"))
            if scrivi:
                self._menu_js("menuCodiciPasso('scrivo')")
                # come la pagina Codici: con "Applica a tutte le versioni" (di base con più versioni) cambiano tutte
                tutte = self._conf.get("codici_tutte")
                inst = [g for g in core.NOMI_VERSIONE if (Path(dolphin) / "GameSettings" / f"{g}.ini").exists()]
                self.codici_applica(inst if (tutte if isinstance(tutte, bool) else len(inst) > 1) and gid in inst else [gid], stati)
            self._menu_js("menuCodiciPasso('riavvio')")
            time.sleep(0.6)
            self._menu_nascondi()
            nascosto = True
            self._chiudi_dolphin()
            time.sleep(0.8)
            slot = 1 if stato1 and self._stato1_c_e(gid) else None
            self.gioca_avvia(gid, self._conf.get("gioca_solo", True), intero, slot, ricorda=False)
        except Exception as e:  # noqa: BLE001
            core.log_errore(f"menu riavvia: {e!r}")
            if not nascosto:
                self._menu_js("menuCodiciPasso('errore')")
        finally:
            self._riavvio_lock.release()

    def _menu_sopra(self):
        """Dopo aver premuto un tasto al gioco (che così torna davanti), rimetto il menu sopra di lui. Solo se è aperto:
        chiuso con LB+RB durante la mappa 3D o un viaggio, la barra ricompariva davanti a tutto e i tasti non andavano più
        né al menu né al gioco."""
        if not self._menu_aperto:
            return
        import ctypes
        from ctypes import wintypes
        u = ctypes.windll.user32
        u.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint]
        w, g = u.FindWindowW(None, TITOLO_MENU), core.finestra_gioco()
        if w:
            u.SetWindowPos(w, wintypes.HWND(-1), 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0040)
            if g:
                u.SetWindowPos(g, w, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010)
            if not core._davanti(w):  # con SetForegroundWindow nudo a volte il gioco restava davanti: i tasti arrivavano
                self._log_menu("menu non tornato in primo piano")  # a Spidey e al menu insieme

    @protetto
    def menu_stati(self):
        """Slot 1-8 (quelli coi tasti rapidi di Dolphin) della versione in gioco, con foto e data."""
        gid = core.gioco_in_corso()
        if not gid or gid == "?":
            return {"errore": "gioco"}
        r = self.gioca_stati(gid)
        return {"gid": gid, "stati": [s for s in (r or {}).get("stati", []) if s["n"] in core.SLOT_TASTI]}

    @protetto
    def menu_stato_salva(self, n):
        """Salva nello slot n e rimette il menu sopra; poi la foto la fa la guardia degli stati."""
        import time
        gid, dolphin = core.gioco_in_corso(), core.trova_dolphin(self._conf)
        if not gid or gid == "?" or not dolphin:
            return {"errore": "gioco"}
        self._aspetta_rilascio()  # per salvare il gioco viene davanti: con X ancora premuto Spidey darebbe un pugno
        ok = self._salva_stato(core.file_stato(dolphin, gid, int(n)), int(n), dopo_tasto=self._menu_sopra)
        self._menu_sopra()
        return self.menu_stati() if ok else {"errore": "st_err_tasti"}

    def _salva_stato(self, f, n, dopo_tasto=None):
        """Salva lo slot n (Maiusc+F<n>) e aspetta che il file sia scritto e la foto fatta. True = salvato. dopo_tasto =
        subito dopo il tasto (menu: rimesso davanti, se no per qualche secondo i tasti andavano anche a Spidey)."""
        import time
        prima = f.stat().st_mtime if f.exists() else 0
        core.tasto_stato(n, True)
        if dopo_tasto:
            dopo_tasto()
        for _ in range(40):
            time.sleep(0.15)
            if f.exists() and f.stat().st_mtime != prima:
                break
        time.sleep(1.6)  # la finisce di scrivere e la guardia degli stati fa la foto
        return f.exists() and f.stat().st_mtime != prima

    @protetto
    def menu_stato_carica(self, n):
        """Chiude il menu, carica lo slot n e fa ripartire il gioco."""
        def via():
            import time
            self._aspetta_rilascio()  # A ancora premuto arriverebbe al gioco (salto): aspetto PRIMA di nascondere il menu
            self._menu_nascondi()
            time.sleep(0.2)
            core.tasto_stato(int(n), False)
        threading.Thread(target=via, daemon=True).start()
        return True

    @protetto
    def menu_esci(self):
        """Esci dal gioco dal menu (tutto col controller): chiude il menu, poi il gioco e Dolphin."""
        def via():
            import time
            self._aspetta_rilascio()  # prima che il gioco torni davanti (nascondendo il menu): se no A arriva a Spidey
            self._menu_nascondi()
            time.sleep(0.2)
            self._chiudi_dolphin()
        threading.Thread(target=via, daemon=True).start()
        return True

    @protetto
    def menu_riduci(self):
        """Riduci il gioco a icona dal menu (Sistema): chiude il menu; se il gioco è a schermo intero prima lo rimette in
        finestra (ridotto a icona da schermo intero, tornando ripartirebbe a schermo intero sopra a tutto)."""
        def via():
            import ctypes
            import time
            self._aspetta_rilascio()
            self._menu_nascondi()
            time.sleep(0.2)
            st = core.stato_finestra_gioco()
            if st and st["intero"]:
                core.schermo_intero_al_volo()
                for _ in range(30):
                    time.sleep(0.1)
                    st = core.stato_finestra_gioco()
                    if not st or not st["intero"]:
                        break
            h = core.finestra_gioco()
            if h:
                ctypes.windll.user32.ShowWindow(h, 6)  # SW_MINIMIZE
        threading.Thread(target=via, daemon=True).start()
        return True

    # ------------------------------------------------------------ camera dal vivo (menu in gioco e pagina Spider-Cam)
    def _pid_dolphin(self):
        import psutil
        for pr in psutil.process_iter(["name"]):
            n = (pr.info.get("name") or "").lower()
            if n.startswith("dolphin") and n.endswith(".exe") and "memory" not in n and "tool" not in n:
                return pr.pid
        return None

    def _cam_testa(self, gid):
        import app_cam
        return app_cam.testa_vivo(gid)

    def _cam_codice_vivo(self, gid, cerca=True):
        """Dove sta il codice camera in esecuzione nella memoria di Dolphin ([(indirizzo, righe)], [] = non c'è,
        None = non ancora cercato). Cercarlo costa qualche secondo: una volta per partita, poi resta in memoria."""
        import ar_vivo
        pid = self._pid_dolphin()
        c = self._cam_vivo
        if c and c["pid"] == pid and c["gid"] == gid:
            return c["dove"]
        if not cerca or not pid or not gid or gid == "?":
            return None
        with self._cam_vivo_lock:
            c = self._cam_vivo
            if c and c["pid"] == pid and c["gid"] == gid:
                return c["dove"]
            dove = []
            try:
                pr = ar_vivo.Processo(pid)
                try:
                    dove = ar_vivo.trova_codice(pr, self._cam_testa(gid))
                finally:
                    pr.chiudi()
            except Exception as e:  # noqa: BLE001
                core.log_errore(f"camera dal vivo: {e!r}")
            self._cam_vivo = {"pid": pid, "gid": gid, "dove": dove}
            return dove

    def _cam_cerca_presto(self, gid):
        """La ricerca parte in sottofondo (es. appena apri il menu): quando arrivi alla Camera è già pronta."""
        if gid and gid != "?" and self._cam_codice_vivo(gid, cerca=False) is None:
            threading.Thread(target=self._cam_codice_vivo, args=(gid,), daemon=True).start()

    def _cam_metti_vivo(self, gid, valori, fov, scrivi_fov=True):
        """Cambia i valori del codice camera in esecuzione (e il FOV nella memoria del gioco).
        "ok" | "corto" (il codice caricato è più corto: vale dal prossimo avvio) | "nessuno" (codice spento) | "cerco"."""
        import math
        import app_cam
        import ar_vivo
        dove = self._cam_codice_vivo(gid, cerca=False)
        if dove is None:
            self._cam_cerca_presto(gid)
            return "cerco"
        if not dove:
            return "nessuno"
        righe = app_cam.codici(valori, fov, gid)[0][1:]
        c = self._cam_vivo  # (letto una volta: un'altra chiamata può azzerarlo intanto)
        if not c:
            return "cerco"
        pid = c["pid"]
        try:
            pr = ar_vivo.Processo(pid)
            try:
                testa = self._cam_testa(gid)
                if not all(ar_vivo.ancora_li(pr, d, testa) for d in dove):  # codici ricaricati in Dolphin: lo ricerco
                    self._cam_vivo = None
                    self._cam_cerca_presto(gid)
                    return "cerco"
                ok = all([ar_vivo.metti_codice(pr, d, righe) for d in dove])  # tutte le copie, anche se una non ci sta
            finally:
                pr.chiudi()
        except OSError:
            return "nessuno"
        if ok and scrivi_fov:
            try:
                import dolphin_memory_engine as dme
                with self._dme_lock:
                    if core.aggancia_dme():
                        app_cam.cs.versione = gid
                        dme.write_float(app_cam.cs.A(app_cam.cs.FOV), math.radians(float(fov)))
            except Exception:  # noqa: BLE001
                pass
        return "ok" if ok else "corto"

    # ------------------------------------------------------------ le due camere (principale / alternativa con R3)
    def _cam_modi(self):
        # la prima "amazing" (modo 4) ora si chiama "cinematica": chi l'aveva scelta la ritrova uguale (una volta sola)
        if not self._conf.get("cam_modi_v2"):
            m = self._conf.get("cam_modi")
            if m and "amazing" in m:
                self._conf["cam_modi"] = ["cinematica" if x == "amazing" else x for x in m]
            self._conf["cam_modi_v2"] = True
            core.scrivi_config(self._conf)
        return core.cam_modi_valore(self._conf.get("cam_modi"))[0]

    def _cam_modi_memoria(self, modi=None, leggi=False):
        """Scrive nel gioco in corso le due camere (byte 817F0084/85 del Gecko della camera) e dice quale è attiva."""
        try:
            import dolphin_memory_engine as dme
            with self._dme_lock:
                if not core.aggancia_dme():
                    return None
                # codice nuovo acceso: costanti e camere scritte dal Gecko e programma scritto dal codice AR (senza il
                # programma il Gecko non fa niente e "già cambiata nel gioco" sarebbe falso)
                gecko = (dme.read_word(0x817F01FC) == 1 and dme.read_byte(0x817F0086) == 1
                         and dme.read_word(CAM_PROGRAMMA) != 0)
                if modi is not None:
                    _, val = core.cam_modi_valore(modi)
                    slot = dme.read_byte(0x817F0080) & 1
                    prima = dme.read_byte(0x817F0084 + slot)
                    dme.write_byte(0x817F0084, val >> 24 & 0xFF)
                    dme.write_byte(0x817F0085, val >> 16 & 0xFF)
                    dopo = (val >> (24 - 8 * slot)) & 0xFF
                    # la camera attiva passa all'originale (2) o ne esce: il FOV come con R3 (originale = 90°, uscendo
                    # rimetto quello che c'era prima). Con R3 lo fa il codice classico; da app e menu no.
                    fov = {"GK2I52": 0x8046A7C0}.get(core.gioco_in_corso(), 0x8046A740)
                    partita = (self._pid_dolphin(), core.gioco_in_corso())  # il FOV ricordato vale solo in questa partita
                    if dopo == 2 and prima != 2:
                        self._fov_prima_originale = (partita, dme.read_float(fov))
                        dme.write_float(fov, 1.5708)
                    elif prima == 2 and dopo != 2:
                        ricordato = getattr(self, "_fov_prima_originale", None)
                        if ricordato and ricordato[0] == partita:
                            dme.write_float(fov, ricordato[1])
                return {"slot": dme.read_byte(0x817F0080) & 1, "gecko": gecko}
        except Exception:  # noqa: BLE001
            return None

    @protetto
    def cam_modi(self):
        gid = core.gioco_in_corso()
        vivo = self._cam_modi_memoria(leggi=True) if gid and gid != "?" else None
        import cam_ps4
        opz = dict(self._conf.get("cam_opzioni") or {})
        opz["prima_vista"] = {v: k for k, v in cam_ps4.VISTE.items()}[cam_ps4.valore_vista(opz)]
        opz["tuffo_l3"] = self._tuffo_acceso()
        opz.setdefault("picchiata", True)
        return {"modi": self._cam_modi(), "slot": vivo["slot"] if vivo else None, "gecko": bool(vivo and vivo["gecko"]),
                "opzioni": opz, "tua": self._cam_tua()}

    def _cam_tua(self):
        """La camera del gioco ("classica") salvata nel gioco è la tua (valori diversi dalla Migliorata)? Migliorata e La tua
        sono la stessa camera con valori diversi: c'è posto per uno solo dei due nel codice."""
        import app_cam
        sal = self._conf.get("cam_salvata")
        if not sal or not sal.get("valori"):
            return False
        if "tua" in sal:  # detto dalla pagina Spider-Cam ("La tua" scelta anche con gli stessi valori della Migliorata)
            return bool(sal["tua"])
        _, _, v, fov = app_cam.PRESET_FISSI["migliorata"]
        try:
            return round(sal.get("fov", fov)) != fov or any(abs(float(a) - float(b)) > 1e-3
                                                            for g in app_cam.GRUPPI for a, b in zip(sal["valori"][g], v[g]))
        except (KeyError, TypeError, ValueError):
            return True

    @protetto
    def cam_modi_imposta(self, modi):
        """Sceglie le due camere: subito nel gioco aperto e nel codice di tutte le versioni (vale anche le prossime volte)."""
        modi, _ = core.cam_modi_valore(modi)
        self._conf["cam_modi"] = modi
        core.scrivi_config(self._conf)
        dolphin = core.trova_dolphin(self._conf)
        scritti = []
        for g in core.NOMI_VERSIONE:
            ini = Path(dolphin) / "GameSettings" / f"{g}.ini" if dolphin else None
            if ini and ini.is_file():
                core.allinea_camera(ini, g, modi, self._conf.get("cam_opzioni"))
                scritti.append(g)
        gid = core.gioco_in_corso()
        vivo = self._cam_modi_memoria(modi) if gid and gid != "?" else None
        return {"modi": modi, "versioni": scritti, "vivo": None if not vivo else "ok" if vivo["gecko"] else "vecchio"}

    def _tuffo_acceso(self):
        """Tuffo con L3 = codice a sé (tuffo.py): acceso se lo è in almeno una versione installata (nessuna = vero)."""
        try:
            mv = core.mod_versioni(core.trova_dolphin(self._conf))
            st = [m["tuffo"] for m in mv.values() if m.get("ini") and m.get("codici")]
            return any(st) if st else True
        except Exception:  # noqa: BLE001
            return True

    def _tuffo_imposta(self, si):
        """Accende/spegne il codice del tuffo con L3 in tutte le versioni con codici (vale dal prossimo avvio)."""
        dolphin = core.trova_dolphin(self._conf)
        db = next((c for c in core.carica_codici_db() if c["id"] == "tuffo_l3"), None)
        if not dolphin or not db:
            return []
        fatti = []
        for g in core.NOMI_VERSIONE:
            ini = Path(dolphin) / "GameSettings" / f"{g}.ini"
            if not ini.is_file() or g not in db["versioni"] or not core.leggi_codici_ini(ini)["attivi"]:
                continue
            core.backup_file(ini, "GameSettings")
            if si:
                core.scrivi_codici_ini(ini, [(db["nome_ini"], db["versioni"][g])], [])
            else:
                core.scrivi_codici_ini(ini, [], [(db["nome_ini"], False)])
            fatti.append(g)
        return fatti

    @protetto
    def cam_opzione(self, nome, val):
        """Opzioni della camera ("prima_vista" = movimento della testa in prima persona: "no" / "si";
        "tuffo_l3" / "picchiata" = tuffo con L3 e camera della picchiata, vero/falso): INI di tutte le versioni + dal vivo."""
        import cam_ps4
        if nome == "prima_vista" and val not in cam_ps4.VISTE:
            return {"errore": "valore"}
        if nome == "tuffo_l3":  # codice a sé: acceso/spento negli INI (col gioco aperto vale dal prossimo avvio)
            self._tuffo_imposta(bool(val))
            opz = dict(self._conf.get("cam_opzioni") or {})
            opz.pop("tuffo_l3", None)
            self._conf["cam_opzioni"] = opz
            core.scrivi_config(self._conf)
            gid = core.gioco_in_corso()
            return {"opzioni": dict(opz, tuffo_l3=self._tuffo_acceso()), "riavvio": bool(gid and gid != "?")}
        opz = dict(self._conf.get("cam_opzioni") or {}, **{nome: val if nome == "prima_vista" else bool(val)})
        opz.pop("prima_testa", None) if nome == "prima_vista" else None  # quella di prima (vero/falso) non serve più
        self._conf["cam_opzioni"] = opz
        core.scrivi_config(self._conf)
        gid = core.gioco_in_corso()
        if gid and gid != "?":  # prima il gioco aperto (si vede subito), poi gli INI (5 versioni: ~2 s)
            try:
                with self._dme_lock:
                    dme = core.aggancia_dme()
                    if dme:
                        v = core.cam_opzioni_valore(opz)
                        dme.write_byte(0x817F0088, v >> 24)
                        dme.write_byte(0x817F0089, (v >> 16) & 0xFF)
            except Exception:  # noqa: BLE001
                pass
        dolphin = core.trova_dolphin(self._conf)
        for g in core.NOMI_VERSIONE:
            ini = Path(dolphin) / "GameSettings" / f"{g}.ini" if dolphin else None
            if ini and ini.is_file():
                core.allinea_camera(ini, g, self._cam_modi(), opz)
        return {"opzioni": dict(opz, tuffo_l3=self._tuffo_acceso())}  # (senza, l'interruttore del tuffo si riaccendeva a schermo)

    @protetto
    def menu_cam_stato(self):
        """Per la sezione Camera del menu: preset (fissi + tuoi), le scelte di prima, se il codice è modificabile dal vivo."""
        import app_cam
        lingua = self._conf.get("lingua") or core.lingua_sistema()
        preset = []
        sal = self._conf.get("cam_salvata")
        if sal and sal.get("valori"):  # quella salvata nel gioco (se non è uguale a un preset pronto)
            uguale = lambda v: all(abs(float(a) - float(b)) < 1e-3 for g in app_cam.GRUPPI for a, b in zip(sal["valori"][g], v[g]))
            if not any(uguale(v) and round(fov) == sal["fov"] for _, _, v, fov in app_cam.PRESET_FISSI.values()):
                preset.append({"chiave": "s:", "nome": None,  # il nome lo mette la pagina (nella lingua giusta)
                               "valori": sal["valori"], "fov": sal["fov"], "fisso": True, "salvata": True})
        for k, (it, en, v, fov) in app_cam.PRESET_FISSI.items():
            nome = {"it": it, "en": en, **app_cam.NOMI_ALTRE_LINGUE.get(k, {})}.get(lingua, en)
            preset.append({"chiave": "f:" + k, "nome": nome, "valori": {g: list(v[g]) for g in app_cam.GRUPPI}, "fov": fov, "fisso": True})
        for nome, d in (self._conf.get("cam_preset") or {}).items():
            if isinstance(d, dict) and d.get("valori"):
                preset.append({"chiave": "u:" + nome, "nome": nome, "valori": d["valori"], "fov": d.get("fov", 90), "fisso": False})
        gid = core.gioco_in_corso()
        dove = self._cam_codice_vivo(gid, cerca=False) if gid and gid != "?" else None
        if dove is None:
            self._cam_cerca_presto(gid)
        u = self._conf.get("cam_ultimi") or {}
        scelta = self._conf.get("menu_cam")
        if scelta and scelta.get("partita") != f"{self._pid_dolphin()}:{gid}":
            scelta = None  # scelta di un'altra partita e mai salvata: si riparte dalla camera salvata davvero
        scelta = scelta or ({"preset": "s:", "d": 1, "h": 0, "r": 1, "fov": sal["fov"]} if preset and preset[0].get("salvata") else None)
        return {"preset": preset, "scelta": scelta, "gid": gid,
                "ultimo_preset": u.get("preset_chiave"), "vivo": None if dove is None else bool(dove),
                "versioni": [g for g in core.NOMI_VERSIONE if (Path(core.trova_dolphin(self._conf) or ".") / "GameSettings" / f"{g}.ini").exists()],
                "tutte": self._conf.get("cam_tutte")}

    @protetto
    def menu_cam_anteprima(self, si):
        """Mentre regoli la camera del gioco nella barra del menu la vedi davvero (John: "original sembra più vicina di
        improved", ma giocava con la moderna e la barra non cambiava niente a schermo). Se la camera del gioco è
        nell'altro slot, passo a quello (byte 817F0080, come R3) e alla fine rimetto lo slot di prima."""
        try:
            import dolphin_memory_engine as dme
            with self._dme_lock:
                if not core.aggancia_dme():
                    return {"anteprima": False}
                b = dme.read_byte(0x817F0080)
                slot, partita = b & 1, (self._pid_dolphin(), core.gioco_in_corso())
                ant = getattr(self, "_cam_ant", None)
                if not si:
                    self._cam_ant = None
                    if ant and ant[0] == partita and slot != ant[1]:
                        dme.write_byte(0x817F0080, (b & 0xFE) | ant[1])
                    return {"anteprima": False}
                if ant:
                    return {"anteprima": True}
                modi = self._cam_modi()
                if modi[slot] == "classica" or modi[1 - slot] != "classica" or dme.read_byte(0x817F0086) != 1:
                    return {"anteprima": False, "in_uso": modi[slot] == "classica"}
                self._cam_ant = (partita, slot)
                dme.write_byte(0x817F0080, (b & 0xFE) | (1 - slot))
                return {"anteprima": True}
        except Exception:  # noqa: BLE001
            return {"anteprima": False}

    @protetto
    def menu_cam_imposta(self, valori, fov, scelta=None):
        """Dal vivo mentre muovi i cursori del menu; scelta = {preset, d, h, r, fov} ricordata per la prossima volta."""
        gid = core.gioco_in_corso()
        if scelta is not None:
            self._conf["menu_cam"] = dict(scelta, partita=f"{self._pid_dolphin()}:{gid}")  # vale per questa partita
        if not gid or gid == "?":
            return {"vivo": "nessuno"}
        return {"vivo": self._cam_metti_vivo(gid, valori, fov)}

    @protetto
    def menu_cam_salva(self, valori, fov, scelta=None, preset_chiave=None):
        """Salva la camera nel gioco (INI: vale anche le prossime volte), in tutte le versioni se "Tutte" è acceso."""
        import app_cam
        dolphin = core.trova_dolphin(self._conf)
        gid = core.gioco_in_corso()
        if not dolphin:
            return {"errore": "dolphin"}
        installate = [g for g in core.NOMI_VERSIONE if (Path(dolphin) / "GameSettings" / f"{g}.ini").exists()]
        vers = installate if self._conf.get("cam_tutte", len(installate) > 1) else [gid if gid in installate else (installate or list(self._tutti_giochi(dolphin)) or ["GK2E52"])[0]]
        r = {"salvati": [], "errori": []}
        for g in vers:
            x = app_cam.salva(dolphin, valori, fov, g)
            r["salvati"] += x["salvati"]
            r["errori"] += x["errori"]
        if scelta is not None:
            self._conf["menu_cam"] = scelta
        if r["salvati"]:
            self._conf["cam_salvata"] = {"valori": valori, "fov": round(fov)}
        self._conf["cam_ultimi"] = {"valori": valori, "fov": round(fov), "collega": True, "min_uguale": False,
                                    "preset_chiave": preset_chiave or "f:migliorata", "rif": None}
        core.scrivi_config(self._conf)
        r["versioni"] = vers
        return r

    @protetto
    def menu_ragnatela(self, rid, alt=False):
        if alt:  # ragnatele del costume alternativo: le mette il filo quando in gioco c'è l'alternativo
            r = self.applica({"ragnatele_alt": rid})
            self._log_menu(f"ragnatele dell'alternativo {rid}")
            return {"ok": not (r or {}).get("errore"), "errore": (r or {}).get("errore")}
        r = self.applica({"ragnatele": rid})
        self._log_menu(f"ragnatele {rid} -> {'errore ' + str(r.get('errore')) if (r or {}).get('errore') else 'ok'}")
        return {"ok": not (r or {}).get("errore"), "errore": (r or {}).get("errore")}

    @protetto
    def menu_skin(self, slot, path):
        r = self.applica({slot: path})
        self._log_menu(f"skin {slot} {Path(str(path)).name} -> {'errore ' + str(r.get('errore')) if (r or {}).get('errore') else 'ok'}")
        return {"ok": not (r or {}).get("errore"), "errore": (r or {}).get("errore")}

    # ------------------------------------------------------------ controller
    def _ini_versioni(self, dolphin):
        return {g: Path(dolphin) / "GameSettings" / f"{g}.ini" for g in core.NOMI_VERSIONE}

    @protetto
    def controller_stato(self):
        """Profilo dei tasti di Spider-Man 2 in Dolphin + controlli (vedi app_controller.stato)."""
        import app_controller as ac
        dolphin = core.trova_dolphin(self._conf)
        if dolphin:
            ac.aggiorna_vecchio(dolphin, self._conf)
        r = ac.stato(dolphin, self._ini_versioni(dolphin) if dolphin else {})
        r["dolphin"] = str(dolphin) if dolphin else None
        r["predefinito"] = ac.analizza(ac.leggi(ac.predefinito()))
        r["extra_default"] = ac.EXTRA_DEFAULT
        r["nomi_sdl"] = ac.NOMI_SDL
        r["dolphin_aperto"] = bool(core.exe_dolphin_aperti())
        r["pad"] = self._pad()
        f = ac.file_profilo(dolphin) if dolphin else None
        letta = ac.inversione(ac.leggi(f)) if f and f.is_file() else {}
        scelta = self._conf.get("cam_inverti") or {}
        r["inverti"] = {a: bool(letta.get(a)) if letta.get(a) is not None else bool(scelta.get(a)) for a in ("y", "x")}
        return r

    @protetto
    def controller_inverti(self, asse, si):
        """Camera invertita su/giù (asse "y") o sinistra/destra ("x"): nel profilo del pad (vale per tutte le camere,
        anche quella del gioco, e nella mod esportata) e ricordata (config cam_inverti) per quando il profilo si rifà."""
        import app_controller as ac
        if asse not in ("y", "x"):
            return {"errore": "asse"}
        dolphin = core.trova_dolphin(self._conf)
        if not dolphin:
            return {"errore": "dolphin"}
        self._conf.setdefault("cam_inverti", {})[asse] = bool(si)
        core.scrivi_config(self._conf)
        f = ac.file_profilo(dolphin)
        if not f.is_file():
            ac.assicura(dolphin, None)
        ac.applica_inversione(dolphin, self._conf["cam_inverti"])
        return self.controller_stato()

    def pad_leggi(self):
        """Tutti i pad collegati, letti da Python (app_controller.LettorePad) ~30 volte al secondo dalla pagina: tasti già
        nell'ordine di un pad Xbox per ogni marca, nome vero, quale hai toccato per ultimo. Il Gamepad del browser
        chiamava "Xbox 360 Controller" ogni pad XInput, a volte "Unknown Gamepad" coi tasti in un altro ordine, e con due
        pad guardava solo il primo."""
        try:
            with self._pad_app_lock:
                if self._pad_app is None:
                    import app_controller
                    self._pad_app = app_controller.LettorePad()
                return self._pad_app.leggi()
        except Exception as e:  # noqa: BLE001 - la pagina ripiega sul Gamepad del browser
            if not getattr(self, "_pad_app_errore", False):
                self._pad_app_errore = True
                core.log_errore(f"pad_leggi: {e!r}")
            return None

    @protetto
    def controller_salva(self, device, base, extra):
        """Scrive i tasti nel profilo (le righe degli stick restano com'erano)."""
        import app_controller as ac
        dolphin = core.trova_dolphin(self._conf)
        if not dolphin:
            return {"errore": "dolphin"}
        f = ac.file_profilo(dolphin)
        righe = ac.leggi(f if f.is_file() else ac.predefinito())
        ac.scrivi(f, ac.componi(righe, device, base, extra))
        return self.controller_stato()

    @protetto
    def _controller_ripristina(self, verso="xinput", nome_sdl=None):
        """Profilo dell'app da capo: per pad Xbox (XInput) o, convertito, per pad PlayStation/Nintendo (SDL)."""
        import app_controller as ac
        dolphin = core.trova_dolphin(self._conf)
        if not dolphin:
            return {"errore": "dolphin"}
        righe = ac.leggi(ac.predefinito())
        info = ac.analizza(righe)
        base, extra, dev = info["base"], info["extra"], info["device"]
        if verso == "sdl":
            base, extra = ac.converti_backend(info, "sdl")
            dev = f"SDL/0/{ac.NOMI_SDL.get(nome_sdl, nome_sdl) or ac.NOMI_SDL['ps5']}"  # chiave (ps5/ps4/switch) o nome (meglio controller_auto)
        # profilo da capo: la camera invertita scelta nell'app resta (config cam_inverti)
        ac.scrivi(ac.file_profilo(dolphin), ac.inverti(ac.componi(righe, dev, base, extra), self._conf.get("cam_inverti"))[0])
        return self.controller_stato()

    def _dispositivi_dolphin(self, attesa=9):
        """Come Dolphin chiama i controller collegati ("SDL/0/DualSense Wireless Controller"...): accendo per un attimo
        il suo registro dei controller (Config/Logger.ini, categoria CI), lo apro qualche secondo senza gioco, leggo le
        righe "Added device: ..." e rimetto il registro com'era. Solo con Dolphin chiuso. None = non si può."""
        import ctypes
        import re
        import subprocess
        import time
        dolphin = core.trova_dolphin(self._conf)
        exe = core.trova_exe_dolphin(self._conf, dolphin) if dolphin else None
        if not dolphin or not exe or core.exe_dolphin_aperti():
            return None
        ini, log = Path(dolphin) / "Config" / "Logger.ini", Path(dolphin) / "Logs" / "dolphin.log"
        prima = ini.read_bytes() if ini.is_file() else None
        testo = (prima or b"").decode("utf-8", "replace")
        nl = "\r\n" if "\r\n" in testo else "\n"
        righe = [r for r in testo.splitlines() if not re.match(r"\s*(CI|WriteToFile)\s*=", r)]
        if "[Logs]" not in [r.strip() for r in righe]:
            righe += ["[Logs]"]
        righe.insert([r.strip() for r in righe].index("[Logs]") + 1, "CI = True")
        if "[Options]" not in [r.strip() for r in righe]:
            righe += ["[Options]"]
        righe.insert([r.strip() for r in righe].index("[Options]") + 1, "WriteToFile = True")
        trovati = []
        try:
            ini.parent.mkdir(parents=True, exist_ok=True)
            ini.write_bytes((nl.join(righe) + nl).encode("utf-8"))
            da = log.stat().st_size if log.is_file() else 0
            si = subprocess.STARTUPINFO()
            si.dwFlags, si.wShowWindow = 1, 7  # STARTF_USESHOWWINDOW, SW_SHOWMINNOACTIVE: ridotto a icona, senza rubare il fuoco
            proc = avvia_esterno([str(exe), "-u", str(dolphin)], startupinfo=si)
            fine, visti = time.time() + attesa, 0.0
            while time.time() < fine:
                time.sleep(0.4)
                if log.is_file() and log.stat().st_size > da:
                    nuovo = log.read_bytes()[da:].decode("utf-8", "replace")
                    trovati = re.findall(r"Added device: (.+?)\s*$", nuovo, re.M)
                    if any(d.startswith("SDL/") for d in trovati) or "SteamDeck" in nuovo:  # SDL e gli altri sistemi hanno finito
                        if not visti:
                            visti = time.time()
                        elif time.time() - visti > 1.0:
                            break
            u = ctypes.windll.user32
            for h, _ in core.finestre_dolphin():
                u.PostMessageW(h, 0x0010, 0, 0)  # WM_CLOSE
            try:
                proc.wait(5)
            except subprocess.TimeoutExpired:
                proc.kill()
        finally:
            if prima is None:
                ini.unlink(missing_ok=True)
            else:
                ini.write_bytes(prima)
        return trovati

    @protetto
    def controller_auto(self, da_capo=False):
        """Profilo dei tasti giusto per il pad collegato, da solo: pad Xbox -> XInput; tutti gli altri (PlayStation,
        Nintendo, Stadia, generici) -> SDL col NOME che usa Dolphin (verificato, ricordato, o chiesto a Dolphin).
        da_capo = rimette anche i tasti dell'app (Ripristina), se no cambia solo il dispositivo e tiene i tasti scelti."""
        import app_controller as ac
        dolphin = core.trova_dolphin(self._conf)
        if not dolphin:
            return {"errore": "dolphin"}
        pad = ac.pad_collegati()
        xbox = next((x for x in pad if x["tipo"] == "xbox"), None)
        altro = next((x for x in pad if x["tipo"] != "xbox"), None)
        f = ac.file_profilo(dolphin)
        prof = ac.analizza(ac.leggi(f)) if f.is_file() else None
        if xbox or not altro:  # pad Xbox (o nessun pad): profilo XInput dell'app
            if da_capo or not prof or prof["backend"] != "xinput":
                return self._controller_ripristina("xinput")
            return self.controller_stato()
        cache = self._conf.setdefault("pad_sdl", {})
        nome = ac.nome_atteso(altro, cache)
        dispositivi = None
        if not nome:
            dispositivi = self._dispositivi_dolphin()
            if dispositivi is None:
                return {"errore": "chiudi_dolphin"}
            nome = ac.scegli_sdl(dispositivi, altro)
            if not nome:
                core.log_errore(f"controller_auto: Dolphin non vede il pad {altro} come SDL: {dispositivi}")
                return {"errore": "non_visto", "dispositivi": dispositivi}
            cache[ac.chiave_pad(altro)] = nome
            core.scrivi_config(self._conf)
        dev = f"SDL/0/{nome}"
        if da_capo or not prof or prof["backend"] != "sdl":
            righe = ac.leggi(ac.predefinito())
            info = ac.analizza(righe)
            base, extra = ac.converti_backend(info, "sdl")
        else:  # già SDL: tengo i tasti, cambio solo il nome del dispositivo
            righe = ac.leggi(f)
            base, extra = prof["base"], prof["extra"]
        ac.scrivi(f, ac.inverti(ac.componi(righe, dev, base, extra), self._conf.get("cam_inverti"))[0])
        st = self._controller_ini_sistema(dolphin)
        st["dispositivo"] = dev
        return st

    def _controller_ini_sistema(self, dolphin):
        """Dopo aver scritto il profilo: anche gli INI delle versioni lo usano (PadProfile1), poi lo stato aggiornato."""
        import app_controller as ac
        st = ac.stato(dolphin, self._ini_versioni(dolphin))
        for g in st["ini_senza"]:
            ac.metti_nei_giochi(self._ini_versioni(dolphin)[g])
        return self.controller_stato()

    @protetto
    def controller_sistema(self):
        """Gli INI del gioco che non usano il profilo dell'app: glielo metto (e creo il profilo se manca)."""
        import app_controller as ac
        dolphin = core.trova_dolphin(self._conf)
        if not dolphin:
            return {"errore": "dolphin"}
        f = ac.file_profilo(dolphin)
        if not f.is_file():
            f.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ac.predefinito(), f)
        st = ac.stato(dolphin, self._ini_versioni(dolphin))
        for g in st["ini_senza"]:
            ac.metti_nei_giochi(self._ini_versioni(dolphin)[g])
        return self.controller_stato()

    @protetto
    def impostazioni_gioco(self):
        """Interruttori di avvio (pagina Impostazioni): messaggi di Dolphin, FPS, schermo intero, solo il gioco."""
        dolphin = core.trova_dolphin(self._conf)
        gv = core.grafica_valori(dolphin, self._conf.get("ultima_versione") or "GK2E52") if dolphin else {}
        return {"osd": bool(self._conf.get("notifiche_dolphin", False)), "fps": bool(gv.get("fps")),
                "intero": bool(self._conf.get("gioca_intero", True)), "solo": bool(self._conf.get("gioca_solo", True)),
                "sopra": self._sopra(), "bordi": bool(self._conf.get("schermo_senza_bordi", True)),
                "tasti": bool(self._conf.get("tasti_auto", True))}

    @protetto
    def grafica_android_salva(self, valori):
        """Impostazioni grafiche per lo zip Android (non toccano questo PC)."""
        self._conf["grafica_android"] = {k: v for k, v in valori.items() if k in core.ANDROID_BASE}
        core.scrivi_config(self._conf)
        return True

    @protetto
    def grafica_applica(self, valori):
        """valori = {chiave: valore} da scrivere in tutte le versioni installate (+ "intero" in Dolphin.ini)."""
        dolphin = core.trova_dolphin(self._conf)
        if not dolphin:
            return {"errore": "dolphin"}
        aperto = bool(core.exe_dolphin_aperti())
        valori = dict(valori)
        intero = valori.pop("intero", None)
        bordi = valori.pop("bordi", None)
        globali = valori.pop("globali", False)
        osd = valori.pop("osd", None)
        fps30 = valori.pop("fps30", None)
        fatti = []
        if fps30 is not None:  # 30 fps = spengo il codice $60fps (60 fps = lo riaccendo) in tutte le versioni installate
            db = next(c for c in core.carica_codici_db() if c["id"] == "60fps")
            for g, nome in core.NOMI_VERSIONE.items():
                ini = Path(dolphin) / "GameSettings" / f"{g}.ini"
                if ini.exists() and g in db["versioni"]:
                    core.backup_file(ini, "GameSettings")
                    core.scrivi_codici_ini(ini, [] if fps30 else [("$60fps", db["versioni"][g])], [("$60fps", False)] if fps30 else [])
                    fatti.append(nome)
        formato = valori.get("formato")
        if formato in (1, 2):  # 4:3 = immagine originale: widescreen spento + "4:3" acceso (vale anche partendo da uno
            # stato salvato fatto in 16:9, che ha 1.78 nella RAM); 16:9 = il contrario. (L'HUD 16:9 in 4:3 non fa niente.)
            dbc = {c["id"]: c for c in core.carica_codici_db()}
            ws, q = dbc["widescreen"], dbc["aspetto_43"]
            for g, nome in core.NOMI_VERSIONE.items():
                ini = Path(dolphin) / "GameSettings" / f"{g}.ini"
                if ini.exists() and g in ws["versioni"] and core.grafica_valori(dolphin, g).get("formato") != formato:
                    core.backup_file(ini, "GameSettings")
                    on, off = (ws, q) if formato == 1 else (q, ws)
                    core.scrivi_codici_ini(ini, [(on["nome_ini"], on["versioni"][g])], [(off["nome_ini"], off is q)])
                    fatti.append(nome)
        if osd is not None:  # messaggi di Dolphin: scelta dell'app, la passa a Dolphin quando avvii dal launcher
            self._conf["notifiche_dolphin"] = bool(osd)
            core.scrivi_config(self._conf)
        if intero is not None:  # stesso interruttore del launcher: vale quando si avvia da lì
            self._conf["gioca_intero"] = bool(intero)
            core.scrivi_config(self._conf)
        if bordi is not None:  # schermo intero senza bordi: scelta dell'app, passata a Dolphin a ogni avvio
            self._conf["schermo_senza_bordi"] = bool(bordi)
            core.scrivi_config(self._conf)
        if globali or valori:
            self._conf["grafica_globali"] = bool(globali)
            core.scrivi_config(self._conf)
        if globali:  # usa le impostazioni generali di Dolphin: tolgo quelle dell'app dagli INI del gioco
            for g, nome in core.NOMI_VERSIONE.items():
                ini = Path(dolphin) / "GameSettings" / f"{g}.ini"
                if ini.exists():
                    core.backup_file(ini, "GameSettings")
                    core.grafica_togli(ini)
                    fatti.append(nome)
        elif valori:
            # INI nuovi solo per le versioni di cui hai il disco (prima: sempre GK2E52 -> su un PC di prova, che
            # ha solo il disco ITA, compariva un INI USA che poi riceveva i codici e l'avviso "Cambio costume spento (USA)")
            dischi = self._tutti_giochi(dolphin)
            for g, nome in core.NOMI_VERSIONE.items():
                ini = Path(dolphin) / "GameSettings" / f"{g}.ini"
                if ini.exists() or g in dischi:
                    core.backup_file(ini, "GameSettings")
                    core.grafica_scrivi(ini, valori)
                    fatti.append(nome)
        return {"fatti": list(dict.fromkeys(fatti)), "dolphin_aperto": aperto}

    # ------------------------------------------------------------ texture personalizzate
    def _texture(self):
        if self._tex_voci is None:
            pack = core.trova_pack(self._conf)
            re_ = core.voce_re(pack) if pack else None
            self._tex_voci = ([re_] if re_ else []) + (core.catalogo_texture(pack) if pack else [])
        return self._tex_voci

    @protetto
    def texture_stato(self):
        pack, dolphin = core.trova_pack(self._conf), core.trova_dolphin(self._conf)
        voci = self._texture()
        if not (pack and dolphin):
            return {"voci": [], "prop": {}, "estranei": 0}
        prop = core.stato_texture(dolphin, pack, voci)
        conti = core.conta_texture(pack, voci, prop)
        return {"voci": [{k: v[k] for k in ("id", "nome", "mod", "crediti", "link")} | {"file": conti[v["id"]]["diverse"]} for v in voci],
                "prop": prop, "estranei": sum(x == "?" for x in prop.values()), "modi": core.modi_texture(self._conf.get("tx_modi", {}), voci)}

    @protetto
    def texture_avanzamento(self):
        return dict(core.AVANZA_TEXTURE)

    @protetto
    def texture_modo(self, vid, modo):
        """Preferenza per pacchetto: "tutte" o "nuove" (solo le texture che RE non ha). Vale anche per l'installer."""
        modi = self._conf.setdefault("tx_modi", {})  # salvo anche "tutte": per l'Update Pack la base è "nuove"
        modi[vid] = "nuove" if modo == "nuove" else "tutte"
        core.scrivi_config(self._conf)
        return True

    @protetto
    def texture_copertina(self, vid):
        v = next(x for x in self._texture() if x["id"] == vid)
        return core.copertina_texture(v)

    @protetto
    def texture_coppia(self, vid, nome, lato=420):
        """Immagine di RE (prima) e del pacchetto (dopo). Per RE stessa: solo la sua (l'originale del gioco non c'è)."""
        v = next(x for x in self._texture() if x["id"] == vid)
        uff = core.cartella_ufficiale(core.trova_pack(self._conf))
        nuova = core.tex(v["path"], nome)
        w, h = core.Image.open(nuova).size
        prima = None if vid == "re" or not core.tex(uff, nome) else core.miniatura_texture(core.tex(uff, nome), lato)
        return {"uff": prima, "nuova": core.miniatura_texture(nuova, lato), "dim": f"{w}×{h}"}

    @protetto
    def texture_applica(self, scelte):
        """scelte = {nome file: "re" | "gioco" | id pacchetto}."""
        pack, dolphin = core.trova_pack(self._conf), core.trova_dolphin(self._conf)
        if not dolphin:
            return {"errore": "dolphin"}
        ins = self._ins = core.Installazione(dolphin)  # la pagina ne segue l'avanzamento
        ins.texture(pack, self._texture(), scelte)
        ris = ins.esegui()
        self._peso_tex = None
        if self._conf.get("compressione") and ins.nuovi:  # compressione accesa: comprimo anche quelle appena messe
            ris["comprimo"] = bool(self._avvia_compressione(solo=ins.nuovi))
        ris["dolphin_aperto"] = bool(core.exe_dolphin_aperti())
        return ris

    @protetto
    def avanzamento(self):
        """Quanti file ha già sistemato l'installazione in corso (per la barra mentre si applica)."""
        i = self._ins
        return {"fatti": i.fatti, "totale": i.totale} if i else {"fatti": 0, "totale": 0}

    # ------------------------------------------------------------ compressione texture (DDS)
    def _comp_info(self, dolphin):
        cart = core.cartelle_texture(dolphin)[0]
        pack = core.trova_pack(self._conf)
        return {"attiva": bool(self._conf.get("compressione")), "dds": len(core.compressi(cart)),
                "png": sum(1 for c, _ in core.da_comprimere(dolphin, pack) if c == cart), "texconv": bool(core.texconv())}

    def _avvia_compressione(self, solo=None, indietro=False):
        if self._lavoro and not self._lavoro.finito:
            return None
        dolphin, pack = core.trova_dolphin(self._conf), core.trova_pack(self._conf)
        self._lavoro = core.Compressione(dolphin, pack, solo, indietro)
        threading.Thread(target=self._lavoro.esegui, daemon=True).start()
        return True

    @protetto
    def comprimi(self, indietro=False):
        """Comprime tutte le texture comprimibili (o torna ai PNG). Va in sottofondo: avanzamento con lavoro_stato."""
        if not indietro and not core.texconv():
            return {"errore": "texconv"}
        if not self._avvia_compressione(indietro=indietro):
            return {"errore": "occupato"}
        self._conf["compressione"] = not indietro
        core.scrivi_config(self._conf)
        self._peso_tex = None
        return True

    @protetto
    def lavoro_stato(self):
        if not self._lavoro:
            return None
        st = self._lavoro.stato()
        if st["finito"]:
            self._peso_tex = None
        return st

    @protetto
    def lavoro_annulla(self):
        if self._lavoro:
            self._lavoro.annulla = True
            for p in getattr(self._lavoro, "passi", []):
                p.annulla = True
        return True

    # ------------------------------------------------------------ aggiungere roba al pack
    @protetto
    def aggiungi_scegli(self, modo):
        """Fa scegliere una cartella o un archivio e dice cosa contiene."""
        if modo == "cartella":
            r = self._finestra.create_file_dialog(webview.FileDialog.FOLDER)
        else:
            r = self._finestra.create_file_dialog(webview.FileDialog.OPEN, file_types=("Archivi (*.zip;*.rar;*.7z)", "Tutti i file (*.*)"))
        if not r:
            return None
        return self._analizza_aggiunta(r[0] if isinstance(r, (list, tuple)) else r)

    @protetto
    def aggiungi_percorso(self, p):
        """Come aggiungi_scegli, ma con una cartella o un archivio trascinati sulla finestra."""
        q = Path(p)
        if not (q.is_dir() or (q.is_file() and q.suffix.lower() in (".zip", ".rar", ".7z"))):
            return {"errore": "tipo"}
        return self._analizza_aggiunta(p)

    @protetto
    def trascinati_installer(self, percorsi):
        """File buttati sulla finestra: quali sono archivi dell'installer (peso + MD5 come "Ce l'ho già")."""
        cat = core.carica_moddb()["file"]
        ok, diversi, altri, ignoti = {}, [], [], []
        for p in map(Path, percorsi):
            if p.is_dir():
                altri.append(str(p))
                continue
            if not p.is_file():
                continue
            dim, md5 = p.stat().st_size, None
            trovato = None
            for c in cat:
                if c["byte"] == dim:
                    md5 = md5 or core.md5_file(p)
                    if md5 == c["md5"]:
                        trovato = c
                        break
            if trovato:
                ok[trovato["id"]] = str(p)
                self._conf.setdefault("archivi_file", {})[trovato["id"]] = str(p)
            elif any(Path(c["file"]).stem.lower() in p.stem.lower() for c in cat):  # stesso nome, file diverso (es. versione nuova)
                diversi.append(p.name)
            elif p.suffix.lower() in (".zip", ".rar", ".7z"):
                altri.append(str(p))  # skin / HUD / texture: si aggiungono come col pulsante Aggiungi
            else:
                ignoti.append(p.name)
        if ok:
            core.scrivi_config(self._conf)
        return {"ok": ok, "nomi": [c["nome"] for c in cat if c["id"] in ok], "diversi": diversi, "altri": altri, "ignoti": ignoti}

    def _aggancia_trascina(self):
        """Trascina e rilascia: con un ascoltatore "drop" registrato da Python, pywebview dà il percorso vero dei file."""
        if self._trascina_ok:
            return
        self._trascina_ok = True
        from webview.dom import DOMEventHandler
        self._finestra.dom.document.events.drop += DOMEventHandler(self._su_drop, True, False)

    def _su_drop(self, e):
        files = (e.get("dataTransfer") or {}).get("files") or []
        percorsi = [f["pywebviewFullPath"] for f in files if f.get("pywebviewFullPath")]
        if percorsi:
            self._finestra.evaluate_js(f"fileTrascinati({json.dumps(percorsi)})")

    def _analizza_aggiunta(self, p):
        try:
            cartella = core.prepara_aggiunta(p)
        except RuntimeError:
            return {"errore": "estrattore"}
        info = core.analizza_aggiunta(cartella, core.trova_pack(self._conf))
        if not info["nome"]:
            info["nome"] = Path(p).stem.replace("_", " ")
        self._aggiunta = info
        return info

    @protetto
    def aggiungi_conferma(self, tipo, nome):
        a = self._aggiunta
        if not a:
            return {"errore": "niente"}
        try:
            core.aggiungi_al_pack(core.trova_pack(self._conf), a["radice"], tipo, nome, a["hud"])
        except FileExistsError:
            return {"errore": "esiste"}
        except ValueError:
            return {"errore": "nome"}
        self._aggiunta = None
        self._tex_voci = None
        self._catalogo(forza=True)
        return {"ok": True}

    # ------------------------------------------------------------ installer (ModDB -> libreria -> Dolphin)
    def _libreria_predefinita(self):
        if self._conf.get("libreria"):
            return self._conf["libreria"]
        return str(core.cartella_app() / "Libreria")

    @protetto
    def installer_stato(self):
        dolphin = core.trova_dolphin(self._conf)
        cat = core.carica_moddb()
        lib = Path(self._libreria_predefinita())
        info = {}
        try:
            info = json.loads((lib / "libreria.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
        stato_ver = {}
        if dolphin:
            con_tex = core.versioni_texture(dolphin)
            for g in core.NOMI_VERSIONE:
                ini = Path(dolphin) / "GameSettings" / f"{g}.ini"
                codici = bool(ini.exists() and core.leggi_codici_ini(ini)["attivi"])
                stato_ver[g] = {"texture": g in con_tex, "codici": codici}
        return {"dolphin": str(dolphin) if dolphin else None, "giochi": core.trova_giochi(dolphin) if dolphin else {},
                "stato_ver": stato_ver,
                "nomi": core.NOMI_VERSIONE, "catalogo": cat, "libreria": str(lib), "installati": info.get("componenti", {}),
                "formato": info.get("formato"), "estrattore": bool(core._estrattore()), "texconv": bool(core.texconv()),
                "dolphin_aperto": bool(core.exe_dolphin_aperti()), "download": str(core.cartella_download())}

    @protetto
    def installer_gpu(self):
        """Con quale scheda video texconv converte in DDS (prova di ~1-4 s la prima volta): gpu None = solo processore,
        circa 12 volte più lento -> l'installer consiglia i PNG."""
        return core.texconv_gpu()

    @protetto
    def installer_archivi(self):
        """Archivi già scaricati (Download, Desktop, cartelle scelte prima, file scelti a mano)."""
        extra = self._conf.get("archivi_cartelle", [])
        trovati = core.cerca_archivi(extra)
        for i, p in self._conf.get("archivi_file", {}).items():  # scelto a mano o appena scaricato da ModDB: ha la precedenza
            if i in trovati and Path(p).is_file() and p != trovati[i]:
                trovati[i] = p
        for i in os.environ.get("SPIDEY_IGNORA", "").split(","):  # per provare il download: finge di non averli
            trovati.pop(i.strip(), None)
        cat = {c["id"]: c for c in core.carica_moddb()["file"]}
        for i, p in self._conf.get("archivi_file", {}).items():  # scelti a mano
            if i not in trovati and Path(p).is_file() and core.md5_file(p) == cat.get(i, {}).get("md5"):
                trovati[i] = p
        return trovati

    @protetto
    def installer_rimuovi(self, cid, prova=False):
        """Toglie un pacchetto dalla libreria (solo le sue cartelle). Non si può con la base (Spider-Man 2: RE) né se
        qualcosa del pacchetto è in uso adesso in Dolphin (skin, ragnatele, HUD, tasti o texture accese).
        prova = True: dice solo se si può e quanto pesa."""
        c = {x["id"]: x for x in core.carica_moddb()["file"]}[cid]
        pack = core.trova_pack(self._conf)
        if not pack or c.get("obbligatorio"):
            return {"errore": "ins_rim_base"}
        if c.get("aggiorna"):  # scrive dentro cartelle che ha già RE (es. 2003 Beta Suit): togliendolo sparirebbe anche quella di RE
            return {"errore": "ins_rim_aggiorna"}
        lib = Path(pack).resolve()
        cartelle = [(lib / a).resolve() for _, a in c["ricetta"]]
        generiche = {(lib / x).resolve() for x in ("Textures/RE", "Skins", "Skins/Suit Mods", "Skins/HUDs", "Skins/Webs", "Layout Controller")}
        if any(p in generiche for p in cartelle):
            return {"errore": "ins_rim_base"}

        def dentro(p):
            return bool(p) and any(Path(p).resolve().is_relative_to(x) for x in cartelle)
        dolphin = core.trova_dolphin(self._conf)
        uso = []
        if dolphin:
            voci, rag = self._catalogo()
            ins = self._installate(dolphin, voci, rag)
            for slot in ("primaria", "alternativa"):
                if ins[slot] and dentro(ins[slot]["path"]):
                    uso.append(slot)
            r = next((x for x in rag if x["id"] == ins["ragnatele"]), None)
            if r and dentro(r.get("path")):
                uso.append("ragnatele")
            hud = core.installate_hud(dolphin, core.catalogo_hud(pack), core.catalogo_tasti(pack))
            uso += [k for k in ("hud", "tasti") if hud[k] and dentro(hud[k]["path"])]
            voci_tex = self._texture()
            mie = {v["id"] for v in voci_tex if dentro(v.get("path"))}
            if mie and set(core.stato_texture(dolphin, pack, voci_tex).values()) & mie:
                uso.append("texture")
        # spazio liberato davvero: i file collegati (doppioni, o in uso in Dolphin) restano finché c'è un altro nome
        visti = {}
        for x in cartelle:
            for f in (x.rglob("*") if x.is_dir() else []):
                if f.is_file():
                    st = f.stat()
                    k = (st.st_dev, st.st_ino)
                    visti[k] = (st.st_size, st.st_nlink, visti.get(k, (0, 0, 0))[2] + 1)
        peso = sum(sz for sz, nl, n in visti.values() if nl <= n)
        if uso or prova:
            return {"uso": uso, "peso": peso, "zip": bool(core.cerca_archivi(self._conf.get("archivi_cartelle", [])).get(cid))}
        for x in cartelle:
            core._rimuovi(x)
        f = lib / "libreria.json"
        if f.is_file():
            d = json.loads(f.read_text(encoding="utf-8"))
            d.get("componenti", {}).pop(cid, None)
            core.scrivi_sicuro(f, json.dumps(d, ensure_ascii=False, indent=1))
        self._catalogo(forza=True)
        self._tex_voci = None
        return {"ok": True, "peso": peso}

    @protetto
    def installer_scegli_file(self, cid):
        """"Ce l'ho già": l'utente indica l'archivio; controllo che sia quello giusto (MD5)."""
        cat = {c["id"]: c for c in core.carica_moddb()["file"]}[cid]
        r = self._finestra.create_file_dialog(webview.FileDialog.OPEN, file_types=(f"Archivio (*{Path(cat['file']).suffix})", "Tutti i file (*.*)"))
        if not r:
            return None
        p = r[0] if isinstance(r, (list, tuple)) else r
        if core.md5_file(p) != cat["md5"]:
            return {"errore": "md5"}
        self._conf.setdefault("archivi_file", {})[cid] = p
        cart = self._conf.setdefault("archivi_cartelle", [])
        if str(Path(p).parent) not in cart:
            cart.append(str(Path(p).parent))  # nella stessa cartella magari ci sono anche gli altri
        core.scrivi_config(self._conf)
        return p

    @protetto
    def installer_scarica(self, cid):
        """Apre la pagina di download di ModDB in una finestra dell'app: il file finisce in Download da solo."""
        cat = {c["id"]: c for c in core.carica_moddb()["file"]}[cid]
        vecchia = self._fin_moddb.get(cid)
        if vecchia:  # già aperta (anche nascosta mentre scarica): la riporto davanti, senza interrompere niente
            try:
                vecchia.show()
                vecchia.restore()
                return True
            except Exception:  # noqa: BLE001
                self._fin_moddb.pop(cid, None)
        DOWNLOAD.pop(cat["file"], None)
        self._moddb_chiusa.discard(cid)
        fin = webview.create_window(f"ModDB · {cat['nome']}", url="https://www.moddb.com" + cat["start"], width=900, height=620)
        self._fin_moddb[cid] = fin

        def chiusa():
            self._moddb_chiusa.add(cid)
            self._fin_moddb.pop(cid, None)
            st = DOWNLOAD.get(cat["file"])
            if st and st["stato"] == "scarico":  # chiusa a metà: il download si ferma, il pezzo scaricato va tolto
                st["stato"] = "errore"
                threading.Timer(2.0, _togli_scaricato_male, args=(st["file"],)).start()
        fin.events.closed += chiusa
        return True

    @protetto
    def installer_annulla_download(self, cid):
        """"Annulla" sul download: fermo davvero (chiudo la sua finestra ModDB nascosta) e tolgo il file a metà."""
        cat = {c["id"]: c for c in core.carica_moddb()["file"]}[cid]
        fin = self._fin_moddb.pop(cid, None)
        st = DOWNLOAD.get(cat["file"])
        if st and st["stato"] == "scarico":
            st["stato"] = "errore"
        if fin:
            try:
                fin.destroy()
            except Exception:  # noqa: BLE001
                pass
        if st and st["stato"] != "finito":
            threading.Timer(2.0, _togli_scaricato_male, args=(st["file"],)).start()
        return True

    @protetto
    def installer_download(self, cid):
        """Avanzamento del download in corso (dalla finestra ModDB) e, a fine, il controllo MD5."""
        cat = {c["id"]: c for c in core.carica_moddb()["file"]}[cid]
        st = DOWNLOAD.get(cat["file"])
        fin = self._fin_moddb.get(cid)
        if not st:
            return {"stato": "chiusa" if cid in self._moddb_chiusa else "attesa"}
        if st["stato"] == "scarico" and fin and not st.get("nascosta"):
            try:  # il download è partito: la finestra di ModDB non serve più, la nascondo (chiuderla lo fermerebbe)
                fin.hide()
                st["nascosta"] = True
            except Exception:  # noqa: BLE001
                pass
        if st["stato"] in ("finito", "errore") and fin:
            try:
                fin.destroy()
            except Exception:  # noqa: BLE001
                pass
            self._fin_moddb.pop(cid, None)
        if st["stato"] == "finito":
            ok = Path(st["file"]).is_file() and core.md5_file(st["file"]) == cat["md5"]
            if ok:  # ricordato subito: non serve ritrovarlo con la ricerca
                self._conf.setdefault("archivi_file", {})[cid] = st["file"]
                core.scrivi_config(self._conf)
            else:  # scaricato ma sbagliato (pagina cambiata, file rovinato): non lo lascio in Download
                _togli_scaricato_male(st["file"])
            return {"stato": "ok" if ok else "md5", "file": st["file"]}
        return {k: v for k, v in st.items() if k != "nascosta"}

    @protetto
    def installer_scegli_libreria(self):
        r = self._finestra.create_file_dialog(webview.FileDialog.FOLDER)
        if not r:
            return None
        p = Path(r[0] if isinstance(r, (list, tuple)) else r)
        if p.name.lower() != "libreria" and any(p.iterdir()):
            p = p / "Spider-Man 2 Libreria"  # mai mischiare con altri file: sottocartella apposta
        self._conf["libreria"] = str(p)
        core.scrivi_config(self._conf)
        return str(p)

    @protetto
    def installer_avvia(self, scelte):
        """Un avvio alla volta: tra il clic e la partenza del lavoro passano secondi (ricerca degli zip, MD5) e un doppio
        clic faceva partire due installazioni (o due finestre di salvataggio per l'export)."""
        if not self._avvio_lock.acquire(blocking=False):
            return {"errore": "occupato"}
        try:
            return self._installer_avvia(scelte)
        finally:
            self._avvio_lock.release()

    def _installer_avvia(self, scelte):
        """scelte = {"ids": [...], "versioni": [...], "formato": "dds"|"png", "cancella": bool, "salvataggi": bool}"""
        if self._lavoro and not self._lavoro.finito:
            return {"errore": "occupato"}
        dolphin = core.trova_dolphin(self._conf)
        if not dolphin:
            return {"errore": "dolphin"}
        archivi = self.installer_archivi() if scelte["ids"] else {}
        mancano = [i for i in scelte["ids"] if i not in archivi]
        if mancano:
            return {"errore": "mancano", "ids": mancano}
        lib = self._libreria_predefinita()
        gia = (Path(lib) / "libreria.json").exists()  # c'è già un'installazione: tengo le scelte attuali
        oc = core.OC_CPU.get(self._conf.get("grafica_cpu") or core.processore()["livello"])
        gioco = core.InstallaGioco(dolphin, lib, scelte["versioni"], scelte.get("salvataggi", False), mantieni=gia,
                                   modi=self._conf.get("tx_modi"), conf=self._conf, cam_modi=self._cam_modi(),
                                   cam_opzioni=self._conf.get("cam_opzioni"), oc=oc)
        passi = [gioco]
        if scelte["ids"]:
            passi.insert(0, core.Libreria(lib, {i: archivi[i] for i in scelte["ids"]}, scelte.get("formato", "dds"),
                                          scelte.get("cancella", False)))
        self._lavoro = LavoroInstaller(*passi)

        def dopo():
            self._lavoro.esegui()
            if not self._lavoro.errore:
                self._conf["pack"] = lib  # da ora l'app usa la libreria nuova
                core.scrivi_config(self._conf)
                self._voci = None
                self._tex_voci = None
                self._peso_tex = None
        threading.Thread(target=dopo, daemon=True).start()
        return True

    # ------------------------------------------------------------ esportazione della mod pronta
    @protetto
    def esporta_info(self):
        dolphin = core.trova_dolphin(self._conf)
        if not dolphin:
            return {"errore": "dolphin"}
        con_tex = core.versioni_texture(dolphin)
        pronte = [g for g in core.NOMI_VERSIONE if g in con_tex and (Path(dolphin) / "GameSettings" / f"{g}.ini").exists()]
        return {"versioni": pronte, "nomi": core.NOMI_VERSIONE, "piattaforme": core.PIATTAFORME,
                "android": core.ANDROID_BASE | self._conf.get("grafica_android", {}), "mac": core.MAC_BASE | self._conf.get("grafica_mac", {}),
                "dolphin_aperto": bool(core.exe_dolphin_aperti()),
                "rag_alt": bool(self._conf.get("rag_alt"))}  # ragnatele dell'alternativo: le cambia l'app, nello zip no

    @protetto
    def esporta_avvia(self, opz):
        if not self._avvio_lock.acquire(blocking=False):
            return {"errore": "occupato"}
        try:
            return self._esporta_avvia(opz)
        finally:
            self._avvio_lock.release()

    def _esporta_avvia(self, opz):
        if self._lavoro and not self._lavoro.finito:
            return {"errore": "occupato"}
        dolphin = core.trova_dolphin(self._conf)
        nome = f"SM2 Enhanced - {opz['nome_piattaforma']}.zip"
        r = self._finestra.create_file_dialog(webview.FileDialog.SAVE, directory=str(core.cartella_download()),
                                              save_filename=nome, file_types=("Zip (*.zip)",))
        if not r:
            return None
        dest = Path(r[0] if isinstance(r, (list, tuple)) else r)
        if dest.suffix.lower() != ".zip":
            dest = dest.with_suffix(".zip")
        grafica, formato, fps30 = None, opz.get("formato", "dds"), False
        if opz["piattaforma"] == "android":  # per Android valgono le impostazioni di Grafica › Android
            grafica = core.ANDROID_BASE | self._conf.get("grafica_android", {})
            formato, fps30 = grafica["tex"], grafica["fps30"]
        elif opz["piattaforma"] == "mac":  # per il Mac valgono le impostazioni di Grafica › Mac
            grafica = core.MAC_BASE | self._conf.get("grafica_mac", {})
            formato = grafica["tex"]
        self._lavoro = core.Esportazione(dolphin, dest, opz["piattaforma"], opz.get("controller"), opz["versioni"],
                                         formato, fps30, opz.get("salvataggi", False), opz.get("leggimi", ""), grafica,
                                         opz.get("parti", ("texture", "ini", "controller")))
        threading.Thread(target=self._lavoro.esegui, daemon=True).start()
        return str(dest)

    # ------------------------------------------------------------ launcher (pagina Gioca)
    @protetto
    def gioca_stato(self, aggiorna=False):
        """Tutto quello che serve alla pagina Gioca, anche al primo avvio (senza Dolphin o senza gioco)."""
        dolphin = core.trova_dolphin(self._conf)
        giochi = self._tutti_giochi(dolphin, aggiorna)
        exe = core.trova_exe_dolphin(self._conf, dolphin)
        if exe and str(exe) != self._conf.get("dolphin_exe"):
            self._conf["dolphin_exe"] = str(exe)
            core.scrivi_config(self._conf)
        gv = core.grafica_valori(dolphin, self._conf.get("ultima_versione") or "GK2E52") if dolphin else {}
        return {"pad": self._pad(), "dolphin": str(dolphin) if dolphin else None, "exe": str(exe) if exe else None,
                "rag_alt": bool(self._conf.get("rag_alt")),  # per la finestra Comandi: cambiano solo con l'app aperta
                "versione_dolphin": core.versione_exe_dolphin(exe), "dell_app": core.dolphin_dell_app(exe),
                "aggiornamento": self._ultima, "app_agg": self._agg_info(), "aperto": bool(core.exe_dolphin_aperti()), "nomi": core.NOMI_VERSIONE,
                "giochi": {g: {"disco": p, "file": Path(p).name} for g, p in giochi.items()},
                "persi": {g: p for g, p in self._conf.get("dischi", {}).items() if g not in giochi and not Path(p).is_file()},
                "mod": core.mod_versioni(dolphin) if dolphin else {},
                "ultima": self._conf.get("ultima_versione"),
                "tutte": self._conf.get("cam_tutte"), "solo": self._conf.get("gioca_solo", True),
                "intero": self._conf.get("gioca_intero", True), "gioco": core.gioco_in_corso(),
                "trucchi": core.trucchi_accesi(dolphin) if dolphin else True, "fps": bool(gv.get("fps")),
                "da_stato": bool(self._conf.get("gioca_da_stato", False)),
                "senza_mod": bool(self._conf.get("senza_mod")), "libreria": bool(core.trova_pack(self._conf)),
                "orig": core.SKIN_ORIGINALE.is_file()}

    def _tutti_giochi(self, dolphin, aggiorna=False):
        """Dischi aggiunti nell'app (config "dischi") + quelli nelle cartelle dei giochi di Dolphin."""
        if self._giochi is None or aggiorna:
            g = {k: p for k, p in self._conf.get("dischi", {}).items() if Path(p).is_file()}
            if dolphin:
                for k, p in core.trova_giochi(dolphin).items():
                    g.setdefault(k, p)
            self._giochi = g
        if self._giochi and self._dal_disco_manca() and not self._orig_in_corso \
                and set(self._giochi.values()) - self._orig_provati:
            self._orig_in_corso = True
            threading.Thread(target=self._skin_originale_dal_disco, args=(dict(self._giochi), dolphin), daemon=True).start()
        return self._giochi

    def _dal_disco_manca(self):
        """Manca ancora qualcosa che l'app prende dal disco del gioco (costume originale, modello 3D)?"""
        return not core.SKIN_ORIGINALE.is_file() or not core.modello_pronto(risorsa("contenuti/modello_pose.json"))

    def _skin_originale_dal_disco(self, giochi, dolphin):
        """Il costume originale NON è dentro l'app: appena l'app sa dov'è il gioco lo prende dal suo disco (DolphinTool,
        che c'è accanto a Dolphin.exe, estrae l'archivio del gioco in una cartella temporanea; ~2 s) e lo salva in APPDATA.
        Se non si può (Dolphin vecchio senza DolphinTool...), lo prende dalla memoria la prima volta che giochi."""
        import shutil
        try:
            exe = core.trova_exe_dolphin(self._conf, dolphin)
            tool = Path(exe).parent / "DolphinTool.exe" if exe else None
            for disco in giochi.values():
                if disco in self._orig_provati or not self._dal_disco_manca():
                    continue
                self._orig_provati.add(disco)
                if not tool or not tool.is_file():
                    continue
                tmp = core.CONF_DIR / "_disco_tmp"
                pr = None
                try:
                    shutil.rmtree(tmp, ignore_errors=True)
                    cartella, nome, _ = core.SKIN_PAK
                    pr = avvia_esterno([str(tool), "extract", "-i", str(disco), "-s", cartella, "-o", str(tmp), "-q"],
                                       creationflags=subprocess.CREATE_NO_WINDOW)
                    pr.wait(timeout=180)
                    pak = tmp / "files" / cartella / nome
                    if pak.is_file() and not core.SKIN_ORIGINALE.is_file() and core.skin_originale_dal_pak(pak):
                        self._skin_originale_pronta("disco")
                    pose = risorsa("contenuti/modello_pose.json")
                    if pak.is_file() and not core.modello_pronto(pose) and core.modello_dal_pak(pak, pose):
                        self._modello_pronto()
                except Exception as e:  # noqa: BLE001
                    core.log_errore(f"costume originale dal disco {disco}: {e!r}")
                finally:
                    if pr and pr.poll() is None:  # scaduto il tempo: DolphinTool non deve restare acceso
                        pr.kill()
                    shutil.rmtree(tmp, ignore_errors=True)
        finally:
            self._orig_in_corso = False

    def _skin_originale_dalla_ram(self):
        """Riserva: col gioco aperto, se il costume originale manca ancora, lo leggo dalla memoria (ogni 10 s al massimo)."""
        import time
        if core.SKIN_ORIGINALE.is_file() or time.time() - self._orig_ram < 10:
            return
        self._orig_ram = time.time()
        with self._dme_lock:
            dme = core.aggancia_dme()
            ok = bool(dme) and core.skin_originale_dalla_ram(dme)
        if ok:
            self._skin_originale_pronta("memoria")

    def _skin_originale_pronta(self, da):
        self._log_menu(f"costume originale preso dal gioco ({da})")
        try:
            self._finestra.evaluate_js("origPronta()")
        except Exception:  # noqa: BLE001
            pass

    def _modello_pronto(self):
        self._log_menu("modello 3D preso dal gioco (disco)")
        for f in (self._finestra, getattr(self, "_menu", None)):
            try:
                if f:
                    f.evaluate_js("typeof modelloPronto === 'function' && modelloPronto()")
            except Exception:  # noqa: BLE001
                pass

    @protetto
    def modello_spidey(self):
        """Il modello 3D di Spidey ricostruito dal disco del gioco di chi usa l'app ({"gioco", "idle"}), o None se l'app non
        ha ancora trovato il gioco."""
        return core.modello_json() if core.modello_pronto(risorsa("contenuti/modello_pose.json")) else None

    @protetto
    def skin_originale(self):
        """Il costume originale preso dal gioco di chi usa l'app (data URL), o None se l'app non l'ha ancora trovato."""
        f = core.SKIN_ORIGINALE
        return "data:image/png;base64," + base64.b64encode(f.read_bytes()).decode() if f.is_file() else None

    def _metti_dischi(self, trovati):
        dischi = self._conf.setdefault("dischi", {})
        dischi.update({g: str(p) for g, p in trovati.items()})
        core.scrivi_config(self._conf)
        self._giochi = None
        dolphin = core.trova_dolphin(self._conf)
        if dolphin and not core.exe_dolphin_aperti():  # così li vede anche Dolphin nella sua lista
            for c in {str(Path(p).parent) for p in trovati.values()}:
                core.aggiungi_cartella_giochi(dolphin, c)

    @protetto
    def gioca_aggiungi_gioco(self):
        """L'utente sceglie il file (o i file) del gioco: tengo quelli che sono Spider-Man 2."""
        tipi = ("Giochi GameCube (*.iso;*.rvz;*.gcm;*.gcz;*.ciso;*.wia;*.tgc)", "Tutti i file (*.*)")
        r = self._finestra.create_file_dialog(webview.FileDialog.OPEN, allow_multiple=True, file_types=tipi)
        if not r:
            return None
        trovati, altri = {}, []
        for p in (r if isinstance(r, (list, tuple)) else [r]):
            g = core.id_disco(p)
            if g:
                trovati[g] = p
            else:
                altri.append(Path(p).name)
        if trovati:
            self._metti_dischi(trovati)
        return {"trovati": sorted(trovati), "altri": altri}

    @protetto
    def gioca_cerca_giochi(self):
        """Cerca Spider-Man 2 nei posti soliti del PC (Desktop, Download, Documenti, radici dei dischi)."""
        trovati = core.cerca_dischi(core.cartelle_da_cercare())
        nuovi = {g: p for g, p in trovati.items() if g not in (self._giochi or {})}
        if trovati:
            self._metti_dischi(trovati)
        return {"trovati": sorted(trovati), "nuovi": sorted(nuovi)}

    @protetto
    def gioca_installa_dolphin(self):
        """Scarica e prepara l'ultima Dolphin nella cartella dell'app (anche per aggiornarla)."""
        if self._lavoro and not self._lavoro.finito:
            return {"errore": "occupato"}
        if core.exe_dolphin_aperti():
            return {"errore": "gioca_aperto"}
        job = core.InstallaDolphin()
        self._lavoro = job

        def via():
            job.esegui()
            if job.exe and not job.errore:
                self._conf["dolphin_exe"], self._conf["dolphin"] = str(job.exe), str(job.exe.parent / "User")
                core.scrivi_config(self._conf)
                self._giochi = None
        threading.Thread(target=via, daemon=True).start()
        return True

    @protetto
    def gioca_fps(self, on):
        """Contatore FPS di Dolphin: negli INI del gioco (o in GFX.ini se si usano le impostazioni di Dolphin)."""
        dolphin = core.trova_dolphin(self._conf)
        if not dolphin:
            return {"errore": "dolphin"}
        if self._conf.get("grafica_globali"):
            if core.exe_dolphin_aperti():
                return {"errore": "gr_chiudi"}
            ini = Path(dolphin) / "Config" / "GFX.ini"
            core.backup_file(ini, "Config")
            core.scrivi_ini_valori(ini, {("Settings", "ShowFPS"): "True" if on else "False"})
            return {"dolphin_aperto": False}
        return self.grafica_applica({"fps": bool(on)})

    @protetto
    def gioca_scegli_exe(self):
        r = self._finestra.create_file_dialog(webview.FileDialog.OPEN, file_types=("Dolphin (*.exe)",))
        if not r:
            return None
        p = Path(r[0] if isinstance(r, (list, tuple)) else r)
        if not p.name.lower().startswith("dolphin") or p.suffix.lower() != ".exe":
            return {"errore": "gioca_exe_sbagliato"}
        self._conf["dolphin_exe"] = str(p)
        core.scrivi_config(self._conf)
        return str(p)

    @protetto
    def gioca_live(self):
        """Per la pagina Gioca, ogni paio di secondi: Dolphin aperto? quale gioco gira?"""
        fin = core.finestre_dolphin()
        return {"aperto": bool(core.exe_dolphin_aperti()), "gioco": core.gioco_in_corso(fin), "stati_rev": self._guardia.rev,
                "pad": self._pad()}

    def _pad(self):
        """Controller collegati e se il profilo dei tasti va bene per loro (per il launcher, prima di giocare)."""
        import app_controller as ac
        try:
            dolphin = core.trova_dolphin(self._conf)
            f = ac.file_profilo(dolphin) if dolphin else None
            prof = ac.analizza(ac.leggi(f)) if f and f.is_file() else (ac.analizza(ac.leggi(ac.predefinito())) if dolphin else None)
            pad = ac.pad_collegati()
            esito, quale = ac.verdetto(prof, pad, self._conf.get("pad_sdl", {}))
            return {"esito": esito, "pad": quale, "tutti": pad}
        except Exception:  # noqa: BLE001 - è solo un aiuto
            return None

    @protetto
    def gioca_stati(self, gid):
        """Slot della versione con foto, versione di Dolphin, compatibilità e codici cambiati (con i titoli leggibili)."""
        dolphin = core.trova_dolphin(self._conf)
        if not dolphin:
            return {"errore": "dolphin"}
        ver = core.versione_exe_dolphin(core.trova_exe_dolphin(self._conf, dolphin))
        titoli = {c["nome_ini"]: c["titolo"] for c in core.carica_codici_db()}
        titoli.update({c["nome"] if c["nome"].startswith("$") else "$" + c["nome"]: {"it": c["nome"]} for c in self._conf.get("codici_miei", [])})
        stati = core.stati_salvati(dolphin, gid, ver)
        # i codici Gecko stanno DENTRO lo stato (RAM): partendo da lì girano quelli di quando l'hai fatto, anche se
        # nell'INI sono cambiati (John: menu rovinato dall'HUD 16:9 vecchio partendo dallo stato 1)
        gecko = {c["nome_ini"] for c in core.carica_codici_db() if c.get("tipo") == "gecko"}
        cambio = self._gecko_cambio(dolphin, gid, gecko)
        for s in stati:
            if any(k in s for k in ("accesi", "spenti", "cambiati")):
                s["gecko_vecchi"] = any(x in gecko for k in ("accesi", "spenti", "cambiati") for x in s.get(k, []))
            else:  # stato senza i dati dell'app (salvato senza l'app aperta): più vecchio dell'ultimo cambio dei Gecko
                s["gecko_vecchi"] = bool(cambio and s.get("data", 0) < cambio)
            if s.get("n") in core.SLOT_STATI and s.get("n", 99) <= 8:  # slot 1-8: li aggiorno io ai codici di adesso
                s["gecko_vecchi"] = False  # appena parte il gioco (_sorveglia_codici) e prima di caricarli: niente avviso
            for k in ("accesi", "spenti", "cambiati"):
                if k in s:
                    s[k] = [{"nome": x, "titolo": titoli.get(x)} for x in s[k]]
        return {"stati": stati, "versione": ver}

    def _gecko_cambio(self, dolphin, gid, gecko):
        """Quando sono cambiati per l'ultima volta i codici Gecko accesi nell'INI della versione (impronta delle righe in
        config gecko_cambio): la prima volta vale la data dell'INI (l'app li aggiorna lì dentro)."""
        import time
        uso = core.codici_in_uso(dolphin, gid)["codici"]
        imp = hashlib.md5(repr(sorted((n, h) for n, h in uso.items() if n in gecko)).encode()).hexdigest()
        reg = self._conf.setdefault("gecko_cambio", {}).get(gid)
        if not reg or reg.get("md5") != imp:
            ini = Path(dolphin) / "GameSettings" / f"{gid}.ini"
            quando = time.time() if reg else (ini.stat().st_mtime if ini.exists() else 0)
            self._conf["gecko_cambio"][gid] = reg = {"md5": imp, "quando": quando}
            core.scrivi_config(self._conf)
        return reg.get("quando", 0)

    @protetto
    def gioca_salva_stato(self, n):
        """Foto subito (prima che il gioco vada avanti), poi Maiusc+F<n> a Dolphin; il resto lo fa la guardia."""
        import time
        g = self._guardia.gid
        h = core.finestra_gioco()
        if not g or not h or not core._davanti(h):
            return {"errore": "st_err_tasti"}
        self._guardia.foto_pronte[(g, int(n))] = (time.time(), core.foto_finestra(h))
        return True if core.tasto_stato(int(n), True) else {"errore": "st_err_tasti"}

    @protetto
    def gioca_carica_stato(self, n):
        return True if core.tasto_stato(int(n), False) else {"errore": "st_err_tasti"}

    @protetto
    def gioca_elimina_stato(self, gid, n):
        dolphin = core.trova_dolphin(self._conf)
        ok = bool(dolphin) and core.elimina_stato(dolphin, gid, int(n))
        self._guardia.dimentica(gid, int(n))
        return ok

    @protetto
    def gioca_schermo_intero(self):
        return core.schermo_intero_al_volo()

    @protetto
    def gioca_apri_dolphin(self):
        """Apre Dolphin normale (per le sue impostazioni), senza gioco."""
        exe = core.trova_exe_dolphin(self._conf, core.trova_dolphin(self._conf))
        if not exe:
            return {"errore": "gioca_exe_no"}
        if not core.exe_dolphin_aperti():
            avvia_esterno([str(exe)], cwd=str(exe.parent))
        return True

    @protetto
    def gioca_chiudi(self):
        return core.chiudi_gioco()

    @protetto
    def gioca_avvia(self, gid, solo=True, intero=True, slot=None, ricorda=True):
        """Apre Dolphin direttamente sul gioco. solo = senza la finestra di Dolphin (-b: si chiude quando esci dal gioco).
        ricorda = False: avvio speciale (es. da Spider-Cam), non cambia le scelte del launcher."""
        dolphin = core.trova_dolphin(self._conf)
        if core.exe_dolphin_aperti():
            return {"errore": "gioca_aperto"}
        exe = core.trova_exe_dolphin(self._conf, dolphin)
        disco = self._tutti_giochi(dolphin).get(gid)
        if not exe:
            return {"errore": "gioca_exe_no"}
        if not disco or not Path(disco).is_file():
            return {"errore": "gioca_err_disco", "disco": disco or gid}
        trucchi = False
        if not core.trucchi_accesi(dolphin):  # senza i trucchi accesi i codici della mod non partono
            ini = Path(dolphin) / "Config" / "Dolphin.ini"
            core.backup_file(ini, "Config")
            core.scrivi_ini_valori(ini, {("Core", "EnableCheats"): "True"})
            trucchi = True
        core.aggiorna_codici_vecchi(Path(dolphin) / "GameSettings" / f"{gid}.ini", gid)  # es. vecchio HUD -> HUD con interruttore
        core.allinea_camera(Path(dolphin) / "GameSettings" / f"{gid}.ini", gid, self._cam_modi(), self._conf.get("cam_opzioni"))
        core.spegni_di_serie(dolphin, exe, gid)  # codici di serie di Dolphin accesi a mano: si pestano coi nostri
        try:
            import app_controller
            app_controller.aggiorna_vecchio(dolphin, self._conf)  # vecchio profilo -> L3 costume, R3 camera, Select mappa, LB HUD
            app_controller.assicura(dolphin, gid)  # anche senza mod/codici: il pad funziona col profilo dell'app
            app_controller.applica_inversione(dolphin, self._conf.get("cam_inverti"))  # camera invertita scelta nell'app
        except Exception:  # noqa: BLE001 - non deve mai bloccare l'avvio
            pass
        pad_auto = None
        try:  # il pad collegato non risponderebbe col profilo attuale: lo configuro io (la prima volta 3-4 s, poi subito)
            v = self._pad()
            if v and v["esito"] in ("sdl", "nome", "xinput") and self._conf.get("pad_auto", True):
                r = self.controller_auto()
                pad_auto = r.get("dispositivo") or (v["pad"] or {}).get("nome") if not r.get("errore") else None
        except Exception as e:  # noqa: BLE001
            core.log_errore(f"pad automatico all'avvio: {e!r}")
        tasti_auto = None
        try:  # tasti a schermo della famiglia del pad (col PS5 dall'amico il gioco mostrava ancora i tasti Xbox)
            tasti_auto = self._tasti_per_pad(dolphin)
        except Exception as e:  # noqa: BLE001 - non deve mai bloccare l'avvio
            core.log_errore(f"tasti a schermo automatici: {e!r}")
        if ricorda:
            self._conf["ultima_versione"], self._conf["gioca_solo"], self._conf["gioca_intero"] = gid, bool(solo), bool(intero)
            core.scrivi_config(self._conf)
        # -C = impostazione valida solo per questa partita (Dolphin.ini non cambia)
        # senza bordi = una finestra grande quanto lo schermo: niente cambio di modalità video entrando/uscendo (Alt+Invio),
        # molto più stabile (soprattutto sui portatili con due schede video) e le finestrelle possono starci sopra
        bordi = self._conf.get("schermo_senza_bordi", True)
        intero_arg = ["-C", f"Dolphin.Display.Fullscreen={'True' if intero else 'False'}",
                      "-C", f"Graphics.Settings.BorderlessFullscreen={'True' if bordi else 'False'}",
                      "-C", f"Dolphin.Interface.OnScreenDisplayMessages={'True' if self._conf.get('notifiche_dolphin') else 'False'}"]
        slot = int(slot) if isinstance(slot, (int, float, str)) and str(slot).isdigit() else None
        # stato salvato: con -s Dolphin lo carica mentre il gioco sta ancora caricando e a volte si pianta. Con gli slot che
        # hanno il tasto rapido (1-8) parto normale e lo carico io (F<n>) quando il gioco gira fluido.
        dopo = bool(slot) and slot in core.SLOT_TASTI
        stato = ["-s", str(core.file_stato(dolphin, gid, slot))] if slot and not dopo else []
        avvia_esterno([str(exe)] + (["-b"] if solo else []) + intero_arg + stato + ["-e", str(disco)], cwd=str(exe.parent))
        if dopo:
            threading.Thread(target=self._carica_quando_pronto, args=(gid, slot), daemon=True).start()
        return {"ok": True, "trucchi": trucchi, "dopo": dopo, "pad_auto": pad_auto, "tasti_auto": tasti_auto}

    def _tasti_per_pad(self, dolphin):
        """Prima di giocare: se il pad collegato è PlayStation e nel gioco ci sono i tasti a schermo Xbox (o il contrario),
        mette i tasti dell'altra famiglia: quelli scelti l'ultima volta per quella famiglia (config tasti_fam, scritto da
        hud_applica), se no i predefiniti. Solo se i tasti installati sono della mod (riconosciuti) e con "tasti_auto"
        acceso (Impostazioni > Quando giochi). Ritorna il nome dei tasti messi, o None."""
        if not self._conf.get("tasti_auto", True) or not dolphin:
            return None
        v = self._pad()
        fam = {"xbox": "xbox", "ps": "ps"}.get(((v or {}).get("pad") or {}).get("tipo"))
        pack = core.trova_pack(self._conf)
        if not fam or not pack:
            return None
        cat = core.catalogo_tasti(pack)
        inst = core.installate_hud(dolphin, [], cat).get("tasti")
        if not inst or inst.get("id") in (None, "?") or core.famiglia_tasti(inst["id"]) == fam:
            return None
        della = [c for c in cat if core.famiglia_tasti(c["id"]) == fam]
        base = "SPIDER" if fam == "ps" else Path(core.SCELTE_BASE["tasti"]).name.upper()
        voce = (next((c for c in della if c["id"] == self._conf.get("tasti_fam", {}).get(fam)), None)
                or next((c for c in della if base in c["id"].upper()), None) or (della[0] if della else None))
        if not voce:
            return None
        ins = core.Installazione(dolphin)
        ins.tasti(pack, voce["default"], self._conf.get("disegno_controller", {}))
        ins.esegui()
        self._log_menu(f"tasti a schermo: pad {fam} -> {voce['id']} (prima {inst['id']})")
        return voce["nome"]

    def _carica_quando_pronto(self, gid, slot):
        import time
        try:
            pronto = core.aspetta_gioco_pronto(gid)
            if not core.gioco_in_corso():
                return  # chiuso prima
            self._codici_pronti.wait(20)  # prima gli stati aggiornati ai codici di adesso (vedi _sorveglia_codici)
            time.sleep(0.3 if pronto else 0)
            core.tasto_stato(slot, False)
        except Exception:  # noqa: BLE001 - filo in sottofondo: almeno nel registro
            core.log_errore(traceback.format_exc())

    @protetto
    def mostra_file(self, percorso):
        avvia_esterno(["explorer", "/select,", str(Path(percorso))])
        return True

    # ------------------------------------------------------------ Spider-Cam
    def _camera(self):
        if self._cam is None:
            import app_cam
            self._cam = app_cam.Camera()
        return self._cam

    @protetto
    def cam_info(self):
        import app_cam
        if "cam_preset" not in self._conf:  # prima volta: prendo le configurazioni della vecchia Spider-Cam
            vecchi, ultimi = ({}, None) if core.DA_ZERO else app_cam.preset_spidercam()
            self._conf["cam_preset"] = vecchi
            if ultimi and "cam_ultimi" not in self._conf:
                self._conf["cam_ultimi"] = ultimi
            core.scrivi_config(self._conf)
        dolphin = core.trova_dolphin(self._conf)
        fissi = {k: {"it": it, "en": en, **app_cam.NOMI_ALTRE_LINGUE.get(k, {}), "valori": {g: list(v[g]) for g in app_cam.GRUPPI}, "fov": fov}
                 for k, (it, en, v, fov) in app_cam.PRESET_FISSI.items()}
        orig = {g: list(o) for g, (_, o) in app_cam.cs.GRUPPI.items()}
        return {"fissi": fissi, "utente": self._conf.get("cam_preset", {}), "ultimi": self._conf.get("cam_ultimi"),
                "originali": orig, "gruppi": app_cam.GRUPPI, "collegati": list(app_cam.cs.COLLEGATI),
                "trucchi": app_cam.trucchi_attivi(dolphin) if dolphin else None,
                "versione_salva": self._conf.get("cam_versione", "GK2E52"),
                "codice": any(core.leggi_codici_ini(Path(dolphin) / "GameSettings" / f"{g}.ini")["presenti"] & {app_cam.cs.NOME_CODICE, *app_cam.cs.VECCHI_CAMERA}
                              for g in core.NOMI_VERSIONE if dolphin and (Path(dolphin) / "GameSettings" / f"{g}.ini").is_file()),
                "ultima": self._conf.get("ultima_versione"),
                "dischi": sorted(g for g, p in self._tutti_giochi(dolphin).items() if Path(p).is_file()) if dolphin else [],
                "versioni": [{"id": g, "nome": n, "ini": bool(dolphin and (Path(dolphin) / "GameSettings" / f"{g}.ini").exists())}
                             for g, n in core.NOMI_VERSIONE.items()]}

    @protetto
    def cam_avvia(self, gid):
        """Avvia il gioco IN FINESTRA con il codice della camera spento solo per questa partita: così gli slider si vedono
        dal vivo (col codice acceso il gioco li riscriverebbe). Dolphin legge i codici all'avvio: appena il gioco è partito
        il codice torna acceso nell'INI (vale dalla prossima partita)."""
        import app_cam
        dolphin = core.trova_dolphin(self._conf)
        if not dolphin:
            return {"errore": "err_dolphin"}
        if core.exe_dolphin_aperti():
            return {"errore": "gioca_aperto"}
        self._riaccendi_camera()  # caso mai fosse rimasto qualcosa da una volta prima
        ini = Path(dolphin) / "GameSettings" / f"{gid}.ini"
        accesi = core.posizioni_attivi(ini, {app_cam.cs.NOME_CODICE, *app_cam.cs.VECCHI_CAMERA}) if ini.exists() else {}
        if accesi:
            core.backup_file(ini, "GameSettings")
            core.scrivi_codici_ini(ini, [], [(n, False) for n in accesi])
            self._conf.setdefault("cam_da_riaccendere", {})[gid] = accesi  # anche se l'app si chiude: lo rimetto al prossimo avvio
            core.scrivi_config(self._conf)
        r = self.gioca_avvia(gid, self._conf.get("gioca_solo", True), False, None, False)
        if not r or r.get("errore"):
            self._riaccendi_camera(subito=True)
            return r
        threading.Thread(target=self._aspetta_e_riaccendi, args=(gid,), daemon=True).start()
        return dict(r, spento=bool(accesi))

    @protetto
    def cam_riavvia(self, gid):
        """Codice camera acceso nella partita in corso: chiudo il gioco (Dolphin può chiedere conferma), aspetto che si
        chiuda e lo riapro senza codice."""
        import time
        core.chiudi_gioco()
        for _ in range(120):
            time.sleep(0.5)
            if not core.exe_dolphin_aperti():
                time.sleep(0.5)
                return self.cam_avvia(gid)
        return {"errore": "cam_non_chiuso"}

    def _aspetta_e_riaccendi(self, gid):
        """Il codice torna acceso quando il gioco è partito da qualche secondo (codici già letti) o se Dolphin si chiude."""
        import time
        visto, inizio = None, time.time()
        while time.time() - inizio < 300:
            time.sleep(1)
            if core.gioco_in_corso() == gid:
                if not visto and self._sopra():  # appena compare: sopra l'app, vicino agli slider
                    time.sleep(1.5)
                    core.gioco_sopra(True, sistema=True, app=TITOLO)
                visto = visto or time.time()
                if time.time() - visto > 4:
                    break
            elif time.time() - inizio > 20 and not core.exe_dolphin_aperti():
                break
        self._riaccendi_camera(subito=True)

    def _riaccendi_camera(self, subito=False):
        """Rimette accesi i codici camera spenti da cam_avvia (solo con Dolphin chiuso, o subito se richiesto)."""
        da_fare = self._conf.get("cam_da_riaccendere") or {}
        if not da_fare or (not subito and core.exe_dolphin_aperti()):
            return
        dolphin = core.trova_dolphin(self._conf)
        for gid, nomi in da_fare.items():
            ini = Path(dolphin) / "GameSettings" / f"{gid}.ini" if dolphin else None
            if ini and ini.exists():  # al suo posto; se intanto l'hai salvato da Spider-Cam è già acceso e non cambia niente
                core.riaccendi_codici(ini, nomi if isinstance(nomi, dict) else {n: 999 for n in nomi})
                # gioca_avvia, con la camera classica spenta, aveva spento anche il Gecko e il programma: li riaccendo
                core.allinea_camera(ini, gid, self._cam_modi(), self._conf.get("cam_opzioni"))
        self._conf["cam_da_riaccendere"] = {}
        core.scrivi_config(self._conf)

    @protetto
    def cam_accendi(self, si):
        self._camera().accendi(si)
        return True

    @protetto
    def cam_imposta(self, valori, fov):
        self._camera().imposta(valori, fov)
        # col codice camera acceso il gioco riscriverebbe i valori: cambio anche il codice caricato in Dolphin (ar_vivo),
        # così gli slider si vedono dal vivo senza riavviare il gioco senza codice
        self._cam_attesa = (valori, fov)
        if not getattr(self, "_cam_filo", None) or not self._cam_filo.is_alive():
            self._cam_filo = threading.Thread(target=self._cam_applica_vivo, daemon=True)
            self._cam_filo.start()
        return True

    def _cam_applica_vivo(self):
        import time
        fine = time.time() + 40
        while getattr(self, "_cam_attesa", None) and time.time() < fine:
            valori, fov = self._cam_attesa
            self._cam_attesa = None
            gid = core.gioco_in_corso()
            if gid and gid != "?":
                esito = self._cam_metti_vivo(gid, valori, fov, scrivi_fov=False)
                self._cam_esito = (esito, time.time())
                if esito == "cerco" and self._cam_attesa is None:  # sta ancora cercando il codice: riprovo coi valori di adesso
                    self._cam_attesa = (valori, fov)
                    time.sleep(0.5)
            time.sleep(0.08)

    @protetto
    def cam_stato(self):
        st = dict(self._camera().stato)
        es = getattr(self, "_cam_esito", None)
        if es and es[0] == "ok" and st.get("conn") == "live":  # codice acceso ma aggiornato dal vivo: nessun conflitto
            st["conflitto"], st["codice_vivo"] = False, True
        elif st.get("conflitto") and st.get("conn") == "live":
            # appena parte la partita il codice camera dentro Dolphin non è ancora stato trovato (qualche secondo):
            # finché lo cerco non è un conflitto (prima l'avviso compariva e poi spariva da solo)
            dove = self._cam_codice_vivo(st.get("id"), cerca=False)
            if dove is None:
                self._cam_cerca_presto(st.get("id"))
                st["conflitto"], st["cerco"] = False, True
            elif dove:
                st["conflitto"], st["codice_vivo"] = False, True
        return st

    @protetto
    def cam_sistema(self):
        import app_cam
        dolphin = core.trova_dolphin(self._conf)
        aperto = bool(core.exe_dolphin_aperti())
        gioco = core.gioco_in_corso() if aperto else None
        return {"trucchi": app_cam.trucchi_attivi(dolphin) if dolphin else None, "dolphin": bool(dolphin),
                "dolphin_aperto": aperto, "gioco": gioco if gioco and gioco != "?" else None,
                "finestra": core.stato_finestra_gioco() if gioco else None}

    def _sopra(self):
        return bool(self._conf.get("gioco_sopra", self._conf.get("cam_sopra", True)))

    @protetto
    def cam_sopra(self, si):
        """Finestra del gioco sempre in primo piano (sì/no): vale subito e per le prossime partite (anche da Impostazioni)."""
        self._conf["gioco_sopra"] = bool(si)
        core.scrivi_config(self._conf)
        return core.gioco_sopra(bool(si))

    def _sorveglia_codici(self):
        """Stati salvati coi codici Gecko VECCHI (vedi stati_codici.py): quando vedo partire Spider-Man 2 prendo la zona
        dei codici appena installata da Dolphin (dopo 3 s: sono quelli dell'INI di adesso; il launcher carica gli stati
        solo a gioco pronto, ~10 s, e aspetta _codici_pronti) e aggiorno i FILE degli stati di quella versione che hanno
        codici diversi. Se il gioco era già aperto quando è partita l'app non so con che codici è partito: niente."""
        import time
        h_prima, nato, t0, primo, fatto = None, False, 0.0, True, False
        while True:
            time.sleep(0.5)
            try:
                h = core.finestra_gioco() if core.exe_dolphin_aperti() else None
                if h != h_prima:
                    nato, t0, h_prima, fatto = bool(h) and not primo, time.time(), h, False
                    if nato:
                        self._codici_pronti.clear()
                    else:
                        self._codici_pronti.set()
                primo = False
                if h and not nato and not fatto and time.time() - t0 >= 3:
                    # gioco già aperto quando è partita l'app: niente stati, ma il codice camera dentro Dolphin lo cerco
                    # subito (John: aprendo il menu la prima volta le camere non si potevano cambiare finché non finiva)
                    fatto = True
                    self._cam_cerca_presto(core.gioco_in_corso())
                if not nato or fatto or time.time() - t0 < 3:
                    continue
                fatto = True
                gid = core.gioco_in_corso()
                try:
                    if gid and gid != "?":
                        self._aggiorna_stati(gid)
                finally:
                    self._codici_pronti.set()
                # il codice camera in esecuzione dentro Dolphin (Spider-Cam e menu in gioco dal vivo): cercato adesso in
                # sottofondo, così quando apri il menu o Spider-Cam è già pronto (prima partiva aprendo il menu: qualche
                # secondo in cui le camere non si potevano cambiare)
                self._cam_cerca_presto(gid)
            except Exception:  # noqa: BLE001 - il filo non deve fermarsi
                self._codici_pronti.set()
                core.log_errore(traceback.format_exc())

    def _sorveglia_camere(self):
        """Mentre giochi, le due camere (817F0084/85) e le opzioni (0088/89) nella memoria del gioco devono essere quelle
        scelte nell'app (John e un amico: nel menu c'era la Amazing ma R3 dava la camera originale). Il Gecko le scrive
        una volta sola all'avvio, quindi possono restare diverse: uno STATO SALVATO si porta dietro quelle di quando l'hai
        fatto, due scelte veloci potevano arrivare in disordine. Ogni secondo controllo e, se serve, le rimetto."""
        import time
        while True:
            time.sleep(1.0)
            try:
                if not core.exe_dolphin_aperti():
                    continue
                gid = core.gioco_in_corso()
                if gid and gid != "?":
                    self._cam_sincronizza(gid)
            except Exception:  # noqa: BLE001 - il filo non deve fermarsi
                core.log_errore(traceback.format_exc())

    def _cam_sincronizza(self, gid):
        import dolphin_memory_engine as dme
        modi = self._cam_modi()
        _, val = core.cam_modi_valore(modi)
        opz = core.cam_opzioni_valore(self._conf.get("cam_opzioni"))
        with self._dme_lock:
            if not core.aggancia_dme():
                return
            # codice camera nuovo in funzione: camere scritte dal Gecko (0086) e programma scritto dal codice AR
            if dme.read_byte(0x817F0086) != 1 or dme.read_word(CAM_PROGRAMMA) == 0:
                return
            o = bytes([opz >> 24 & 0xFF, opz >> 16 & 0xFF])
            if dme.read_bytes(0x817F0088, 2) != o:
                dme.write_bytes(0x817F0088, o)
            ora = dme.read_bytes(0x817F0084, 2)
            if ora == bytes([val >> 24 & 0xFF, val >> 16 & 0xFF]):
                return
            self._cam_modi_memoria(modi)
        self._log_menu(f"camere nel gioco {ora.hex()} -> {modi} (rimesse quelle scelte)")

    def _aggiorna_stati(self, gid):
        import stati_codici as sc
        D = core.trova_dolphin(self._conf)
        if not D:
            return
        with self._dme_lock:  # anche l'aggancio: sgancia e riaggancia, gli altri fili leggono intanto
            dme = core.aggancia_dme()
            if not dme:
                return
            foto = sc.foto_codici(dme, sc.punti_conosciuti(gid))
        bak = core.CONF_DIR / "backup_stati"
        uso = None
        for n in core.SLOT_STATI:
            p = core.file_stato(D, gid, n)
            vecchio = sc.stato_vecchio(p, gid, foto) if p.exists() else None
            if vecchio is None:
                continue
            if vecchio:
                bak.mkdir(parents=True, exist_ok=True)
                shutil.copy2(p, bak / p.name)  # lo stato com'era (uno per slot, l'ultimo)
                esito = sc.aggiorna(p, gid, foto)
                self._log_menu(f"stato {p.name}: codici Gecko {esito}")
                if esito != "aggiornato":
                    continue
            # dati dell'app: lo stato ha i codici Gecko di adesso (aggiornato ora o già prima; la data del file è la stessa)
            uso = uso or core.codici_in_uso(D, gid)
            gecko = {c["nome_ini"] for c in core.carica_codici_db() if c.get("tipo") == "gecko"}
            f = core.STATI_INFO / f"{gid}.s{n:02d}.json"
            try:
                info = json.loads(f.read_text(encoding="utf-8")) if f.exists() else None
            except (OSError, ValueError):
                info = None
            if info and info.get("mtime") == p.stat().st_mtime:
                cod = {k: v for k, v in info.get("codici", {}).items() if k not in gecko}
                cod.update({k: v for k, v in uso["codici"].items() if k in gecko})
                if cod != info.get("codici"):
                    info["codici"] = cod
                    f.write_text(json.dumps(info), encoding="utf-8")
            else:
                core.salva_info_stato(D, gid, n, None, uso, core.versione_exe_dolphin(core.trova_exe_dolphin(self._conf, D)))
        self._guardia.rev += 1  # la scheda degli stati rilegge gli avvisi

    def _sorveglia_sopra(self):
        """Ogni volta che compare la finestra di Spider-Man 2 (avviato da qui o da Dolphin) la tengo sopra le altre:
        in finestra resta visibile anche mentre cambi skin, slider o codici nell'app."""
        import time
        fatta, intero, giri = None, False, 0
        while True:
            time.sleep(0.5 if fatta else 1.5)
            giri += 1  # col gioco aperto più spesso: la domanda di chiusura deve comparire subito
            h = None
            try:
                h = core.finestra_gioco() if core.exe_dolphin_aperti() else None
                if bool(h) != bool(fatta) or giri % 10 == 0:  # gioco aperto/chiuso (e ogni tanto, se la pagina è stata ricaricata): la pagina ferma il 3D e il pad mentre giochi (CPU per Dolphin)
                    try:
                        self._finestra.evaluate_js(f"window.giocoAperto = {'true' if h else 'false'}")
                    except Exception:  # noqa: BLE001
                        pass
                if h and h != fatta and self._sopra():
                    time.sleep(1)
                    core.gioco_sopra(True)
                if h and self._sopra():
                    core.finestrelle_sopra()  # conferma di chiusura & co. sopra il gioco
                if h:
                    self._skin_originale_dalla_ram()
                ora = bool(h) and bool((core.stato_finestra_gioco() or {}).get("intero"))
                if ora and not intero:  # come Windows/i browser: "premi ... per uscire dallo schermo intero"
                    if h != fatta:  # gioco appena partito a schermo intero: aspetto che smetta di essere nero
                        threading.Thread(target=self._avviso_quando_pronto, args=(h,), daemon=True).start()
                    else:
                        self._avviso_intero(h)
                intero = ora
                fatta = h
            except Exception as e:  # noqa: BLE001 - il filo non deve fermarsi
                fatta = h or fatta  # se no a ogni giro rifarebbe "sopra" + 1 s di attesa
                if giri % 120 == 1:  # nel registro, ma non a raffica
                    core.log_errore(f"_sorveglia_sopra: {e!r}")

    def _avviso_quando_pronto(self, h):  # noqa: D401
        """All'avvio il gioco è nero per qualche secondo (e intanto viene messo in primo piano): il popup arriva
        quando si vede qualcosa, così non lo copre nessuno e non passa inosservato."""
        import time
        for _ in range(60):
            time.sleep(0.5)
            if core.finestra_gioco() != h:
                return
            try:
                luce = core.luce_gioco(h)  # None = la finestra non si lascia ancora fotografare: non è pronta
            except Exception:  # noqa: BLE001
                luce = None
            _log_avviso(f"luce {luce}")
            if luce is not None and luce > 6:
                time.sleep(1)  # i crediti sono appena comparsi: un attimo e arriva
                break
        self._fuoco_al_gioco()  # il pad va solo alla finestra attiva: che sia il gioco (senza clic col mouse)
        if (core.stato_finestra_gioco() or {}).get("intero"):
            self._avviso_intero(h)
            time.sleep(1.5)
            self._fuoco_al_gioco()  # (anche se l'avviso, che nasce senza fuoco, gliel'avesse tolto)

    def _avviso_intero(self, h, contenuto=None):
        """Finestrella in alto al centro, sopra il gioco a schermo intero, che sparisce da sola dopo 4 s. Non prende
        il fuoco: i comandi restano al gioco. contenuto = (html, larghezza) al posto della frase dello schermo intero."""
        testi = {"it": "Per uscire dallo schermo intero premi", "en": "To exit full screen press", "de": "Zum Beenden des Vollbilds drücke",
                 "fr": "Pour quitter le plein écran, appuie sur", "es": "Para salir de pantalla completa pulsa"}
        frase = testi.get(self._conf.get("lingua") or core.lingua_sistema(), testi["en"])
        tasto = '<kbd>Alt</kbd> + <kbd>Invio</kbd>' if (self._conf.get("lingua") or core.lingua_sistema()) == "it" else '<kbd>Alt</kbd> + <kbd>Enter</kbd>'
        html = (f'<html><body style="margin:0;background:#0c0f18;color:#e8ecf5;font:600 13px Segoe UI,sans-serif;display:flex;'
                f'align-items:center;justify-content:center;height:100vh;border:1px solid #2c3550;border-radius:10px;box-sizing:border-box;'
                f'user-select:none;white-space:nowrap">{frase}&nbsp;{tasto}<style>kbd{{background:#232a3d;border:1px solid #3a4462;border-bottom-width:3px;'
                f'border-radius:5px;padding:1px 7px;margin:0 3px;font:700 12px Segoe UI}}</style></body></html>')
        larg, alt = (400, 44) if len(frase) < 40 else (450, 44)
        if contenuto:
            html = html.replace(f"{frase}&nbsp;{tasto}", contenuto[0])
            larg = contenuto[1]
        _log_avviso(f"avviso_intero h={h}")
        Api._n_avviso = getattr(Api, "_n_avviso", 0) + 1
        titolo = f"SM2 Enhanced · avviso {Api._n_avviso}"

        def al_centro():  # pywebview mette x/y in punti "logici": col ridimensionamento di Windows finiva spostato.
            import ctypes  # Lo centro io in pixel veri sul monitor del gioco, senza rubargli il fuoco.
            import time
            u = ctypes.windll.user32
            for _ in range(160):  # la prima finestrella dell'app può metterci qualche secondo a nascere
                w = u.FindWindowW(None, titolo)
                if w:
                    break
                time.sleep(0.05)
            _log_avviso(f"finestrella {titolo} -> {w}")
            if not w:
                f.destroy()
                return
            from ctypes import wintypes
            u.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint]

            def sopra_al_gioco(w):  # il popup è sopra la finestra del gioco nell'ordine delle finestre?
                k = u.GetWindow(h, 3)  # GW_HWNDPREV
                while k:
                    if k == w:
                        return True
                    k = u.GetWindow(k, 3)
                return False
            fine = time.time() + 4
            while time.time() < fine:  # 4 s dal momento in cui si vede; sempre sopra (anche se il gioco torna in primo piano)
                mon, _ = core._monitor(h)
                r = core._rett(w)
                lw = r.right - r.left
                x = mon.left + (mon.right - mon.left - lw) // 2
                y = mon.top + max(24, (mon.bottom - mon.top) // 30)
                u.SetWindowPos(w, wintypes.HWND(-1), x, y, 0, 0, 0x0001 | 0x0010 | 0x0040)  # NOSIZE | NOACTIVATE | SHOWWINDOW
                if not sopra_al_gioco(w):  # il gioco a schermo intero, in primo piano, resta davanti a un "sempre sopra" alzato
                    u.SetWindowPos(h, w, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010)  # da un altro programma: metto IL GIOCO sotto al popup
                    _log_avviso(f"gioco messo sotto al popup -> {sopra_al_gioco(w)}")
                time.sleep(0.25)
            f.destroy()
        try:
            mon, _ = core._monitor(h)
            f = webview.create_window(titolo, html=html, width=larg, height=alt, x=mon.left, y=mon.top - 4000, frameless=True,
                                      on_top=True, focus=False, resizable=False, shadow=True, background_color="#0c0f18", min_size=(larg, alt))
            threading.Thread(target=al_centro, daemon=True).start()
        except Exception as e:  # noqa: BLE001 - è solo un aiuto
            _log_avviso(f"errore popup {e!r}")

    @protetto
    def cam_ultimi(self, dati):
        self._conf["cam_ultimi"] = dati
        core.scrivi_config(self._conf)
        return True

    @protetto
    def cam_salva(self, valori, fov, ver, tutte=None, tua=None):
        """Salva la camera nella versione ver; tutte = [ID, ...] per salvarla in più versioni insieme.
        tua = True/False: nella camera del gioco c'è "La tua" o la Migliorata (scelta dalla pagina: vedi _cam_tua)."""
        import app_cam
        dolphin = core.trova_dolphin(self._conf)
        if not dolphin:
            return {"errore": "dolphin"}
        self._conf["cam_versione"] = ver
        core.scrivi_config(self._conf)
        r = {"salvati": [], "errori": [], "righe": 0, "versioni": []}
        for g in (tutte or [ver]):
            x = app_cam.salva(dolphin, valori, fov, g)
            r["salvati"] += x["salvati"]
            r["errori"] += x["errori"]
            r["righe"] = x["righe"]
            if x["salvati"]:
                r["versioni"].append(core.NOMI_VERSIONE[g])
        r["trucchi"] = app_cam.trucchi_attivi(dolphin)
        if r["salvati"]:  # la camera che c'è davvero nel gioco: il menu in gioco parte da questa
            self._conf["cam_salvata"] = {"valori": valori, "fov": round(fov)}
            if tua is not None:
                self._conf["cam_salvata"]["tua"] = bool(tua)
            core.scrivi_config(self._conf)
        return r

    @protetto
    def cam_codice(self, valori, fov, ver):
        import app_cam
        camera, righe_fov = app_cam.codici(valori, fov, ver)
        return "\n".join(camera) + "\n\n" + "\n".join(righe_fov)

    @protetto
    def copia_testo(self, testo):
        import subprocess
        subprocess.run("clip", input=testo.encode("utf-16-le"), check=False, creationflags=0x08000000)
        return True

    @protetto
    def cam_preset_salva(self, nome, dati):
        self._conf.setdefault("cam_preset", {})[nome] = dati
        core.scrivi_config(self._conf)
        return True

    @protetto
    def cam_preset_rinomina(self, vecchio, nuovo):
        p = self._conf.get("cam_preset", {})
        if vecchio not in p or not nuovo or nuovo in p:
            return {"errore": "nome"}
        self._conf["cam_preset"] = {(nuovo if k == vecchio else k): v for k, v in p.items()}
        core.scrivi_config(self._conf)
        return True

    @protetto
    def cam_preset_elimina(self, nome):
        self._conf.get("cam_preset", {}).pop(nome, None)
        core.scrivi_config(self._conf)
        return True

    @protetto
    def cam_esporta(self, nome, dati):
        r = self._finestra.create_file_dialog(webview.FileDialog.SAVE, save_filename=f"{nome}.spidercam.json",
                                              file_types=("Spider-Cam (*.json)",))
        if not r:
            return None
        f = r[0] if isinstance(r, (list, tuple)) else r
        Path(f).write_text(json.dumps({"spidercam": "app", "preset": {nome: dati}}, indent=2, ensure_ascii=False),
                           encoding="utf-8")
        return f

    @protetto
    def cam_importa(self):
        r = self._finestra.create_file_dialog(webview.FileDialog.OPEN, file_types=("Spider-Cam (*.json)",))
        if not r:
            return None
        f = r[0] if isinstance(r, (list, tuple)) else r
        try:
            d = json.loads(Path(f).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {"errore": "import"}
        grezzi = d.get("preset", d) if isinstance(d, dict) else {}
        trovati = {}
        import app_cam
        for nome, p in grezzi.items():
            if not isinstance(p, dict):
                continue
            val = p.get("valori", p)
            try:
                v = {g: [float(x) for x in app_cam.cs.normalizza(val[g])] for g in app_cam.GRUPPI}
            except (KeyError, TypeError, ValueError):
                continue
            trovati[str(nome)] = {"valori": v, "fov": float(p.get("fov", 90)), "min_uguale": bool(p.get("min_uguale", False))}
        if not trovati:
            return {"errore": "import"}
        self._conf.setdefault("cam_preset", {}).update(trovati)
        core.scrivi_config(self._conf)
        return trovati

    @protetto
    def cam_trucchi(self):
        import app_cam
        if core.exe_dolphin_aperti():
            return {"errore": "chiudi_dolphin"}
        dolphin = core.trova_dolphin(self._conf)
        app_cam.attiva_trucchi_ini(dolphin)
        return True

    @protetto
    def cam_patch(self, ver):
        import app_cam
        app_cam.installa_patch(core.trova_dolphin(self._conf), ver)
        return True

    # ------------------------------------------------------------ azioni
    @protetto
    def applica(self, scelte):
        """scelte = {"primaria": cartella|None, "alternativa": cartella|None, "ragnatele": id|None} (None = non toccare)."""
        dolphin = core.trova_dolphin(self._conf)
        if not dolphin:
            return {"errore": "dolphin"}
        ins = self._ins = core.Installazione(dolphin)  # la pagina ne segue l'avanzamento
        base = core.cartella_ufficiale(core.trova_pack(self._conf))  # texture della tuta che una skin non ha
        if scelte.get("primaria"):
            ins.skin(scelte["primaria"], base=base)
        if scelte.get("alternativa"):
            ins.skin(scelte["alternativa"], alternativa=True, base=base)
        c = self._conf
        if scelte.get("ragnatele"):
            _, rag = self._catalogo()
            r = next(x for x in rag if x["id"] == scelte["ragnatele"])
            if r["path"] is None:  # originali del gioco: a gioco aperto non si possono rimettere (i file andrebbero
                c["rag_alt"] = None  # cancellati) -> niente ragnatele alternative
            c["rag_pri"] = r["id"]
            if not c.get("rag_messe"):  # col costume alternativo in gioco le principali nuove le mette il filo dopo
                ins.ragnatele(r["path"])
        if scelte.get("ragnatele_alt"):  # il filo le mette (o rimette le principali) quando serve
            a = scelte["ragnatele_alt"]
            c["rag_alt"] = None if a in ("uguali", "vanilla", c.get("rag_pri")) else a
        core.scrivi_config(c)
        ris = ins.esegui()
        ris["dolphin_aperto"] = bool(core.exe_dolphin_aperti())
        return ris

    @protetto
    def imposta(self, chiave, valore):
        self._conf[chiave] = valore
        core.scrivi_config(self._conf)
        return True

    @protetto
    def _prova_da_zero(self):
        """Apre una seconda app in "prova da zero": cartella sua, non vede niente di quello che c'è sul PC."""
        args = [sys.executable, "--da-zero"] if getattr(sys, "frozen", False) else [sys.executable, str(Path(__file__).resolve()), "--da-zero"]
        avvia_esterno(args)
        return True

    @protetto
    def prova_ricomincia(self):
        """Prova da zero: cancella impostazioni, Dolphin e libreria della prova (gli zip scaricati restano) e riapre."""
        if not core.DA_ZERO:
            return False
        (core.BASE_PROVA / "_ricomincia").write_text("1", encoding="utf-8")
        self._prova_da_zero()
        threading.Timer(0.8, lambda: self._finestra.destroy()).start()
        return True

    @protetto
    def apri(self, cosa):
        if cosa == "licenze":  # licenze complete dei componenti (contenuti/LICENZE.txt, fatto da crea_licenze.py)
            import shutil
            f = core.CONF_DIR / "LICENZE.txt"
            shutil.copyfile(risorsa("contenuti/LICENZE.txt"), f)
            os.startfile(f)
            return True
        dolphin = core.trova_dolphin(self._conf)
        mappa = {"texture": core.cartelle_texture(dolphin)[0] if dolphin else None,
                 "backup": core.BACKUP_DIR, "pack": core.corto(core.trova_pack(self._conf)), "log": core.CONF_DIR,
                 "prova": core.BASE_PROVA if core.DA_ZERO else None}
        p = mappa.get(cosa)
        if p:
            Path(p).mkdir(parents=True, exist_ok=True)
            os.startfile(p)
        return bool(p)

    # ------------------------------------------------------------ aggiornamenti dell'app
    def _leggi_ultima_app(self):
        """Manifesto online (core.ultima_app): dall'indirizzo salvato da un trasloco, se c'è."""
        def trasloco(nuovo):
            self._conf["agg_url"] = nuovo
            core.scrivi_config(self._conf)

        def sostenitori(nomi):  # sostenitori Swing++ per i Crediti: copia in config (senza rete si vede l'ultima lista)
            if nomi != self._conf.get("sostenitori"):
                self._conf["sostenitori"] = nomi
                core.scrivi_config(self._conf)
        return core.ultima_app(self._conf.get("agg_url"), trasloco, sostenitori)

    @protetto
    def sostenitori(self):
        return self._conf.get("sostenitori") or []

    def _agg_info(self):
        nuova = self._ultima_app
        return {"versione": core.VERSIONE_APP, "nuova": nuova, "nascosta": self._conf.get("agg_nascosta"),
                "da_sola": bool(nuova and nuova.get("exe") and getattr(sys, "frozen", False))}  # da Python: solo la pagina

    @protetto
    def app_agg_stato(self):
        """Per il launcher e le Impostazioni: c'è una versione nuova dell'app? (letta in sottofondo all'avvio)"""
        return self._agg_info()

    @protetto
    def app_agg_controlla(self):
        """"Controlla aggiornamenti" in Impostazioni: rilegge il manifesto adesso."""
        self._ultima_app = self._leggi_ultima_app()
        return self._agg_info()

    @protetto
    def app_agg_nascondi(self, versione):
        """La 'x' sull'avviso: non mostrarlo più nel launcher per QUESTA versione (in Impostazioni resta)."""
        self._conf["agg_nascosta"] = versione
        core.scrivi_config(self._conf)
        return True

    @protetto
    def app_agg_scarica(self):
        info = self._ultima_app
        if not (info and info.get("exe") and getattr(sys, "frozen", False)):
            return {"errore": "upd_no"}
        if self._agg and not self._agg.finito:
            return True
        self._agg = core.AggiornaApp(info, sys.executable)
        threading.Thread(target=self._agg.esegui, daemon=True).start()
        return True

    @protetto
    def app_agg_avanzamento(self):
        return self._agg.stato() if self._agg else None

    @protetto
    def app_agg_annulla(self):
        if self._agg:
            self._agg.annulla = True
        return True

    @protetto
    def app_agg_applica(self):
        """Scaricata e controllata: scambio gli exe, avvio il nuovo e chiudo questa."""
        if not (self._agg and self._agg.finito and not self._agg.errore):
            return {"errore": "upd_no"}
        nuovo = self._agg.applica()
        if not nuovo:
            return {"errore": "upd_scambio"}
        try:
            avvia_esterno([str(nuovo), "--aggiornato", str(self._agg.vecchio), str(os.getpid())] + (["--da-zero"] if core.DA_ZERO else []))
        except OSError:
            os.replace(nuovo, self._agg.nuovo)  # il nuovo non parte: rimetto quello di prima
            os.replace(self._agg.vecchio, nuovo)
            return {"errore": "upd_scambio"}
        threading.Timer(0.4, lambda: self._finestra.destroy()).start()
        return True

    SEGNALA_URL = "https://github.com/JohnSwingMods/sm2-enhanced/issues/new"

    @protetto
    def segnala_prepara(self, errore=None):
        """"Segnala un problema": zip in Download con le informazioni utili (versioni, PC, controller, impostazioni
        principali) e la coda dei registri (errori, uscite, crash, menu), SENZA nome utente, nome del PC né percorsi
        personali (sostituiti). errore = il messaggio appena mostrato, se si arriva da un errore. Ritorna il file e la
        pagina di GitHub per scrivere la segnalazione (titolo e testo già pronti, solo versioni: niente dati personali)."""
        import platform
        import re
        import urllib.parse
        import zipfile
        from datetime import datetime
        casa, utente, pc = str(Path.home()), os.environ.get("USERNAME", ""), os.environ.get("COMPUTERNAME", "")

        def pulito(s):
            s = str(s)
            for vero, finto in ((casa, "<home>"), (casa.replace("\\", "/"), "<home>")):
                s = re.sub(re.escape(vero), finto, s, flags=re.I)
            for nome, finto in ((utente, "<utente>"), (pc, "<pc>")):
                if len(nome) >= 3:
                    s = re.sub(r"(?<![A-Za-z0-9])" + re.escape(nome) + r"(?![A-Za-z0-9])", finto, s, flags=re.I)
            return s

        dolphin = core.trova_dolphin(self._conf)
        exe = core.trova_exe_dolphin(self._conf, dolphin) if dolphin else None
        righe = [f"SM2 Enhanced {core.VERSIONE_APP}", f"Windows {platform.release()} ({platform.version()}, {platform.machine()})"]
        try:
            cpu = core.processore()
            righe.append(f"Processore: {cpu.get('nome') if isinstance(cpu, dict) else cpu}")
        except Exception:  # noqa: BLE001
            pass
        try:
            import psutil
            righe.append(f"RAM: {psutil.virtual_memory().total / 2 ** 30:.1f} GB")
        except Exception:  # noqa: BLE001
            pass
        righe.append(f"Dolphin: {core.versione_exe_dolphin(exe) if exe else 'non trovato'}")
        try:
            giochi = self._tutti_giochi(dolphin) if dolphin else {}
            righe.append("Versioni del gioco: " + (", ".join(f"{core.NOMI_VERSIONE.get(g, g)} ({Path(p).suffix})" for g, p in giochi.items()) or "nessuna"))
            if dolphin:
                righe.append("Mod per versione: " + json.dumps(core.mod_versioni(dolphin), ensure_ascii=False, default=str))
        except Exception as e:  # noqa: BLE001
            righe.append(f"Versioni del gioco: errore {e!r}")
        try:
            p = self._pad()
            righe.append("Controller: " + (", ".join(f"{x['tipo']} {x['nome']} {x.get('vid', '')}:{x.get('pid', '')}" for x in p["tutti"]) or "nessuno")
                         + f" (profilo: {p['esito']})" if p else "Controller: ?")
        except Exception:  # noqa: BLE001
            pass
        try:
            righe.append(f"Libreria: formato {json.loads((Path(self._libreria_predefinita()) / 'libreria.json').read_text(encoding='utf-8')).get('formato')}")
        except (OSError, ValueError):
            righe.append("Libreria: non installata")
        righe.append(f"Scheda video per i DDS: {(core._TEXCONV_GPU[0]['gpu'] or 'nessuna (processore)') if core._TEXCONV_GPU else 'non provata'}")
        righe.append(f"Programmi per rar/7z: {', '.join(e.name for e in core._estrattori()) or 'nessuno'}")
        righe.append(f"Lingua: {self._conf.get('lingua') or core.lingua_sistema()}")
        if errore:
            righe += ["", "Errore mostrato:", str(errore)]
        dest = core.cartella_download()
        dest.mkdir(parents=True, exist_ok=True)
        f = dest / f"SM2 Enhanced - segnalazione {datetime.now():%Y-%m-%d %H-%M}.zip"
        with zipfile.ZipFile(f, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("info.txt", pulito("\n".join(righe)) + "\n")
            for nome, quante in (("errori.log", 400), ("uscite.log", 200), ("crash.log", 200), ("menu.log", 200)):
                log = core.CONF_DIR / nome
                if log.is_file():
                    coda = log.read_text(encoding="utf-8", errors="replace").splitlines()[-quante:]
                    z.writestr(nome, pulito("\n".join(coda)) + "\n")
        titolo = f"[{core.VERSIONE_APP}] " + (pulito(str(errore))[:80] if errore else "")
        testo = (f"**What happened?**\n\n\n**What were you doing?**\n\n\n---\nSM2 Enhanced {core.VERSIONE_APP}, Windows {platform.release()}\n"
                 f"Please drag the file `{f.name}` (in your Downloads folder) into this box.")
        url = self.SEGNALA_URL + "?" + urllib.parse.urlencode({"title": titolo, "body": testo})
        return {"file": str(f), "nome": f.name, "url": url}

    @protetto
    def segnala_mostra(self, file):
        """Apre Esplora risorse con il file della segnalazione selezionato (solo i file fatti da segnala_prepara)."""
        p = Path(file)
        if p.parent == core.cartella_download() and p.name.startswith("SM2 Enhanced - segnalazione") and p.is_file():
            avvia_esterno(["explorer", "/select,", str(p)])
        return True

    @protetto
    def apri_link(self, url):
        pagina = (self._ultima_app or {}).get("pagina")
        if url.startswith(("https://www.moddb.com/", "https://dolphin-emu.org/", "https://www.patreon.com/", "https://github.com/")) or (pagina and url == pagina):
            import webbrowser
            webbrowser.open(url)
        return True

    @protetto
    def scegli_cartella(self, cosa):
        r = self._finestra.create_file_dialog(webview.FileDialog.FOLDER)
        if not r:
            return None
        p = Path(r[0] if isinstance(r, (list, tuple)) else r)
        if cosa == "dolphin" and not ((p / "Config").is_dir() or (p / "GameSettings").is_dir()):
            return {"errore": "non_dolphin"}
        if cosa == "pack" and not (p / "Skins" / "Suit Mods").is_dir():
            return {"errore": "non_pack"}
        self._conf[cosa] = str(p)
        core.scrivi_config(self._conf)
        if cosa == "pack":
            self._catalogo(forza=True)
        return str(p)


def avvia_esterno(args, **kw):
    """Avvia un programma esterno (Dolphin, Esplora risorse) "pulito": l'exe dell'app imposta la cartella delle sue
    librerie (_MEI...) e i figli la erediterebbero. Dolphin caricherebbe le DLL dell'app e le terrebbe bloccate: alla
    chiusura dell'app comparirebbe "Failed to remove temporary directory"."""
    import subprocess
    if getattr(sys, "frozen", False):
        import ctypes
        ctypes.windll.kernel32.SetDllDirectoryW(None)
    return subprocess.Popen(args, env=core.ambiente_figli(), close_fds=True, **kw)  # (vedi core.ambiente_figli)


TITOLO_MENU = "SM2 Enhanced · menu"  # anche in app_web/menu.html (<title>)
TITOLO = core.NOME_APP + ((" (prova da zero" + (" TEST)" if os.environ.get("SPIDEY_BASE_PROVA") else ")")) if core.DA_ZERO
                               else " (TEST)" if os.environ.get("SPIDEY_BASE_PROVA") else "")  # (prove: titolo diverso dall'app vera)


def _ricomincia_prova():
    """Prova da zero: "Ricomincia" lascia un segnale; qui (prima di aprire qualsiasi file) cancello tutto tranne gli
    zip scaricati, così non serve riscaricarli ogni volta."""
    import shutil
    import time
    segnale = core.BASE_PROVA / "_ricomincia"
    if not segnale.exists():
        return
    time.sleep(1.5)  # la finestra di prima si sta chiudendo
    for sotto in ("AppData", "Documenti"):
        for _ in range(30):  # i processi del browser interno della finestra di prima possono tenere file per qualche secondo
            try:
                core._rimuovi(core.BASE_PROVA / sotto)
            except OSError:
                pass
            if not (core.BASE_PROVA / sotto).exists():
                break
            time.sleep(1)
    segnale.unlink(missing_ok=True)


def _gia_aperta():
    """Un'app sola alla volta (due userebbero la stessa porta): se c'è già, la porto davanti e questa si chiude."""
    import ctypes
    k = ctypes.windll.kernel32
    nome = ("SM2Enhanced_prova" + ("_test" if os.environ.get("SPIDEY_BASE_PROVA") else "")) if core.DA_ZERO else "SM2Enhanced_launcher"
    globals()["_MUTEX"] = k.CreateMutexW(None, False, nome)
    gia = k.GetLastError() == 183  # ERROR_ALREADY_EXISTS
    vecchia = None
    if not gia and not core.DA_ZERO:  # c'è aperta l'app di prima col nome vecchio ("Spider-Man 2 DE")?
        vecchia = k.OpenMutexW(0x00100000, False, "SpiderMan2DE_launcher")  # SYNCHRONIZE
        if vecchia:
            k.CloseHandle(vecchia)
    if not gia and not vecchia:
        return False
    u = ctypes.windll.user32
    h = (u.FindWindowW(None, TITOLO) or u.FindWindowW(None, "SM2 Enhanced") or u.FindWindowW(None, "SM2 Enhanced Plus")
         or u.FindWindowW(None, "Spider-Man 2 · Definitive Edition"))  # anche le versioni vecchie ("Plus", nome di prima: stesso mutex)
    if h:
        u.ShowWindow(h, 9)
        u.SetForegroundWindow(h)
    return True


_APPENA_AGGIORNATA = None  # versione, se questo avvio arriva da un aggiornamento (--aggiornato): il launcher lo dice


# REGISTRO DELLE USCITE (su un PC di prova l'app è SPARITA mentre si configurava OBS col DSR, niente in errori.log).
# uscite.log in AppData: ogni avvio e ogni uscita col motivo (finestra chiusa, os._exit, fine di webview.start, errore non
# gestito, motore WebView2 morto, cambio di risoluzione dello schermo); un "avvio" senza uscita prima = morte improvvisa.
# crash.log = faulthandler: i crash "duri" del processo (es. dentro pythonnet/WebView2) col punto in cui è morto.
def _uscita(motivo):
    try:
        core.CONF_DIR.mkdir(parents=True, exist_ok=True)
        f = core.CONF_DIR / "uscite.log"
        righe = f.read_text(encoding="utf-8").splitlines()[-300:] if f.exists() else []
        righe.append(f"{time.strftime('%Y-%m-%d %H:%M:%S')}  pid {os.getpid()}  {core.NOME_APP} {core.VERSIONE_APP}  {motivo}")
        core.scrivi_sicuro(f, "\n".join(righe) + "\n")
    except Exception:  # noqa: BLE001 - il registro non deve mai far danni
        pass


def _registro_uscite(fin):
    import faulthandler
    _uscita("avvio")
    try:
        crash = open(core.CONF_DIR / "crash.log", "a", encoding="utf-8")  # resta aperto: faulthandler ci scrive se il processo muore
        crash.write(f"\n--- avvio {time.strftime('%Y-%m-%d %H:%M:%S')} pid {os.getpid()} ---\n")
        crash.flush()
        faulthandler.enable(crash, all_threads=True)
    except Exception as e:  # noqa: BLE001
        core.log_errore(f"faulthandler: {e!r}")
    vecchio = sys.excepthook

    def errore(tipo, val, tb):
        core.log_errore("".join(traceback.format_exception(tipo, val, tb)))
        _uscita(f"errore non gestito: {tipo.__name__}: {val}")
        vecchio(tipo, val, tb)
    sys.excepthook = errore
    threading.excepthook = lambda a: (core.log_errore("".join(traceback.format_exception(a.exc_type, a.exc_value, a.exc_traceback))),
                                      _uscita(f"errore nel filo {getattr(a.thread, 'name', '?')}: {a.exc_type.__name__}: {a.exc_value}"))
    from webview.platforms import edgechromium
    pronto = edgechromium.EdgeChrome.on_webview_ready

    def pronto_col_registro(self, sender, args):  # il motore della finestra (WebView2) che muore: lo scrivo, e se è
        pronto(self, sender, args)                 # solo la pagina a essersi chiusa/bloccata la ricarico
        try:
            def fallito(s, a):
                tipo = str(a.ProcessFailedKind)
                _uscita(f"WebView2 ProcessFailed: {tipo} motivo={getattr(a, 'Reason', '?')} uscita={getattr(a, 'ExitCode', '?')}")
                if "RenderProcess" in tipo:
                    try:
                        s.Reload()
                    except Exception as e:  # noqa: BLE001
                        core.log_errore(f"ricarica dopo WebView2 ProcessFailed: {e!r}")
            self.webview.CoreWebView2.ProcessFailed += fallito
        except Exception as e:  # noqa: BLE001
            core.log_errore(f"ascolto WebView2 ProcessFailed: {e!r}")
    edgechromium.EdgeChrome.on_webview_ready = pronto_col_registro

    def schermo():  # il DSR cambia la risoluzione del desktop: la segno, per legarla a un'eventuale sparizione
        import ctypes  # (risoluzione vera del monitor principale: GetSystemMetrics cambia anche quando l'app diventa "DPI aware")

        class DM(ctypes.Structure):
            _fields_ = [("nome", ctypes.c_wchar * 32), ("v", ctypes.c_ushort * 4), ("campi", ctypes.c_ulong), ("x", ctypes.c_byte * 16),
                        ("altro", ctypes.c_short * 5), ("form", ctypes.c_wchar * 32), ("lp", ctypes.c_ushort), ("bpp", ctypes.c_ulong),
                        ("w", ctypes.c_ulong), ("h", ctypes.c_ulong), ("resto", ctypes.c_byte * 64)]
        u, prima = ctypes.windll.user32, None
        while True:
            try:
                dm = DM()
                dm.v[2] = ctypes.sizeof(DM)  # dmSize
                ora = (dm.w, dm.h) if u.EnumDisplaySettingsW(None, -1, ctypes.byref(dm)) else prima
                if prima and ora != prima:
                    _uscita(f"risoluzione dello schermo {prima[0]}x{prima[1]} -> {ora[0]}x{ora[1]}")
                prima = ora
            except Exception:  # noqa: BLE001
                pass
            time.sleep(2)
    threading.Thread(target=schermo, daemon=True).start()


def main():
    global _APPENA_AGGIORNATA
    if core.dopo_aggiornamento(sys.argv):  # prima della regola "un'app sola": aspetta che la versione di prima si chiuda
        _APPENA_AGGIORNATA = core.VERSIONE_APP
    if core.DA_ZERO:
        _ricomincia_prova()
    if (getattr(sys, "frozen", False) or core.DA_ZERO) and _gia_aperta():
        return
    try:  # nome nuovo (SM2 Enhanced): sposta Documenti/Spider-Man 2 DE se c'è ancora e aggiorna i percorsi salvati
        core.cartella_app()
    except Exception as e:  # noqa: BLE001
        core.log_errore(f"spostamento della cartella col nome vecchio: {e!r}")
    api = Api()
    url = str(risorsa("app_web") / "index.html")
    if "--pagina" in sys.argv:  # per provare: apre direttamente una sezione
        url += "?pagina=" + sys.argv[sys.argv.index("--pagina") + 1]
    fin = webview.create_window(TITOLO, url=url,
                                js_api=api, width=1360, height=860, min_size=(1040, 680), background_color="#0a0c12",
                                maximized=True)
    api._finestra = fin
    _registro_uscite(fin)

    def chiusa():
        """Chiusa la finestra principale si chiude TUTTO: il menu in gioco (nascosto ma vivo dopo averlo usato), popup e
        finestre ModDB terrebbero acceso il programma, e la regola "un'istanza sola" impedirebbe di riaprirlo."""
        m3 = getattr(api, "_m3", None)
        if m3:  # mappa 3D aperta: Spidey dov'era, icone e "su" del gioco rimessi (senza aspettare il filo della vista: le sue
            m3["fine"] = m3.get("fine") or "esci"  # chiamate alla pagina aspetterebbero questa finestra che si sta chiudendo)
            vista = m3.get("vista")
            try:
                if vista and vista.P:
                    vista.v.metti(tuple(vista.pos0))
                    vista.icone_visibili()
            except Exception:  # noqa: BLE001
                pass
        for w in list(webview.windows):
            if w is not fin:
                try:
                    w.destroy()
                except Exception:  # noqa: BLE001
                    pass
        try:
            api._musica.proc.kill()  # PowerShell della musica
        except Exception:  # noqa: BLE001
            pass
        _uscita("finestra principale chiusa")
        threading.Timer(1.5, lambda: (_uscita("fine (os._exit dopo la chiusura)"), os._exit(0))).start()
    fin.events.closed += chiusa
    fin.events.loaded += api._aggancia_trascina  # file trascinati sulla finestra
    if _TEMPI:  # (prove) quando parte il programma, compare la finestra e la pagina è caricata
        def segna(cosa):
            with open(_TEMPI, "a", encoding="utf-8") as f:
                f.write(f"{time.time():.2f}\t0\t[{cosa}]\n")
        segna("avvio")
        fin.events.shown += lambda: segna("finestra")
        fin.events.loaded += lambda: segna("pagina caricata")
    from webview.platforms import edgechromium
    edgechromium.EdgeChrome.on_download_starting = _scarica_in_download  # download della finestra ModDB
    webview.settings["ALLOW_DOWNLOADS"] = True
    if "--porta" in sys.argv:  # per provare con l'exe aperto: la porta fissa servirebbe le pagine dell'exe
        webview.settings["DEFAULT_HTTP_PORT"] = int(sys.argv[sys.argv.index("--porta") + 1])
    elif core.DA_ZERO:  # la prova da zero gira insieme all'app vera: porta sua
        webview.settings["DEFAULT_HTTP_PORT"] = 42099 if os.environ.get("SPIDEY_BASE_PROVA") else 42088
    if "--js" in sys.argv:  # per provare: esegue del JavaScript nella pagina qualche secondo dopo l'avvio
        codice = sys.argv[sys.argv.index("--js") + 1]
        fin.events.loaded += lambda: threading.Timer(4, lambda: fin.evaluate_js(codice)).start()
    core.CONF_DIR.mkdir(parents=True, exist_ok=True)
    import shutil  # la cache HTTP di WebView2 terrebbe pagine vecchie dopo un aggiornamento: la svuoto (localStorage resta)
    for c in (core.CONF_DIR / "webview").glob("**/Default/*Cache*"):
        shutil.rmtree(c, ignore_errors=True)
    webview.start(http_server=True, private_mode=False, storage_path=str(core.CONF_DIR / "webview"),
                  debug="--debug" in sys.argv)
    _uscita("fine di webview.start")


if __name__ == "__main__":
    main()
