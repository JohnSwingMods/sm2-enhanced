// MENU IN GIOCO > MONDO > VIAGGIO: MAPPA DI TUTTA LA CITTÀ (mappa_citta.py). La fotografa l'app dal gioco dell'utente, una
// volta sola (giro fotografico di giorno e di notte), poi resta in AppData. Qui: anteprima nel riquadro di Viaggio (centrata
// su Spidey) e ESPLORATORE a tutto menu: levetta sinistra / frecce = muovi, levetta destra = gira (←/→) e zoom (↑/↓),
// LT/RT = zoom a scatti, R3 = orientamento di partenza, A = vai qui (sopra i tetti), Y = torna su Spidey, X due volte = rifai la mappa,
// B = indietro. Pixel della mappa = J . (x, z) + O (geometria da Python). Di notte si vede la mappa fatta di notte
// (dissolvenza all'alba e al tramonto, con l'ora del gioco).
"use strict";
const MC = { aperto: false, img: {}, px: 0, py: 0, s: 0.3, rot: 0, rifai: false, stickL: 0,
  tasselli: new Map(), chiesti: new Set() };
const MC_SMAX = 1.6;  // zoom massimo (pixel dello schermo per pixel della mappa: la mappa ha 1,5 pixel per metro)

function mcGeo() { return VG.dati && VG.dati.citta; }
function mcPx(geo, x, z) { const J = geo.J, O = geo.O; return [J[0][0] * x + J[0][1] * z + O[0], J[1][0] * x + J[1][1] * z + O[1]]; }
function mcMondo(geo, px, py) {
  const [[a, b], [c, d]] = geo.J, det = a * d - b * c, u = px - geo.O[0], v = py - geo.O[1];
  return [(d * u - b * v) / det, (-c * u + a * v) / det];
}
// strati della mappa: t giorno, a alba, s tramonto, n notte (mappe vecchie: solo giorno, o giorno e notte)
function mcStrati(geo) { return (geo && geo.strati) || (geo && geo.notte ? ["t", "n"] : ["t"]); }
// luce adesso, dall'ora del gioco (come cambia la mappa del gioco, misurato): {base, sopra, f} = strato sotto pieno e
// quello sopra con opacità f (dissolvenza tra due momenti)
function mcLuci(geo) {
  const st = mcStrati(geo), s = VG.dati && VG.dati.ora;
  if (s == null || st.length < 2) return { base: "t", sopra: null, f: 0 };
  const h = (s / 3600) % 24, tutte = st.includes("a") && st.includes("s");
  const k = tutte ? [[0, "n"], [5.5, "n"], [6.25, "a"], [7.5, "a"], [8.5, "t"], [17, "t"], [17.75, "s"], [18.5, "s"], [19.25, "n"], [24, "n"]]
    : [[0, "n"], [5, "n"], [7, "t"], [18, "t"], [20, "n"], [24, "n"]];
  for (let i = 0; i < k.length - 1; i++) {
    const [h0, l0] = k[i], [h1, l1] = k[i + 1];
    if (h >= h0 && h <= h1) return l0 === l1 ? { base: l0, sopra: null, f: 0 } : { base: l0, sopra: l1, f: (h - h0) / (h1 - h0) };
  }
  return { base: "t", sopra: null, f: 0 };
}
async function mcImmagine(grande, strato) {  // base64 da Python -> URL del blob (una volta)
  const k = `${grande ? "g" : "p"}${strato || "t"}`;
  if (MC.img[k]) return MC.img[k];
  const b = await api().menu_mappa_immagine(!!grande, strato || "t");
  if (!b) return null;
  const bin = atob(b), u8 = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) u8[i] = bin.charCodeAt(i);
  MC.img[k] = URL.createObjectURL(new Blob([u8], { type: "image/jpeg" }));
  return MC.img[k];
}
function mcDimentica() {
  for (const v of Object.values(MC.img)) URL.revokeObjectURL(v.url || v);  // (il mare: {url, colore})
  MC.img = {};
}

// ------------------------------------------------ riquadro di Viaggio
function mcRiquadro(d, focus) {  // HTML del riquadro di sinistra quando la mappa del gioco NON è aperta
  const lav = d.creando;
  if (lav) {
    const f = lav.fase === "foto" ? t(lav.notte ? "mc_fase_foto_notte" : "mc_fase_foto", lav.n, lav.tot)
      : lav.fase === "cucio" ? t("mc_fase_cucio_pc", lav.n) : t(lav.fase === "luce" ? "mc_fase_luce" : "mc_fase_apro");
    const pc = lav.tot ? Math.round(100 * lav.n / lav.tot) : 0;
    return `<div class="vg-mappa mc-crea ${focus ? "focus" : ""}" data-v="mappa"><div class="vg-griglia"></div>
      <div class="mc-lavoro"><div class="vg-giro"></div><b>${f}</b><div class="mc-barra"><i style="width:${pc}%"></i></div><small>${t("mc_lavoro_sub")}</small></div></div>`;
  }
  if (!d.citta) {
    return `<div class="vg-mappa mc-crea ${focus ? "focus" : ""}" data-v="mappa"><div class="vg-griglia"></div>
      <div class="mc-invito"><span class="mc-ico"><svg><use href="#i-mondo"/></svg></span><h3>${t("mc_crea_tit")}</h3><p>${t("mc_crea_testo")}</p>
        <div class="vg-vai"><kbd class="pad a">A</kbd><span><b>${t("mc_crea")}</b><small>${t("mc_crea_sub")}</small></span></div>
        <p class="mc-oppure">${t("mc_oppure")}</p></div>
      ${d.gioco ? "" : `<div class="vg-velo">${t("vg_no_gioco")}</div>`}</div>`;
  }
  return `<div class="vg-mappa mc-anteprima ${focus ? "focus" : ""}" data-v="mappa"><div class="mc-fondo"></div><div class="mc-segni"></div>
      <div class="vg-info"><small>${t("mc_tit")}</small><span>${t("mc_quando", d.citta.quando || "")}</span></div>
      <div class="vg-vai"><kbd class="pad a">A</kbd><span><b>${t("mc_apri")}</b><small>${t("mc_apri_sub")}</small></span></div>
      ${d.gioco ? "" : `<div class="vg-velo">${t("vg_no_gioco")}</div>`}</div>`;
}
async function mcRiempiAnteprima(box) {  // dopo il disegno: immagine piccola centrata su Spidey, segni dei posti
  const el = box.querySelector(".mc-anteprima"), geo = mcGeo();
  if (!el || !geo) return;
  const lu = mcLuci(geo), url = await mcImmagine(false, lu.sopra && lu.f > 0.5 ? lu.sopra : lu.base);
  if (!url || !el.isConnected) return;
  const fondo = el.querySelector(".mc-fondo"), segni = el.querySelector(".mc-segni");
  const r = (geo.anteprima ? geo.anteprima[0] : 1280) / geo.W, k = 1.25, w = el.clientWidth, h = el.clientHeight;
  const sp = VG.dati.spidey, [cx, cy] = sp ? mcPx(geo, sp[0], sp[1]) : [geo.W / 2, geo.H / 2];
  const ox = w / 2 - cx * r * k, oy = h / 2 - cy * r * k;
  fondo.style.backgroundImage = `url(${url})`;
  if (geo.fondo) fondo.style.backgroundColor = geo.fondo;
  fondo.style.backgroundSize = `${geo.W * r * k}px auto`;
  fondo.style.backgroundPosition = `${ox}px ${oy}px`;
  const punto = (x, z, cls, testo) => { const [px, py] = mcPx(geo, x, z); return `<i class="${cls}" style="left:${ox + px * r * k}px;top:${oy + py * r * k}px">${testo || ""}</i>`; };
  segni.innerHTML = (VG.dati.posti || []).map((p, i) => p.x != null ? punto(p.x, p.z, "mc-posto", VG.dati.posti.length - i) : "").join("")
    + (sp ? punto(sp[0], sp[1], "mc-spidey") : "");
}

// ------------------------------------------------ creazione
async function mcCrea() {
  const r = await api().menu_mappa_crea();
  if (!r || r.errore) { toast(t(r && r.errore === "occupato" ? "mc_err_occupato" : "vg_err_gioco")); return; }
  vgLeggi();
}
function mcAvanza() { vgLeggi(); }  // da Python: avanzamento del giro fotografico
async function mcFine(esito) {  // da Python: giro finito
  if (esito === "ok") { mcDimentica(); toast(t("mc_pronta")); await vgLeggi(); if (M.tab === "ora" && OR.pag === "viaggio") mcApri(); return; }
  toast(t("mc_err_" + esito));
  vgLeggi();
}

// ------------------------------------------------ esploratore
// Uno strato per luce (giorno, alba, tramonto, notte: si vedono quello dell'ora del gioco e, nelle dissolvenze, quello
// dopo sopra con l'opacità giusta: mcLuci). In ognuno la panoramica (immagine intera
// rimpicciolita) e, quando lo zoom supera la sua risoluzione, i quadrati a piena risoluzione che si vedono (chiesti a Python
// uno alla volta, tenuti in memoria). Vista: punto (MC.px, MC.py) al centro, ruotata di MC.rot, zoom MC.s.
async function mcApri() {
  const geo = mcGeo();
  if (!geo) return;
  let el = $("#mc-esplora");
  if (!el) {
    el = document.createElement("div");
    el.id = "mc-esplora";
    $("#menu").appendChild(el);
  }
  const strato = l => `<div class="mc-livello" data-l="${l}"><div class="mc-mare"></div><img class="mc-img" alt=""><div class="mc-tasselli"></div></div>`;
  el.innerHTML = `<div class="mc-testa"><svg><use href="#i-mondo"/></svg><b>${t("mc_tit")}</b><span id="mc-dove"></span></div>
    <div class="mc-vista"><div id="mc-strato">${mcStrati(geo).map(strato).join("")}</div><div id="mc-segni"></div>
      <div class="mc-mirino"><i></i></div><div class="mc-nord"><i id="mc-ago"><b>N</b></i></div>
      <div class="mc-carico" id="mc-carico"><div class="vg-giro"></div><span>${t("mc_carico")}</span></div></div>`;
  el.classList.remove("nascosto");
  el.style.bottom = `${(($("#mn-piede") || {}).offsetHeight || 46) - 6}px`;
  el.querySelector(".mc-vista").style.background = geo.fondo || "";  // fuori dall'immagine: colore dell'acqua
  MC.aperto = true; MC.rifai = false;
  if (MC.geoQuando !== geo.quando) { for (const u of MC.tasselli.values()) URL.revokeObjectURL(u); MC.tasselli.clear(); MC.chiesti.clear(); MC.geoQuando = geo.quando; }
  const sp = VG.dati.spidey;
  [MC.px, MC.py] = sp ? mcPx(geo, sp[0], sp[1]) : [geo.W / 2, geo.H / 2];
  MC.s = 0.3;
  piede();
  const lu = mcLuci(geo);
  await Promise.all([lu.base, lu.sopra].filter(Boolean).map(async l => {
    const url = await mcImmagine(true, l);
    const img = document.querySelector(`#mc-strato .mc-livello[data-l="${l}"] .mc-img`);
    if (!url || !img || !MC.aperto) return;
    await new Promise(ok => { img.onload = ok; img.onerror = ok; img.src = url; });
  }));
  if (!MC.aperto) return;
  $("#mc-carico").classList.add("nascosto");
  mcDisegna();
}
function mcChiudi() {
  MC.aperto = false;
  const el = $("#mc-esplora");
  if (el) el.classList.add("nascosto");
  piede();
}
async function mcTassello(l, tx, ty) {  // un quadrato a piena risoluzione (base64 da Python -> blob)
  const k = `${l}_${tx}_${ty}`;
  if (MC.chiesti.has(k)) return;
  MC.chiesti.add(k);
  const b = await api().menu_mappa_tassello(tx, ty, l);
  if (!b) return;
  const bin = atob(b), u8 = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) u8[i] = bin.charCodeAt(i);
  MC.tasselli.set(k, URL.createObjectURL(new Blob([u8], { type: "image/jpeg" })));
  if (MC.tasselli.size > 120) {  // i più vecchi via (memoria)
    const vecchio = MC.tasselli.keys().next().value;
    URL.revokeObjectURL(MC.tasselli.get(vecchio)); MC.tasselli.delete(vecchio); MC.chiesti.delete(vecchio);
  }
  if (MC.aperto) mcDisegna();
}
// zoom minimo: tutta la mappa (anche girata) dentro la vista. Il mirino arriva in ogni punto della mappa (John: da
// lontano si bloccava e non arrivava agli angoli); oltre il bordo continua il mare (.mc-mare, stesse onde)
function mcSmin(geo, w, h) {
  const c = Math.abs(Math.cos(MC.rot)), s = Math.abs(Math.sin(MC.rot));
  return Math.min(MC_SMAX, 0.92 * Math.min(w / (geo.W * c + geo.H * s), h / (geo.W * s + geo.H * c)));
}
function mcLimita(geo, w, h) {
  MC.s = Math.max(mcSmin(geo, w, h), Math.min(MC_SMAX, MC.s));
  MC.px = Math.max(0, Math.min(geo.W, MC.px));
  MC.py = Math.max(0, Math.min(geo.H, MC.py));
}
// il mare ripetibile dello strato l attorno alla mappa (mappe vecchie: niente). Da vicino la trama (stessa fase dei
// quadrati), da lontano (sotto la mappa c'è la panoramica rimpicciolita, liscia) il suo colore medio
async function mcMare(geo, l, vicino) {
  const liv = document.querySelector(`#mc-strato .mc-livello[data-l="${l}"] .mc-mare`);
  if (!liv || !geo.mare) return;
  const k = `m${l}`;
  if (!liv.dataset.fatto) {
    liv.dataset.fatto = "1";
    if (!MC.img[k]) {
      const r = await api().menu_mappa_mare(l);
      if (!r || !r.b64) return;
      const u8 = Uint8Array.from(atob(r.b64), c => c.charCodeAt(0));
      MC.img[k] = { url: URL.createObjectURL(new Blob([u8], { type: "image/jpeg" })), colore: r.colore };
    }
    const P = geo.mare, fuori = P * Math.ceil(9000 / P);  // multiplo del periodo: stessa fase dei quadrati
    Object.assign(liv.style, { left: `${-fuori}px`, top: `${-fuori}px`, width: `${geo.W + 2 * fuori}px`,
      height: `${geo.H + 2 * fuori}px`, backgroundSize: `${P}px ${P}px`, backgroundColor: MC.img[k].colore });
  }
  const m = MC.img[k];
  if (!m) return;
  const bg = vicino ? `url(${m.url})` : "none";
  if (liv.style.backgroundImage !== bg) liv.style.backgroundImage = bg;
}
function mcSchermo(px, py, w, h) {  // pixel della mappa -> punto della vista
  const c = Math.cos(MC.rot), s = Math.sin(MC.rot), dx = (px - MC.px) * MC.s, dy = (py - MC.py) * MC.s;
  return [w / 2 + c * dx - s * dy, h / 2 + s * dx + c * dy];
}
function mcDisegna() {
  const geo = mcGeo(), vista = document.querySelector("#mc-esplora .mc-vista");
  if (!geo || !vista) return;
  const w = vista.clientWidth, h = vista.clientHeight;
  mcLimita(geo, w, h);
  const s = MC.s, strato = $("#mc-strato");
  strato.style.width = `${geo.W}px`; strato.style.height = `${geo.H}px`;
  strato.style.transform = `translate(${w / 2}px, ${h / 2}px) rotate(${MC.rot}rad) scale(${s}) translate(${-MC.px}px, ${-MC.py}px)`;
  // quali quadrati si vedono: angoli della vista riportati sulla mappa
  const c = Math.cos(MC.rot), sn = Math.sin(MC.rot), xs = [], ys = [];
  for (const [vx, vy] of [[0, 0], [w, 0], [0, h], [w, h]]) {
    const dx = (vx - w / 2) / s, dy = (vy - h / 2) / s;
    xs.push(MC.px + c * dx + sn * dy); ys.push(MC.py - sn * dx + c * dy);
  }
  const T = geo.tassello || 1024, pan = geo.panoramica ? geo.panoramica[0] / geo.W : 1;
  const lu = mcLuci(geo);
  for (const l of mcStrati(geo)) {
    const liv = document.querySelector(`#mc-strato .mc-livello[data-l="${l}"]`);
    if (!liv) continue;
    const serve = l === lu.base || (l === lu.sopra && lu.f > 0.001);
    liv.style.opacity = l === lu.base ? "1" : lu.f.toFixed(3);
    liv.style.zIndex = l === lu.base ? "1" : "2";
    liv.style.display = serve ? "" : "none";
    const img = liv.querySelector(".mc-img");
    img.style.width = `${geo.W}px`;
    if (serve && !img.getAttribute("src")) mcImmagine(true, l).then(u => { if (u) img.src = u; });
    if (serve) mcMare(geo, l, geo.tassello && s > pan * 1.15);
    const box = liv.querySelector(".mc-tasselli");
    if (serve && geo.tassello && s > pan * 1.15) {
      const x0 = Math.max(0, Math.floor(Math.min(...xs) / T)), x1 = Math.min(Math.ceil(geo.W / T) - 1, Math.floor(Math.max(...xs) / T));
      const y0 = Math.max(0, Math.floor(Math.min(...ys) / T)), y1 = Math.min(Math.ceil(geo.H / T) - 1, Math.floor(Math.max(...ys) / T));
      let html = "";
      for (let ty = y0; ty <= y1; ty++) for (let tx = x0; tx <= x1; tx++) {
        const u = MC.tasselli.get(`${l}_${tx}_${ty}`);
        if (u) html += `<img src="${u}" style="left:${tx * T}px;top:${ty * T}px" alt="">`;
        else mcTassello(l, tx, ty);
      }
      if (box.dataset.html !== html) { box.innerHTML = html; box.dataset.html = html; }
    } else if (box.dataset.html) { box.innerHTML = ""; box.dataset.html = ""; }
  }
  const punto = (x, z, cls, testo) => { const [px, py] = mcPx(geo, x, z), [qx, qy] = mcSchermo(px, py, w, h); return `<i class="${cls}" style="left:${qx}px;top:${qy}px">${testo || ""}</i>`; };
  const d = VG.dati || {};
  $("#mc-segni").innerHTML = (d.posti || []).map((p, i) => p.x != null ? punto(p.x, p.z, "mc-posto", d.posti.length - i) : "").join("")
    + (d.spidey ? punto(d.spidey[0], d.spidey[1], "mc-spidey") : "");
  // la freccia del nord: direzione dello schermo dove va il nord del gioco (-x nel mondo, verso Central Park)
  const [ax, ay] = mcPx(geo, 0, 0), [bx, by] = mcPx(geo, -100, 0);
  const [sx0, sy0] = mcSchermo(ax, ay, w, h), [sx1, sy1] = mcSchermo(bx, by, w, h);
  const ago = $("#mc-ago"), an = Math.atan2(sx1 - sx0, sy0 - sy1);
  if (ago) { ago.style.transform = `rotate(${an}rad)`; ago.firstChild.style.transform = `rotate(${-an}rad)`; }
  const [x, z] = mcMondo(geo, MC.px, MC.py);
  $("#mc-dove").textContent = d.spidey ? t("mc_distanza", Math.round(Math.hypot(x - d.spidey[0], z - d.spidey[1]))) : "";
}
function mcMuovi(dx, dy) {  // dx/dy in pixel dello schermo (la vista può essere ruotata)
  const c = Math.cos(MC.rot), s = Math.sin(MC.rot);
  MC.px += (c * dx + s * dy) / MC.s; MC.py += (-s * dx + c * dy) / MC.s;
  mcDisegna();
}
function mcZoom(k) { MC.s *= k; mcDisegna(); }
function mcStick(x, y, sinistro) {  // levette (da Python, analogiche, su = negativo), curva morbida
  if (Math.abs(x) < 0.2 && Math.abs(y) < 0.2) return;
  const v = n => Math.sign(n) * Math.min(1, n * n);
  if (sinistro) {  // sinistra = muovi (le frecce che manda insieme non devono contare due volte)
    MC.stickL = Date.now();
    mcMuovi(v(x) * 30, v(y) * 30);
    return;
  }
  // destra: ←/→ gira la mappa attorno al mirino, ↑/↓ zoom
  if (Math.abs(x) >= 0.2) MC.rot -= v(x) * 0.055;
  if (Math.abs(y) >= 0.2) MC.s *= Math.exp(-v(y) * 0.045);
  mcDisegna();
}
function tastoEsplora(k, rip) {
  const passo = 60 + Math.min(rip, 12) * 18;
  const dir = k === "sx" || k === "dx" || k === "su" || k === "giu";
  if (dir && Date.now() - MC.stickL < 250) return true;  // è la levetta sinistra (già fluida da menuStickL)
  if (k === "sx") mcMuovi(-passo, 0);
  else if (k === "dx") mcMuovi(passo, 0);
  else if (k === "su") mcMuovi(0, -passo);
  else if (k === "giu") mcMuovi(0, passo);
  else if (k === "lt" || k === "rt") mcZoom(k === "rt" ? 1.45 : 1 / 1.45);
  else if (k === "r3" || k === "l3") { MC.rot = 0; mcDisegna(); }
  else if (k === "y") { const sp = VG.dati && VG.dati.spidey; if (sp) { [MC.px, MC.py] = mcPx(mcGeo(), sp[0], sp[1]); mcDisegna(); } }
  else if (k === "b") mcChiudi();
  else if (k === "x") {
    if (!MC.rifai) { MC.rifai = true; toast(t("mc_rifai_sicuro")); piede(); return true; }
    MC.rifai = false; mcChiudi(); mcCrea();
  } else if (k === "a") {
    const [x, z] = mcMondo(mcGeo(), MC.px, MC.py);
    mcChiudi();
    api().menu_viaggio_vai("punto", null, x, z).then(r => { if (!r || r.errore) toast(t("vg_err_" + ((r && r.errore) || "gioco"))); });
  }
  if (k !== "x" && MC.rifai) { MC.rifai = false; piede(); }
  return true;
}
function mcPiede(k) {
  return [[k("stick", "L"), t("mc_muovi")], [k("stick", "R"), t("mc_gira_zoom")], [k("", "LT") + k("", "RT"), t("mc_zoom")], [k("a", "A"), t("mc_vai")],
    [k("y", "Y"), t("mc_spidey")], [k("x", "X"), t(MC.rifai ? "mc_rifai_sicuro" : "mc_rifai")], [k("b", "B"), t("mn_indietro")]];
}

// ------------------------------------------------ mappa 3D (mappa3d.py: la telecamera della mappa del gioco, al posto
// della mappa piatta). A sul riquadro della mappa nella pagina Viaggio: Python apre la mappa del gioco (anche se è chiusa) e
// la telecamera parte dall'alto; il menu diventa una barra in basso (come la camera stile TV), al centro del gioco il mirino,
// sopra i posti salvati i segnalini. A = vai (al posto scelto con Y o dove c'è il mirino), B = esci, X = salva qui.
const M3 = { stato: null, info: {}, ant: undefined };  // stato: null | "apro" | "pronta" | "chiudo"; ant = anteprima
function m3Apri() {
  if (M3.stato) return;
  M3.stato = "apro";
  api().menu_mappa3d().then(r => {
    if (!r || r.errore) { M3.stato = null; toast(t(r && r.errore === "occupato" ? "mc_err_occupato" : "vg_err_gioco")); }
  });
}
function m3Stato(s, esito) {  // da Python
  if (s === "apro") { M3.stato = "apro"; toast(t("m3_apro")); return; }
  if (s === "pronta") { M3.stato = "pronta"; M3.info = {}; document.body.classList.add("barra"); scala(); m3Barra(); return; }
  M3.stato = null;
  document.body.classList.remove("barra");
  scala();
  if (esito === "apri") toast(t("mc_err_apri"));
  else if (esito !== "vai" && esito !== "esci") toast(t("m3_err"));
  M3.ant = undefined;  // c'è una foto nuova
  vgLeggi();
  if (M.tab === "ora" && OR.pag === "viaggio") disegnaViaggio();
  piede();
}
function m3Info(o) { M3.info = o || {}; if (M3.stato === "pronta") m3Barra(); }  // da Python: posto scelto con Y
// da Python ogni secondo mentre la mappa 3D è aperta: la barra dev'esserci e piena (John: alla seconda apertura era vuota;
// se succede la rimetto e lo scrivo nel registro per capire perché)
function m3Tieni() {
  if (M3.stato === "chiudo") return;  // (si sta chiudendo: Python manda ancora un ultimo controllo)
  const vuota = !$("#cam-barra .m3-comandi"), senza = !document.body.classList.contains("barra");
  if (M3.stato !== "pronta" || vuota || senza) {
    api().log_js(`mappa 3D: barra rimessa (stato ${M3.stato}, vuota ${vuota}, senza barra ${senza}, tab ${M.tab})`);
    if (M3.stato !== "chiudo") M3.stato = "pronta";
    document.body.classList.add("barra"); scala(); m3Barra();
  }
}
function m3Barra() {
  const k = (c, x) => `<kbd class="pad ${c}">${x}</kbd>`, inf = M3.info || {};
  const sotto = inf.posto ? (inf.nome ? `${inf.nome} · ${inf.posto}/${inf.tot}` : t("m3_posto_scelto", inf.posto, inf.tot)) : t("m3_tit");
  $("#cam-barra").innerHTML = `<div class="cb-sx"><div class="mc-nord m3-nord"><i id="m3-ago"><b>N</b></i></div><div><small>${t("mc_tit")}</small><b class="${inf.posto ? "m3-scelto" : ""}">${sotto}</b></div></div>
    <div class="m3-comandi"><span>${k("stick", "L")}${t("mc_muovi")}</span><span>${k("stick", "R")}${t("mc_gira_zoom")}</span>
      <span>${k("", "LT")}${k("", "RT")}${t("m3_inclina")}</span><span>${k("stick", "R3")}${t("m3_alto")}</span>
      <span>${k("y", "Y")}${t("m3_posti")}</span><span>${k("x", "X")}${t("m3_salva")}</span></div>
    <div class="m3-dx"><span>${k("a", "A")}${t(inf.posto ? "m3_vai_posto" : "mc_vai")}</span><span>${k("b", "B")}${t("m3_esci")}</span></div>`;
  m3Bussola(M3.ago || 0);
}
// da Python mentre giri la visuale: angolo (radianti, in senso orario dall'alto dello schermo) dove sta il nord del gioco
function m3Bussola(an) {
  M3.ago = an;
  const ago = $("#m3-ago");
  if (ago) { ago.style.transform = `rotate(${an}rad)`; ago.firstChild.style.transform = `rotate(${-an}rad)`; }
}
function tastoM3(k) {
  if (M3.stato === "apro" && k === "b") { api().menu_mappa3d_fine(false); return true; }  // ci ripensi mentre si apre
  if (M3.stato !== "pronta") return true;
  if (k === "a" || k === "b") { M3.stato = "chiudo"; api().menu_mappa3d_fine(k === "a"); }
  else if (k === "l3" || k === "r3") api().menu_mappa3d_comando("alto");  // di nuovo dall'alto
  else if (k === "y") api().menu_mappa3d_comando("posto");  // posto salvato dopo (la croce no: la manda anche la levetta)
  else if (k === "x") api().menu_mappa3d_comando("salva");
  return true;
}
// riquadro della mappa nella pagina Viaggio: anteprima (foto dall'alto dell'ultima apertura, "tu" al centro) e A = apri
function m3Riquadro(d, focus) {
  if (M3.ant === undefined) {
    M3.ant = null;
    api().menu_mappa3d_anteprima().then(r => { M3.ant = r || false; if (M.tab === "ora" && OR.pag === "viaggio") disegnaViaggio(); });
  }
  const a = M3.ant;
  // "tu" dove sei ADESSO nella foto (u, v 0..1; la foto riempie il riquadro: object-fit cover, posizionato con m3Tu)
  const dentro = a && a.tu && a.tu[0] > 0.04 && a.tu[0] < 0.96 && a.tu[1] > 0.04 && a.tu[1] < 0.96;
  return `<div class="vg-mappa m3-riq ${focus ? "focus" : ""} ${a ? "con-foto" : "pronta"}" data-v="mappa">
    ${a ? `<img class="m3-ant" src="data:image/jpeg;base64,${a.img}" alt="" onload="m3Tu(this)">${dentro ? `<i class="m3-tu nascosto"></i>` : a.tu ? `<i class="m3-tu m3-freccia nascosto"><b></b><em>${t("m3_tu")}</em></i>` : ""}` : `<div class="vg-griglia"></div><div class="vg-radar"></div>`}
    <div class="vg-info"><small>${t("m3_tit")}</small><b>${t("mc_tit")}</b><span>${a ? t(a.tu && !dentro ? "m3_ant_fuori" : "m3_ant_sub") : t("m3_prima")}</span></div>
    <div class="vg-vai"><kbd class="pad a">A</kbd><span><b>${t("m3_apri")}</b><small>${t("m3_apri_sub")}</small></span></div>
    ${d.gioco ? "" : `<div class="vg-velo">${t("vg_no_gioco")}</div>`}
  </div>`;
}
// la foto è tagliata per riempire il riquadro: la sposto (object-position) perché "tu" stia il più possibile al centro e
// metto il pallino sul punto giusto
function m3Tu(img) {
  const a = M3.ant, tu = img.parentNode && img.parentNode.querySelector(".m3-tu");
  if (!a || !a.tu || !tu) return;
  const W = img.clientWidth, H = img.clientHeight, iw = img.naturalWidth, ih = img.naturalHeight;
  if (!W || !H || !iw || !ih) return;
  const k = Math.max(W / iw, H / ih), sw = iw * k, sh = ih * k;
  if (tu.classList.contains("m3-freccia")) {  // fuori dalla foto: freccia sul bordo verso dove sei (John)
    const ox = (W - sw) / 2, oy = (H - sh) / 2, px = ox + a.tu[0] * sw - W / 2, py = oy + a.tu[1] * sh - H / 2;
    const m = 26, k2 = Math.min((W / 2 - m) / Math.max(1e-6, Math.abs(px)), (H / 2 - m) / Math.max(1e-6, Math.abs(py)));
    img.style.objectPosition = "50% 50%";
    tu.style.left = (W / 2 + px * k2) + "px";
    tu.style.top = (H / 2 + py * k2) + "px";
    tu.querySelector("b").style.transform = `rotate(${Math.atan2(py, px)}rad)`;
    tu.classList.remove("nascosto");
    return;
  }
  const ox = Math.min(0, Math.max(W - sw, W / 2 - a.tu[0] * sw)), oy = Math.min(0, Math.max(H - sh, H / 2 - a.tu[1] * sh));
  img.style.objectPosition = `${ox}px ${oy}px`;
  tu.style.left = (ox + a.tu[0] * sw) + "px";
  tu.style.top = (oy + a.tu[1] * sh) + "px";
  tu.classList.remove("nascosto");
}
