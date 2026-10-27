"""ORA DEL GIORNO FISSA (idea di John, 2026-10-18: giorno / tramonto / notte dall'app o dal menu in gioco).

L'orologio del ciclo giorno-notte è un intero = secondi del giorno (0..86399): ITA 0x8056D188, USA/UK/DE/FR 0x8056D108
(il gioco lo legge come r13-0x6158 in tutte le versioni: 0x80011CB0.., aggiornamento 0x80012240..). Corre ~48 volte più
veloce del tempo vero (un giorno = ~30 minuti). Le copie (ore float 0x8056B8A4 ITA, secondi float 0x8056E358 ITA) le rifà
il gioco da questo a ogni fotogramma: scriverle non serve. Scrivendo l'intero cielo, luce e finestre cambiano subito
(provato su ITA: 21:09 -> 12:00). Ore scelte guardando le foto (dolphin_z/ore_mosaico.jpg): alba 6:30 (cielo rosa),
giorno 12:00, tramonto 18:00 (cielo viola-rosa, palazzi ancora al sole), notte 22:30 (finestre accese).

Codice AR nascosto "$Time of day (fixed, set by the app)" (codici_db "ora_fissa", parte_di "ora": la voce la gestisce il
menu in gioco > Cielo, non Codici): solo in partita (Spidey c'è e niente pausa) e solo se la parola SPENTO è 0, scrive i
secondi a ogni fotogramma. SPENTO (0x817FF100, memoria a zero a ogni avvio) la mette a 1 l'app quando cambi ora o fermi /
fai ripartire il tempo col gioco aperto: da lì l'ora la scrive l'app (un codice AR già caricato non si può cambiare) e il
codice nell'INI vale dalla prossima partita, anche senza l'app.
"""
NOME = "$Time of day (fixed, set by the app)"
ORE = {"alba": 6 * 3600 + 1800, "giorno": 12 * 3600, "tramonto": 18 * 3600, "notte": 22 * 3600 + 1800}
INDIRIZZO = {"GK2I52": 0x8056D188}  # le altre (stesso programma USA): 0x8056D108
PAUSA = {"GK2I52": 0x8056BA3B}  # byte pausa (anche rallenty); le altre 0x8056B9BB
SPENTO = 0x817FF100  # 1 = il codice dell'INI non scrive (ci pensa l'app, dal vivo)
# i 4 orari fissi anche come codici VISIBILI (Codici > Ora del giorno, esclusivi, spenti di base): stesse righe del codice
# nascosto, così si possono esportare (es. una versione "sempre notte" per il telefono). Il menu in gioco > Cielo usa il
# preset se l'ora scelta è uno di questi, se no il codice nascosto con l'ora precisa.
PRESET = {"alba": "$Time of day: dawn (6:30, fixed)", "giorno": "$Time of day: day (12:00, fixed)",
          "tramonto": "$Time of day: sunset (18:00, fixed)", "notte": "$Time of day: night (22:30, fixed)"}
TUTTI = [NOME, *PRESET.values()]


def indirizzo(gid):
    return INDIRIZZO.get(gid, 0x8056D108)


def righe(gid, secondi):
    pa = PAUSA.get(gid, 0x8056B9BB)
    return ["D4AD1A04 FFFFFFFF", f"C8{pa & 0xFFFFFF:06X} 00000000", f"0D{SPENTO & 0xFFFFFF:06X} 00000000",
            f"04{indirizzo(gid) & 0xFFFFFF:06X} {int(secondi) % 86400:08X}"]


def da_righe(righe_ini):
    """Secondi scritti in un blocco del codice (None se non riconosciuto)."""
    for r in righe_ini or []:
        r = r.strip().upper()
        if r.startswith("04") and len(r) == 17:
            return int(r[9:], 16) % 86400
    return None
