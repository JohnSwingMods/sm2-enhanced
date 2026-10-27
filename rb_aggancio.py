"""RB (= Z del GameCube) SENZA RADDRIZZARE LA CAMERA (pezzo nascosto di "Cambio costume", codici_db "skin_aggancio").

John: "con la camera migliorata/originale RB raddrizza la camera, ed è brutto che per cambiare costume ti si raddrizzi ogni
volta". Il colpetto di RB cambia costume (costume_ar.py), ma il gioco originale con Z rimette la camera dietro Spidey.
La funzione che legge i tasti per Spidey (0x802CAFD8, ingresso 0x13 = Z: "andi. r0, r9, 0x10" a ITA 0x802CB410,
USA/UK/DE/FR 0x802CB3A0) qui vede Z SOLO se:
  - è tenuto da più di TENUTA fotogrammi (contatore N = 817F0005 del codice costume: tenuto a lungo = niente costume,
    camera raddrizzata come prima; stessa soglia del codice costume), oppure
  - insieme a Z c'è su (rallenty) o Start (Select = Z + Start = mappa): le combinazioni del gioco arrivano subito, oppure
  - fuori partita (Spidey stato -1) o in pausa/rallenty (byte pausa 1): lì il codice costume non conta e Z non va toccato.
I nostri codici leggono i tasti dalla memoria (805546A0 / 80554620): per loro Z resta Z. Senza il codice costume acceso
questo pezzo è spento (parte_di), quindi N non resta mai a 0 con Z nascosto per sempre.
Provato su ITA (cartella utente a parte): camera originale, colpetto = camera ferma e costume cambiato, tenuto = raddrizza.
"""
import cam_ps4
import ppcasm as asm

NOME = "$RB hook (needed by RB tap to switch skin)"
DIST = 0x2A0  # dal "andi. r0, r3, 4" della croce (cam_ps4.VERSIONI croce_giu) al "andi. r0, r9, 0x10" di Z
ORIGINALE = 0x71200010  # andi. r0, r9, 0x10
TENUTA = 15  # fotogrammi (0,25 s a 60 fps): uguale a costume_ar.MAX_FOTOGRAMMI
N = 0x817F0005


def _routine(v):
    st, pa = v["stato"], v["pausa"]
    return f"""
    andi. r0, r9, 0x10
    beq rb_fine
    andi. r0, r9, 0x1008
    bne rb_vero
    lis r12, {st >> 16:#x}
    ori r12, r12, {st & 0xFFFF:#x}
    lwz r0, 0(r12)
    cmpwi r0, -1
    beq rb_vero
    lis r12, {pa >> 16:#x}
    ori r12, r12, {pa & 0xFFFF:#x}
    lbz r0, 0(r12)
    cmpwi r0, 0
    bne rb_vero
    lis r12, 0x817F
    lbz r0, {N & 0xFFFF:#x}(r12)
    cmplwi r0, {TENUTA}
    bgt rb_vero
    li r0, 0
    cmpwi r0, 0
    b rb_fine
rb_vero:
    li r0, 1
    cmpwi r0, 0
rb_fine:
"""


def punto(ver):
    return cam_ps4.VERSIONI[ver]["croce_giu"] + DIST


def codice(ver):
    return asm.c2(punto(ver), asm.assembla(_routine(cam_ps4.VERSIONI[ver])))


if __name__ == "__main__":
    for g in ("GK2I52", "GK2E52"):
        c = codice(g)
        print(g, hex(punto(g)), len(c) * 8, "byte Gecko")
        print("\n".join(c))
