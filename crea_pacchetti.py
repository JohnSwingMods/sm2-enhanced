"""Zip pronti per chi NON ha Windows, da mettere nella pagina della release accanto all'exe (richieste su YouTube):
Android e Linux / Steam Deck. Dentro: i codici per le 5 versioni del gioco (gli stessi che mette l'app: contenuti/
GameSettings), il profilo del controller, il salvataggio al 100% e un LEGGIMI in inglese e italiano. Niente texture HD
(sono mod di altri: il LEGGIMI dice dove scaricarle) e niente file del gioco.

Uso: python crea_pacchetti.py <cartella di uscita>   (crea "SM2.Enhanced.<versione>.Android.zip" e "...Linux.SteamDeck.zip")"""
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

import app_core as core

RE_MODDB = "https://www.moddb.com/mods/spider-man-2-re-alpha"
CODICI = "https://github.com/JohnSwingMods/sm2-enhanced"

COMUNE_EN = """You need your own copy of Spider-Man 2 for GameCube (USA, UK, Italian, German or French): no game files are
included. Works with Dolphin 2412 or newer.

WHAT'S INSIDE
- The SM2 Enhanced codes for all 5 versions of the game: 60 fps, no motion blur, 16:9 with a round HUD, the new
  cameras (modern / Amazing, R3 to switch), L3 dive, wall-run and web-zip momentum, suit switch with a tap of RB (Z).
- A 100% save (slot "SPIDEY"): only copied if you want it, see below.
- The controller profile "spiderman 2" (extra buttons: L3 dive, R3 camera, Select map, LB hide/show the HUD).

HD TEXTURES (optional, recommended)
They are made by other modders, so they're not in this zip. Download "Spider-Man 2: RE" from
{re}
and put the textures (the .png files) in the folder Load/Textures/GK2E52 inside the Dolphin folder below
(GK2E52 works for every version of the game: the small GK2P52/GK2I52/GK2D52/GK2F52 .txt files link them).
Then turn on Graphics > Advanced > "Load Custom Textures" in Dolphin.

Not available outside the Windows app: the in-game menu (LB + RB), the live camera tuning, the 3D map, the
webs of the alternate suit. Everything else is in the codes and works the same.
Source code and Windows app: {codici}
"""
COMUNE_IT = """Serve la tua copia di Spider-Man 2 per GameCube (USA, UK, italiana, tedesca o francese): nessun file del gioco è
incluso. Funziona con Dolphin 2412 o più recente.

COSA C'È DENTRO
- I codici di SM2 Enhanced per tutte e 5 le versioni: 60 fps, niente motion blur, 16:9 con l'HUD tondo, le camere nuove
  (moderna / Amazing, R3 per cambiare), tuffo con L3, momentum sui muri e nel web zip, costume col colpetto di RB (Z).
- Un salvataggio al 100% (casella "SPIDEY"): copialo solo se lo vuoi, vedi sotto.
- Il profilo del controller "spiderman 2" (tasti in più: L3 tuffo, R3 camera, Select mappa, LB nascondi/mostra l'HUD).

TEXTURE HD (facoltative, consigliate)
Sono di altri modder, quindi non sono in questo zip. Scarica "Spider-Man 2: RE" da
{re}
e metti le texture (i file .png) nella cartella Load/Textures/GK2E52 dentro la cartella di Dolphin indicata sotto
(GK2E52 vale per tutte le versioni: i file .txt GK2P52/GK2I52/GK2D52/GK2F52 le collegano).
Poi accendi in Dolphin Grafica > Avanzate > "Carica texture personalizzate".

Fuori dall'app per Windows non ci sono: il menu in gioco (LB + RB), la regolazione della camera dal vivo, la mappa 3D,
le ragnatele del costume alternativo. Tutto il resto sta nei codici e funziona uguale.
Codice sorgente e app per Windows: {codici}
"""

ANDROID_EN = """SM2 ENHANCED {ver} - ANDROID
==============================

{comune}
HOW TO INSTALL
1. Install Dolphin (Play Store or dolphin-emu.org) and add your game.
2. NEW Dolphin (nothing to keep): Dolphin > Settings > User Data > Import User Data > choose this zip.
   Careful: importing REPLACES Dolphin's data (settings, saves, states).
   ALREADY using Dolphin: Settings > User Data > open the user folder and copy into it the folders of this zip
   (GameSettings, GC, Config/Profiles), without the Config/Dolphin.ini file.
3. Settings > Config > General > turn on "Enable Cheats" (already on with the import).
4. Touchscreen: nothing else to do. Gamepad: Settings > GameCube Input > Port 1 > Profile > load "spiderman 2",
   then pick your controller as the device and save the profile.
5. Very fast phone (Snapdragon 8 Gen 2 or similar): it runs at 60 fps. If it stutters, in the game's settings
   (long press the game > Edit settings) lower the resolution or turn off the "$60fps" code in Cheats.
"""
ANDROID_IT = """COME SI INSTALLA
1. Installa Dolphin (Play Store o dolphin-emu.org) e aggiungi il gioco.
2. Dolphin NUOVO (niente da tenere): Dolphin > Impostazioni > Dati utente > Importa dati utente > scegli questo zip.
   Attenzione: l'importazione SOSTITUISCE i dati di Dolphin (impostazioni, salvataggi, stati).
   Usi GIÀ Dolphin: Impostazioni > Dati utente > apri la cartella utente e copiaci dentro le cartelle di questo zip
   (GameSettings, GC, Config/Profiles), senza il file Config/Dolphin.ini.
3. Impostazioni > Configurazione > Generale > accendi "Abilita trucchi" (con l'importazione è già acceso).
4. Touch: niente altro da fare. Pad: Impostazioni > Input GameCube > Porta 1 > Profilo > carica "spiderman 2",
   poi scegli il tuo controller come dispositivo e salva il profilo.
5. Telefono molto potente (Snapdragon 8 Gen 2 o simili): va a 60 fps. Se scatta, nelle impostazioni del gioco
   (tieni premuto sul gioco > Modifica impostazioni) abbassa la risoluzione o spegni il codice "$60fps" nei Trucchi.
"""
LINUX_EN = """SM2 ENHANCED {ver} - LINUX / STEAM DECK
========================================

{comune}
HOW TO INSTALL
1. Install Dolphin: on Steam Deck from Discover (desktop mode) or with EmuDeck; on other distros the Flatpak
   (org.DolphinEmu.dolphin-emu) or your package manager. Add your game.
2. Copy the two folders of this zip:
   - Flatpak (Steam Deck, EmuDeck, Discover):
       config/ -> ~/.var/app/org.DolphinEmu.dolphin-emu/config/dolphin-emu/
       data/   -> ~/.var/app/org.DolphinEmu.dolphin-emu/data/dolphin-emu/
   - Native package:
       config/ -> ~/.config/dolphin-emu/
       data/   -> ~/.local/share/dolphin-emu/
   (Show hidden files to see the folders that start with a dot. Merge the folders, don't delete what's there.)
   The 100% save is data/GC: skip it if you want to keep your own save.
3. Dolphin > Config > General > turn on "Enable Cheats".
4. Controller: the profile "spiderman 2" is made for the Steam Deck's built-in controls. With another pad:
   Controllers > Port 1 Configure > Profile "spiderman 2" > Load, choose your controller as the Device, Save.
   On Steam Deck in Game Mode, if Steam Input is in the way, pick "Steam Deck Controller" as the Device.
5. HD textures folder: data/dolphin-emu/Load/Textures/GK2E52 (same paths as step 2).
"""
LINUX_IT = """COME SI INSTALLA
1. Installa Dolphin: sullo Steam Deck da Discover (modalità desktop) o con EmuDeck; sulle altre distribuzioni il Flatpak
   (org.DolphinEmu.dolphin-emu) o il gestore dei pacchetti. Aggiungi il gioco.
2. Copia le due cartelle di questo zip:
   - Flatpak (Steam Deck, EmuDeck, Discover):
       config/ -> ~/.var/app/org.DolphinEmu.dolphin-emu/config/dolphin-emu/
       data/   -> ~/.var/app/org.DolphinEmu.dolphin-emu/data/dolphin-emu/
   - Pacchetto normale:
       config/ -> ~/.config/dolphin-emu/
       data/   -> ~/.local/share/dolphin-emu/
   (Mostra i file nascosti per vedere le cartelle che iniziano col punto. Unisci le cartelle, non cancellare niente.)
   Il salvataggio al 100% è data/GC: saltalo se vuoi tenere il tuo.
3. Dolphin > Config > Generale > accendi "Abilita trucchi".
4. Controller: il profilo "spiderman 2" è fatto per i comandi dello Steam Deck. Con un altro pad:
   Controller > Porta 1 Configura > Profilo "spiderman 2" > Carica, scegli il tuo controller come Dispositivo, Salva.
   Sullo Steam Deck in modalità Gioco, se Steam Input dà fastidio, scegli "Steam Deck Controller" come Dispositivo.
5. Cartella delle texture HD: data/dolphin-emu/Load/Textures/GK2E52 (stessi percorsi del passo 2).
"""


def leggimi(testo_en, testo_it):
    return (testo_en.format(ver=core.VERSIONE_APP, comune=COMUNE_EN.format(re=RE_MODDB, codici=CODICI)).rstrip() + "\n\n\n"
            + "ITALIANO\n========\n\n" + COMUNE_IT.format(re=RE_MODDB, codici=CODICI) + "\n" + testo_it)


def crea(uscita):
    uscita = Path(uscita)
    uscita.mkdir(parents=True, exist_ok=True)
    fatti = []
    for nome, piatt, controller, grafica, en, it, nel_ini in (
            ("Android", "android", "android_retroid", core.ANDROID_BASE, ANDROID_EN, ANDROID_IT, False),
            ("Linux.SteamDeck", "linux", "linux_deck", core.LINUX_BASE, LINUX_EN, LINUX_IT, True)):
        tmp = Path(tempfile.mkdtemp(prefix="sm2_pacchetto_"))
        try:
            (tmp / "Config").mkdir()
            dest = uscita / f"SM2.Enhanced.{core.VERSIONE_APP}.{nome}.zip"
            dest.unlink(missing_ok=True)
            e = core.Esportazione(tmp, dest, piatt, controller, core.ID_GIOCO, formato="png", salvataggi=True,
                                  leggimi=leggimi(en, it), grafica=grafica, parti=("ini", "controller"),
                                  profilo_negli_ini=nel_ini)
            e.esegui()
            if e.errore:
                raise RuntimeError(f"{nome}: {e.errore}")
            with zipfile.ZipFile(dest, "a", zipfile.ZIP_DEFLATED) as z:
                # cartella delle texture gia' pronta: chi scarica RE le mette in GK2E52, i .txt la collegano alle altre versioni
                for g in core.ID_GIOCO[1:]:
                    z.writestr(core._nel_zip(piatt, f"Load/Textures/GK2E52/{g}.txt"), "")
                if piatt == "android":  # per "Importa dati utente" (Dolphin nuovo): trucchi gia' accesi
                    z.writestr("Config/Dolphin.ini", "[Core]\r\nEnableCheats = True\r\n")
            fatti.append(dest)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    return fatti


if __name__ == "__main__":
    for f in crea(sys.argv[1] if len(sys.argv) > 1 else "dist"):
        with zipfile.ZipFile(f) as z:
            print(f.name, f"{f.stat().st_size // 1024} KB", len(z.namelist()), "file")
