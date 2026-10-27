// MENU IN GIOCO > MONDO: due pagine (LT/RT), CIELO (ora del giorno, ora.py) e VIAGGIO (teletrasporto, teletrasporto.py).
// Cielo: cielo disegnato che cambia colore con l'ora, città, sole/luna sull'arco, orologio grande, barra delle 24 ore.
// ←/→ = 15 minuti (tenendo premuto di più), ↑/↓ = un'ora, Y = momento dopo (alba/giorno/tramonto/notte), A = ferma /
// fai scorrere il tempo. Ogni cambio va subito nel gioco (DME) e, col tempo fermo, anche negli INI.
// Viaggio: due colonne (←/→): a sinistra la mappa 3D della città (m3Riquadro in menu_mappa.js: anteprima + A = apri), a
// destra "torna dov'eri" e i tuoi posti salvati con la foto (↑/↓ scegli, A vai, X salva il posto dove sei, Y toglie un posto).
"use strict";
const OR = { pag: "cielo", sec: null, fermo: false, gioco: false, tmInvia: null, tmLeggi: null, cambiato: 0, citta: null };
const VG = { dati: null, sel: 0, togli: false, vai: false, nome: null };  // vai = primo A su un posto (John: premuto per
// sbaglio); nome = indice del posto che stai rinominando (L3 o F2: si scrive con la tastiera, Invio/A salva, Esc/B annulla)
const OR_MOMENTI = [["alba", 6 * 3600 + 1800, "i-alba"], ["giorno", 12 * 3600, "i-sole"], ["tramonto", 18 * 3600, "i-tramonto"], ["notte", 22 * 3600 + 1800, "i-luna"]];
// colori del cielo (ora, in alto, in basso), interpolati
const OR_CIELO = [[0, "#04071a", "#0e1631"], [4.5, "#070b22", "#1b2147"], [5.6, "#2b2457", "#c56f99"], [6.6, "#5a6fb8", "#f2a7a0"],
  [8, "#4d8fd6", "#bfe0ff"], [12, "#2f7fe0", "#9fd0ff"], [16.5, "#4a7fd0", "#f3c58f"], [18, "#5b4a9e", "#f08c6c"],
  [19, "#2c2455", "#7a3a6a"], [20.5, "#0b1030", "#1d2350"], [24, "#04071a", "#0e1631"]];

function orHex(c) { return [1, 3, 5].map(i => parseInt(c.slice(i, i + 2), 16)); }
function orMix(a, b, f) { const x = orHex(a), y = orHex(b); return `rgb(${x.map((v, i) => Math.round(v + (y[i] - v) * f)).join(",")})`; }
function orColori(h) {
  for (let i = 0; i < OR_CIELO.length - 1; i++) {
    const [h0, a0, b0] = OR_CIELO[i], [h1, a1, b1] = OR_CIELO[i + 1];
    if (h >= h0 && h <= h1) { const f = (h - h0) / (h1 - h0); return [orMix(a0, a1, f), orMix(b0, b1, f)]; }
  }
  return [OR_CIELO[0][1], OR_CIELO[0][2]];
}
const orNotte = h => h < 5 || h > 20.5 ? 1 : h < 6.5 ? (6.5 - h) / 1.5 : h > 19 ? (h - 19) / 1.5 : 0;  // 0 giorno .. 1 notte
const orTesto = s => `${String(Math.floor(s / 3600) % 24).padStart(2, "0")}:${String(Math.floor(s / 60) % 60).padStart(2, "0")}`;
function orFase(h) {
  return h >= 5 && h < 7.5 ? "alba" : h >= 7.5 && h < 17 ? "giorno" : h >= 17 && h < 19.5 ? "tramonto" : h >= 19.5 && h < 22 ? "sera" : "notte";
}
function orCitta() {  // skyline su due strati, con finestre che si accendono di notte: SVG fatto una volta
  if (OR.citta) return OR.citta;
  let seme = 11, lontani = "", palazzi = "", finestre = "";
  const rnd = () => (seme = (seme * 9301 + 49297) % 233280) / 233280;
  for (let x = -10; x < 1000;) {  // lontani: tanti, sottili, qualche guglia
    const w = 22 + rnd() * 40, h = 90 + rnd() * 150, y = 300 - h;
    lontani += `<rect x="${x | 0}" y="${y | 0}" width="${w | 0}" height="${h | 0}"/>`;
    if (rnd() < 0.18) lontani += `<rect x="${(x + w / 2 - 1.5) | 0}" y="${(y - 26) | 0}" width="3" height="26"/>`;
    x += w + 2;
  }
  for (let x = 0; x < 1000;) {  // vicini: più bassi e larghi, con finestre e qualche tetto a gradino
    const w = 40 + rnd() * 70, h = 50 + rnd() * 120, y = 300 - h;
    palazzi += `<rect x="${x | 0}" y="${y | 0}" width="${w | 0}" height="${h | 0}"/>`;
    if (rnd() < 0.35) palazzi += `<rect x="${(x + w * 0.2) | 0}" y="${(y - 14) | 0}" width="${(w * 0.6) | 0}" height="14"/>`;
    for (let wy = y + 10; wy < 290; wy += 13)
      for (let wx = x + 6; wx < x + w - 7; wx += 10)
        if (rnd() < 0.32) finestre += `<rect x="${wx | 0}" y="${wy | 0}" width="4" height="5" fill="${rnd() < .75 ? "#ffd98a" : "#9cc4ff"}"/>`;
    x += w + 5;
  }
  return (OR.citta = `<svg class="or-citta" viewBox="0 0 1000 300" preserveAspectRatio="none"><g class="or-lontani">${lontani}</g>
    <g class="or-palazzi">${palazzi}</g><g class="or-finestre">${finestre}</g></svg>`);
}

// ---------------------------------------------------------------- pagina e schede
function disegnaMondo() {
  const box = $("#mp-ora");
  if (!box) return;
  if (!box.querySelector(".or-schede")) {
    box.innerHTML = `<div class="or-schede"><kbd class="pad">LT</kbd>
        <button data-pag="cielo"><svg><use href="#i-sole"/></svg><span><b>${t("mn_cielo")}</b><small>${t("or_cielo_sub")}</small></span></button>
        <button data-pag="viaggio"><svg><use href="#i-pin"/></svg><span><b>${t("vg_tit")}</b><small>${t("vg_sub")}</small></span></button>
        <kbd class="pad">RT</kbd></div>
      <div class="or-corpo" data-pag="cielo"></div><div class="or-corpo" data-pag="viaggio"></div>`;
    box.querySelectorAll(".or-schede button").forEach(b => b.onclick = () => mondoPagina(b.dataset.pag));
  }
  box.querySelectorAll(".or-schede button").forEach(b => b.classList.toggle("attivo", b.dataset.pag === OR.pag));
  box.querySelectorAll(".or-corpo").forEach(c => c.classList.toggle("attiva", c.dataset.pag === OR.pag));
  if (OR.pag === "cielo") disegnaOra(); else disegnaViaggio();
}
function mondoPagina(p) {
  OR.pag = p;
  VG.togli = false;
  disegnaMondo();
  if (p === "viaggio") vgLeggi(); else orVivo();
  piede();
}

// ---------------------------------------------------------------- cielo
function disegnaOra() {
  const box = $('#mp-ora .or-corpo[data-pag="cielo"]');
  if (!box) return;
  if (!box.querySelector(".or-cielo")) {
    box.innerHTML = `<div class="or-cielo"><div class="or-stelle"></div><svg class="or-arco" viewBox="0 0 1000 420" preserveAspectRatio="none"><path d="M60 400 A 440 360 0 0 1 940 400" vector-effect="non-scaling-stroke"/></svg>
        <div class="or-astro"></div>${orCitta()}
        <div class="or-orologio"><b></b><small></small><em class="or-stato"></em></div>
        <div class="or-vivo"><img alt=""><span><i></i>${t("or_vivo")}</span></div></div>
      <div class="or-lato"><div class="or-titolo">${t("or_momenti")}</div><div class="or-momenti">${OR_MOMENTI.map(([k, s, ic]) =>
        `<button data-s="${s}"><svg><use href="#${ic}"/></svg><span><b>${t("gr_ora_" + k)}</b><small>${orTesto(s)}</small></span></button>`).join("")}</div>
        <div class="or-titolo">${t("or_ora_precisa")}</div>
        <div class="or-barra"><div class="or-pista"></div><i class="or-cursore"></i>
          <div class="or-tacche">${[0, 6, 12, 18, 24].map(h => `<span>${String(h % 24).padStart(2, "0")}</span>`).join("")}</div></div>
        <div class="or-titolo">${t("or_tempo")}</div><button class="or-ferma"><span class="or-int"><i></i></span><span><b></b><small></small></span></button>
        <p class="or-nota"></p></div>`;
    box.querySelectorAll(".or-momenti button").forEach(b => b.onclick = () => orCambia(+b.dataset.s, true));
    box.querySelector(".or-ferma").onclick = () => tastoOra("a");
    const pista = box.querySelector(".or-pista");  // clic sulla barra = quell'ora (a quarti d'ora)
    pista.style.background = `linear-gradient(90deg, ${Array.from({ length: 25 }, (_, i) => orColori(i)[1]).join(", ")})`;
    pista.onclick = e => { const r = pista.getBoundingClientRect(); orCambia(Math.round((e.clientX - r.left) / r.width * 96) * 900, true); };
  }
  const s = OR.sec ?? 12 * 3600, h = s / 3600, [alto, basso] = orColori(h), notte = orNotte(h);
  box.querySelector(".or-cielo").style.background = `linear-gradient(180deg, ${alto}, ${basso})`;
  box.querySelector(".or-stelle").style.opacity = notte;
  box.querySelector(".or-finestre").style.opacity = 0.15 + notte * 0.85;
  box.querySelector(".or-palazzi").style.fill = orMix("#3b4a6b", "#070a14", Math.min(1, 0.15 + notte * 0.85));
  box.querySelector(".or-lontani").style.fill = orMix("#7f93b8", "#151b36", notte);  // nella foschia: più chiari dei vicini
  box.querySelector(".or-cursore").style.left = (s / 86400 * 100) + "%";
  // sole dalle 5:30 alle 19:30 lungo l'arco, la luna il resto del tempo
  const sole = h >= 5.5 && h <= 19.5, f = sole ? (h - 5.5) / 14 : ((h - 19.5 + 24) % 24) / 10;
  const a = Math.PI * (1 - Math.min(1, Math.max(0, f)));
  const astro = box.querySelector(".or-astro");
  astro.className = "or-astro " + (sole ? "sole" : "luna");
  astro.style.left = 50 + 44 * Math.cos(a) + "%";
  astro.style.top = 95 - 86 * Math.sin(a) + "%";
  box.querySelector(".or-orologio b").textContent = OR.sec === null ? "--:--" : orTesto(s);
  box.querySelector(".or-orologio small").textContent = t("or_fase_" + orFase(h));
  const st = box.querySelector(".or-stato");
  st.textContent = !OR.gioco ? t("or_niente_gioco") : OR.fermo ? "⏸ " + t("or_fermo") : "▶ " + t("or_scorre");
  st.className = "or-stato " + (OR.fermo ? "fermo" : "");
  box.querySelectorAll(".or-momenti button").forEach(b => b.classList.toggle("attivo", Math.abs(+b.dataset.s - s) < 1800));
  const fb = box.querySelector(".or-ferma");
  fb.classList.toggle("on", OR.fermo);
  fb.querySelector("b").textContent = t(OR.fermo ? "or_fermo" : "or_scorre");
  fb.querySelector("small").textContent = t(OR.fermo ? "or_fermo_sub" : "or_scorre_sub");
  box.querySelector(".or-nota").textContent = t("or_nota");
  if (M.tab === "ora" && !SI.aperto && !ST.aperto) piede();  // "Ferma il tempo" / "Fai scorrere"
}
async function orLeggi() {
  if (Date.now() - OR.cambiato < 1500) return;  // stai scorrendo: non sovrascrivo la tua scelta con quella del gioco
  const r = await api().menu_ora_stato();
  if (!r || r.errore) return;
  OR.gioco = !!r.gioco;
  if (r.sec !== null && r.sec !== undefined) OR.sec = r.sec;
  OR.fermo = !!r.fermo;
  if (M.tab === "ora" && OR.pag === "cielo") disegnaOra();
}
function oraApri() {
  disegnaMondo(); orLeggi(); orVivo();
  clearInterval(OR.tmLeggi); OR.tmLeggi = setInterval(() => { orLeggi(); if (OR.pag === "viaggio") vgLeggi(); }, 1000);
  if (OR.pag === "viaggio") vgLeggi();
}
function oraChiudi() { clearInterval(OR.tmLeggi); clearTimeout(OR.tmVivo); }
function orCambia(sec, subito = false) {
  OR.sec = ((Math.round(sec) % 86400) + 86400) % 86400;
  OR.cambiato = Date.now();
  disegnaOra();
  // tenendo premuto l'ora va nel gioco mentre scorre (~10 volte al secondo), non solo quando lasci (John: si perdeva
  // l'effetto del cielo che cambia dal vivo); l'ultima scelta parte comunque
  clearTimeout(OR.tmInvia);
  const invia = () => { OR.inviato = Date.now(); api().menu_ora_imposta(OR.sec, OR.fermo); };
  if (subito || Date.now() - (OR.inviato || 0) > 90) invia();
  else OR.tmInvia = setTimeout(invia, 90);
}
// riquadro "nel gioco" nell'angolo del cielo: la finestra del gioco dal vivo (il menu la copre), per vedere il cielo vero
// cambiare mentre scegli l'ora
async function orVivo() {
  clearTimeout(OR.tmVivo);
  if (M.chiuso || M.tab !== "ora" || OR.pag !== "cielo") return;
  const img = $("#mp-ora .or-vivo img");
  if (img) {
    const r = await api().menu_ora_vista();
    if (r) { img.src = "data:image/jpeg;base64," + r; img.parentNode.classList.add("pronto"); }
  }
  OR.tmVivo = setTimeout(orVivo, Date.now() - OR.cambiato < 2000 ? 120 : 400);
}
function tastoOra(k, rip = 0) {  // true = tasto usato qui
  if (k === "lt" || k === "rt") { mondoPagina(OR.pag === "cielo" ? "viaggio" : "cielo"); return true; }
  if (OR.pag === "viaggio") return tastoViaggio(k);
  const s = OR.sec ?? 12 * 3600;
  if (k === "sx" || k === "dx") { const passo = rip > 12 ? 3600 : rip > 4 ? 1800 : 900; orCambia(Math.round(s / 900) * 900 + (k === "dx" ? passo : -passo)); return true; }
  if (k === "su" || k === "giu") { orCambia(s + (k === "su" ? 3600 : -3600)); return true; }
  if (k === "y") {  // momento dopo
    const i = OR_MOMENTI.findIndex(([, x]) => x > s + 60);
    orCambia(OR_MOMENTI[i < 0 ? 0 : i][1], true);
    return true;
  }
  if (k === "a") {
    OR.fermo = !OR.fermo;
    OR.cambiato = Date.now();
    disegnaOra();
    api().menu_ora_imposta(s, OR.fermo);
    toast(t(OR.fermo ? "or_fermo_toast" : "or_scorre_toast"));
    return true;
  }
  return false;
}

// ---------------------------------------------------------------- viaggio
function vgVoci() {  // cosa si può scegliere con ↑/↓
  const d = VG.dati || {};
  return [{ tipo: "mappa" }, ...(d.indietro ? [{ tipo: "indietro" }] : []), { tipo: "salva" },
    ...(d.posti || []).map((p, i) => ({ tipo: "posto", i }))];
}
async function vgLeggi() {
  if (M3.stato) return;  // mappa 3D aperta: la pagina sotto la barra non serve (e il ponte JSON ruba CPU a Dolphin)
  const r = await api().menu_viaggio_stato();
  if (!r || r.errore) return;
  // ridisegno solo se qualcosa è cambiato: rifare tutto ogni secondo faceva sfarfallare foto e pallino "tu" dell'anteprima
  const firma = JSON.stringify([r.gioco, r.indietro, (r.posti || []).map(p => [p.x, p.z, p.quando, !!p.foto, p.nome])]);
  VG.dati = r;
  if (r.esito && r.esito !== "ok") toast(t("vg_esito_" + r.esito));
  VG.sel = Math.min(VG.sel, vgVoci().length - 1);
  if ((firma === VG.firma && !r.esito) || VG.nome !== null) return;  // (mentre scrivi il nome non ridisegno)
  VG.firma = firma;
  if (M.tab === "ora" && OR.pag === "viaggio") disegnaViaggio();
}
const vgFa = s => s < 60 ? t("vg_fa_s", s) : s < 3600 ? t("vg_fa_m", Math.round(s / 60)) : t("vg_fa_h", Math.round(s / 3600));
function disegnaViaggio() {
  const box = $('#mp-ora .or-corpo[data-pag="viaggio"]');
  if (!box) return;
  const d = VG.dati || { posti: [] }, voci = vgVoci(), sel = voci[VG.sel] || {};
  const sinistra = m3Riquadro(d, sel.tipo === "mappa");  // la mappa 3D (al posto della mappa piatta e dei passi)
  // sopra tutta la pagina: "in viaggio" mentre si sposta, poi per un attimo l'altezza dove è arrivato (punto della mappa)
  const velo = VG.viaggio ? `<div class="vg-viaggio"><div class="vg-giro"></div><b>${t("vg_in_viaggio")}</b><small>${t("vg_in_viaggio_sub")}</small></div>`
    : VG.arrivo != null ? `<div class="vg-viaggio arrivato"><div class="vg-ok">✓</div><b>${VG.arrivo < 4 ? t("vg_arrivato_terra") : t("vg_arrivato", VG.arrivo)}</b></div>` : "";
  box.innerHTML = `${sinistra}
    <div class="vg-lato"><div class="or-titolo">${t("vg_posti")}</div><div class="vg-lista">
      ${d.indietro ? `<button class="vg-voce indietro ${sel.tipo === "indietro" ? "focus" : ""} ${VG.vai && sel.tipo === "indietro" ? "conferma" : ""}" data-v="indietro"><span class="vg-ico">↩</span><span><b>${VG.vai && sel.tipo === "indietro" ? t("vg_vai_sicuro") : t("vg_indietro")}</b><small>${t("vg_indietro_sub")}</small></span></button>` : ""}
      <button class="vg-voce salva ${sel.tipo === "salva" ? "focus" : ""}" data-v="salva"><span class="vg-ico">+</span><span><b>${t("vg_salva")}</b><small>${t("vg_salva_sub")}</small></span><kbd class="pad x">X</kbd></button>
      ${(d.posti || []).map((p, i) => `<button class="vg-voce posto ${sel.tipo === "posto" && sel.i === i ? "focus" : ""} ${VG.togli && sel.i === i ? "togli" : ""} ${VG.vai && sel.tipo === "posto" && sel.i === i ? "conferma" : ""}" data-v="posto" data-i="${i}">
        <span class="vg-foto">${p.foto ? `<img src="data:image/jpeg;base64,${p.foto}" alt="">` : "<svg><use href=\"#i-pin\"/></svg>"}</span>
        <span>${VG.nome === i ? `<input class="vg-nome" maxlength="32" placeholder="${t("vg_posto_n", d.posti.length - i)}">` : `<b>${VG.togli && sel.tipo === "posto" && sel.i === i ? t("vg_togli_sicuro") : VG.vai && sel.tipo === "posto" && sel.i === i ? t("vg_vai_sicuro") : vgNome(p, i)}</b>`}<small>${VG.nome === i ? t("vg_nome_sub") : p.nome ? t("vg_posto_n", d.posti.length - i) + " · " + (p.quando || "") : p.quando || ""}</small></span></button>`).join("")}
      ${(d.posti || []).length ? "" : `<p class="vg-vuoto">${t("vg_vuoto")}</p>`}
    </div><p class="or-nota">${t("vg_nota")}</p></div>${velo}`;
  box.querySelectorAll("[data-v]").forEach(b => b.onclick = () => {
    VG.sel = Math.max(0, vgVoci().findIndex(v => v.tipo === b.dataset.v && (v.i === undefined || v.i === +b.dataset.i)));
    tastoViaggio("a");
  });
  const f = box.querySelector(".vg-voce.focus");
  if (f) f.scrollIntoView({ block: "nearest" });
  const inp = box.querySelector(".vg-nome");
  if (inp) {
    inp.value = (d.posti[VG.nome] || {}).nome || "";
    inp.onclick = e => e.stopPropagation();
    api().menu_tastiera().finally(() => { inp.focus(); inp.select(); });  // (la finestra del menu prende la tastiera)
  }
}
function vgNome(p, i) { return p.nome || t("vg_posto_n", ((VG.dati || {}).posti || []).length - i); }
function vgRinomina(salva) {  // fine della scrittura del nome
  const i = VG.nome, inp = $("#mp-ora .vg-nome");
  VG.nome = null;
  if (salva && inp && i !== null) {
    const nome = inp.value.trim();
    const p = ((VG.dati || {}).posti || [])[i];
    if (p) p.nome = nome || undefined;
    api().menu_viaggio_rinomina(i, nome).then(() => { VG.firma = null; vgLeggi(); });
    toast(t(nome ? "vg_rinominato" : "vg_nome_tolto"));
  }
  disegnaViaggio(); piede();
}
function vgInViaggio(si, esito, altezza) {  // da Python: Spidey si sta spostando (il menu resta aperto finché non arriva)
  VG.viaggio = si;
  clearTimeout(VG.tmArrivo);
  VG.arrivo = !si && esito === "ok" && altezza != null ? altezza : null;
  if (VG.arrivo != null) VG.tmArrivo = setTimeout(() => { VG.arrivo = null; if (M.tab === "ora" && OR.pag === "viaggio") disegnaViaggio(); }, 2500);
  if (!si && esito && esito !== "ok" && esito !== "lento") toast(t("vg_esito_" + esito));
  if (!si) vgLeggi();
  if (M.tab === "ora" && OR.pag === "viaggio") disegnaViaggio();
}
async function vgVai(cosa, i) {
  const r = await api().menu_viaggio_vai(cosa, i);
  if (!r || r.errore) toast(t("vg_err_" + ((r && r.errore) || "gioco")));
}
async function vgSalva() {
  const r = await api().menu_viaggio_salva();
  if (!r || r.errore) { toast(t("vg_err_gioco")); return; }
  toast(t("vg_salvato"));
  await vgLeggi();
  VG.sel = vgVoci().findIndex(v => v.tipo === "salva") + 1;
  disegnaViaggio();
}
function tastoViaggio(k) {
  if (VG.viaggio) return true;  // in viaggio: aspetta che arrivi
  if (VG.nome !== null) {  // stai scrivendo il nome: A salva, B annulla, il resto lo fa la tastiera
    if (k === "a" || k === "b") vgRinomina(k === "a");
    return true;
  }
  const voci = vgVoci(), v = voci[VG.sel] || {};
  const vai = VG.vai; VG.vai = false;  // la conferma vale solo per il tasto subito dopo
  if (vai && k !== "a") { disegnaViaggio(); piede(); }
  // due colonne: mappa a sinistra (voce 0), posti a destra (voci 1..). ←/→ passano da una all'altra, ↑/↓ scorrono i posti
  // (prima tutto era una lista sola con ↑/↓: per arrivare ai posti a destra bisognava "scendere", John: controintuitivo)
  if (k === "sx" || k === "dx") {
    if (k === "dx" && VG.sel === 0 && voci.length > 1) VG.sel = Math.min(VG.lista || 1, voci.length - 1);
    else if (k === "sx" && VG.sel > 0) { VG.lista = VG.sel; VG.sel = 0; }
    VG.togli = false; disegnaViaggio(); piede(); return true;
  }
  if (k === "su" || k === "giu") {
    if (VG.sel === 0) VG.sel = Math.min(VG.lista || 1, voci.length - 1);  // dalla mappa: si entra nei posti
    else VG.sel = Math.max(1, Math.min(voci.length - 1, VG.sel + (k === "giu" ? 1 : -1)));
    VG.lista = VG.sel || VG.lista;
    VG.togli = false; disegnaViaggio(); piede(); return true;
  }
  if (k === "x") { vgSalva(); return true; }
  if ((k === "l3" || k === "r3") && v.tipo === "posto") { VG.togli = false; VG.nome = v.i; disegnaViaggio(); piede(); return true; }
  if (k === "y" && v.tipo === "posto") {
    if (!VG.togli) { VG.togli = true; disegnaViaggio(); piede(); return true; }
    VG.togli = false;
    api().menu_viaggio_togli(v.i).then(vgLeggi);
    toast(t("vg_tolto"));
    return true;
  }
  if (k === "a") {
    VG.togli = false;
    if (v.tipo === "salva") vgSalva();
    else if (v.tipo === "mappa") {  // la mappa 3D (apre anche la mappa del gioco se è chiusa)
      if ((VG.dati || {}).gioco) m3Apri();
      else toast(t("vg_err_gioco"));
    }
    else if (v.tipo === "indietro" || v.tipo === "posto") {  // due A: un A per sbaglio non ti porta via (John)
      if (!vai) { VG.vai = true; disegnaViaggio(); piede(); return true; }
      disegnaViaggio(); piede();
      if (v.tipo === "indietro") vgVai("indietro"); else vgVai("posto", v.i);
    }
    return true;
  }
  return false;
}

function oraPiede(k) {
  if (MC.aperto) return mcPiede(k);
  const comuni = [[k("", "LT") + k("", "RT"), t(OR.pag === "cielo" ? "vg_tit" : "mn_cielo")], [k("", "LB") + k("", "RB"), t("mn_sezione")], [k("b", "B"), t("mn_chiudi")]];
  if (OR.pag === "viaggio") {
    if (VG.nome !== null) return [[k("a", "A"), t("vg_nome_salva")], [k("b", "B"), t("mn_indietro")]];
    const v = vgVoci()[VG.sel] || {};
    return [[k("", "←") + k("", "→"), t(VG.sel === 0 ? "vg_p_posti" : "vg_p_mappa")], ...(VG.sel > 0 ? [[k("", "↑") + k("", "↓"), t("mn_scegli")]] : []),
      [k("a", "A"), t(v.tipo === "salva" ? "vg_salva_corto" : v.tipo === "mappa" ? "m3_apri" : VG.vai ? "vg_vai_conferma" : "vg_vai_corto")], [k("x", "X"), t("vg_salva_corto")],
      ...(v.tipo === "posto" ? [[k("y", "Y"), t(VG.togli ? "vg_togli_sicuro" : "vg_togli")], [k("stick", "L3"), t("vg_rinomina")]] : []), ...comuni];
  }
  return [[k("", "←") + k("", "→"), t("or_p_minuti")], [k("", "↑") + k("", "↓"), t("or_p_ore")], [k("y", "Y"), t("or_p_momenti")],
    [k("a", "A"), t(OR.fermo ? "or_p_scorri" : "or_p_ferma")], ...comuni];
}
