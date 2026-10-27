"use strict";
// ================================================================ testi IT / EN
// i testi sono in lingue.js (TESTI)
let L = "it";
const LINGUE = ["it", "en", "de", "fr", "es"];
const t = (k, ...a) => (TESTI[L][k] ?? TESTI.en[k] ?? k).replace(/\{(\d)\}/g, (_, i) => a[i]);
const tr = o => o ? (o[L] ?? o.en ?? o.it ?? "") : "";  // testo multilingua di un oggetto (codici, preset)
const $ = s => document.querySelector(s), $$ = s => [...document.querySelectorAll(s)];
const api = () => window.pywebview.api;

// ================================================================ stato
const S = {
  dati: null, inst: { primaria: null, alternativa: null, ragnatele: null, ragnatele_alt: null },
  scelta: { primaria: null, alternativa: null, ragnatele: null, ragnatele_alt: null },
  slot: "primaria", filtro: "tutte", cerca: "", pagina: "skin",
  mini: {}, tex: {}, rag_img: {}, filo: {}, pers: false,
};
let viewer, fotoViewer;

// ================================================================ utilità catalogo
const voce = id => S.dati.skin.find(v => v.id === id);
function catena(nodo, path, acc = []) {  // nodi dalla radice al nodo che ha quel percorso
  const qui = [...acc, nodo];
  if (nodo.path === path) return qui;
  for (const f of nodo.figli) { const r = catena(f, path, qui); if (r) return r; }
  return null;
}
function fogliaDefault(n) {
  if (n.path && !n.figli.some(f => f.default)) return n.path;
  const s = n.figli.find(f => f.default) || n.figli[0];
  return s ? fogliaDefault(s) : n.path;
}
function nomeVariante(v, path) {
  if (!v || v.varianti < 2) return "";
  const c = catena(v.albero, path) || [];
  return c.slice(1).map(n => n.nome + (n.default ? " ★" : "")).join(" · ") || t("base");
}
const attuale = slot => S.scelta[slot] ?? S.inst[slot];
const SLOT_SKIN = ["primaria", "alternativa", "ragnatele", "ragnatele_alt"];
const isRag = slot => slot === "ragnatele" || slot === "ragnatele_alt";
// bollino "Solo con l'app": le cose che fanno i fili in sottofondo di spidey_app (menu LB + RB, ragnatele dell'alternativo,
// camera dal vivo, linee del disegno del controller...). Avviando il gioco da Dolphin senza l'app non ci sono.
const soloApp = (mini = false) => `<span class="solo-app ${mini ? "mini" : ""}" data-tip="solo_app_tip"><svg><use href="#i-stella-piena"/></svg>${mini ? "" : `<span>${t("solo_app")}</span>`}</span>`;  // ragnatele del costume principale / alternativo
function apriPatreon() {  // Patreon = solo sostegno volontario (l'app è tutta gratis, niente funzioni bloccate)
  if (S.dati && S.dati.patreon) api().apri_link(S.dati.patreon);
}
function nomeCorto(slot) {
  const a = attuale(slot);
  if (slot === "ragnatele_alt" && (!a || a === "uguali")) return t("rag_uguali");
  if (isRag(slot)) { const r = S.dati.ragnatele.find(x => x.id === a); return r ? (r.id === "vanilla" ? t("rag_vanilla") : r.nome) : "—"; }
  if (!a) return t("nessuna");
  const v = voce(a.id);
  return v ? v.nome : t("sconosciuta");
}

// ================================================================ testi e lingua
function applicaTesti() {
  document.documentElement.lang = L;
  $$("[data-t]").forEach(e => e.textContent = t(e.dataset.t));
  $$(".lingue [data-l]").forEach(b => b.classList.toggle("attivo", b.dataset.l === L));
  $("#lingua-ora").textContent = L.toUpperCase();
  $("#cerca").placeholder = t(isRag(S.slot) ? "cerca_rag" : "cerca_skin");
  $("#cod-cerca").placeholder = t("cerca_codice");
  $("#h-cerca").placeholder = t("cerca_hud");
  // ogni pagina per conto suo: se una va in errore (es. un pezzo che c'è solo con la pagina aperta) le altre si ridisegnano lo stesso
  const prova = f => { try { f(); } catch (e) { api().log_js("applicaTesti: " + (e && e.stack || e)); } };
  if (H.dati) prova(disegnaHud);
  prova(aggiornaTesta); prova(aggiornaPillole);
  if (C.dati) prova(disegnaCodici);
  if (K.info) prova(() => { costruisciCam(); if (S.pagina === "cam") piedeCam(); });
  if (G.dati) prova(disegnaGrafica);
  if (T.dati) prova(disegnaTexture);
  if (I.dati) prova(disegnaInstaller);
  if (E.info) prova(disegnaEsporta);
  if (typeof Q !== "undefined" && Q.dati) disegnaGioca();
  if (S.dati) { disegnaSlot(); disegnaChip(); disegnaGriglia(); aggiornaPalco(); disegnaModifiche(); if (S.pers) disegnaPers(); }
}
function aggiornaTesta() {
  const p = S.pagina;
  const guida = p === "gioca" && Q.dati && (Q.guida || !giPronto(Q.dati));
  const tit = { gioca: guida ? ["titolo_guida", "sub_guida"] : ["titolo_gioca", "sub_gioca"], skin: ["titolo_skin", "sub_skin"], impostazioni: ["titolo_imp", "sub_imp"], codici: ["titolo_codici", "sub_codici"], hud: ["titolo_hud", "sub_hud"], cam: ["titolo_cam", "sub_cam"], grafica: ["titolo_grafica", "sub_grafica"], texture: ["titolo_texture", "sub_texture"], installa: ["titolo_installa", "sub_installa"], esporta: ["titolo_esporta", "sub_esporta"], controller: ["titolo_controller", "sub_controller"] }[p];
  $("#titolo").textContent = tit ? t(tit[0]) : t("nav_" + p);
  $("#sottotitolo").textContent = tit ? t(tit[1]) : t("presto_testo");
  $("#piede").classList.toggle("nascosto", !["skin", "codici", "hud", "cam", "grafica", "texture"].includes(p));
  disegnaModifiche();
}
function aggiornaNav() {  // voci del menu ancora vuote (senza mod / senza codici): spente, ma cliccabili (spiegano cosa serve)
  const senzaMod = !!(S.dati && !S.dati.pack), senzaCodici = !!(Q.dati && Q.dati.mod && !ID_ORDINE.some(g => Q.dati.mod[g] && Q.dati.mod[g].codici > 0));
  for (const [p, vuota] of [["skin", senzaMod], ["hud", senzaMod], ["texture", senzaMod], ["codici", senzaCodici], ["installa", senzaCodici && senzaMod]]) {
    const b = $(`.voce-nav[data-pagina="${p}"]`);
    if (b) { b.classList.toggle("vuota", vuota); b.title = vuota ? t(p === "codici" ? "nav_vuota_codici" : p === "installa" ? "nav_vuota_installa" : "nav_vuota_mod") : ""; }
  }
}
function aggiornaPillole() {
  const d = S.dati, pd = $("#p-dolphin");
  aggiornaNav();
  if (!d) return;
  pd.classList.toggle("errore", !d.dolphin);
  pd.querySelector("span").textContent = d.dolphin ? t("dolphin_ok", d.cartelle.join(" · ") || "OK") : t("dolphin_no");
  pd.title = d.dolphin || "";
  $("#p-aperto").classList.toggle("nascosto", !d.dolphin_aperto);
}

// ================================================================ slot, chip, griglia
function disegnaSlot() {
  $$("#pg-skin .slot button").forEach(b => {
    const s = b.dataset.slot;
    b.classList.toggle("attivo", s === S.slot);
    b.classList.toggle("cambiato", S.scelta[s] !== null);
    b.querySelector(".ora").textContent = nomeCorto(s);
    if (s === "alternativa") {  // codice "Cambio costume" spento: in gioco l'alternativo non si può usare
      let w = b.querySelector(".slot-avviso");
      const spento = (S.dati.alt_spento || []);
      if (!spento.length) { if (w) w.remove(); }
      else {
        if (!w) { w = document.createElement("span"); w.className = "slot-avviso"; b.appendChild(w); }
        w.textContent = "⚠ " + t("alt_spento", spento.join(", "));
        w.onclick = e => { e.stopPropagation(); vaiA("codici"); };
      }
    }
  });
}
const nomeGruppo = g => g === "Collezione" ? "Spider-Man 2: RE" : g === "Aggiunte" ? t("gruppo_aggiunte") : g;  // gruppo interno -> nome mostrato
function gruppoChip(v) { return v.gruppo; }
let ORDINE = "az";  // A-Z o per autore; i preferiti stanno sempre in testa
try { ORDINE = localStorage.getItem("ordine_skin2") || "az"; } catch (e) {}
function disegnaChip() {
  const riga = $("#chip");
  riga.innerHTML = "";
  if (isRag(S.slot)) return;
  const conta = { tutte: S.dati.skin.length };
  S.dati.skin.forEach(v => conta[gruppoChip(v)] = (conta[gruppoChip(v)] || 0) + 1);
  const gruppi = [...new Set(S.dati.skin.map(v => v.gruppo))];
  conta.preferiti = (S.dati.preferite || []).filter(id => S.dati.skin.some(v => v.id === id)).length;
  if (S.filtro === "preferiti" && !conta.preferiti) S.filtro = "tutte";
  for (const [k, nome] of [["tutte", t("tutte")], ["preferiti", "★ " + t("mn_preferiti")], ...gruppi.map(g => [g, nomeGruppo(g)])]) {
    if (!conta[k]) continue;
    const b = document.createElement("button");
    b.className = "chip" + (S.filtro === k ? " attivo" : "");
    b.innerHTML = `${nome}<b>${conta[k]}</b>`;
    b.onclick = () => { S.filtro = k; disegnaChip(); disegnaGriglia(); };
    riga.appendChild(b);
  }
  const ord = document.createElement("div");
  ord.className = "ordine";
  for (const [k, nome] of [["az", t("a_z")], ["autore", t("per_autore")]]) {
    const b = document.createElement("button");
    b.className = ORDINE === k ? "attivo" : "";
    b.textContent = nome;
    b.onclick = () => { ORDINE = k; try { localStorage.setItem("ordine_skin2", k); } catch (e) {} disegnaChip(); disegnaGriglia(); };
    ord.appendChild(b);
  }
  riga.appendChild(ord);
  const pc = document.createElement("div");
  pc.className = "pose piccola";
  pc.innerHTML = `<button data-posa="idle" data-tip="posa_idle"><svg><use href="#i-conserte"/></svg></button><button data-posa="azione" data-tip="posa_azione"><svg><use href="#i-azione"/></svg></button>`;
  pc.title = t("imp_posa");
  pc.querySelectorAll("button").forEach(b => { b.classList.toggle("attivo", b.dataset.posa === POSA_CAT); b.onclick = () => cambiaPosaCatalogo(b.dataset.posa); });
  riga.appendChild(pc);
}
function corrisponde(testo) {
  const q = S.cerca.trim().toLowerCase();
  return !q || q.split(/\s+/).every(p => testo.toLowerCase().includes(p));
}
function disegnaGriglia() {
  const g = $("#griglia");
  g.innerHTML = "";
  let n = 0;
  if (isRag(S.slot)) {
    const alt = S.slot === "ragnatele_alt", priVan = attuale("ragnatele") === "vanilla";
    if (alt) {  // ragnatele che cambiano insieme al costume: si spiega come funziona (e quando non si può)
      g.insertAdjacentHTML("beforeend", `<div class="rag-alt-nota ${priVan ? "giallo" : ""}"><svg style="width:18px;height:18px;flex:none"><use href="#ragno"/></svg><span>${priVan ? "" : soloApp()}${t(priVan ? "rag_alt_vanilla" : "rag_alt_nota")}</span></div>`);
      n++;
      g.appendChild(cartaRagnatela({ id: "uguali" }, t("rag_uguali")));
    }
    for (const r of S.dati.ragnatele) {
      if (alt && r.id === "vanilla") continue;  // le originali non si possono rimettere a gioco aperto
      const nome = r.id === "vanilla" ? t("rag_vanilla") : r.nome;
      if (!corrisponde(nome)) continue;
      n++;
      g.appendChild(cartaRagnatela(r, nome, alt && priVan));
    }
  } else {
    let ultimo = null;
    const pref = S.dati.preferite || [], inPref = v => pref.includes(v.id);
    let elenco = ORDINE === "az" ? [...S.dati.skin].sort((a, b) => a.nome.localeCompare(b.nome, undefined, { numeric: true })) : S.dati.skin;
    const inTesta = S.filtro !== "preferiti";  // i preferiti sempre per primi (col loro titoletto)
    if (inTesta) elenco = [...elenco.filter(inPref), ...elenco.filter(v => !inPref(v))];
    const visibili = elenco.filter(v => (S.filtro === "preferiti" ? inPref(v) : S.filtro === "tutte" || gruppoChip(v) === S.filtro)
      && corrisponde(v.nome + " " + nomeGruppo(v.gruppo)));
    const conPref = inTesta && visibili.some(inPref) && visibili.some(v => !inPref(v));
    for (const v of visibili) {
      if (conPref && inPref(v) && ultimo !== "★") {
        ultimo = "★";
        const h = document.createElement("div");
        h.className = "gruppo-titolo";
        h.innerHTML = `★ ${t("mn_preferiti")}`;
        g.appendChild(h);
      } else if (conPref && ORDINE === "az" && !inPref(v) && ultimo === "★") {
        ultimo = "az";
        const h = document.createElement("div");
        h.className = "gruppo-titolo";
        h.textContent = t("tutte");
        g.appendChild(h);
      }
      if (ORDINE === "autore" && !(conPref && inPref(v)) && v.gruppo !== ultimo) {
        ultimo = v.gruppo;
        const h = document.createElement("div");
        h.className = "gruppo-titolo";
        h.innerHTML = `${nomeGruppo(v.gruppo)}<span>· ${v.crediti || ""}</span>`;
        const stessi = S.dati.skin.filter(x => x.gruppo === v.gruppo);
        if (v.link && stessi.every(x => x.link === v.link)) { h.title = v.link; h.classList.add("cliccabile"); h.onclick = () => api().apri_link(v.link); }
        if (!stessi.every(x => x.crediti === v.crediti)) h.querySelector("span").textContent = "";
        g.appendChild(h);
      }
      n++;
      g.appendChild(cartaSkin(v));
    }
  }
  $("#vuoto").classList.toggle("nascosto", n > 0);
}
function cartaSkin(v) {
  const c = document.createElement("div");
  c.tabIndex = 0;
  const inst = S.inst[S.slot], sc = S.scelta[S.slot], cur = attuale(S.slot);
  c.className = "carta";
  if (cur && cur.id === v.id) c.classList.add("selezionata");
  if (inst && inst.id === v.id) c.classList.add("installata");
  const badge = [];
  if (inst && inst.id === v.id) badge.push(`<span class="in-uso">● ${t("in_uso")}</span>`);
  if (sc && sc.id === v.id) badge.push(`<span class="scelta">● ${t("scelta")}</span>`);
  const mini = S.mini[kMini(v)];
  // varianti: pulsante a parte (in basso sulla foto, non si mescola ai badge): sceglie la skin e apre subito le varianti
  const varBtn = v.varianti > 1 ? `<button class="var-btn" data-tip="var_scegli"><svg><use href="#i-pers"/></svg>${t("varianti", v.varianti)}</button>` : "";
  c.innerHTML = `<div class="badge">${badge.join("")}</div>
    <div class="foto">${mini ? `<img class="pronta" src="${mini}">` : `<div class="attesa"></div>`}${varBtn}</div>
    <div class="testo"><b title="${v.nome}">${v.nome}</b><small>${nomeGruppo(v.gruppo)}</small></div>
    <button class="pref ${(S.dati.preferite || []).includes(v.id) ? "on" : ""}" data-tip="pref_tip"><svg><use href="#${(S.dati.preferite || []).includes(v.id) ? "i-stella-piena" : "i-stella"}"/></svg></button>`;
  c.dataset.k = v.k;
  c.querySelector(".pref").onclick = async e => {  // stellina = preferito (anche nel menu in gioco: vanno in testa)
    e.stopPropagation();
    const si = !(S.dati.preferite || []).includes(v.id);
    const r = await api().skin_preferita(v.id, si);
    if (r && !r.errore) { S.dati.preferite = r; disegnaChip(); disegnaGriglia(); }
  };
  c.onclick = () => scegliSkin(v);
  c.ondblclick = () => { if (v.varianti > 1) apriPers(); };
  const vb = c.querySelector(".var-btn");
  if (vb) vb.onclick = e => { e.stopPropagation(); scegliSkin(v); apriPers(); };
  return c;
}
function cartaRagnatela(r, nome, bloccata = false) {
  const c = document.createElement("div");
  c.tabIndex = 0;
  const slot = S.slot, inst = S.inst[slot] || (slot === "ragnatele_alt" ? "uguali" : null), cur = attuale(slot) || inst;
  c.className = "carta" + (cur === r.id ? " selezionata" : "") + (inst === r.id ? " installata" : "") + (bloccata ? " bloccata" : "") + (r.id === "uguali" ? " uguali" : "");
  const badge = [];
  if (inst === r.id) badge.push(`<span class="in-uso">● ${t("in_uso")}</span>`);
  if (S.scelta[slot] === r.id) badge.push(`<span class="scelta">● ${t("scelta")}</span>`);
  const img = S.rag_img[r.id];
  const pri = S.dati.ragnatele.find(x => x.id === attuale("ragnatele"));
  c.innerHTML = `<div class="badge">${badge.join("")}</div>
    <div class="foto largo">${r.id === "uguali" ? `<svg><use href="#ragno"/></svg>=` : r.id === "vanilla" ? `<svg style="width:60px;height:60px;color:#2a3147"><use href="#ragno"/></svg>` :
      img ? `<img class="pronta" src="${img}">` : `<div class="attesa"></div>`}</div>
    <div class="testo"><b>${nome}</b><small>${r.id === "uguali" ? t("rag_uguali_sub", pri ? (pri.id === "vanilla" ? t("rag_vanilla") : pri.nome) : "—") : r.id === "vanilla" ? t("rag_vanilla_sub") : t("rag_file", r.file)}</small></div>`;
  c.onclick = () => { if (bloccata) { toast(t("slot_ragnatele_alt"), t("rag_alt_vanilla"), "avviso", 6000); return; } scegliRagnatela(r.id); };
  if (r.id === "uguali") return c;
  if (r.id !== "vanilla" && !img) api().ragnatela_img(r.id).then(d => { if (d && !d.errore) { S.rag_img[r.id] = d; disegnaGriglia(); if (attuale("ragnatele") === r.id) aggiornaPalco(); } });
  return c;
}

// ================================================================ scelte
function scegliSkin(v) {
  const inst = S.inst[S.slot], sc = S.scelta[S.slot];
  if (sc && sc.id === v.id) return;
  if (inst && inst.id === v.id) S.scelta[S.slot] = null;          // torna a quella installata
  else S.scelta[S.slot] = { id: v.id, path: v.default };
  dopoScelta();
}
function scegliRagnatela(id) {
  const inst = S.inst[S.slot] || (S.slot === "ragnatele_alt" ? "uguali" : null);
  S.scelta[S.slot] = id === inst ? null : id;
  dopoScelta();
}
function scegliVariante(path) {
  const a = attuale(S.slot);
  const inst = S.inst[S.slot];
  S.scelta[S.slot] = inst && inst.id === a.id && inst.path === path ? null : { id: a.id, path };
  dopoScelta();
}
function dopoScelta() { disegnaSlot(); disegnaGriglia(); aggiornaPalco(); disegnaModifiche(); if (S.pers) disegnaPers(); }

// ================================================================ palco
let richiestaPalco = 0, ultimaPalco = null;
async function aggiornaPalco() {
  const is2d = isRag(S.slot);  // ragnatele: il filo che penzola in 3D, gli altri effetti in 2D nell'angolo
  $("#b-pers").classList.toggle("nascosto", true);
  $("#img2d").classList.toggle("nascosto", !is2d);
  $("#img2d").classList.toggle("striscia", is2d);
  $("#palco").classList.toggle("appeso", is2d);
  for (const x of ["#pose", "#b-fronte", "#b-retro"]) $(x).classList.toggle("nascosto", is2d);  // per il filo non servono
  viewer.appeso = is2d;
  const et = $("#et-stato");
  const cambiato = S.scelta[S.slot] !== null;
  et.textContent = cambiato ? t("da_applicare") : t("installata");
  et.className = "etichetta " + (cambiato ? "giallo" : "verde");
  const mia = ++richiestaPalco;
  if (is2d) {
    let qui = attuale(S.slot);
    if (S.slot === "ragnatele_alt" && (!qui || qui === "uguali")) qui = attuale("ragnatele");  // uguali: si vedono le principali
    const r = S.dati.ragnatele.find(x => x.id === qui);
    $("#et-gruppo").textContent = t(S.slot === "ragnatele_alt" ? "slot_ragnatele_alt" : "slot_ragnatele");
    $("#nome-palco").textContent = r ? (r.id === "vanilla" ? t("rag_vanilla") : r.nome) : "—";
    $("#nome-palco").classList.toggle("lungo", $("#nome-palco").textContent.length > 16);
    $("#variante-palco").textContent = r ? (r.id === "vanilla" ? t("rag_vanilla_sub") : t("rag_file", r.file)) : "";
    $("#crediti-palco").innerHTML = "";
    const img = $("#img2d");
    const id = r ? r.id : "vanilla";
    if (!(id in S.filo)) { const d = id === "vanilla" ? null : await api().ragnatela_filo(id); S.filo[id] = d && !d.errore ? d : null; }
    if (mia !== richiestaPalco) return;
    await viewer.filo(S.filo[id]);
    if (!r || r.id === "vanilla") { img.classList.add("nascosto"); return; }
    if (!S.rag_img[r.id]) { const d = await api().ragnatela_img(r.id); if (d && !d.errore) S.rag_img[r.id] = d; }
    if (mia === richiestaPalco) img.src = S.rag_img[r.id] || "";
    return;
  }
  const a = attuale(S.slot), v = a && voce(a.id);
  $("#et-gruppo").textContent = v ? nomeGruppo(v.gruppo) : "";
  $("#nome-palco").textContent = v ? v.nome : (a ? t("sconosciuta") : t("nessuna"));
  $("#nome-palco").classList.toggle("lungo", $("#nome-palco").textContent.length > 16);
  $("#variante-palco").textContent = v ? nomeVariante(v, a.path) : (a ? t("sconosciuta_sub") : "");
  $("#crediti-palco").innerHTML = v ? `${t("crediti", v.crediti)} <a class="link" data-link="${v.link}">${t("pagina_moddb")}</a>` : "";
  $("#b-pers").classList.toggle("nascosto", !(v && v.varianti > 1));
  if (!a || !a.path) { const o = S.dati && !S.dati.pack ? await texOriginale() : null; if (mia === richiestaPalco) viewer.texture(o); return; }  // senza la mod: costume originale
  if (!S.tex[a.path]) {
    const tm = setTimeout(() => $("#caricamento").classList.remove("nascosto"), 120);
    const d = await api().texture(a.path, 1024, 512);
    clearTimeout(tm);
    $("#caricamento").classList.add("nascosto");
    if (d && !d.errore) S.tex[a.path] = d;
  }
  if (mia === richiestaPalco) {
    await viewer.texture(S.tex[a.path]);
    if (a.path !== ultimaPalco) { ultimaPalco = a.path; viewer.ang = 0; viewer.alt = 0.08; }
  }
}

// ================================================================ personalizza
function apriPers() { S.pers = true; $("#pers").classList.remove("nascosto"); disegnaPers(); }
function chiudiPers() { S.pers = false; $("#pers").classList.add("nascosto"); }
function disegnaPers() {
  const a = attuale(S.slot), v = a && voce(a.id);
  if (!v || v.varianti < 2) { chiudiPers(); return; }
  $("#pers-titolo").textContent = v.nome;
  const box = $("#pers-livelli");
  box.innerHTML = "";
  const c = catena(v.albero, a.path) || [v.albero];
  for (let i = 0; i < c.length; i++) {
    const nodo = c[i];
    if (!nodo.figli.length) break;
    const opz = [];
    if (nodo.path) opz.push({ nome: t("base"), path: nodo.path, attivo: c.length === i + 1, def: !nodo.figli.some(f => f.default) });
    nodo.figli.forEach(f => opz.push({ nome: f.nome, path: fogliaDefault(f), attivo: c[i + 1] === f, def: f.default }));
    const liv = document.createElement("div");
    liv.className = "livello";
    liv.innerHTML = `<h4>${t("opzione")} ${i + 1}</h4><div class="opzioni"></div>`;
    for (const o of opz) {
      const b = document.createElement("button");
      b.className = "opz" + (o.attivo ? " attivo" : "");
      b.innerHTML = `${o.nome}${o.def ? '<span class="stella">★</span>' : ""}`;
      b.onclick = () => scegliVariante(o.path);
      liv.querySelector(".opzioni").appendChild(b);
    }
    box.appendChild(liv);
  }
}

// ================================================================ modifiche e applica
function disegnaModifiche() {
  if (S.pagina === "codici") { piedeCodici(); return; }
  if (S.pagina === "hud") { piedeHud(); return; }
  if (S.pagina === "cam") { piedeCam(); return; }
  if (S.pagina === "grafica") { piedeGrafica(); return; }
  if (S.pagina === "texture") { piedeTexture(); return; }
  if (!S.dati) return;
  const box = $("#modifiche");
  box.innerHTML = "";
  const slots = SLOT_SKIN.filter(s => S.scelta[s] !== null);
  if (!slots.length) {
    box.innerHTML = `<div class="tutto-ok"><svg><use href="#i-ok"/></svg>${t("tutto_ok")}</div>`;
    $("#piede").classList.add("nascondi-azioni");
    return;
  }
  $("#piede").classList.remove("nascondi-azioni");
  for (const s of slots) {
    const m = document.createElement("div");
    m.className = "mod";
    m.innerHTML = `${t("mod_" + s)}: <b>${nomeCorto(s)}</b><button title="${t("annulla")}">×</button>`;
    m.querySelector("button").onclick = () => { S.scelta[s] = null; dopoScelta(); };
    box.appendChild(m);
  }
}
function applicando() { return document.body.classList.contains("applicando") || ($("#applica") && $("#applica").disabled); }
async function conBarra(testo, lavoro) {  // mentre applica: rotella sul pulsante + barra con i file nel piede
  const b = $("#applica"), box = $("#modifiche");
  b.disabled = true; b.classList.add("in-corso");
  $("#annulla").disabled = true;
  box.innerHTML = `<div class="applico"><b>${testo}</b><small></small><div class="barra"><i></i></div></div>`;
  document.body.classList.add("applicando");  // niente clic sulla pagina a metà lavoro
  const fase = (scritta, quota) => {  // aggiorna la barra (quota 0..1, null = lascia)
    const a = box.querySelector(".applico");
    if (!a) return;  // la pagina si è già ridisegnata
    if (scritta) a.querySelector("b").textContent = scritta;
    if (quota != null) a.querySelector(".barra i").style.width = Math.round(quota * 100) + "%";
  };
  const tm = setInterval(async () => {
    const st = await api().avanzamento();
    if (!st || st.errore || !st.totale || !box.querySelector(".applico")) return;
    box.querySelector(".applico small").textContent = `${Math.min(st.fatti, st.totale)} / ${st.totale}`;
    fase(null, st.fatti / st.totale * 0.9);  // l'ultimo pezzo è per il controllo finale
  }, 250);
  try { return await lavoro(fase); }
  finally { clearInterval(tm); b.disabled = false; b.classList.remove("in-corso"); $("#annulla").disabled = false; document.body.classList.remove("applicando"); }
}
async function applica() {
  if (applicando()) return;
  const sc = { ...S.scelta };  // copia: se intanto scegli un'altra skin, quella resta da applicare (non segnata come messa)
  if (!sc.primaria && !sc.alternativa && !sc.ragnatele && !sc.ragnatele_alt) return;
  const r = await conBarra(t("applico_skin"), () => api().applica({ primaria: sc.primaria && sc.primaria.path, alternativa: sc.alternativa && sc.alternativa.path, ragnatele: sc.ragnatele, ragnatele_alt: sc.ragnatele_alt }));
  if (!r || r.errore) { dopoScelta(); toast(t("errore"), errTesto(r && r.errore), "errore"); return; }
  for (const s of SLOT_SKIN) if (sc[s] !== null) { S.inst[s] = sc[s]; if (S.scelta[s] === sc[s]) S.scelta[s] = null; }
  if (sc.ragnatele === "vanilla") S.inst.ragnatele_alt = "uguali";  // con le originali non si alterna
  dopoScelta();
  if (r.copiati + r.cancellati === 0 && sc.ragnatele_alt) { toast(t("fatto"), t(sc.ragnatele_alt === "uguali" ? "rag_alt_tolte" : "rag_alt_ok"), "", 6000); return; }
  const testo = r.copiati + r.cancellati ? t("fatto_testo", r.copiati, r.cancellati, r.cartelle.join(", ")) : t("niente_da_fare");
  toast(t("fatto"), testo + (r.dolphin_aperto ? " " + t("riavvia") : ""), r.dolphin_aperto ? "avviso" : "", r.dolphin_aperto ? 7000 : 4500);
}

// ================================================================ miniature (render 3D offscreen, salvate in cache)
let codaMini = [], lavoraMini = false;
let POSA_CAT = "idle";
try { POSA_CAT = localStorage.getItem("posa_catalogo") || "idle"; } catch (e) {}
// _3 = foto nelle proporzioni della carta (22:26): con 220x300 la carta tagliava sopra e sotto, e il piede avanti spariva
const kMini = v => POSA_CAT === "idle" ? v.k + "_idle3" : v.k + "_b3";
function segnaPosaCatalogo() { $$("#pose-catalogo button, .pose.piccola button").forEach(b => b.classList.toggle("attivo", b.dataset.posa === POSA_CAT)); }
function cambiaPosaCatalogo(p) {
  if (POSA_CAT === p) return;
  POSA_CAT = p;
  try { localStorage.setItem("posa_catalogo", p); } catch (e) {}
  segnaPosaCatalogo(); codaMini = []; disegnaGriglia(); miniature();
}
async function miniature(forza = false) {
  if (POSA_CAT === "idle") fotoViewer.usaModello("idle", (await modelliSpidey()).idle);
  else fotoViewer.usaModello("base");
  fotoViewer.dist = POSA_CAT === "idle" ? 2.65 : 3.1;  // a braccia conserte è più stretto: un po' più vicino
  fotoViewer.ang = POSA_CAT === "idle" ? 0.25 : 0.42;
  const chiavi = S.dati.skin.map(kMini);
  if (!forza) {
    const pronte = await api().miniature(chiavi);
    if (pronte && !pronte.errore) Object.assign(S.mini, pronte);
    disegnaGriglia();
  }
  if (!(await modelliSpidey()).gioco.parti.length) return;  // senza il modello del gioco niente foto nuove (verrebbero vuote)
  codaMini = S.dati.skin.filter(v => forza || !S.mini[kMini(v)]);
  if (!lavoraMini) lavoraCoda();
}
async function lavoraCoda() {
  lavoraMini = true;
  while (codaMini.length) {
    const v = codaMini.shift();
    const d = await api().texture(v.default, 512, 256);
    if (!d || d.errore) continue;
    const png = await fotoViewer.foto_di(d);
    S.mini[kMini(v)] = png;
    api().salva_miniatura(kMini(v), png);
    const img = document.querySelector(`.carta[data-k="${v.k}"] .foto`);
    if (img) img.innerHTML = `<img class="pronta" src="${png}">`;
  }
  lavoraMini = false;
}

// ================================================================ codici
const C = { dati: null, gid: null, tutte: undefined, mod: {}, cerca: "", chiuse: new Set(["essenziale"]) };
try { const x = JSON.parse(localStorage.getItem("sezioni_chiuse")); if (Array.isArray(x)) C.chiuse = new Set(x); } catch (e) {}
const LIVELLI = ["essenziale", "consigliato", "facile", "difficile", "ora", "divertimento", "miei"];
function apriSezione(liv, apri) {
  if (apri) C.chiuse.delete(liv); else C.chiuse.add(liv);
  try { localStorage.setItem("sezioni_chiuse", JSON.stringify([...C.chiuse])); } catch (e) {}
}
function mostraCodice(id) {  // apre la sezione del codice, ci scorre e lo fa lampeggiare
  apriSezione(codice(id).livello, true);
  disegnaCodici();
  const el = document.querySelector(`.codice[data-id="${id}"]`);
  if (!el) return;
  const box = $("#cod-lista"), r = el.getBoundingClientRect(), rb = box.getBoundingClientRect();  // scorre solo la lista, non la finestra
  box.scrollTo({ top: box.scrollTop + (r.top - rb.top - (rb.height - r.height) / 2) / zoomPagina(), behavior: "smooth" });
  el.classList.add("lampeggia"); setTimeout(() => el.classList.remove("lampeggia"), 2200);
}
const codice = id => C.dati.codici.find(c => c.id === id);
const versione = gid => C.dati.versioni.find(v => v.id === gid);
const salvato = (gid, id) => versione(gid).attivi.includes(codice(id).nome_ini);
const installate = () => C.dati.versioni.filter(v => v.installata);
const hanno = id => installate().filter(v => codice(id).versioni.includes(v.id));  // versioni che hai e che hanno il codice
function base(id) {  // stato salvato; con "tutte le versioni": quello comune, null se è diverso tra le versioni
  if (!C.tutte) return salvato(C.gid, id);
  const vs = hanno(id).map(v => salvato(v.id, id));
  return vs.every(x => x === vs[0]) ? !!vs[0] : null;
}
const effettivo = id => id in C.mod ? C.mod[id] : !!base(id);
const disponibile = c => C.tutte ? installate().some(v => c.versioni.includes(v.id)) : c.versioni.includes(C.gid);
const misti = () => C.dati.codici.filter(c => disponibile(c) && base(c.id) === null && !(c.id in C.mod));
async function caricaCodici() {
  const d = await api().codici_stato();
  if (!d || d.errore) { toast(t("errore"), errTesto(d && d.errore), "errore"); return; }
  C.dati = d;
  if (!C.gid || !versione(C.gid).installata) C.gid = (d.versioni.find(v => v.installata) || d.versioni.find(v => v.disco) || d.versioni[0]).id;
  if (C.tutte === undefined) C.tutte = typeof d.tutte === "boolean" ? d.tutte : installate().length > 1;  // più versioni = tutte insieme
  disegnaCodici();
}
async function cambiaCodice(id, on) {
  const c = codice(id);
  if (on) {  // conflitto di tasti con un codice già acceso: chiedo cosa fare
    for (const x of c.conflitti.filter(x => effettivo(x) && codice(x).versioni.includes(C.gid))) {
      const o = codice(x);
      const r = await modale({ titolo: t("conflitto_tit"),
        testo: t("conflitto_testo", tr(c.titolo), tr(o.titolo), (o.tasti || c.tasti || "?").replace(" | ", " " + t("com_o") + " ")) + " " + t("nella_sezione", t("sez_" + o.livello)),
        bottoni: [["mostra", t("vai_al_codice", tr(o.titolo))], ["annulla", t("annulla_scelta")], ["tieni", t("tieni_entrambi")], ["spegni", t("spegni_x", tr(o.titolo)), true]] });
      if (r === "mostra") { disegnaCodici(); mostraCodice(x); return; }
      if (r === "annulla" || r === null) { disegnaCodici(); return; }
      if (r === "spegni") { if (base(x) !== false) C.mod[x] = false; else delete C.mod[x]; }
    }
  }
  const imposta = (x, v) => { if (v === base(x)) delete C.mod[x]; else C.mod[x] = v; };
  imposta(id, on);
  if (on && c.esclusivo) {
    const spenti = C.dati.codici.filter(o => o.id !== id && o.esclusivo === c.esclusivo && effettivo(o.id));
    spenti.forEach(o => imposta(o.id, false));
    if (spenti.length) toast(t("esclusivo_spento", spenti.map(o => tr(o.titolo)).join(", ")), "", "avviso", 3500);
  }
  disegnaCodici();
}
function consigliati() {
  C.mod = {};
  for (const c of C.dati.codici) {
    const vuoi = c.livello === "essenziale";
    if (disponibile(c) && vuoi !== base(c.id)) C.mod[c.id] = vuoi;
  }
  toast(t("consigliati_ok"), "", "", 2500);
  disegnaCodici();
}
function disegnaCodici() {
  if (!C.dati) return;
  const vb = $("#cod-versioni");
  vb.innerHTML = "";
  for (const v of C.dati.versioni) {
    const b = document.createElement("button");
    b.className = ((C.tutte ? v.installata : v.id === C.gid) ? "attivo" : "") + (v.installata ? "" : v.disco ? " senza" : " no");  // senza = hai il gioco ma ancora nessun codice
    b.innerHTML = `<i></i>${v.nome}`;
    b.title = v.installata ? v.id : v.disco ? `${v.id} · ${t("cod_senza_codici")}` : `${v.id} · ${t("non_installata")}`;
    b.onclick = () => {  // clic su una versione = lavoro solo su quella
      if ((!v.installata && !v.disco) || (v.id === C.gid && !C.tutte)) return;
      C.gid = v.id; C.mod = {}; if (C.tutte) { C.tutte = false; api().imposta("codici_tutte", false); } disegnaCodici();
    };
    vb.appendChild(b);
  }
  $("#cod-tutte").checked = C.tutte;
  const pb = $("#cod-patch"), vv = (C.tutte && installate().find(v => v.pal && !v.patch60)) || versione(C.gid);  // patch 60Hz delle PAL: sempre in vista, fuori dalle sezioni
  const pbOn = vv.pal && vv.installata;  // senza codici la patch arriva insieme ai codici essenziali (banner sotto)
  pb.classList.toggle("nascosto", !pbOn);
  if (pbOn) {
    pb.className = "patch-barra " + (vv.patch60 ? "ok" : "no");
    pb.innerHTML = `<svg><use href="${vv.patch60 ? "#i-ok" : "#i-ingr"}"/></svg><span>${t(vv.patch60 ? "patch60_banner_ok" : "patch60_banner_no")}</span>` +
      (vv.patch60 ? "" : `<button class="primario">${t("b_patch")}</button>`);
    const b = pb.querySelector("button");
    if (b) b.onclick = async () => { const r = await api().cam_patch(vv.id); if (r && !r.errore) { toast(t("fatto"), t("patch_ok")); C.dati = null; caricaCodici(); } };
  }
  const senza = C.dati.versioni.filter(x => x.disco && !x.installata);  // hai il gioco ma ancora nessun codice
  const es = $("#cod-essenziali");
  es.classList.toggle("nascosto", !senza.length);
  if (senza.length) {
    es.innerHTML = `<svg><use href="#i-codici"/></svg><span>${t("cod_ess_banner", senza.map(x => x.nome).join(", "))}</span><button class="primario">${t("cod_ess_b")}</button>`;
    es.querySelector("button").onclick = async () => {
      const r = await api().codici_essenziali();
      if (!r || r.errore) { toast(t("errore"), errTesto(r && r.errore), "errore"); return; }
      toast(t("fatto"), t("cod_ess_ok", r.fatti.join(", ")) + (r.dolphin_aperto ? " " + t("riavvia") : ""), "", 6000);
      C.dati = null; C.mod = {}; Q.dati = null; G.dati = null; await caricaCodici();
    };
  }
  if (!C.tutte && !versione(C.gid).installata) { $("#cod-lista").innerHTML = ""; return; }  // versione scelta ancora senza codici: c'è il banner sopra
  if (!C.dati.versioni.some(x => x.installata)) {  // niente codici ancora: se manca Dolphin o il gioco lo dico, con la strada
    const manca = !S.dati.dolphin ? "dolphin" : !C.dati.versioni.some(x => x.disco) ? "gioco" : null;
    $("#cod-lista").innerHTML = manca ? `<div class="vuoto-box"><svg><use href="#${manca === "dolphin" ? "i-scarica" : "i-play"}"/></svg>
      <h3>${t("cod_vuoto_" + manca)}</h3><p>${t("cod_vuoto_" + manca + "_sub")}</p><button class="primario" id="cod-vai-gioca">${t("cod_vai_launcher")} →</button></div>` : "";
    const b = $("#cod-vai-gioca"); if (b) b.onclick = () => vaiA("gioca");
    return;
  }
  const box = $("#cod-lista");
  const scroll = box.scrollTop;
  box.innerHTML = "";
  const v = versione(C.gid);
  const accesi = new Set(C.dati.codici.filter(c => effettivo(c.id)).map(c => c.id));
  const q = C.cerca.trim().toLowerCase();
  const mi = C.tutte ? misti() : [];
  if (mi.length) {  // accesi in una versione sì e in un'altra no: un clic e diventano uguali dappertutto
    const bar = document.createElement("div");
    bar.className = "patch-barra giallo";
    bar.innerHTML = `<svg><use href="#i-ingr"/></svg><span>${t("cod_misti", mi.length, mi.map(c => tr(c.titolo)).join(", "))}</span><button class="primario">${t("cod_misti_b")}</button>`;
    bar.querySelector("button").onclick = () => { mi.forEach(c => { C.mod[c.id] = true; }); disegnaCodici(); };
    box.appendChild(bar);
  }
  for (const liv of LIVELLI) {
    const lista = C.dati.codici.filter(c => c.livello === liv &&
      (!q || (tr(c.titolo) + " " + tr(c.desc) + " " + c.nome_ini).toLowerCase().includes(q)));
    if (!lista.length && (q || liv === "miei")) continue;
    const disp = lista.filter(disponibile);
    const sez = document.createElement("div");
    sez.className = "cod-sezione " + liv;
    const n = disp.filter(c => accesi.has(c.id)).length;
    const chiusa = C.chiuse.has(liv) && !q;
    if (chiusa) sez.classList.add("chiusa");
    const nomiOn = disp.filter(c => accesi.has(c.id)).map(c => tr(c.titolo));
    const cambiati = disp.some(c => c.id in C.mod);
    sez.innerHTML = `<button class="sez-testa"><svg class="freccia-sez"><use href="#i-indietro"/></svg><h3>${t("sez_" + liv)}<span class="conta">${n} / ${disp.length}</span>${cambiati ? '<i class="punto-mod"></i>' : ""}</h3>
      <span class="sez-azione">${chiusa ? t("apri_sez") : t("chiudi_sez")}</span></button>
      <p>${t("sez_" + liv + "_sub")}</p>
      ${chiusa ? `<div class="riassunto">${n ? `<b>${t("attivi_n", n)}:</b> ${nomiOn.join(" · ")}` : t("nessuno_attivo")}</div>` : ""}`;
    sez.querySelector(".sez-testa").onclick = () => { apriSezione(liv, C.chiuse.has(liv)); disegnaCodici(); };
    if (chiusa) { box.appendChild(sez); continue; }
    if (!disp.length) {
      sez.insertAdjacentHTML("beforeend", `<div class="nota-sez">${t("non_ita")}</div>`);
    } else {
      const gr = document.createElement("div");
      gr.className = "cod-griglia";
      disp.forEach(c => gr.appendChild(cartaCodice(c, accesi)));
      sez.appendChild(gr);
    }
    box.appendChild(sez);
  }
  box.scrollTop = scroll;
  piedeCodici();
}
function cartaCodice(c, accesi) {
  const on = accesi.has(c.id);
  const confl = c.conflitti.filter(x => accesi.has(x));
  const d = document.createElement("div");
  d.className = "codice" + (on ? " on" : "") + (c.id in C.mod ? " cambiato" : "") + (on && confl.length ? " conflitto" : "");
  const meta = [];
  if (c.tasti) meta.push(c.tasti.split(" | ").map((x, i) => `<span class="tasto ${i ? "alt" : ""}">${x}</span>`).join(`<em class="oppure">${t("com_o")}</em>`));  // tasto della mod | combinazione GameCube
  if (on && confl.length) meta.push(`<span class="avviso link-codice" data-vai-codice="${confl[0]}">${t("conflitto", confl.map(x => tr(codice(x).titolo) + " (" + t("sez_" + codice(x).livello) + ")").join(", "))}</span>`);
  if (c.livello === "miei") meta.push(`<span class="link elimina" data-elimina="${c.id}">${t("cod_elimina")}</span>`);
  if (C.tutte && !(c.id in C.mod) && base(c.id) === null)
    meta.push(`<span class="solo-in">${t("cod_solo_in", hanno(c.id).filter(v => salvato(v.id, c.id)).map(v => v.nome).join(", "))}</span>`);
  if (c.pezzi && c.pezzi.length)  // codici nascosti dentro questa voce (si accendono e spengono con lei)
    meta.push(`<span class="pezzi" title="${t("cod_pezzi_tip")}">${t("cod_contiene")} ${c.pezzi.map(p => `<b class="pz"><i class="tipo-cod ${p.tipo.toLowerCase()}">${p.tipo}</i>${tr(p.titolo)}</b>`).join("")}</span>`);
  if (c.id === "camera") meta.push(`<span class="link" data-vai="cam">${t("regola_cam")} →</span>`);
  if (c.id === "skin") meta.push(`<span class="link" data-vai="skin">${t("nav_skin")} →</span>`);
  d.innerHTML = `<div class="info"><b>${tr(c.titolo)}</b><p>${c.livello === "miei" ? t("cod_mio_desc", c.righe_n) : tr(c.desc)}</p>${meta.length ? `<div class="meta">${meta.join("")}</div>` : ""}</div>
    <label class="interruttore"><input type="checkbox" ${on ? "checked" : ""}><span></span></label>`;
  d.querySelector("input").onchange = e => cambiaCodice(c.id, e.target.checked);
  d.querySelectorAll("[data-vai]").forEach(x => x.onclick = () => vaiA(x.dataset.vai));
  d.querySelectorAll("[data-elimina]").forEach(x => x.onclick = () => eliminaCodice(c));
  d.querySelectorAll("[data-vai-codice]").forEach(x => x.onclick = () => mostraCodice(x.dataset.vaiCodice));
  d.title = c.nome_ini.slice(1);
  d.dataset.id = c.id;
  return d;
}
function piedeCodici() {
  if (S.pagina !== "codici") return;
  const box = $("#modifiche");
  box.innerHTML = "";
  const ids = C.dati ? Object.keys(C.mod) : [];
  if (!ids.length) {
    box.innerHTML = `<div class="tutto-ok"><svg><use href="#i-ok"/></svg>${t("tutto_salvato")}</div>`;
    $("#piede").classList.add("nascondi-azioni");
    return;
  }
  $("#piede").classList.remove("nascondi-azioni");
  for (const id of ids.slice(0, 6)) {
    const m = document.createElement("div");
    m.className = "mod";
    m.innerHTML = `${tr(codice(id).titolo)}: <b>${C.mod[id] ? t("acceso") : t("spento")}</b><button>×</button>`;
    m.querySelector("button").onclick = () => { delete C.mod[id]; disegnaCodici(); };
    box.appendChild(m);
  }
  if (ids.length > 6) box.insertAdjacentHTML("beforeend", `<span>+${ids.length - 6}</span>`);
}
async function aggiungiCodice() {
  let val = { campo: "", area: "", spunte: [C.gid] };
  for (;;) {
    val = await modale({ titolo: t("cod_agg"), testo: t("cod_agg_testo"), campo: val.campo, segnaposto: t("cod_agg_nome"), area: val.area,
      spunte: C.dati.versioni.filter(v => v.installata).map(v => [v.id, v.nome, val.spunte.includes(v.id)]),
      bottoni: [[null, t("annulla")], ["modulo", t("cod_agg"), true]] });
    if (!val) return;
    const r = await api().codice_aggiungi(val.campo, val.area, val.spunte);
    if (r && r.errore) { toast(t("errore"), r.errore === "riga" ? t("cod_err_riga", r.n, r.riga) : t("cod_err_" + r.errore), "errore", 7000); continue; }
    if (!r) return;
    await caricaCodici();
    C.mod[r.id] = true;                 // acceso: si salva con Applica
    apriSezione("miei", true);
    disegnaCodici();
    mostraCodice(r.id);
    toast(t("fatto"), t("cod_agg_ok", r.nome), "", 6000);
    return;
  }
}
async function eliminaCodice(c) {
  if (!(await modale({ titolo: t("cod_elimina_tit", tr(c.titolo)), testo: t("cod_elimina_testo"), bottoni: [[false, t("annulla")], [true, t("cod_elimina"), true]] }))) return;
  await api().codice_elimina(c.id);
  delete C.mod[c.id];
  await caricaCodici();
}
async function applicaCodici() {
  if (!C.dati || !Object.keys(C.mod).length) return;
  const accesi = C.dati.codici.filter(c => effettivo(c.id) && c.versioni.includes(C.gid));
  const coppie = [];
  for (const a of accesi) for (const b of a.conflitti) if (a.id < b && effettivo(b)) coppie.push(`${tr(a.titolo)} + ${tr(codice(b).titolo)}`);
  if (coppie.length && !(await modale({ titolo: t("conflitto_tit"), testo: t("conflitti_applica", coppie.join(", ")),
      bottoni: [[false, t("annulla_scelta")], [true, t("applica_lo_stesso"), true]] }))) return;
  const gids = C.tutte ? C.dati.versioni.filter(v => v.installata).map(v => v.id) : [C.gid];
  const spenti = Object.values(C.mod).some(v => !v);
  $("#applica").disabled = true;
  const r = await api().codici_applica(gids, C.mod);
  $("#applica").disabled = false;
  if (!r || r.errore) { toast(t("errore"), errTesto(r && r.errore), "errore"); return; }
  if (!r.fatti.length) { toast(t("errore"), t("cod_niente"), "errore"); return; }
  C.mod = {};
  G.dati = null;  // Grafica rilegge il "30 fps" (= $60fps spento)
  await caricaCodici();
  const live = r.dolphin_aperto ? await api().gioca_live() : null;
  if (live && live.gioco && gids.includes(live.gioco)) {  // gioco aperto: i codici partono all'avvio -> riavvio adesso?
    toast(t("fatto"), t("cod_fatto", r.fatti.join(", ")), "", 3000);
    // riprendere da uno stato salvato dava problemi: si riavvia da capo (i salvataggi del gioco restano)
    const s1 = await api().stato1_c_e();
    const scelta = await modale({ titolo: t("cd_riavvio_tit"), testo: t("cd_riavvio_testo"),
      bottoni: [["dopo", t("cd_dopo")], ...(s1 === true ? [["stato1", t("cd_riavvia_stato1")]] : []), ["completo", t("cd_riavvia_ora"), true]] });
    if (scelta === "completo") { await api().riavvia_gioco(false); toast(t("cd_passo_riavvio"), t("cd_completo_sub"), "", 7000); }
    if (scelta === "stato1") { await api().riavvia_gioco(true); toast(t("cd_passo_riavvio"), t("cd_stato1_sub"), "", 7000); }
    return;
  }
  toast(t("fatto"), t("cod_fatto", r.fatti.join(", ")) + (r.saltati.length ? t("cod_saltati", r.saltati.join(", ")) : "") +
    (r.dolphin_aperto ? t("cod_riavvia") : ""), r.dolphin_aperto || r.saltati.length ? "avviso" : "", 6000);
}

// ================================================================ HUD e tasti
const H = { dati: null, slot: "hud", scelta: { hud: null, tasti: null, disegno: null }, img: {}, cerca: "" };
// "disegno" = il controller disegnato in Opzioni > Controller: si sceglie per famiglia, quella dei tasti a schermo scelti
const hFam = () => { const a = hattuale("tasti"); return a && /playstation|ps[2-5]/i.test(a.path || a.id || "") ? "ps" : "xbox"; };
const hvoci = () => H.slot === "disegno" ? H.dati.disegni.filter(d => d.fam === hFam()) : H.dati[H.slot];
const hvoce = (slot, id) => (slot === "disegno" ? H.dati.disegni : H.dati[slot]).find(v => v.id === id);
const hattuale = slot => slot === "disegno" ? (H.scelta.disegno && H.scelta.disegno.fam === hFam() ? H.scelta.disegno
    : H.dati.inst.disegno && H.dati.inst.disegno.fam === hFam() ? H.dati.inst.disegno : { id: H.dati.disegni_scelti[hFam()], fam: hFam() })
  : H.scelta[slot] ?? H.dati.inst[slot];
async function caricaHud() {
  const d = await api().hud_stato();
  if (!d || d.errore) { toast(t("errore"), errTesto(d && d.errore), "errore"); return; }
  H.dati = d;
  // disegno del controller non ancora messo (es. c'è ancora il 360 del pack): lo propongo come modifica da applicare
  const fam = hFam(), voluto = d.disegni_scelti && d.disegni_scelti[fam];
  if (voluto && !(d.inst.disegno && d.inst.disegno.id === voluto) && !H.scelta.disegno) H.scelta.disegno = { id: voluto, fam };
  disegnaHud();
}
function hNome(slot) {
  const a = hattuale(slot);
  if (!a) return t("originale");
  const v = hvoce(slot, a.id);
  return v ? v.nome : t("sconosciuta");
}
function disegnaHud() {
  if (!H.dati) return;
  $$("#pg-hud .slot button").forEach(b => {
    const s = b.dataset.hslot;
    b.classList.toggle("attivo", s === H.slot);
    b.classList.toggle("cambiato", H.scelta[s] !== null);
    b.querySelector(".ora").textContent = hNome(s);
  });
  hGriglia();
  hPalco();
  piedeHud();
}
async function hImg(slot, path, larg) {
  const k = slot + "|" + path + "|" + larg;
  if (!H.img[k]) { const d = slot === "disegno" ? await api().disegno_anteprima(path, larg) : await api().hud_anteprima(slot, path, larg); if (d && !d.errore) H.img[k] = d; }
  return H.img[k];
}
function hGriglia() {
  const g = $("#h-griglia");
  g.innerHTML = "";
  const q = H.cerca.trim().toLowerCase();
  const inst = H.slot === "disegno" ? (H.dati.inst.disegno || {}) : H.dati.inst[H.slot], cur = hattuale(H.slot);
  let ultimo = null;
  for (const v of hvoci()) {
    if (q && !(v.nome + " " + v.gruppo).toLowerCase().includes(q)) continue;
    if (H.slot === "hud" && v.gruppo !== ultimo) {
      ultimo = v.gruppo;
      g.insertAdjacentHTML("beforeend", `<div class="gruppo-titolo">${nomeGruppo(v.gruppo)}</div>`);
    }
    const c = document.createElement("div");
    c.tabIndex = 0;
    c.className = "carta" + (cur && cur.id === v.id ? " selezionata" : "") + (inst && inst.id === v.id ? " installata" : "");
    const badge = [];
    if (inst && inst.id === v.id) badge.push(`<span class="in-uso">● ${t("in_uso")}</span>`);
    if (H.scelta[H.slot] && H.scelta[H.slot].id === v.id) badge.push(`<span class="scelta">● ${t("scelta")}</span>`);
    if (v.varianti > 1) badge.push(`<span class="var">${t("varianti", v.varianti)}</span>`);
    c.innerHTML = `<div class="badge">${badge.join("")}</div>
      <div class="foto ${H.slot === "hud" || H.slot === "disegno" ? "quadra" : "largo"}"><div class="attesa"></div></div>
      <div class="testo"><b title="${v.nome}">${v.nome}</b><small>${H.slot === "hud" ? nomeGruppo(v.gruppo) : H.slot === "disegno" ? (v.predefinito ? "★ " + t("predefinito") : v.fam === "ps" ? "PlayStation" : "Xbox") : (v.xbox ? "Xbox" : "")}</small></div>`;
    c.onclick = () => hScegli(v);
    g.appendChild(c);
    const slot = H.slot;
    hImg(slot, slot === "disegno" ? v.id : v.default, 320).then(d => {
      if (!d) return;
      const f = c.querySelector(".foto");
      f.innerHTML = `<img class="pronta" src="${d}">`;
    });
  }
}
function hScegli(v, path = null) {
  if (H.slot === "disegno") {  // scelta per la famiglia dei tasti; uguale a quella di adesso = nessuna modifica
    H.scelta.disegno = H.dati.inst.disegno && H.dati.inst.disegno.id === v.id ? null : { id: v.id, fam: v.fam };
    disegnaHud(); return;
  }
  const inst = H.dati.inst[H.slot];
  const p = path || v.default;
  H.scelta[H.slot] = inst && inst.id === v.id && inst.path === p ? null : { id: v.id, path: p };
  disegnaHud();
}
let hRichiesta = 0;
async function hPalco() {
  const a = hattuale(H.slot), v = a && hvoce(H.slot, a.id);
  const mia = ++hRichiesta;
  const cambiato = H.scelta[H.slot] !== null;
  const et = $("#h-stato");
  et.textContent = cambiato ? t("da_applicare") : t("installata");
  et.className = "etichetta " + (cambiato ? "giallo" : "verde");
  $("#h-gruppo").textContent = H.slot === "hud" ? (v ? nomeGruppo(v.gruppo) : "") : H.slot === "disegno" ? t("disegno_menu") : t("tasti_layout");
  $("#h-nome").textContent = v ? v.nome : (a ? t("sconosciuta") : t("originale"));
  // varianti
  const vb = $("#h-varianti");
  vb.innerHTML = "";
  if (v && v.varianti > 1) {
    const opz = [];
    (function giro(n, pref) {
      if (n.path) opz.push({ nome: pref || t("base"), path: n.path });
      n.figli.forEach(f => giro(f, f.nome));
    })(v.albero, "");
    for (const o of opz) {
      const b = document.createElement("button");
      b.className = "opz" + (o.path === a.path ? " attivo" : "");
      b.textContent = o.nome;
      b.onclick = () => hScegli(v, o.path);
      vb.appendChild(b);
    }
  }
  $("#h-nota").textContent = H.slot === "hud" ? (v && v.pezzi < 3 ? t("hud_pezzi_base") : "") : H.slot === "disegno" ? t("disegno_nota", hFam() === "ps" ? "PlayStation" : "Xbox")
    : (v && v.xbox ? t("tasti_xbox") : t("tasti_altri"));
  if (H.slot === "disegno") $("#h-nota").insertAdjacentHTML("afterbegin", soloApp());  // le linee gialle le sposta l'app mentre giochi
  const img = $("#h-img");
  if (!a || !(a.path || H.slot === "disegno")) { img.removeAttribute("src"); $("#h-pezzi").innerHTML = ""; return; }
  const d = await hImg(H.slot, H.slot === "disegno" ? a.id : a.path, 900);
  if (mia !== hRichiesta) return;
  img.src = d || "";
  img.className = H.slot === "hud" || H.slot === "disegno" ? "quadra" : "largo";
  const pz = $("#h-pezzi");
  pz.innerHTML = "";
  if (H.slot === "hud") {
    const pezzi = await api().hud_pezzi(a.path);
    if (mia !== hRichiesta || !Array.isArray(pezzi)) return;
    pz.innerHTML = `<div class="pezzi-titolo">${t("pezzi_extra")}</div>` + pezzi.map(p =>
      `<figure class="${p.base ? "prestito" : "proprio"}"><img src="${p.img}"><figcaption>${p.base ? t("da_base") : t("della_hud")}</figcaption></figure>`).join("");
  }
}
function piedeHud() {
  if (S.pagina !== "hud") return;
  const box = $("#modifiche");
  box.innerHTML = "";
  const slots = ["hud", "tasti", "disegno"].filter(s => H.scelta[s] !== null);
  if (!slots.length) {
    box.innerHTML = `<div class="tutto-ok"><svg><use href="#i-ok"/></svg>${t("tutto_salvato")}</div>`;
    $("#piede").classList.add("nascondi-azioni");
    return;
  }
  $("#piede").classList.remove("nascondi-azioni");
  for (const s of slots) {
    const m = document.createElement("div");
    m.className = "mod";
    m.innerHTML = `${t("hslot_" + s)}: <b>${hNome(s)}</b><button>×</button>`;
    m.querySelector("button").onclick = () => { H.scelta[s] = null; disegnaHud(); };
    box.appendChild(m);
  }
}
async function applicaHud() {
  if (!H.dati || (!H.scelta.hud && !H.scelta.tasti && !H.scelta.disegno)) return;
  const ds = H.scelta.disegno;
  const r = await conBarra(t("applico_hud"), () => api().hud_applica({ hud: H.scelta.hud && H.scelta.hud.path, tasti: H.scelta.tasti && H.scelta.tasti.path,
    disegno: ds ? { [ds.fam]: ds.id } : null }));
  if (!r || r.errore) { disegnaHud(); toast(t("errore"), errTesto(r && r.errore), "errore"); return; }
  if (ds) H.dati.disegni_scelti[ds.fam] = ds.id;
  for (const s of ["hud", "tasti", "disegno"]) if (H.scelta[s]) { H.dati.inst[s] = H.scelta[s]; H.scelta[s] = null; }
  caricaHud();  // rilegge anche il disegno che c'è adesso in Dolphin
  disegnaHud();
  const testo = r.copiati + r.cancellati ? t("fatto_testo", r.copiati, r.cancellati, r.cartelle.join(", ")) : t("niente_da_fare");
  toast(t("fatto"), testo + (r.dolphin_aperto ? " " + t("riavvia") : ""), r.dolphin_aperto ? "avviso" : "", 5000);
}

// ================================================================ Spider-Cam
const K = { info: null, valori: null, fov: 95, collega: true, minUguale: false, preset: "migliorata", rif: null,
            stato: null, ver: "GK2E52", trucchi: null, timer: null, sistema: null,
            modo: "semplice", base: null, s: { d: 1, h: 0, r: 1 } };
// Modalità semplice (come nel menu in gioco): si parte dai valori del preset (K.base) e 3 cursori valgono per tutte le
// situazioni: distanza (x), altezza (+ m), reattività (ritardo x). La modalità avanzata regola ogni situazione a parte.
const SEMPLICE = { d: [0.6, 1.6, 0.05], h: [-1, 1, 0.1], r: [0.5, 2, 0.1] };
function kSempliceBase() { K.base = JSON.parse(JSON.stringify(K.valori)); K.s = { d: 1, h: 0, r: 1 }; }
function kSempliceValori() {
  const v = {};
  for (const g of K.info.gruppi) {
    const x = K.base[g];
    v[g] = [tondo(Math.min(8, Math.max(0.5, x[0] * K.s.d)), 2), tondo(Math.min(8, Math.max(0.5, x[1] * K.s.d)), 2),
      tondo(Math.max(0, x[2] + K.s.h), 2), tondo(Math.min(0.5, Math.max(0.02, x[3] * K.s.r)), 2)];
  }
  return v;
}
function kSempliceTesto(k) {
  if (k === "d") return Math.round(K.s.d * 100) + "%";
  if (k === "h") return (K.s.h > 0 ? "+" : "") + K.s.h.toFixed(1) + " m";
  return K.s.r < 0.95 ? t("cam_m_reattiva") + " ×" + (1 / K.s.r).toFixed(1) : K.s.r > 1.05 ? t("cam_m_morbida") + " ×" + K.s.r.toFixed(1) : t("cam_m_normale");
}
function kModo() {  // mostra la modalità scelta (semplice = 3 cursori, avanzata = tabella per situazione)
  const sem = K.modo === "semplice";
  if (sem && (!K.base || JSON.stringify(kSempliceValori()) !== JSON.stringify(K.valori))) kSempliceBase();  // cambiati a mano: si riparte da qui
  $$("#cam-modo button").forEach(b => b.classList.toggle("attivo", b.dataset.m === K.modo));
  $("#cam-modo-sub").textContent = t(sem ? "cam_semplice_sub" : "cam_avanzata_sub");
  $("#cam-semplice").classList.toggle("nascosto", !sem);
  $("#cam-avanzata").classList.toggle("nascosto", sem);
  if (!sem) return;
  const box = $("#cam-semplice"), nomi = { d: "dist", h: "alt", r: "rit" };
  box.innerHTML = Object.entries(SEMPLICE).map(([k, [mi, ma, pa]]) => `<div class="cam-s" data-k="${k}">
      <div class="cam-nome"><b>${t("cam_m_" + nomi[k])}</b><small>${t("cam_m_" + nomi[k] + "_sub")}</small></div>
      <div class="cella larga"><input type="range" min="${mi}" max="${ma}" step="${pa}" value="${K.s[k]}"></div><output>${kSempliceTesto(k)}</output></div>`).join("")
    + `<div class="cam-s-nota"><svg><use href="#i-giro"/></svg><span>${t("cam_semplice_nota")}</span></div>`;
  box.querySelectorAll(".cam-s").forEach(r => {
    const k = r.dataset.k, sl = r.querySelector("input"), out = r.querySelector("output"), [mi, ma] = SEMPLICE[k];
    const pct = () => sl.style.setProperty("--pct", ((K.s[k] - mi) / (ma - mi) * 100) + "%");
    pct();
    sl.oninput = () => {
      K.s[k] = tondo(+sl.value, 2);
      K.valori = kSempliceValori();
      out.textContent = kSempliceTesto(k); pct();
      aggiornaCelle(); kInvia();
    };
    r.ondblclick = () => { sl.value = K.s[k] = k === "h" ? 0 : 1; sl.oninput(); };  // doppio clic = come il preset
  });
}
const SCALE = [[0.5, 8, 0.05, 2], [0.5, 8, 0.05, 2], [-1, 4, 0.05, 2], [0.02, 0.6, 0.01, 2]];
const COLONNE = ["min", "des", "alt", "rit"];
const tondo = (x, c) => Math.round(x * 10 ** c) / 10 ** c;
function kIstantanea() { return JSON.stringify({ v: K.valori, f: Math.round(K.fov), m: K.minUguale }); }
function kTuttiPreset() {
  const out = [];
  if (K.tua) out.push({ chiave: "t:", nome: t("cc_tua_nome"), dati: K.tua, fisso: true });  // "La tua" (la camera fatta da te)
  for (const [id, p] of Object.entries(K.info.fissi)) out.push({ chiave: "f:" + id, nome: tr(p), dati: p, fisso: true });
  for (const [nome, p] of Object.entries(K.info.utente)) out.push({ chiave: "u:" + nome, nome, dati: p, fisso: false });
  return out;
}
function kEffettivi() {
  const v = {};
  for (const g of K.info.gruppi) { const x = K.valori[g]; v[g] = K.minUguale ? [x[1], x[1], x[2], x[3]] : [...x]; }
  return v;
}
async function caricaCam() {
  const d = await api().cam_info();
  if (!d || d.errore) { toast(t("errore"), errTesto(d && d.errore), "errore"); return; }
  K.info = d;
  K.trucchi = d.trucchi;
  K.ver = d.versione_salva;
  if (d.dischi.length && !d.dischi.includes(K.ver)) K.ver = d.dischi.includes(d.ultima) ? d.ultima : ID_ORDINE.find(g => d.dischi.includes(g));  // una versione che hai
  const u = d.ultimi;
  if (u && u.valori && d.gruppi.every(g => u.valori[g])) {
    K.valori = Object.fromEntries(d.gruppi.map(g => [g, u.valori[g].map(Number)]));
    K.fov = u.fov ?? 95; K.collega = u.collega ?? true; K.minUguale = u.min_uguale ?? false;
    K.preset = (u.preset_chiave && u.preset_chiave.startsWith("f:") && !(u.preset_chiave.slice(2) in K.info.fissi) ? "f:migliorata" : u.preset_chiave) || "f:migliorata";  // preset pronto rinominato o tolto
    K.rif = u.rif || null;
    K.modo = u.modo || "semplice";
    if (u.semplice && u.semplice.base && d.gruppi.every(g => u.semplice.base[g])) { K.base = u.semplice.base; K.s = { d: 1, h: 0, r: 1, ...u.semplice.s }; }
    K.tua = u.tua && u.tua.valori && d.gruppi.every(g => u.tua.valori[g]) ? u.tua : null;
    if (!K.tua && kVariante() === "tua") K.tua = kFotoTua();  // valori tuoi di prima di "La tua": diventano la tua camera
    if (!kTuttiPreset().some(p => p.chiave === K.preset)) {  // preset tolto (es. "Vicina classica") o eliminato
      const ora = kIstantanea(), uguale = kTuttiPreset().find(p => { kCaricaPreset(p.chiave, true); return kIstantanea() === ora; });
      if (!uguale) kCaricaPreset("f:migliorata", true);  // valori di un preset che non c'è più: riparto dalla camera consigliata
    }
  } else kCaricaPreset("f:migliorata", true);
  costruisciCam();
  kInvia();
}
function kCaricaPreset(chiave, silenzioso) {
  const p = kTuttiPreset().find(x => x.chiave === chiave);
  if (!p) return;
  K.valori = Object.fromEntries(K.info.gruppi.map(g => [g, [...p.dati.valori[g]].map(Number)]));
  K.fov = p.dati.fov ?? 90;
  K.minUguale = !!p.dati.min_uguale;
  K.preset = chiave;
  K.rif = kIstantanea();
  kSempliceBase();  // un preset nuovo: i cursori semplici ripartono da lì
  if (!silenzioso) { aggiornaCelle(); kInvia(); if (K.modo === "semplice") kModo(); }
}
let kTmInvio, kTmUltimi;
// Camera del gioco: "Migliorata" = il preset della camera migliorata così com'è; tutto il resto (cursori mossi, un tuo
// preset, l'originale come punto di partenza...) è "La tua", che l'app si ricorda (K.tua) per poterci tornare.
function kFotoTua() {
  return { valori: JSON.parse(JSON.stringify(K.valori)), fov: Math.round(K.fov), min_uguale: K.minUguale,
    preset_chiave: K.preset === "t:" ? (K.tua && K.tua.preset_chiave) || null : K.preset, modo: K.modo, semplice: { base: K.base, s: K.s } };
}
function kDiverso(d) {  // valori attuali diversi da quelli del preset d?
  const num = x => Math.round(Number(x) * 1000);
  return !!d && (K.info.gruppi.some(g => K.valori[g].some((x, i) => num(x) !== num(d.valori[g][i])))
    || Math.round(K.fov) !== Math.round(d.fov ?? 90) || !!K.minUguale !== !!d.min_uguale);
}
function kVariante() { return K.preset === "f:migliorata" && !kDiverso(K.info.fissi.migliorata) ? "classica" : "tua"; }
function kInvia() {
  clearTimeout(kTmInvio);
  kTmInvio = setTimeout(() => api().cam_imposta(kEffettivi(), K.fov), 25);
  if (K.info && kVariante() === "tua") {  // muovendo un cursore la camera diventa la tua (e la tua si aggiorna)
    const prima = !K.tua || K.preset !== "t:" && K.preset !== (K.tua && K.tua.preset_chiave);
    K.tua = kFotoTua();
    if (prima && $("#cam-coppia .cc-op")) ccDisegna();
  }
  clearTimeout(kTmUltimi);
  kTmUltimi = setTimeout(() => api().cam_ultimi({ valori: K.valori, fov: Math.round(K.fov), collega: K.collega,
    min_uguale: K.minUguale, preset_chiave: K.preset, rif: K.rif, modo: K.modo, semplice: { base: K.base, s: K.s }, tua: K.tua }), 800);
  kModificata();
  if ($("#cam-coppia .cc-op")) ccEvidenzia();
}
function kModificata() {
  const p = kTuttiPreset().find(x => x.chiave === K.preset);
  $("#cam-preset-nome").textContent = p ? p.nome : "—";
  const d = p && p.dati;
  const mod = K.preset !== "t:" && kDiverso(d);  // "La tua" è sempre sé stessa
  $("#cam-modificata").textContent = mod ? "● " + t("modificata") : "";
  const rip = $("#cam-ripristina");
  rip.classList.toggle("nascosto", !mod || !p);
  rip.onclick = () => { kCaricaPreset(K.preset); kMenuPreset(); kModo(); toast(t("fatto"), t("cam_ripristinato", p.nome), "", 3000); };
  const mio = K.preset.startsWith("u:");
  ["#cam-p-rinomina", "#cam-p-elimina"].forEach(q => { $(q).disabled = !mio; $(q).title = mio ? "" : t("fisso"); });
}
// ---- le due camere: principale e alternativa (R3), ognuna moderna / classica / originale (codice Gecko della camera)
const CC = { modi: ["moderna", "amazing"], slot: null, gecko: false };
const CC_MODI = ["moderna", "amazing", "cinematica", "prima", "classica", "originale"];
// John: le camere fatte da noi separate da quelle del gioco (la migliorata è l'originale più vicina: è l'unica che si
// regola coi cursori sotto); la prima persona ha il bollino "sperimentale"
// John: la camera del gioco si regola, quindi tra quelle "del gioco" c'è anche La tua ("tua" = la classica coi tuoi valori:
// Migliorata e La tua sono la stessa camera, c'è posto per una sola delle due tra principale e alternativa)
const CC_GRUPPI = [["cc_g_nuove", ["moderna", "amazing", "cinematica", "prima"]], ["cc_g_gioco", ["classica", "tua", "originale"]]];
const CC_SPER = ["prima"];
const CC_CONSIGLIATE = ["moderna", "amazing"];  // John: principale moderna, alternativa Amazing (anche le predefinite)
const CC_VISTE = ["no", "si"];  // prima persona: movimento della testa (cam_ps4.VISTE)
function ccVariante() { return K.info && K.valori ? kVariante() : CC.tua ? "tua" : "classica"; }  // Migliorata o La tua
function ccAttiva(i, m) { return m === "classica" || m === "tua" ? CC.modi[i] === "classica" && ccVariante() === m : CC.modi[i] === m; }
function ccEvidenzia() {  // solo le scelte accese (muovendo un cursore Migliorata diventa La tua)
  $$("#cam-coppia .cc-carta").forEach(c => c.querySelectorAll(".cc-op").forEach(b => b.classList.toggle("attivo", ccAttiva(+c.dataset.slot, b.dataset.m))));
}
function ccSub(m) {  // La tua: il nome del tuo preset, se ne hai caricato uno
  const pc = m === "tua" && K.tua && K.tua.preset_chiave;
  return pc && pc.startsWith("u:") ? pc.slice(2) : t("cc_m_" + m + "_sub");
}
async function ccCarica() {
  const r = await api().cam_modi();
  if (!r || r.errore) return;
  const prima = JSON.stringify(CC);
  Object.assign(CC, { modi: r.modi, slot: r.slot, gecko: r.gecko, opzioni: r.opzioni || {}, tua: !!r.tua });
  if (JSON.stringify(CC) !== prima || !$("#cam-coppia .cc-op")) ccDisegna();
}
function ccDisegna() {
  $$("#cam-coppia .cc-carta").forEach(c => {
    const i = +c.dataset.slot;
    c.classList.toggle("in-uso", CC.gecko && CC.slot === i);
    // camere nuove grandi (la consigliata per questo slot col bollino); quelle del gioco in una riga piccola a parte
    c.querySelector(".cc-scelte").innerHTML = CC_GRUPPI.map(([g, ms], gi) => `<div class="cc-gr ${gi ? "gioco" : ""}">${t(g)}</div>` + ms.map(m => `<button class="cc-op ${gi ? "piccola" : ""} ${ccAttiva(i, m) ? "attivo" : ""}" data-m="${m}">
      <b>${t("cc_m_" + m)}${CC_SPER.includes(m) ? `<em class="sper">${t("sperimentale")}</em>` : ""}${CC_CONSIGLIATE[i] === m ? `<em class="consigliata">★ ${t("consigliata")}</em>` : ""}</b><small>${ccSub(m)}</small></button>`).join("")).join("");
    c.querySelectorAll(".cc-op").forEach(b => b.onclick = () => ccScegli(i, b.dataset.m));
  });
  // Amazing: la spalla si sceglie con le frecce (di base destra)
  $("#cc-opz-amazing").classList.toggle("nascosto", !CC.modi.includes("amazing"));
  // prima persona (solo se la usi): movimento della testa spento / acceso
  $("#cc-opz-vista").classList.toggle("nascosto", !CC.modi.includes("prima"));
  const vista = (CC.opzioni || {}).prima_vista || "no";
  $("#cc-vista-scelte").innerHTML = CC_VISTE.map(v => `<button class="${v === vista ? "attivo" : ""}" data-v="${v}">${t("cc_vista_" + v)}</button>`).join("");
  $("#cc-vista-sub").textContent = t("cc_vista_" + vista + "_sub");
  $$("#cc-vista-scelte button").forEach(b => b.onclick = async () => {
    CC.opzioni = { ...(CC.opzioni || {}), prima_vista: b.dataset.v }; ccDisegna();  // il pulsante cambia subito (gli INI ci mettono ~2 s)
    const r = await api().cam_opzione("prima_vista", b.dataset.v);
    if (r && r.opzioni) { CC.opzioni = r.opzioni; ccDisegna(); toast(t("fatto"), t("cc_vista_fatto", t("cc_vista_" + b.dataset.v).toLowerCase()), "", 3500); }
  });
  // tuffo con L3 (con tutte le camere) e camera della picchiata (solo camere moderne / Amazing / cinematica)
  const o = CC.opzioni || {}, l3 = o.tuffo_l3 !== false, pic = o.picchiata !== false;
  $("#cc-tuffo-l3").checked = l3;
  $("#cc-picchiata").checked = pic;
  $("#cc-picchiata").disabled = !l3;
  $("#cc-picchiata-riga").classList.toggle("spento", !l3);
  [["#cc-tuffo-l3", "tuffo_l3"], ["#cc-picchiata", "picchiata"]].forEach(([s, k]) => $(s).onchange = async e => {
    const r = await api().cam_opzione(k, e.target.checked);
    if (r && r.opzioni) {
      CC.opzioni = r.opzioni; ccDisegna();
      if (k === "tuffo_l3") { C.dati = null; Q.dati = null; }  // è un codice: Codici e Comandi si rileggono
      toast(t("fatto"), k === "tuffo_l3" && r.riavvio ? t("cc_tuffo_riavvio") : "", "", r.riavvio ? 4000 : 1500);
    }
  });
  // regolazioni della migliorata (preset, cursori, vista dal vivo): solo se la usi in una delle due camere
  const conClassica = CC.modi.includes("classica");
  ["#pg-cam .cc-classica", "#pg-cam .cam-barra", "#pg-cam .cam-corpo"].forEach(s => $(s).classList.toggle("nascosto", !conClassica));
  $("#cc-senza-classica").classList.toggle("nascosto", conClassica);
  $("#cc-usa-classica").onclick = () => ccScegli(1, ccVariante());  // la mette come camera alternativa (R3): Migliorata o La tua
  if (S.pagina === "cam" && K.info) piedeCam();
  const ora = CC.gecko && CC.slot !== null ? CC.modi[CC.slot] : null;
  $("#cc-nota").textContent = ora && ora !== "classica" ? t("cc_nota_altra", t("cc_m_" + ora).toLowerCase()) : "";
}
// Migliorata <-> La tua: stessa camera del gioco, cambiano i valori (caricati qui e salvati subito nel gioco)
async function ccMettiVariante(v) {
  if (!K.info) await caricaCam();
  if (!K.info || kVariante() === v) return false;
  if (v === "classica") { K.tua = kFotoTua(); kCaricaPreset("f:migliorata"); }
  else if (K.tua) {
    kCaricaPreset("t:", true);  // silenzioso: prima rimetto anche i cursori semplici (kInvia rifotograferebbe la tua senza)
    if (K.tua.modo) K.modo = K.tua.modo;
    if (K.tua.semplice && K.tua.semplice.base) { K.base = K.tua.semplice.base; K.s = { d: 1, h: 0, r: 1, ...K.tua.semplice.s }; }
  } else { K.tua = kFotoTua(); K.preset = "t:"; }  // la prima volta parte dalla migliorata: muovi i cursori
  aggiornaCelle(); kModo(); kMenuPreset(); kInvia();
  await kSalvaGioco(true);
  return true;
}
async function ccScegli(i, m) {
  const variante = m === "classica" || m === "tua" ? m : null;
  if (variante) {
    const primaTua = !K.tua;
    const cambiata = await ccMettiVariante(variante);
    m = "classica";
    if (CC.modi[i] === m) {  // stessa camera del gioco, solo i valori
      ccDisegna();
      if (cambiata) toast(t("cc_fatto"), t(variante === "classica" ? "cc_mig_ok" : primaTua ? "cc_tua_nuova" : "cc_tua_ok"), "", 5000);
      return;
    }
  }
  if (CC.modi[i] === m) return;
  const nuovi = [...CC.modi];
  const scambio = nuovi[1 - i] === m;  // uguali non avrebbe senso (R3 non cambierebbe niente): le scambio
  if (scambio) nuovi[1 - i] = nuovi[i];
  nuovi[i] = m;
  CC.modi = nuovi; ccDisegna();
  const r = await api().cam_modi_imposta(nuovi);
  if (!r || r.errore) { toast(t("errore"), "", "errore"); return; }
  CC.modi = r.modi; ccDisegna();
  const nome = x => t("cc_m_" + (x === "classica" ? ccVariante() : x));  // la camera del gioco: Migliorata o La tua
  const sub = [t("cc_fatto_sub", nome(r.modi[0]), nome(r.modi[1]))];
  if (scambio) sub.unshift(t("cc_scambiate_sub"));
  if (r.vivo === "ok") sub.push(t("cc_vivo")); else if (r.vivo === "vecchio") sub.push(t("cc_vecchio"));
  toast(t(scambio ? "cc_scambiate" : "cc_fatto"), sub.join(" "), "", 4500);
}
function costruisciCam() {
  ccDisegna();
  const tab = $("#cam-righe");
  tab.innerHTML = "";
  for (const g of K.info.gruppi) {
    const r = document.createElement("div");
    r.className = "cam-riga";
    r.dataset.g = g;
    r.innerHTML = `<div class="cam-nome"><b>${t("g_" + g)}</b><small class="orig">${t("orig_val", K.info.originali[g].join(" / "))}</small></div>` +
      COLONNE.map((c, i) => `<div class="cella" data-i="${i}"><input type="range" min="${SCALE[i][0]}" max="${SCALE[i][1]}" step="${SCALE[i][2]}">
        <input type="number" min="${SCALE[i][0]}" max="${SCALE[i][1]}" step="${SCALE[i][2]}"></div>`).join("") +
      `<button class="tondo piccolo" data-tip="tip_reset"><svg><use href="#i-giro"/></svg></button>`;
    r.querySelectorAll(".cella").forEach(cel => {
      const i = +cel.dataset.i, [sl, nu] = cel.querySelectorAll("input");
      const metti = (x, da) => {
        x = Math.min(SCALE[i][1], Math.max(SCALE[i][0], tondo(+x, SCALE[i][3])));
        if (isNaN(x)) return;
        K.valori[g][i] = x;
        if (i === 3 && K.collega && K.info.collegati.includes(g)) K.info.collegati.forEach(o => K.valori[o][3] = x);
        aggiornaCelle(da);
        kInvia();
      };
      sl.oninput = () => metti(sl.value, sl);
      nu.onchange = () => metti(nu.value, nu);
      cel.onwheel = e => { e.preventDefault(); metti(K.valori[g][i] + (e.deltaY < 0 ? 1 : -1) * SCALE[i][2], null); };
    });
    r.querySelector("button").onclick = () => { K.valori[g] = [...K.info.originali[g]]; aggiornaCelle(); kInvia(); };
    tab.appendChild(r);
  }
  $("#cam-collega").checked = K.collega;
  $("#cam-minuguale").checked = K.minUguale;
  $$("#cam-modo button").forEach(b => b.onclick = () => { K.modo = b.dataset.m; kModo(); kInvia(); });
  kModo();
  aggiornaCelle();
  kMenuPreset();
  kVersioni();
}
function aggiornaCelle(salta) {
  for (const r of $$("#cam-righe .cam-riga")) {
    const g = r.dataset.g;
    r.querySelectorAll(".cella").forEach(cel => {
      const i = +cel.dataset.i, [sl, nu] = cel.querySelectorAll("input");
      let x = K.valori[g][i];
      if (i === 0 && K.minUguale) x = K.valori[g][1];
      if (sl !== salta) sl.value = x;
      if (nu !== salta) nu.value = x.toFixed(SCALE[i][3]);
      const disab = i === 0 && K.minUguale;
      sl.disabled = nu.disabled = disab;
      sl.style.setProperty("--pct", ((x - SCALE[i][0]) / (SCALE[i][1] - SCALE[i][0]) * 100) + "%");
    });
  }
  const fs = $("#cam-fov"), fn = $("#cam-fov-n");
  if (fs !== salta) fs.value = K.fov;
  if (fn !== salta) fn.value = Math.round(K.fov);
  fs.style.setProperty("--pct", ((K.fov - 60) / (120 - 60) * 100) + "%");
  kModificata();
}
function kMenuPreset() {
  const m = $("#cam-preset-menu");
  m.innerHTML = "";
  const tutti = kTuttiPreset();
  for (const [titolo, lista] of [[t("preset_pronti"), tutti.filter(p => p.fisso)], [t("preset_miei"), tutti.filter(p => !p.fisso)]]) {
    if (!lista.length) continue;
    m.insertAdjacentHTML("beforeend", `<div class="menu-titolo">${titolo}</div>`);
    for (const p of lista) {
      const b = document.createElement("button");
      b.className = "menu-voce" + (p.chiave === K.preset ? " attivo" : "");
      b.textContent = p.nome;
      b.onclick = () => { kCaricaPreset(p.chiave); m.classList.add("nascosto"); kMenuPreset(); };
      m.appendChild(b);
    }
  }
}
function kInstallate() { return K.info.versioni.filter(v => v.ini).map(v => v.id); }
function kVersioni() {  // "Salva per": una versione o tutte quelle installate
  const box = $("#cam-versioni");
  if (!box) return;  // il piede "Salva per" c'è solo con la pagina Spider-Cam aperta
  box.innerHTML = "";
  const live = K.stato && K.stato.conn === "live" && K.stato.id;
  if (live) K.ver = K.stato.id;
  const inst = kInstallate();
  if (K.tutte === undefined) K.tutte = K.info.tutte ?? inst.length > 1;
  if (inst.length > 1) {
    const b = document.createElement("button");
    b.className = "tutte" + (K.tutte ? " attivo" : "");
    b.textContent = t("cam_tutte");
    b.title = t("cam_tutte_tip");
    b.onclick = () => { K.tutte = !K.tutte; api().imposta("cam_tutte", K.tutte); kVersioni(); };
    box.appendChild(b);
  }
  for (const v of K.info.versioni) {
    const b = document.createElement("button");
    const dentro = K.tutte && inst.length > 1 ? inst.includes(v.id) : v.id === K.ver;
    b.className = (dentro ? "attivo" : "") + (live && !K.tutte && v.id !== K.ver ? " no" : "");
    b.innerHTML = `<i></i>${v.nome}`;
    b.title = live ? t("ver_dal_gioco") : v.id;
    b.onclick = () => { if (live && !K.tutte) return; K.tutte = false; api().imposta("cam_tutte", false); if (!live) K.ver = v.id; kVersioni(); };
    box.appendChild(b);
  }
}
async function kSondaggio() {
  if (S.pagina !== "cam" || !K.info) return;  // i dati della pagina non sono ancora arrivati
  const st = await api().cam_stato();
  if (!st || st.errore) return;
  const prima = K.stato && K.stato.conn + K.stato.id;
  K.stato = st;
  const conn = $("#cam-conn");
  conn.className = "pillola " + ({ live: "", carica: "avviso", pal50: "errore", altro: "errore" }[st.conn] ?? "spento");
  conn.querySelector("span").textContent = t("conn_" + st.conn) + (st.id && st.conn === "live" ? " · " + ({ GK2E52: "USA", GK2P52: "UK", GK2I52: "ITA", GK2D52: "DE", GK2F52: "FR" }[st.id] || st.id) : "");
  $$("#cam-righe .cam-riga").forEach(r => r.classList.toggle("attiva", r.dataset.g === st.gruppo));
  $("#cam-adesso").textContent = st.gruppo ? t("g_" + st.gruppo) : "—";
  kVista(st.dati);
  if (prima !== st.conn + st.id) kVersioni();
  kAvviso();
}
const NOME_VER = { GK2E52: "USA", GK2P52: "UK", GK2I52: "ITA", GK2D52: "DE", GK2F52: "FR" };
function kSenzaCodice() {  // nessuna versione ha ancora il codice della camera: spiego e propongo i codici essenziali
  const box = $("#cam-senza");
  const mostra = K.info && !K.info.codice && K.sistema && K.sistema.dolphin;
  box.classList.toggle("nascosto", !mostra);
  if (!mostra || box.dataset.ok) return;
  box.dataset.ok = "1";
  box.innerHTML = `<svg><use href="#i-cam"/></svg><span>${t("cam_senza")}</span><button class="primario piccolo">${t("cod_ess_b")}</button>`;
  box.querySelector("button").onclick = async () => {
    const r = await api().codici_essenziali();
    if (!r || r.errore) { toast(t("errore"), errTesto(r && r.errore), "errore"); return; }
    if (!r.fatti.length) { toast(t("errore"), t("cam_senza_gioco"), "avviso", 6000); return; }
    toast(t("fatto"), t("cod_ess_ok", r.fatti.join(", ")), "", 6000);
    C.dati = null; Q.dati = null;
    const d = await api().cam_info(); if (d && !d.errore) K.info.codice = d.codice;
    delete box.dataset.ok; kSenzaCodice();
  };
}
function kAvvia() {  // gioco chiuso: "Avvia in finestra senza il codice camera" per regolare dal vivo
  const box = $("#cam-avvia"), s = K.sistema, st = K.stato || {};
  const mostra = K.info && s && s.dolphin && !s.dolphin_aperto && st.conn !== "live" && st.conn !== "carica";
  box.classList.toggle("nascosto", !mostra);
  if (!mostra) return;
  const dischi = ID_ORDINE.filter(g => K.info.dischi.includes(g)), b = $("#cam-avvia-btn"), sv = $("#cam-avvia-ver");
  const chiave = dischi.join() + K.ver;
  if (sv.dataset.k === chiave) return;  // niente da ridisegnare (gira ogni 120 ms)
  sv.dataset.k = chiave;
  if (!dischi.length) {  // nessun disco trovato: si aggiunge dal launcher
    box.querySelector("p").textContent = t("cam_avvia_nessuno");
    sv.innerHTML = "";
    b.querySelector("span").textContent = t("cam_avvia_vai");
    b.onclick = () => vaiA("gioca");
    return;
  }
  box.querySelector("p").textContent = t("cam_avvia_sub");
  if (!dischi.includes(K.ver)) K.ver = dischi[0];
  sv.innerHTML = dischi.length > 1 ? dischi.map(g => `<button data-g="${g}" class="${g === K.ver ? "attivo" : ""}">${NOME_VER[g]}</button>`).join("") : "";
  sv.querySelectorAll("button").forEach(x => x.onclick = () => { K.ver = x.dataset.g; api().imposta("cam_versione", K.ver); kVersioni(); kAvvia(); });
  b.querySelector("span").textContent = t("cam_avvia_btn", NOME_VER[K.ver] || K.ver);
  b.onclick = async () => {
    b.disabled = true;
    const r = await api().cam_avvia(K.ver);
    setTimeout(() => { b.disabled = false; }, 8000);
    if (!r || r.errore) { b.disabled = false; toast(t("errore"), r ? t(r.errore, r.disco || "") : "", "errore", 6000); return; }
    toast(t("gioca_avviato"), t(r.spento ? "cam_avviato" : "cam_avviato_senza"), "", 9000);
  };
}
function kGioco() {  // gioco aperto: in primo piano / schermo intero / chiudi, senza uscire dall'app
  const box = $("#cam-gioco"), s = K.sistema;
  const g = s && s.gioco, f = (s && s.finestra) || {};
  box.classList.toggle("nascosto", !g);
  if (!g) return;
  $("#cam-gioco-nome").textContent = t("cam_gioco_aperto", NOME_VER[g] || g);
  const so = $("#cam-sopra");
  so.checked = !!f.sopra;
  so.disabled = !!f.intero;
  so.onchange = async () => { await api().cam_sopra(so.checked); K.sis && K.sis(); };
  $("#cam-intero span").textContent = t(f.intero ? "cam_finestra" : "cam_intero");
  $("#cam-intero").onclick = async () => { await api().gioca_schermo_intero(); setTimeout(() => K.sis && K.sis(), 900); };
  $("#cam-chiudi").onclick = async () => { await api().gioca_chiudi(); toast(t("gioca_chiudi"), t("cam_chiudi_conf"), "", 5000); setTimeout(() => K.sis && K.sis(), 1500); };
}
function kAvviso() {
  kSenzaCodice();
  kAvvia();
  kGioco();
  const st = K.stato || {};
  let av = null;
  if (K.sistema && !K.sistema.dolphin) av = [t("err_dolphin"), null];
  else if (st.conn === "altro") av = [t("av_altro", st.id), null];
  else if (K.trucchi === false) av = [t("av_trucchi"), ["b_attiva", async () => {
    const r = await api().cam_trucchi();
    if (r && r.errore === "chiudi_dolphin") toast(t("errore"), t("trucchi_chiudi"), "avviso", 6000);
    else { K.trucchi = true; toast(t("fatto"), t("trucchi_ok")); kAvviso(); }
  }]];
  else if (st.conn === "pal50") av = [t("av_pal50"), ["b_patch", async () => {
    await api().cam_patch(st.id); toast(t("fatto"), t("patch_ok"), "avviso", 6000);
  }]];
  else if (st.conflitto) av = [t("av_conflitto2"), ["cam_riavvia_btn", async () => {
    toast(t("cam_riavvio_tit"), t("cam_riavvio"), "", 8000);
    const r = await api().cam_riavvia(st.id);
    if (!r || r.errore) { toast(t("errore"), r ? t(r.errore, r.disco || "") : "", "errore", 7000); return; }
    toast(t("gioca_avviato"), t("cam_avviato"), "", 9000);
  }]];
  const box = $("#cam-avviso");
  box.classList.toggle("nascosto", !av);
  if (!av) return;
  box.querySelector("span").textContent = "⚠  " + av[0];
  const b = box.querySelector("button");
  b.classList.toggle("nascosto", !av[1]);
  if (av[1]) { b.textContent = t(av[1][0]); b.onclick = av[1][1]; }
}
function kVista(d) {
  const svg = $("#cam-vista"), W = 520, Hh = 250, x0 = 40, y0 = 170, sc = (W - x0 - 16) / 8;
  let s = "";
  for (let m = 0; m <= 8; m += 2) {
    const x = x0 + m * sc;
    s += `<line x1="${x}" y1="12" x2="${x}" y2="${Hh - 26}" class="griglia-l"/><text x="${x}" y="${Hh - 8}" class="asse">${m ? m + " m" : "0"}</text>`;
  }
  s += `<line x1="${x0}" y1="${y0}" x2="${W - 6}" y2="${y0}" class="terra"/>`;
  s += `<use href="#ragno" x="${x0 - 16}" y="${y0 - 34}" width="32" height="32" class="ragnetto"/>`;
  if (!d) {
    s += `<text x="${W / 2 + 14}" y="${y0 - 70}" class="vuoto">${t("vista_vuota")}</text>`;
    ["#cam-n-voluta", "#cam-n-vera", "#cam-n-fov"].forEach(q => $(q).textContent = "—");
  } else {
    const pos = (h, v) => [Math.min(W - 10, x0 + h * sc), Math.max(10, Math.min(Hh - 30, y0 - v * sc))];
    for (const [k, cl] of [["min", "l-min"], ["des", "l-des"]]) { const x = Math.min(W - 8, x0 + d[k] * sc); s += `<line x1="${x}" y1="12" x2="${x}" y2="${Hh - 26}" class="${cl}"/>`; }
    const [xv, yv] = pos(...d.vera), [xo, yo] = pos(...d.voluta);
    s += `<line x1="${x0}" y1="${y0 - 14}" x2="${xv}" y2="${yv}" class="l-vera"/>`;
    s += `<circle cx="${xo}" cy="${yo}" r="8" class="c-voluta"/>`;
    s += `<g transform="translate(${xv},${yv})"><rect x="-11" y="-8" width="22" height="16" rx="3" class="c-vera"/><path d="M-11 0 L-19 -6 L-19 6 Z" class="c-vera"/><circle cx="4" cy="-1" r="3" class="obiettivo"/></g>`;
    $("#cam-n-voluta").textContent = d.voluta[0].toFixed(2) + " m";
    $("#cam-n-vera").textContent = Math.hypot(...d.vera).toFixed(2) + " m";
    $("#cam-n-fov").textContent = Math.round(d.fov) + "°";
  }
  svg.innerHTML = s;
}
function modale({ titolo, testo = "", campo = null, codice = null, bottoni, area = null, segnaposto = "", spunte = null }) {
  return new Promise(ok => {
    const m = $("#modale");
    m.querySelector("h3").textContent = titolo;
    m.querySelector("p").textContent = testo;
    const inp = m.querySelector("input"), pre = m.querySelector("pre");
    inp.classList.toggle("nascosto", campo === null); inp.value = campo || "";
    pre.classList.toggle("nascosto", !codice); pre.textContent = codice || "";
    inp.placeholder = segnaposto;
    const ta = m.querySelector("textarea"), sp = m.querySelector(".spunte");
    ta.classList.toggle("nascosto", area === null); ta.value = area || ""; ta.placeholder = "04123456 00000001\n04123460 3F800000";
    sp.classList.toggle("nascosto", !spunte);
    sp.innerHTML = spunte ? `<span>${t("cod_versioni")}</span>` + spunte.map(([id, et, on]) =>
      `<label class="spunta"><input type="checkbox" value="${id}" ${on ? "checked" : ""}><span></span><b>${et}</b></label>`).join("") : "";
    const box = m.querySelector(".bottoni");
    box.innerHTML = "";
    const chiudi = v => { m.classList.add("nascosto"); ok(v); };
    for (const [val, etich, primario] of bottoni) {
      const b = document.createElement("button");
      b.className = primario ? "primario" : "leggero";
      b.textContent = etich;
      b.onclick = () => chiudi(val === "campo" ? inp.value.trim() : val === "modulo" ?
        { campo: inp.value.trim(), area: ta.value, spunte: [...sp.querySelectorAll("input:checked")].map(x => x.value) } : val);
      box.appendChild(b);
    }
    m.onkeydown = e => { if (e.key === "Escape") chiudi(null); if (e.key === "Enter" && campo !== null && area === null && e.target === inp) chiudi(inp.value.trim()); };
    m.classList.remove("nascosto");
    setTimeout(() => (campo !== null ? inp : box.lastChild).focus(), 30);
  });
}
async function kSalvaCome() {
  const nome = await modale({ titolo: t("p_salva_come"), testo: t("nome_preset"), campo: "", bottoni: [[null, t("annulla")], ["campo", t("p_salva"), true]] });
  if (!nome) return;
  if (kTuttiPreset().some(p => p.fisso && p.nome === nome)) { toast(t("errore"), t("fisso"), "errore"); return; }
  if (K.info.utente[nome] && !(await modale({ titolo: t("p_salva"), testo: t("sovrascrivi", nome), bottoni: [[false, t("no")], [true, t("si"), true]] }))) return;
  const dati = { valori: K.valori, fov: Math.round(K.fov), min_uguale: K.minUguale };
  await api().cam_preset_salva(nome, dati);
  K.info.utente[nome] = dati; K.preset = "u:" + nome; K.rif = kIstantanea();
  kMenuPreset(); kInvia(); toast(t("fatto"), t("preset_salvato", nome), "", 2500);
}
async function kSalvaPreset() {
  if (!K.preset.startsWith("u:")) return kSalvaCome();
  const nome = K.preset.slice(2);
  const dati = { valori: K.valori, fov: Math.round(K.fov), min_uguale: K.minUguale };
  await api().cam_preset_salva(nome, dati);
  K.info.utente[nome] = dati; K.rif = kIstantanea(); kInvia(); toast(t("fatto"), t("preset_salvato", nome), "", 2500);
}
async function kRinomina() {
  if (!K.preset.startsWith("u:")) { toast(t("errore"), t("fisso"), "errore"); return; }
  const vecchio = K.preset.slice(2);
  const nome = await modale({ titolo: t("p_rinomina"), testo: t("nuovo_nome"), campo: vecchio, bottoni: [[null, t("annulla")], ["campo", t("p_rinomina"), true]] });
  if (!nome || nome === vecchio) return;
  if (K.info.utente[nome] || kTuttiPreset().some(p => p.fisso && p.nome === nome)) { toast(t("errore"), t("nome_usato"), "errore"); return; }
  const r = await api().cam_preset_rinomina(vecchio, nome);
  if (!r || r.errore) { toast(t("errore"), errTesto(r && r.errore), "errore"); return; }
  K.info.utente[nome] = K.info.utente[vecchio]; delete K.info.utente[vecchio];
  K.preset = "u:" + nome; kMenuPreset(); kInvia(); toast(t("fatto"), t("rinominato", nome), "", 2500);
}
async function kElimina() {
  if (!K.preset.startsWith("u:")) { toast(t("errore"), t("fisso"), "errore"); return; }
  const nome = K.preset.slice(2);
  if (!(await modale({ titolo: t("p_elimina"), testo: t("elimina_preset", nome), bottoni: [[false, t("no")], [true, t("si"), true]] }))) return;
  await api().cam_preset_elimina(nome);
  delete K.info.utente[nome];
  kCaricaPreset("f:migliorata"); kMenuPreset();
}
async function kEsporta() {
  const p = kTuttiPreset().find(x => x.chiave === K.preset);
  const f = await api().cam_esporta(p ? p.nome : "Spider-Cam", { valori: K.valori, fov: Math.round(K.fov), min_uguale: K.minUguale });
  if (f && !f.errore) toast(t("fatto"), f, "", 3000);
}
async function kImporta() {
  const r = await api().cam_importa();
  if (!r) return;
  if (r.errore) { toast(t("errore"), t("import_errore"), "errore"); return; }
  Object.assign(K.info.utente, r);
  kCaricaPreset("u:" + Object.keys(r)[0]); kMenuPreset();
  toast(t("fatto"), t("importati", Object.keys(r).join(", ")), "", 3500);
}
async function kVediCodice() {
  const testo = await api().cam_codice(kEffettivi(), Math.round(K.fov), K.ver);
  const r = await modale({ titolo: t("codice_tit", K.ver), testo: t("codice_nota"), codice: testo, bottoni: [[null, t("chiudi")], ["copia", t("copia"), true]] });
  if (r === "copia") { await api().copia_testo(testo); toast(t("copiato"), "", "", 2000); }
}
async function kSalvaGioco(silenzioso = false) {
  if (!K.info || $("#applica").disabled) return;  // Spider-Cam non ancora caricata (Ctrl+S appena aperta) o sta già salvando
  $("#applica").disabled = true;
  const tutte = K.tutte && kInstallate().length > 1 ? kInstallate() : null;
  const tua = kVariante() === "tua";
  const r = await api().cam_salva(kEffettivi(), Math.round(K.fov), K.ver, tutte, tua);
  $("#applica").disabled = false;
  if (!r || r.errore) { toast(t("errore"), errTesto(r && r.errore), "errore"); return; }
  if (r.errori.length) toast(t("errore"), r.errori.join(" · "), "errore", 8000);
  if (r.salvati.length) CC.tua = tua;
  if (r.salvati.length && silenzioso) { C.dati = null; return; }
  if (r.salvati.length) {
    toast(t("fatto"), t("cam_salvata", r.versioni.join(", "), r.righe) + (r.trucchi === false ? " " + t("av_trucchi") : ""), r.trucchi === false ? "avviso" : "", 7000);
    C.dati = null;  // la pagina codici si ricarica
  }
}
function piedeCam() {
  if (S.pagina !== "cam") return;
  if (!CC.modi.includes("classica")) {  // salva nel gioco = valori della migliorata: senza migliorata niente piede
    $("#modifiche").innerHTML = "";
    $("#piede").classList.add("nascondi-azioni");
    return;
  }
  $("#modifiche").innerHTML = `<div class="cam-salva-per"><span>${t("salva_per")}</span><div class="versioni" id="cam-versioni"></div>
    <button class="leggero" id="cam-codice">${t("vedi_codice")}</button></div>`;
  $("#cam-codice").onclick = kVediCodice;
  $("#piede").classList.remove("nascondi-azioni");
  $("#applica span").textContent = t("salva_gioco");
  $("#annulla").classList.add("nascosto");
  if (K.info) kVersioni();
}
function entraCam(si) {
  if (si) {
    if (!K.info) caricaCam().then(() => { api().cam_accendi(true); piedeCam(); });
    else { api().cam_accendi(true); kInvia(); }
    clearInterval(K.timer);
    K.timer = setInterval(kSondaggio, 120);
    clearInterval(K.sistema_t);
    const sis = async () => { const r = await api().cam_sistema(); if (r && !r.errore) { K.sistema = r; K.trucchi = r.trucchi; kAvviso(); } };
    K.sis = sis;
    sis(); K.sistema_t = setInterval(sis, 3000);
    ccCarica(); clearInterval(K.cc_t); K.cc_t = setInterval(ccCarica, 1000);  // R3 in gioco: "IN USO" segue la camera attiva
  } else {
    clearInterval(K.timer); clearInterval(K.sistema_t); clearInterval(K.cc_t);
    api().cam_accendi(false);
    $("#applica span").textContent = t("applica");
    $("#annulla").classList.remove("nascosto");
  }
}

// ================================================================ toast, fumetti
let tmToast;
function errTesto(e) {  // errore dall'app: chiave di testo nota -> il testo nella tua lingua; se no il messaggio grezzo (senza HTML)
  if (!e) return "";
  if (e === "dolphin") return t("err_dolphin");
  if (TESTI.it[e] !== undefined) return t(e);
  return String(e).replace(/[&<>]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
}
function toast(titolo, testo, tipo = "", ms = 4500) {
  const e = $("#toast");
  e.className = "visibile " + tipo;
  e.innerHTML = `<b>${titolo}</b>${testo}`;
  clearTimeout(tmToast);
  tmToast = setTimeout(() => e.className = tipo, ms);
}
function fumetti() {
  const tip = $("#tip");
  document.addEventListener("mouseover", e => {
    const el = e.target.closest("[data-tip]");
    if (!el) { tip.classList.remove("visibile"); return; }
    tip.textContent = t(el.dataset.tip);
    const r = el.getBoundingClientRect(), z = zoomPagina();  // con lo zoom per gli schermi piccoli i px della pagina sono più piccoli
    tip.style.left = (r.left + r.width / 2) / z - tip.offsetWidth / 2 + "px";
    tip.style.top = r.top / z - 34 + "px";
    tip.classList.add("visibile");
  });
}

// ================================================================ launcher: versioni trovate, mod attive, GIOCA
const Q = { dati: null, sel: null, viewer: null, skin: null, parte: false, tm: null, tab: "versioni", stati: null, statiGid: null, rev: -1,
  guida: false, cerco: false, lav: null, alt: false };  // alt = nel launcher mostro il costume alternativo (RB)
try { Q.alt = localStorage.getItem("gi_alt") === "1"; } catch (e) { /* niente */ }
async function caricaGioca(aggiorna = false) {
  if (!Q.viewer) {
    const m = await modelliSpidey();
    Q.viewer = new Viewer($("#c-gioca"), m.gioco, { ang: -0.35, alt: 0.12, dist: 3.3 });
    Q.viewer.usaModello("idle", m.idle);
    $("#gi-sagoma").classList.toggle("nascosto", !!MODELLI_SPIDEY);
    Q.viewer.auto = false;  // gira piano da solo (sotto), si trascina col mouse
    Q.viewer.avvia();
    setInterval(() => { if (S.pagina === "gioca" && !Q.viewer.trasc) Q.viewer.ang += 0.0018; }, 16);
  }
  giSkin();
  const r = await api().gioca_stato(aggiorna);
  if (!r || r.errore) { toast(t("errore"), errTesto(r && r.errore), "errore"); return; }
  Q.dati = r;
  const firma = JSON.stringify([r.dolphin, r.exe, Object.keys(r.giochi || {}).sort(), !!r.senza_mod]);
  if (Q.firma !== undefined ? Q.firma !== firma : !!r.dolphin !== !!(S.dati && S.dati.dolphin)) rinfrescaTutto();  // Dolphin installato, gioco trovato...: le altre pagine si rileggono
  Q.firma = firma;
  aggiornaNav();
  clearInterval(Q.tm);
  Q.tm = setInterval(async () => {  // Dolphin aperto? gioco in corso? (anche se l'hai aperto da Dolphin)
    if (S.pagina !== "gioca") return;
    const l = await api().gioca_live();
    if (!l || l.errore || !Q.dati) return;
    if (l.gioco) Q.parte = false;
    if (l.stati_rev !== Q.rev) { Q.rev = l.stati_rev; giStati(); }
    if (JSON.stringify(l.pad) !== JSON.stringify(Q.dati.pad)) { Q.dati.pad = l.pad; if (!Q.guida && giPronto(Q.dati)) disegnaGioca(); }  // controller collegato/staccato
    if (l.aperto !== Q.dati.aperto || l.gioco !== Q.dati.gioco) {
      if (l.gioco && Q.dati.giochi[l.gioco]) { Q.sel = l.gioco; Q.statiGid = null; }
      Q.statiChiesto = null;  // gioco aperto/chiuso: rileggo gli stati (la striscia "Parti dallo stato 1" torna)
      Q.dati.aperto = l.aperto; Q.dati.gioco = l.gioco; disegnaGioca();
    }
  }, 2000);
  const trovate = ID_ORDINE.filter(g => r.giochi[g]);
  if (r.gioco && r.giochi[r.gioco]) Q.sel = r.gioco;  // c'è una partita in corso: quella versione
  else if (!Q.sel || !r.giochi[Q.sel]) Q.sel = r.giochi[r.ultima] ? r.ultima : trovate[0] || null;
  disegnaGioca();
}
const ID_ORDINE = ["GK2E52", "GK2P52", "GK2I52", "GK2D52", "GK2F52"];
// Costume originale: non è dentro l'app, l'app lo prende dal disco del gioco di chi la usa (appena sa dov'è) e lo
// tiene in AppData. Finché non c'è, Spidey resta grigio.
async function texOriginale() {
  if (!S.orig) { const d = await api().skin_originale(); if (d && !d.errore) S.orig = d; }
  return S.orig || null;
}
async function modelloPronto() {  // chiamata da Python appena il modello 3D è stato ricostruito dal disco del gioco
  const m = await modelliSpidey(true);
  if (!MODELLI_SPIDEY) return;
  for (const v of [viewer, fotoViewer, Q.viewer]) if (v) v.ricarica(m);
  $("#gi-sagoma").classList.add("nascosto");
  if (S.dati && S.dati.skin) miniature();
}
function origPronta() {  // chiamata da Python appena il costume originale è stato preso dal gioco
  S.orig = null; Q.skin = null;
  if (S.pagina === "gioca") giSkin();
  else if (S.pagina === "skin" && S.dati) aggiornaPalco();
}
async function giSkin() {  // Spider-Man nella skin installata adesso (principale, o alternativa se scelta nel launcher)
  const a = Q.alt && S.inst.alternativa && S.inst.alternativa.path ? S.inst.alternativa : S.inst.primaria;
  if (Q.viewer && (!a || !a.path) && S.dati && !S.dati.pack && Q.skin !== "originale") {  // niente skin della mod: il costume originale del gioco
    const o = await texOriginale();
    await Q.viewer.texture(o);
    if (o) Q.skin = "originale";  // se non c'è ancora riprovo la prossima volta
    return;
  }
  if (!Q.viewer || !a || !a.path || Q.skin === a.path) return;
  Q.skin = a.path;
  if (!S.tex[a.path]) { const d = await api().texture(a.path, 1024, 512); if (d && !d.errore) S.tex[a.path] = d; }
  await Q.viewer.texture(S.tex[a.path]);
  if (S.pagina === "gioca") disegnaGioca();
}
function giChip(m, g) {
  if (!m.ini) return `<span class="gi-chip rosso">${t("m_no_mod")}</span>`;
  const c = [[m.texture, m.texture ? "m_texture" : m.hd_spente ? "m_hd_spente" : "m_texture_no"], [m.camera, "m_camera"], [m.fps60, "m_fps60"], [m.blur, "m_blur"]];
  if (m.hz60 !== null) c.push([m.hz60, m.hz60 ? "m_hz60" : "m_hz50"]);
  return c.filter(([ok, k]) => ok || k === "m_texture_no" || k === "m_hd_spente" || k === "m_hz50").map(([ok, k]) => `<span class="gi-chip ${ok ? "verde" : "giallo"}">${ok ? "✓ " : ""}${t(k)}</span>`).join("")
    + `<span class="gi-chip">${t("m_codici", m.codici)}</span>`;
}
const giModOk = d => ID_ORDINE.some(g => d.giochi[g] && d.mod[g] && d.mod[g].texture);
const giPreparato = d => ID_ORDINE.some(g => d.giochi[g] && d.mod[g] && d.mod[g].codici > 0);  // codici essenziali (+ tasti e grafica) messi
function giPronto(d) {  // c'è tutto per giocare: Dolphin, il gioco e il gioco preparato (codici/tasti/grafica) o la mod
  const tr = ID_ORDINE.filter(g => d.giochi[g]);
  return !!(d.dolphin && d.exe && tr.length && (giPreparato(d) || giModOk(d) || d.senza_mod));
}
function disegnaGioca() {
  if (!Q.dati) return;
  
  aggiornaTesta();
  giPadTondo(!(Q.guida || !giPronto(Q.dati)));
  giLbrb(!(Q.guida || !giPronto(Q.dati)));
  if (Q.guida || !giPronto(Q.dati)) { const ap = $("#gi-anteprima"); if (ap) ap.classList.add("nascosto"); disegnaGuida(); return; }
  const d = Q.dati, trovate = ID_ORDINE.filter(g => d.giochi[g]), mancano = ID_ORDINE.filter(g => !d.giochi[g]);
  const a = S.inst.primaria, v = a && S.dati.skin && voce(a.id), alt = S.inst.alternativa, va = alt && S.dati.skin && voce(alt.id);
  const sel = Q.sel && d.giochi[Q.sel], m = sel && d.mod[Q.sel];
  const blocco = !d.exe || !sel || d.aperto || Q.parte;
  const sm2 = d.gioco && d.gioco !== "?";  // Spider-Man 2 in corso (l'ID dice anche quale versione)
  const etich = Q.parte ? t("gioca_parte") : sm2 ? t("gioca_in_corso") : d.aperto ? t("gioca_dolphin_aperto") : t("gioca_bottone");
  const bandiera = sm2 && d.nomi[d.gioco] ? d.gioco : Q.sel;
  $("#gi-info").innerHTML = `<div class="gi-titolo"><span>SM2</span><b>ENHANCED</b></div>
    ${v ? (() => { const mostra = Q.alt && va, vv = mostra ? va : v, aa = mostra ? alt : a; return `<div class="gi-skin"><small>${t("gioca_skin")}</small><b>${vv.nome}</b>${nomeVariante(vv, aa.path) ? `<em>${nomeVariante(vv, aa.path)}</em>` : ""}
      <button class="link" id="gi-skin">${t("gioca_cambia_skin")} ›</button></div>`; })() : ""}
    <button class="gi-play ${sm2 ? "in-gioco" : ""} ${etich.length > 9 ? "lungo" : ""}" id="gi-play" ${blocco ? "disabled" : ""} ${PAD.pad ? `title="${t("gioca_pad")}"` : ""}><svg><use href="#i-play"/></svg>
      ${PAD.pad && !blocco ? `<kbd class="gi-a ${tastiMenu()[0] === "L1" ? "ps" : ""}">${tastiMenu()[0] === "L1" ? "✕" : "A"}</kbd>` : ""}
      <span><b>${etich}</b>${bandiera && d.nomi[bandiera] ? `<small><span class="band">${BANDIERE[bandiera]}</span>${d.nomi[bandiera]}${!sm2 && !d.aperto && d.da_stato && giStato1() ? " · " + t("gi_st1_corto") : ""}</small>` : ""}</span></button>
    ${giRiprendi(d, sm2)}${!sm2 && m && m.hd_spente ? `<div class="gi-hd-spente"><svg><use href="#i-immagine"/></svg>
      <span><b>${t("gi_hd_tit")}</b><small>${t("gi_hd_sub")}</small></span><button class="primario" id="gi-hd">${t("gi_hd_btn")}</button></div>` : ""}
    <div class="gi-opzioni">
      <label class="gi-solo"><span class="interruttore"><input type="checkbox" id="gi-solo" ${d.solo ? "checked" : ""}><span></span></span>
        <span><b>${t("gioca_solo")}</b><small>${t("gioca_solo_sub")}</small></span></label>
      <label class="gi-solo"><span class="interruttore"><input type="checkbox" id="gi-intero" ${d.intero ? "checked" : ""}><span></span></span>
        <span><b>${t("gioca_intero")}</b><small>${t("gioca_intero_sub")}</small></span></label>
      <label class="gi-solo"><span class="interruttore"><input type="checkbox" id="gi-fps" ${d.fps ? "checked" : ""}><span></span></span>
        <span><b>${t("gioca_fps")}</b><small>${t("gioca_fps_sub")}</small></span></label></div>
    ${sm2 ? `<div class="gi-avviso"><span>${t("gioca_in_corso_sub")}</span><div class="gi-azioni">
        <button class="leggero" id="gi-fs"><svg><use href="#i-schermo"/></svg>${t("gioca_fs")}</button>
        <button class="leggero" id="gi-cam"><svg><use href="#i-cam"/></svg>${t("gioca_cam").replace("-", "‑")}</button>
        <button class="leggero" id="gi-chiudi" title="${t("gioca_chiudi_sub")}"><svg><use href="#i-x"/></svg>${t("gioca_chiudi")}</button></div></div>`
      : d.aperto && !Q.parte ? `<div class="gi-avviso giallo"><span>${t(d.gioco === "?" ? "gioca_altro" : "gioca_aperto")}</span></div>` : ""}
    ${!d.trucchi && !d.aperto ? `<div class="gi-avviso"><span>${t("gioca_trucchi_off")}</span></div>` : ""}
    ${giLavora() ? `<div class="gi-avviso gi-agg-lav">${giProg(Q.lav)}</div>`
      : giAggiornamento(d) && !d.aperto ? `<div class="gi-avviso"><span>${t("gioca_agg", d.aggiornamento.versione, d.versione_dolphin.replace("Dolphin ", ""))}</span>
      ${d.dell_app ? `<button class="leggero" id="gi-agg">${t("gioca_agg_b")}</button>` : `<button class="leggero" data-link-esterno="https://dolphin-emu.org/download/">${t("ins_sito_dolphin")} ↗</button>`}</div>` : ""}
    ${appAggMostra(d.app_agg) && !sm2 ? `<div class="gi-avviso upd"><span>${t("upd_banner", d.app_agg.nuova.versione, d.app_agg.versione)}</span>
      <button class="leggero" id="gi-upd">${t(d.app_agg.da_sola ? "upd_aggiorna" : "upd_scarica")}${d.app_agg.da_sola ? "" : " ↗"}</button>
      <button class="link gi-upd-x" id="gi-upd-x" title="${t("upd_nascondi")}"><svg><use href="#i-x"/></svg></button></div>` : ""}
    <div class="gi-exe">${d.exe ? `<span title="${d.exe}">${d.versione_dolphin || t("gioca_exe")}</span><button class="link" id="gi-exe">${t("gioca_exe_cambia")}</button>${d.aperto ? "" : `<button class="link" id="gi-apri">${t("gioca_apri_dolphin")}</button>`}`
      : `<span class="no">${t("gioca_exe_no")}</span><button class="leggero" id="gi-exe">${t("gioca_exe_scegli")}</button>`}
      <button class="link" id="gi-come">${t("gu_come")}</button><button class="link" id="gi-comandi">${t("comandi")}</button></div>`;
  const nStati = Q.stati && Q.statiGid === Q.sel ? Q.stati.stati.length : null;
  const schede = `<div class="gi-schede ordine">${["versioni", "stati", "salv"].map(x => `<button data-tab="${x}" class="${Q.tab === x ? "attivo" : ""}">${t("st_tab_" + x)}${x === "stati" && sel ? ` · ${d.nomi[Q.sel]}${nStati ? ` <i>${nStati}</i>` : ""}` : ""}</button>`).join("")}</div>`;
  if (Q.tab === "stati") { $("#gi-lato").innerHTML = schede + `<div id="gi-stati"></div>`; giSchede(); disegnaStati(); }
  else if (Q.tab === "salv") { $("#gi-lato").innerHTML = schede + `<div id="gi-salv"></div>`; giSchede(); disegnaSalvataggi(); }
  else $("#gi-lato").innerHTML = schede + `<div class="gi-testa"><div><h3>${t("gioca_versioni")}</h3><p>${t("gioca_versioni_sub")}</p></div>
      <button class="leggero" id="gi-ricarica">${t("gioca_ricarica")}</button></div>
    ${!trovate.length ? `<div class="nota-sez">${t("gioca_nessuna")}</div>` : ""}
    ${Object.keys(d.persi || {}).length ? `<div class="gi-avviso giallo gi-persi"><span>${t("gioca_persi", Object.keys(d.persi).map(g => d.nomi[g]).join(", "))}</span>
      <div class="gi-azioni2"><button class="leggero" id="gi-persi-cerca">${t("gu_cerca")}</button><button class="leggero" id="gi-persi-scegli">${t("gu_scegli")}</button></div></div>` : ""}
    ${giAllineaTutte(d, trovate)}
    ${trovate.map(g => `<button class="gi-ver ${g === Q.sel ? "attivo" : ""}" data-g="${g}"><span class="band">${BANDIERE[g]}</span>
      <div class="gi-ver-t"><div><b>${d.nomi[g]}</b>${g === d.gioco ? `<em class="corso">● ${t("gioca_in_corso_badge")}</em>` : g === d.ultima ? `<em>${t("gioca_ultima")}</em>` : ""}</div><small title="${d.giochi[g].disco}">${d.giochi[g].file}</small>
        <div class="gi-chips">${giChip(d.mod[g], g)}</div></div>
      ${giVerDestra(d, g)}</button>`).join("")}
    ${trovate.length && mancano.length ? `<p class="nota gi-mancano">${t("gioca_mancano", mancano.map(g => d.nomi[g]).join(", "))}
      <button class="link" id="gi-m-cerca">${t("gu_cerca")}</button> · <button class="link" id="gi-m-scegli">${t("gu_scegli")}</button></p>` : ""}`;
  $("#gi-play").onclick = () => giocaVia();
  $("#gi-play").disabled = giLavora();  // Dolphin a metà aggiornamento: non si parte
  const gat = $("#gi-allinea-tutte"); if (gat) gat.onclick = () => giAllineaTutteVia(gat);
  const gmc = $("#gi-m-cerca"); if (gmc) { gmc.onclick = giCercaGiochi; $("#gi-m-scegli").onclick = giScegliGioco; }
  const gpc = $("#gi-persi-cerca"); if (gpc) { gpc.onclick = giCercaGiochi; $("#gi-persi-scegli").onclick = giScegliGioco; }
  const gs = $("#gi-stato");
  if (gs) gs.onchange = () => { Q.dati.da_stato = gs.checked; api().imposta("gioca_da_stato", gs.checked); disegnaGioca(); };
  if (Q.sel && Q.statiGid !== Q.sel && Q.statiChiesto !== Q.sel) { Q.statiChiesto = Q.sel; giStati(); }  // per la striscia dello stato 1
  $("#gi-solo").onchange = e => { Q.dati.solo = e.target.checked; api().imposta("gioca_solo", Q.dati.solo); };
  $("#gi-intero").onchange = e => { Q.dati.intero = e.target.checked; api().imposta("gioca_intero", Q.dati.intero); G.dati = null; };
  $("#gi-fps").onchange = async e => {
    const on = e.target.checked, r = await api().gioca_fps(on);
    if (!r || r.errore) { e.target.checked = !on; toast(t("errore"), errTesto(r && r.errore), "errore"); return; }
    Q.dati.fps = on; G.dati = null;
    if (r.dolphin_aperto) toast(t("gioca_fps"), t("gioca_fps_prossimo"), "avviso", 4000);
  };
  $("#gi-come").onclick = () => { Q.guida = true; disegnaGioca(); };
  $("#gi-comandi").onclick = apriComandi;
  $$("#gi-info [data-link-esterno]").forEach(b => b.onclick = () => api().apri_link(b.dataset.linkEsterno));
  const up = $("#gi-upd"); if (up) up.onclick = () => appAggiorna(d.app_agg);
  const ux = $("#gi-upd-x"); if (ux) ux.onclick = async () => { await api().app_agg_nascondi(d.app_agg.nuova.versione); d.app_agg.nascosta = d.app_agg.nuova.versione; disegnaGioca(); };
  const ag = $("#gi-agg"); if (ag) ag.onclick = async () => {
    if (!(await modale({ titolo: t("gioca_agg_tit", d.aggiornamento.versione), testo: t("gioca_agg_testo"),
      bottoni: [[false, t("annulla")], [true, t("gioca_agg_b"), true]] }))) return;
    giInstallaDolphin();
  };
  const ap = $("#gi-apri"); if (ap) ap.onclick = async () => { const r = await api().gioca_apri_dolphin(); if (r && r.errore) toast(t("errore"), errTesto(r.errore), "errore"); };
  const ch = $("#gi-chiudi"); if (ch) ch.onclick = () => api().gioca_chiudi();
  const fs = $("#gi-fs"); if (fs) fs.onclick = async () => { if (!(await api().gioca_schermo_intero())) toast(t("errore"), t("gioca_fs_no"), "errore"); };
  $("#gi-exe").onclick = async () => {
    const r = await api().gioca_scegli_exe();
    if (r && r.errore) toast(t("errore"), errTesto(r.errore), "errore"); else if (r) { Q.dati.exe = r; disegnaGioca(); }
  };
  const sk = $("#gi-skin"); if (sk) sk.onclick = () => vaiA("skin");
  // anteprima del costume alternativo: piccola, sotto lo Spidey 3D (cambia solo il disegno del launcher, non il gioco)
  const giAnt = $("#gi-anteprima");
  if (giAnt) {
    giAnt.classList.toggle("nascosto", !(v && va));
    const mostra = !!(Q.alt && va);
    giAnt.innerHTML = v && va ? `<span class="et" title="${t("gioca_look_tip")}"><svg><use href="#i-occhio"/></svg>${t("gioca_look")}</span>
      <button data-gi-look="0" class="${mostra ? "" : "attivo"}">${t("gioca_look_pri")}</button><button data-gi-look="1" class="${mostra ? "attivo" : ""}"
        title="${t("gioca_look_alt_tip", tastiMenu()[0] === "L1" ? "R1" : "RB")}">${t("gioca_look_alt")}</button>` : "";
  }
  $$("[data-gi-look]").forEach(b => b.onclick = () => {  // principale / alternativo sullo Spidey del launcher
    Q.alt = b.dataset.giLook === "1";
    try { localStorage.setItem("gi_alt", Q.alt ? "1" : "0"); } catch (e) { /* niente */ }
    Q.skin = null; giSkin(); disegnaGioca();
  });
  const cm = $("#gi-cam"); if (cm) cm.onclick = () => vaiA("cam");
  giSchede();
  if (Q.tab === "stati") { if (Q.statiGid !== Q.sel) giStati(); return; }
  if (Q.tab === "salv") return;
  $("#gi-ricarica").onclick = () => caricaGioca(true);
  $$("#gi-lato .gi-ver").forEach(b => {
    b.onclick = e => {
      const al = e.target.closest("[data-allinea]");
      if (al) { giAllinea(b.dataset.g, al.dataset.allinea, al); return; }
      if (e.target.closest("[data-inst]")) { vaiA("installa"); return; }
      Q.sel = b.dataset.g; disegnaGioca();
    };
    b.oncontextmenu = e => { e.preventDefault(); Q.sel = b.dataset.g; Q.tab = "stati"; disegnaGioca(); };
    b.ondblclick = e => { if (!e.target.closest("[data-inst], [data-allinea]")) { Q.sel = b.dataset.g; giocaVia(); } };
  });
}
// controller e tastiera nel launcher: ↑↓ = versione, A / Invio = gioca (solo con l'app in primo piano)
function giMuovi(dir) {
  const tr = ID_ORDINE.filter(g => Q.dati && Q.dati.giochi[g]);
  if (!tr.length || Q.tab !== "versioni") return;
  Q.sel = tr[(Math.max(0, tr.indexOf(Q.sel)) + dir + tr.length) % tr.length];
  disegnaGioca();
  const b = document.querySelector(`.gi-ver[data-g="${Q.sel}"]`); if (b) b.scrollIntoView({ block: "nearest", behavior: "smooth" });
}
const PAD = { prima: [], pad: false };
function giPad() {
  requestAnimationFrame(giPad);
  if (window.giocoAperto && !document.hasFocus()) return;  // mentre giochi il pad serve al gioco, non al launcher
  const p = [...(navigator.getGamepads ? navigator.getGamepads() : [])].find(x => x && x.connected);
  if (!!p !== PAD.pad) { PAD.pad = !!p; if (S.pagina === "gioca" && Q.dati) disegnaGioca(); }
  if (!p) return;
  const ora = p.buttons.map(b => b.pressed), premuto = i => ora[i] && !PAD.prima[i];
  const asse = p.axes[1] || 0;
  ora[100] = asse < -0.6; ora[101] = asse > 0.6;  // stick sinistro su / giù
  // i tasti li gestisce pad.js (tutta l'app col controller): qui solo se c'è un pad, per il bollino A su GIOCA
  PAD.prima = ora;
}
requestAnimationFrame(giPad);
document.addEventListener("keydown", e => {
  const el = e.target instanceof Element ? e.target : document.body;
  // con una finestrella aperta (comandi, menu in gioco, crediti...) frecce e Invio sono suoi: prima cambiavano la
  // versione dietro e Invio avviava il gioco
  const sopra = typeof pnRadice === "function" ? pnRadice() !== document.body : !$("#modale").classList.contains("nascosto");
  if (S.pagina !== "gioca" || !Q.dati || el.closest("input, textarea") || sopra) return;
  if (e.key === "ArrowUp" || e.key === "ArrowDown") { e.preventDefault(); giMuovi(e.key === "ArrowUp" ? -1 : 1); }
  else if (e.key === "Enter" && (el === document.body || el.closest(".gi-ver, #gi-play"))) { e.preventDefault(); giocaVia(); }
});
// ---- aggiornamenti dell'app (manifesto online, vedi core.ultima_app)
function appAggMostra(a) { return !!(a && a.nuova && a.nascosta !== a.nuova.versione); }
function appAggNote(a) {  // le novità nella lingua dell'app (o in inglese / la prima che c'è)
  const n = (a.nuova && a.nuova.note) || {}, righe = n[L] || n.en || n.it || Object.values(n)[0] || [];
  return righe.length ? "\n\n" + righe.map(r => "• " + r).join("\n") : "";
}
async function appAggiorna(a) {
  if (!a || !a.nuova) return;
  const v = a.nuova.versione;
  if (!a.da_sola) {  // da Python o senza file diretto: la pagina da cui scaricarla
    const ok = await modale({ titolo: t("upd_tit", v), testo: t("upd_testo_pagina") + appAggNote(a), bottoni: [[false, t("annulla")], [true, t("upd_scarica") + " ↗", true]] });
    if (ok && a.nuova.pagina) api().apri_link(a.nuova.pagina);
    return;
  }
  if (Q.dati && Q.dati.gioco) { toast(t("upd_tit", v), t("upd_gioco"), "avviso", 6000); return; }
  if (!(await modale({ titolo: t("upd_tit", v), testo: t("upd_testo_sola") + appAggNote(a), bottoni: [[false, t("annulla")], [true, t("upd_aggiorna"), true]] }))) return;
  const r = await api().app_agg_scarica();
  if (!r || r.errore) { toast(t("errore"), errTesto(r && r.errore), "errore"); return; }
  const box = $("#lavoro");  // stesso pannellino della compressione texture
  box.classList.remove("nascosto");
  box.querySelector("b").textContent = t("upd_scarico", v);
  box.querySelector("button").textContent = t("annulla");
  box.querySelector("button").onclick = () => api().app_agg_annulla();
  const st = await new Promise(fine => {
    const tm = setInterval(async () => {
      const x = await api().app_agg_avanzamento();
      if (!x) return;
      box.querySelector("small").textContent = x.totale ? Math.round(x.fatti / x.totale * 100) + "%" : (x.fatti / 1048576).toFixed(1) + " MB";
      box.querySelector(".barra i").style.width = (x.totale ? x.fatti / x.totale * 100 : 5) + "%";
      if (x.finito) { clearInterval(tm); fine(x); }
    }, 400);
  });
  setTimeout(() => box.classList.add("nascosto"), 400);
  if (st.errore) { if (st.errore !== "RuntimeError: annullato") toast(t("errore"), errTesto(st.errore), "errore", 8000); return; }
  appAggPronta(v);
}
async function appAggPronta(v) {
  if (!(await modale({ titolo: t("upd_pronta_tit", v), testo: t("upd_pronta"), bottoni: [[false, t("upd_dopo")], [true, t("upd_riavvia"), true]] }))) {
    toast(t("upd_pronta_tit", v), t("upd_dopo_sub"), "", 5000); return;
  }
  const r = await api().app_agg_applica();
  if (!r || r.errore) toast(t("errore"), errTesto(r && r.errore), "errore", 8000);
}
// ---- primo avvio / "Come funziona": cos'è, cosa serve, 3 passi (Dolphin, gioco, mod)
// Versione aggiunta dopo (su un PC di prova c'era solo ITA, poi la USA): "Copia da ITA" la porta alla
// pari dell'ultima giocata (o di quella più completa): texture, codici, grafica, camera, ora (api versione_allinea)
function giModello(d, escludi) {
  const pronte = ID_ORDINE.filter(g => g !== escludi && d.giochi[g] && d.mod[g] && d.mod[g].ini);
  if (!pronte.length) return null;
  if (pronte.includes(d.ultima)) return d.ultima;
  return pronte.sort((a, b) => (+!!d.mod[b].texture - +!!d.mod[a].texture) || ((d.mod[b].codici || 0) - (d.mod[a].codici || 0)))[0];
}
function giIndietro(d, g) {  // versione da cui copiare se g è indietro, se no null
  const m = d.mod[g] || {}, src = giModello(d, g), s = src && d.mod[src];
  return s && (!m.ini || (s.texture && !m.texture) || (m.codici || 0) < (s.codici || 0) || (s.salv && !m.salv)) ? src : null;
}
function giVerDestra(d, g) {
  const m = d.mod[g] || {}, src = giIndietro(d, g);
  if (src) return `<span class="leggero gi-inst" data-allinea="${src}" title="${t("gioca_allinea_tip", d.nomi[src])}">${t("gioca_allinea", d.nomi[src])}</span>`;
  return m.ini ? `<svg class="spunta"><use href="#i-ok"/></svg>` : `<span class="leggero gi-inst" data-inst>${t("gioca_installa")}</span>`;
}
// Più versioni indietro: una striscia "Copia da ITA in tutte" (John: le aveva dovute premere una per una)
function giAllineaTutte(d, trovate) {
  const m = giModello(d, null), dietro = m ? trovate.filter(g => g !== m && giIndietro(d, g) === m) : [];
  if (dietro.length < 2) return "";
  return `<div class="gi-avviso gi-allinea-tutte"><span>${t("gioca_allinea_tutte_sub", dietro.map(g => d.nomi[g]).join(", "), d.nomi[m])}</span>
    <button class="leggero" id="gi-allinea-tutte" data-da="${m}" data-gid="${dietro.join(",")}">${t("gioca_allinea_tutte", d.nomi[m])}</button></div>`;
}
async function giAllineaTutteVia(b) {
  if (b.disabled) return;
  const da = b.dataset.da, lista = b.dataset.gid.split(","), fatte = [];
  let salv = null;
  b.disabled = true;
  for (const [i, g] of lista.entries()) {
    b.innerHTML = `<span class="rotella piccola"></span>${Q.dati.nomi[g]} · ${i + 1}/${lista.length}`;
    const r = await api().versione_allinea(g, da);
    if (!r || r.errore) { toast(t("errore"), `${Q.dati.nomi[g]}: ${errTesto(r && r.errore)}`, "errore", 7000); break; }
    if (r.salvataggio === "chiedi") r.salvataggio = await giChiediSalv(r, da, g) ? ((await api().salvataggio_copia(da, g, true)) || {}).esito || "errore" : "tenuto";
    fatte.push(Q.dati.nomi[g]); salv = r.salvataggio;
  }
  if (fatte.length) toast(t("gioca_allinea_ok", fatte.join(", "), Q.dati.nomi[da]), t("gioca_allinea_ok_sub") + giAllineaSalv(salv), "", 7000);
  C.dati = null; G.dati = null; T.dati = null;
  await caricaGioca(true);
}
function giAllineaSalv(s) {  // com'è andata col salvataggio (copia_salvataggio)
  return s === "copiato" ? " " + t("gioca_allinea_salv") : s === "dolphin" ? " " + t("gioca_allinea_salv_no")
    : s === "tenuto" ? " " + t("gioca_allinea_salv_tenuto") : "";
}
// ---- salvataggi della memory card (scheda "Salvataggi"): percentuale, tempo, punti; copia tra versioni (John: copiando da
// ITA a USA deve chiedere se lì c'è già un salvataggio, e poterlo fare anche dopo)
function svTempo(s) { const h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60); return h ? `${h} h ${m} min` : `${m} min`; }
function svPc(p) { return p == null ? "—" : p.toLocaleString(L, { maximumFractionDigits: 2 }) + "%"; }
function svRiassunto(slot) { return (slot || []).map(x => `${x.nome} · ${svPc(x.percento)} · ${svTempo(x.tempo)}`).join(" / ") || "?"; }
async function giChiediSalv(info, da, a, altre = 0) {
  // altre = versioni ancora da fare in "Tutte le versioni": in più "Sostituisci in tutte" (risponde "tutte")
  const n = Q.dati.nomi;
  const r = await modale({ titolo: t("sv_chiedi_tit", n[a]), testo: t("sv_chiedi", n[a], svRiassunto(info.salv_qui), n[da], svRiassunto(info.salv_da)),
    bottoni: [[false, t("sv_tieni", n[a])], [true, t("sv_sostituisci"), true], ...(altre ? [["tutte", t("sv_sostituisci_tutte"), true]] : [])] });
  return altre ? r : !!r;
}
async function giCopiaSalv(da, a) {
  let r = await api().salvataggio_copia(da, a, false);
  if (r && r.chiedi) {
    if (!(await giChiediSalv(r, da, a))) return;
    r = await api().salvataggio_copia(da, a, true);
  }
  if (!r || r.errore) { toast(t("errore"), errTesto(r && r.errore), "errore", 7000); return; }
  toast(t("sv_copiato", Q.dati.nomi[da], Q.dati.nomi[a]), t(r.esito === "uguale" ? "sv_uguale" : "sv_copiato_sub"), "", 6000);
  Q.salv = null; await caricaGioca(true);
}
async function giCopiaSalvTutte(da, altre) {
  // una dopo l'altra; dove c'è già un salvataggio diverso chiede per quella versione (Tieni / Sostituisci)
  const n = Q.dati.nomi, fatte = [], tenute = [];
  let tutteSi = false;
  for (const [i, a] of altre.entries()) {
    let r = await api().salvataggio_copia(da, a, tutteSi);
    if (r && r.chiedi) {
      const sc = await giChiediSalv(r, da, a, altre.length - 1 - i);
      if (sc === "tutte") tutteSi = true;
      else if (!sc) { tenute.push(n[a]); continue; }
      r = await api().salvataggio_copia(da, a, true);
    }
    if (!r || r.errore) { toast(t("errore"), errTesto(r && r.errore), "errore", 7000); break; }
    fatte.push(n[a]);
  }
  if (fatte.length) toast(t("sv_copiato_tutte", n[da], fatte.join(", ")), t("sv_copiato_sub") + (tenute.length ? " " + t("sv_tenuti", tenute.join(", ")) : ""), "", 7000);
  Q.salv = null; await caricaGioca(true);
}
async function disegnaSalvataggi() {
  const box = $("#gi-salv");
  if (!box) return;
  if (!Q.salv) box.innerHTML = `<div class="nota-sez"><span class="rotella piccola"></span></div>`;
  const r = await api().salvataggi_stato();
  if (!$("#gi-salv")) return;
  if (!r || r.errore) { box.innerHTML = `<div class="nota-sez">${errTesto(r && r.errore)}</div>`; return; }
  Q.salv = r;
  const data = d => d ? new Date(d.replace(" ", "T")).toLocaleDateString(L, { day: "numeric", month: "short", year: "numeric" }) : "";
  const conDisco = r.versioni.filter(v => v.disco).map(v => v.gid);
  box.innerHTML = `<div class="gi-testa"><div><h3>${t("sv_tit")}</h3><p>${t("sv_sub")}</p></div></div>
    ${r.dolphin_aperto ? `<div class="gi-avviso giallo"><span>${t("salv_dolphin_aperto")}</span></div>` : ""}
    ${r.versioni.map(v => `<div class="sv-ver"><div class="sv-testa"><span class="band">${BANDIERE[v.gid]}</span><b>${v.nome}</b>
        <span class="spazio"></span>${v.file ? `<button class="link" data-sv-mostra="${v.gid}">${t("sv_cartella")}</button>` : ""}
        ${v.slot.length && conDisco.some(g => g !== v.gid) ? `<button class="leggero mini" data-sv-copia="${v.gid}">${t("sv_copia")}</button>` : ""}</div>
      ${v.slot.length ? v.slot.map(x => `<div class="sv-slot"><div class="sv-nome"><b></b><small>${t("sv_casella", x.slot)}${x.data ? " · " + data(x.data) : ""}</small></div>
          <div class="sv-pc"><b>${svPc(x.percento)}</b><div class="barra"><i style="width:${Math.min(100, x.percento || 0)}%"></i></div></div>
          <div class="sv-info"><span>⏱ ${svTempo(x.tempo)}</span><span>★ ${x.punti.toLocaleString(L)}</span></div></div>`).join("")
        : `<div class="sv-vuoto">${t("sv_nessuno")}</div>`}</div>`).join("")}`;
  const schede = box.querySelectorAll(".sv-ver");
  r.versioni.forEach((v, j) => v.slot.forEach((x, i) => {  // nome della casella come testo (viene dal file)
    const el = schede[j].querySelectorAll(".sv-nome b")[i]; if (el) el.textContent = x.nome; }));
  $$("#gi-salv [data-sv-mostra]").forEach(b => b.onclick = () => api().mostra_file(r.versioni.find(v => v.gid === b.dataset.svMostra).file));
  $$("#gi-salv [data-sv-copia]").forEach(b => b.onclick = async () => {
    const da = b.dataset.svCopia, n = Q.dati.nomi;
    const altre = conDisco.filter(g => g !== da);  // John: anche "tutte le versioni" invece di sceglierle una per una
    const a = await modale({ titolo: t("sv_copia_dove", n[da]), testo: t("sv_copia_dove_sub"),
      bottoni: [[null, t("annulla")], ...altre.map(g => [g, n[g], true]), ...(altre.length > 1 ? [["*", t("sv_tutte"), true]] : [])] });
    if (a === "*") giCopiaSalvTutte(da, altre);
    else if (a) giCopiaSalv(da, a);
  });
}
async function giAllinea(g, da, el) {
  if (el.classList.contains("lavoro")) return;
  el.classList.add("lavoro"); el.innerHTML = `<span class="rotella piccola"></span>${t("gioca_allinea", Q.dati.nomi[da])}`;
  const r = await api().versione_allinea(g, da);
  if (!r || r.errore) { toast(t("errore"), errTesto(r && r.errore), "errore", 7000); await caricaGioca(true); return; }
  if (r.salvataggio === "chiedi") r.salvataggio = await giChiediSalv(r, da, g) ? ((await api().salvataggio_copia(da, g, true)) || {}).esito || "errore" : "tenuto";
  toast(t("gioca_allinea_ok", r.a, r.da), t("gioca_allinea_ok_sub") + giAllineaSalv(r.salvataggio) + (r.dolphin_aperto ? " " + t("riavvia") : ""), "", 7000);
  C.dati = null; G.dati = null; T.dati = null;
  Q.sel = g; await caricaGioca(true);
}
function giAggiornamento(d) {
  // versioni di Dolphin: "2609", correzioni rapide "2609a" (John: c'era la 2609a e l'app non diceva niente: voleva solo numeri)
  const a = d.aggiornamento, v = (d.versione_dolphin || "").replace("Dolphin ", "").trim();
  const n = x => { const m = /^(\d+)([a-z]?)$/i.exec(String(x || "").trim()); return m ? [+m[1], m[2].toLowerCase()] : null; };
  const nv = n(v), na = a && n(a.versione);
  return !!(nv && na && (na[0] > nv[0] || (na[0] === nv[0] && na[1] > nv[1])));
}
function disegnaGuida() {
  const d = Q.dati, trovate = ID_ORDINE.filter(g => d.giochi[g]), lav = Q.lav;
  const ok1 = !!(d.dolphin && d.exe), ok2 = trovate.length > 0, ok3 = ok1 && ok2 && giPreparato(d), ok4 = ok1 && giModOk(d);
  // John: due gruppi, così si capisce subito cosa resta nel gioco (codici e file in Dolphin: anche senza l'app e nella mod
  // esportata) e cosa c'è solo mentre l'app è aperta (i fili in sottofondo di spidey_app: menu, ragnatele, camera dal vivo, stati)
  const nelGioco = [["i-immagine", "gu_v1"], ["i-schermo", "gu_v2"], ["i-cam", "gu_v7"], ["i-fulmine", "gu_v8"], ["i-combo", "gu_v6"], ["i-esporta", "gu_v5"]];
  const conApp = [["i-stella-piena", "gu_a1"], ["i-skin", "gu_a2"], ["i-cam", "gu_a3"], ["i-salva", "gu_v4"]];
  const gruppo = (cls, tit, sub, voci) => `<div class="gi-gruppo ${cls}"><div class="gi-gr-testa"><b>${t(tit)}</b><small>${t(sub)}</small></div>
    <ul class="gi-vantaggi">${voci.map(([i, k]) => `<li><svg><use href="#${i}"/></svg>${t(k)}</li>`).join("")}</ul></div>`;
  $("#gi-info").innerHTML = `<div class="gi-titolo"><span>SM2</span><b>ENHANCED</b></div>
    <p class="gi-tagline">${t("gu_tagline")}</p>
    <p class="gi-avviso-fan">${t("avviso_fan")}</p>
    ${gruppo("gioco", "gu_g_gioco", "gu_g_gioco_sub", nelGioco)}${gruppo("app", "gu_g_app", "gu_g_app_sub", conApp)}`;  // "Cosa serve" sta a destra, sotto il titolo dei passi
  const prog = lav && !lav.finito ? giProg(lav) : lav && lav.errore ? `<p class="avviso">${lav.errore}</p>` : "";
  const passo = (n, ok, tit, sub, corpo) => `<div class="gu-passo ${ok ? "ok" : ""}"><div class="gu-num">${ok ? `<svg><use href="#i-ok"/></svg>` : n}</div>
    <div class="gu-corpo"><h4>${t(tit)}</h4><p>${t(sub)}</p>${corpo}</div></div>`;
  const p1 = ok1 ? `<div class="gu-stato">✓ ${t("gu_p1_ok", d.versione_dolphin || "Dolphin")}</div>`
    : `${d.exe && !d.dolphin ? `<p class="gu-nota">${t("gu_p1_mai_aperto")}</p>` : ""}${prog}
       <div class="gu-bottoni"><button class="primario" id="gu-installa" ${lav && !lav.finito ? "disabled" : ""}><svg><use href="#i-scarica"/></svg>${t("gu_p1_installa")}</button>
         <button class="leggero" id="gu-mio">${t("gu_p1_mio")}</button>${d.exe && !d.dolphin ? `<button class="leggero" id="gu-ricontrolla">${t("gu_ricontrolla")}</button>` : ""}</div>`;
  const p2 = (ok2 ? `<div class="gu-stato">✓ ${trovate.map(g => `<span class="band">${BANDIERE[g]}</span>${d.nomi[g]}`).join(" ")}</div>` : "")
    + (Q.cerco ? `<div class="gu-stato cerco"><div class="rotella"></div>${t("gu_cerco")}</div>`
       : `<div class="gu-bottoni"><button class="${ok2 ? "leggero" : "primario"}" id="gu-cerca"><svg><use href="#i-cerca"/></svg>${t("gu_cerca")}</button>
          <button class="leggero" id="gu-scegli">${t("gu_scegli")}</button></div>`);
  const p3 = ok3 ? `<div class="gu-stato">✓ ${t("gu_p3_ok")}</div>`  // codici essenziali + profilo tasti + grafica consigliata, niente da scaricare
    : `<div class="gu-bottoni"><button class="primario" id="gu-prepara" ${ok1 && ok2 ? "" : "disabled"}><svg><use href="#i-fulmine"/></svg>${t("gu_p3_vai")}</button></div>`;
  const p4 = ok4 ? `<div class="gu-stato">✓ ${t("gu_p4_ok")}</div>`
    : `<div class="gu-bottoni"><button class="${ok3 ? "primario" : "leggero"}" id="gu-mod" ${ok1 ? "" : "disabled"}>${t("gu_p4_vai")} →</button></div>`;
  $("#gi-lato").innerHTML = `<div class="gi-guida"><h3>${ok3 && ok2 ? t("gu_pronto") : t("gu_titolo")}</h3><p class="gu-sub">${t("gu_sub")}</p><p class="gu-serve"><b>${t("gu_serve")}:</b> ${t("gu_serve_testo")}</p>
    ${passo(1, ok1, "gu_p1", "gu_p1_sub", p1)}${passo(2, ok2, "gu_p2", "gu_p2_sub", p2)}${passo(3, ok3, "gu_p3", "gu_p3_sub", p3)}<div class="gu-facoltativo">${passo(4, ok4, "gu_p4", "gu_p4_sub", p4)}</div>
    ${ok3 && ok2 ? `<p class="gu-consiglio">💡 ${t("gu_consiglio", t("gr_p_fhd"))} <button class="link" id="gu-grafica">${t("nav_grafica")} →</button></p>` : ""}
    <button class="gi-play piccolo" id="gu-gioca" ${giPronto(d) ? "" : "disabled"}><svg><use href="#i-play"/></svg><span><b>${giPronto(d) ? t("gu_al_launcher") : t("gioca_bottone")}</b></span></button></div>`;
  const on = (id, fn) => { const b = $("#" + id); if (b) b.onclick = fn; };
  on("gu-installa", giInstallaDolphin);
  on("gu-mio", async () => { const r = await api().gioca_scegli_exe(); if (r && r.errore) toast(t("errore"), errTesto(r.errore), "errore"); else if (r) caricaGioca(true); });
  on("gu-ricontrolla", () => caricaGioca(true));
  on("gu-mod", () => vaiA("installa"));
  on("gu-prepara", async () => {  // un clic: codici essenziali, tasti del controller e grafica consigliata in tutte le versioni che hai
    const b = $("#gu-prepara"); b.disabled = true; b.innerHTML = `<span class="rotella piccola"></span>${t("gu_p3_vai")}`;
    const r = await api().codici_essenziali();
    if (!r || r.errore) { toast(t("errore"), errTesto(r && r.errore), "errore"); await caricaGioca(true); return; }
    toast(t("gu_p3_fatto"), t("gu_p3_fatto_sub", r.fatti.join(", ")), "", 6000);
    C.dati = null; G.dati = null; X.dati = null; Q.guida = true; await caricaGioca(true);  // resto nella guida: c'è il passo delle mod grafiche
  });
  on("gu-grafica", () => vaiA("grafica"));
  on("gu-gioca", () => { Q.guida = false; disegnaGioca(); });
  on("gu-cerca", giCercaGiochi);
  on("gu-scegli", giScegliGioco);
}
async function giCercaGiochi() {
  Q.cerco = true; disegnaGioca();
  const r = await api().gioca_cerca_giochi();
  Q.cerco = false;
  await caricaGioca(true);
  if (r && !r.errore) toast(r.trovati.length ? t("gu_trovati", r.trovati.map(g => Q.dati.nomi[g]).join(", ")) : t("gu_non_trovato"), "", r.trovati.length ? "" : "avviso", 4500);
}
async function giScegliGioco() {
  const r = await api().gioca_aggiungi_gioco();
  if (!r || r.errore) return;
  await caricaGioca(true);
  if (r.trovati.length) toast(t("gu_trovati", r.trovati.map(g => Q.dati.nomi[g]).join(", ")), "", "", 4000);
  if (r.altri.length) toast(t("errore"), t("gu_non_sm2", r.altri.join(", ")), "avviso", 6000);
}
// Installazione / aggiornamento di Dolphin in corso? (John: aggiornando dal launcher non si vedeva niente e si poteva
// ripremere "Aggiorna"; il secondo clic l'app lo rifiutava con un errore "occupato")
function giLavora() { return !!(Q.lav && !Q.lav.finito); }
function giProg(lav) {
  const pc = lav.totale ? Math.round(lav.fatti / lav.totale * 100) : 0;
  return `<div class="ins-prog"><div class="testa"><span class="rotella piccola"></span><b>${lav.fase === "estraggo" || lav.fase === "fatto" ? t("gu_estraggo")
      : t("gu_scarico", pc ? pc + "%" : "")}</b></div>
      <div class="barra"><i style="width:${lav.fase === "estraggo" || lav.fase === "fatto" ? 100 : pc || 5}%"></i></div></div>`;
}
async function giInstallaDolphin() {
  if (giLavora()) return;  // già in corso: niente secondo download
  Q.lav = { fase: "cerco", fatti: 0, totale: 0 };
  if (S.pagina === "gioca") disegnaGioca();
  const r = await api().gioca_installa_dolphin();
  if (r && r.errore === "occupato") return;  // (il primo sta già andando: la barra lo segue)
  if (!r || r.errore) { Q.lav = null; toast(t("errore"), errTesto(r && r.errore), "errore"); if (S.pagina === "gioca") disegnaGioca(); return; }
  const tm = setInterval(async () => {
    const st = await api().lavoro_stato();
    if (!st || !st.dolphin) return;
    Q.lav = st;
    if (st.finito) {
      clearInterval(tm);
      if (!st.errore) { Q.lav = null; toast(t("gu_dolphin_ok", st.versione || ""), "", "", 4000); await caricaGioca(true); return; }
      toast(t("errore"), errTesto(st.errore), "errore", 8000);
    }
    if (S.pagina === "gioca") disegnaGioca();
  }, 500);
}

// ---- stati salvati (savestate) della versione scelta
function giStato1() {  // lo stato salvato nello slot 1 della versione scelta (se c'è)
  return Q.stati && Q.statiGid === Q.sel ? Q.stati.stati.find(s => s.n === 1) || null : null;
}
function giPadTondo(mostra) {  // bollino accanto a "Comandi": c'è un controller e i tasti sono pronti per lui?
  const b = $("#gi-pad-tondo"), p = Q.dati && Q.dati.pad;
  const st = p && p.esito !== "manca" ? { ok: ["ok", t("gp_ok", p.pad && p.pad.nome)], nessuno: ["giallo", t("gp_nessuno")], altro: ["giallo", t("gp_altro", p.pad && p.pad.nome)],
    sdl: ["rosso", t("gp_sbagliato", p.pad && p.pad.nome)], xinput: ["rosso", t("gp_sbagliato", p.pad && p.pad.nome)], nome: ["rosso", t("gp_sbagliato", p.pad && p.pad.nome)] }[p.esito] : null;
  b.classList.toggle("nascosto", !mostra || !st);
  if (!st) return;
  b.className = `gi-tondo pad ${st[0]}`;
  b.title = st[1] + (st[0] === "rosso" ? " " + t("gp_clic_sistema") : "");
  b.onclick = async () => { if (st[0] === "rosso" || p.esito === "altro") { if (await giSistemaPad(p)) disegnaGioca(); } else vaiA("controller"); };
}
// LB + RB: il menu in gioco è la cosa più bella dell'app, quindi sta in bella vista nel launcher (pillola accanto a
// Controller/Comandi) e col clic spiega cosa fa. Col pad PlayStation i tasti diventano L1 + R1.
function tastiMenu() {
  const p = Q.dati && Q.dati.pad && Q.dati.pad.pad;
  return p && p.tipo === "ps" ? ["L1", "R1"] : ["LB", "RB"];
}
function giLbrb(mostra) {
  const b = $("#gi-lbrb");
  b.classList.toggle("nascosto", !mostra);
  b.classList.toggle("senza-pad", $("#gi-pad-tondo").classList.contains("nascosto"));
  const [x, y] = tastiMenu();
  b.querySelector(".t1").textContent = x; b.querySelector(".t2").textContent = y;
  b.title = t("mz_come_tit", x, y);
  requestAnimationFrame(() => {  // centrato esattamente sotto "Comandi" (le scritte sotto hanno larghezze diverse)
    const c = $("#gi-com-tondo"), padre = b.offsetParent;
    if (!c || !padre || b.classList.contains("nascosto")) return;
    const z = parseFloat(document.body.style.zoom) || 1;
    const rc = c.getBoundingClientRect(), rp = padre.getBoundingClientRect(), rb = b.getBoundingClientRect();
    b.style.right = ((rp.right - (rc.left + rc.right) / 2) - rb.width / 2) / z + "px";
  });
}
function apriMenuInfo() {
  const [x, y] = tastiMenu();
  for (const k of $("#mz").querySelectorAll(".t1")) k.textContent = x;
  for (const k of $("#mz").querySelectorAll(".t2")) k.textContent = y;
  $("#mz").classList.remove("nascosto");
}
async function giSistemaPad(p, daCapo = false) {  // profilo dei tasti giusto per il pad collegato, da solo (Xbox = XInput, gli altri = SDL col nome che usa Dolphin)
  const tm = setTimeout(() => toast(t("ct_auto_attendi"), "", "", 6000), 400);  // se deve chiedere a Dolphin il nome del pad ci vogliono 3-4 s
  const r = await api().controller_auto(daCapo);
  clearTimeout(tm);
  if (!r || r.errore) {
    const k = { chiudi_dolphin: "ct_auto_chiudi", non_visto: "ct_auto_non_visto", dolphin: "err_dolphin" }[r && r.errore];
    toast(t("errore"), k ? t(k) : errTesto(r && r.errore), "errore", 7000);
    return false;
  }
  X.dati = r; if (Q.dati) Q.dati.pad = r.pad;
  toast(t("fatto"), r.dispositivo ? t("ct_auto_ok", r.dispositivo.split("/").pop()) : t("ct_profilo_ok"), "", 4500);
  return true;
}
document.addEventListener("click", async e => {  // texture HD installate ma spente -> accese
  if (!e.target.closest("#gi-hd")) return;
  const r = await api().hd_accendi();
  if (!r || r.errore) { toast(t("errore"), errTesto(r && r.errore), "errore"); return; }
  toast(t("gi_hd_ok"), r.dolphin_aperto ? t("gi_hd_riavvia") : r.fatti.join(" · "));
  caricaGioca();
});
function giRiprendi(d, sm2) {  // "Parti dallo stato 1": solo se lo slot 1 esiste e il gioco non è già aperto
  if (sm2 || d.aperto || Q.parte) return "";
  const s = giStato1();
  if (!s) return "";
  const ver = (s.versione || "").replace("Dolphin ", "");
  const no = s.compatibile === false, forse = s.compatibile === null && s.versione && s.versione !== d.versione_dolphin;
  const vecchi = !no && !forse && s.gecko_vecchi;  // fatto coi codici Gecko di prima: partendo da qui restano quelli
  const sotto = no ? t("gi_st1_no", ver) : forse ? t("gi_st1_forse", ver) : vecchi ? t("gi_st1_vecchi") : quando(s.data);
  return `<label class="gi-riprendi ${no ? "rosso" : forse || vecchi ? "giallo" : ""} ${d.da_stato ? "on" : ""}" data-tip="${vecchi ? "st_gecko_nota" : "gi_st1_tip"}">
      ${s.foto ? `<img src="data:image/jpeg;base64,${s.foto}" alt="">` : `<span class="gi-st-vuota"><svg><use href="#i-play"/></svg></span>`}
      <span class="t"><b>${t("gi_st1")}</b><small>${no || forse || vecchi ? "⚠ " : ""}${sotto}</small></span>
      <span class="interruttore mini"><input type="checkbox" id="gi-stato" ${d.da_stato ? "checked" : ""}><span></span></span></label>`;
}
function giSchede() {
  $$("#gi-lato [data-tab]").forEach(b => b.onclick = () => { Q.tab = b.dataset.tab; disegnaGioca(); if (Q.tab === "stati") giStati(); });
}
async function giStati() {
  if (!Q.sel) return;
  const gid = Q.sel, r = await api().gioca_stati(gid);
  if (!r || r.errore || gid !== Q.sel) return;
  Q.stati = r; Q.statiGid = gid;
  if (S.pagina === "gioca") disegnaGioca();
}
function quando(ts) {
  const s = Date.now() / 1000 - ts, rf = new Intl.RelativeTimeFormat(L, { numeric: "auto" });
  if (s < 60) return rf.format(0, "second");
  if (s < 3600) return rf.format(-Math.round(s / 60), "minute");
  if (s < 86400) return rf.format(-Math.round(s / 3600), "hour");
  if (s < 86400 * 7) return rf.format(-Math.round(s / 86400), "day");
  return new Date(ts * 1000).toLocaleDateString(L, { day: "numeric", month: "short", year: "numeric" });
}
function disegnaStati() {
  const box = $("#gi-stati"), d = Q.dati;
  if (!box || !d) return;
  const r = Q.statiGid === Q.sel ? Q.stati : null;
  if (!Q.sel) { box.innerHTML = ""; return; }
  if (!r) { box.innerHTML = `<div class="tx-carica"><div class="rotella"></div></div>`; return; }
  const qui = d.gioco === Q.sel;  // il gioco che gira è questa versione: si può salvare e caricare
  const per = Object.fromEntries(r.stati.map(s => [s.n, s]));
  const slots = qui ? [...new Set([...r.stati.map(s => s.n), 1, 2, 3, 4, 5, 6, 7, 8])].sort((a, b) => a - b) : r.stati.map(s => s.n);
  const nome = x => x.titolo ? tr(x.titolo) : x.nome.replace(/^\$/, "");
  box.innerHTML = `<p class="gi-st-aiuto">${t("st_aiuto")}</p>
    ${!slots.length ? `<div class="nota-sez">${t("st_nessuno", d.nomi[Q.sel])}</div>` : ""}
    <div class="gi-st-griglia">${slots.map(n => {
      const s = per[n];
      if (!s) return `<div class="gi-stato vuoto"><div class="gi-foto"><div class="segnaposto"><svg><use href="#ragno"/></svg></div><span class="gi-slot">${t("st_slot", n)} · ${t("st_vuoto")}</span></div>
        <div class="gi-st-azioni"><button class="leggero" data-salva="${n}">${t("st_salva")}</button></div></div>`;
      const avvisi = [];
      if (s.compatibile === false) avvisi.push(`<span class="gi-chip rosso">${t("st_incompatibile", s.versione)}</span>`);
      else if (s.compatibile === null && s.versione) avvisi.push(`<span class="gi-chip giallo">${t("st_forse", s.versione)}</span>`);
      const cod = [...(s.accesi || []).map(x => `<span class="cc su">+ ${nome(x)}</span>`), ...(s.spenti || []).map(x => `<span class="cc giu">− ${nome(x)}</span>`),
        ...(s.cambiati || []).map(x => `<span class="cc mod">~ ${nome(x)}</span>`)];
      const note = [];
      if (s.patch && s.patch.length) note.push(t("st_patch_nota"));
      if ((s.spenti || []).length) note.push(t("st_spenti_nota"));
      if ([...(s.cambiati || []), ...(s.accesi || []), ...(s.spenti || [])].some(x => /camera/i.test(x.nome))) note.push(t("st_camera_nota"));
      if (s.gecko_vecchi) note.push(t("st_gecko_nota"));
      const puoGiocare = !d.aperto && d.exe && s.compatibile !== false, puoCaricare = qui && s.tasto && s.compatibile !== false;
      return `<div class="gi-stato ${s.compatibile === false ? "no" : ""}">
        <div class="gi-foto">${s.foto ? `<img src="data:image/jpeg;base64,${s.foto}" alt="">` : `<div class="segnaposto"><svg><use href="#ragno"/></svg><small>${t("st_no_foto")}</small></div>`}
          <span class="gi-slot">${t("st_slot", n)}${s.tasto ? ` · F${n}` : ""}</span></div>
        <div class="gi-st-testo"><b>${quando(s.data)}</b><small>${new Date(s.data * 1000).toLocaleString(L, { dateStyle: "medium", timeStyle: "short" })} · ${s.versione || "?"}</small>
          ${avvisi.join("")}
          ${cod.length || note.length ? `<div class="gi-st-avviso">${cod.length ? `<b>${t("st_codici")}</b><div class="cc-lista">${cod.join("")}</div>` : ""}${note.map(x => `<p>${x}</p>`).join("")}</div>` : ""}</div>
        <div class="gi-st-azioni">
          ${qui ? `<button class="primario" data-carica="${n}" ${puoCaricare ? "" : "disabled"} title="${s.tasto ? "" : t("st_solo_tasti")}">${t("st_carica")}</button>
                   ${s.tasto ? `<button class="leggero" data-salva="${n}">${t("st_salva")}</button>` : ""}`
                : `<button class="primario" data-gioca-stato="${n}" ${puoGiocare ? "" : "disabled"}><svg><use href="#i-play"/></svg>${t("st_gioca")}</button>`}
          <button class="leggero icona" data-elimina-stato="${n}" title="${t("st_elimina")}"><svg><use href="#i-x"/></svg></button></div></div>`;
    }).join("")}</div>`;
  box.querySelectorAll("[data-gioca-stato]").forEach(b => b.onclick = () => giocaVia(+b.dataset.giocaStato));
  box.querySelectorAll("[data-carica]").forEach(b => b.onclick = async () => {
    const r = await api().gioca_carica_stato(+b.dataset.carica);
    if (r && r.errore) toast(t("errore"), errTesto(r.errore), "errore"); else toast(t("st_caricato", b.dataset.carica), "", "", 2500);
  });
  box.querySelectorAll("[data-salva]").forEach(b => b.onclick = async () => {
    const n = +b.dataset.salva;
    if (per[n] && !(await modale({ titolo: t("st_sovrascrivi_tit", n), testo: t("st_sovrascrivi"), bottoni: [[false, t("annulla")], [true, t("st_salva"), true]] }))) return;
    const r = await api().gioca_salva_stato(n);
    if (r && r.errore) toast(t("errore"), errTesto(r.errore), "errore"); else toast(t("st_salvato", n), "", "", 2500);
  });
  box.querySelectorAll("[data-elimina-stato]").forEach(b => b.onclick = async () => {
    const n = +b.dataset.eliminaStato;
    if (!(await modale({ titolo: t("st_elimina_tit", n), testo: t("st_elimina_testo"), bottoni: [[false, t("annulla")], [true, t("st_elimina"), true]] }))) return;
    await api().gioca_elimina_stato(Q.sel, n);
    giStati();
  });
}
async function giocaVia(slot = null) {
  const d = Q.dati;
  if (!d || !Q.sel || d.aperto || Q.parte) return;
  if (giLavora()) { toast(t("gu_estraggo"), t("gioca_agg_attendi"), "avviso", 3500); return; }  // Dolphin a metà aggiornamento
  const s1 = slot === null && d.da_stato ? giStato1() : null;
  if (s1) {
    if (s1.compatibile === false) {  // fatto con un Dolphin di formato diverso: non si carica
      const scelta = await modale({ titolo: t("gi_st1_no_tit"), testo: t("gi_st1_no_testo", (s1.versione || "?").replace("Dolphin ", ""), (d.versione_dolphin || "").replace("Dolphin ", "")),
        bottoni: [["prova", t("gi_st1_prova")], ["normale", t("gi_st1_normale"), true]] });
      if (!scelta) return;
      slot = scelta === "prova" ? 1 : null;
    } else slot = 1;
  }
  const pe = d.pad && d.pad.esito;  // il controller collegato risponderà in gioco?
  if (pe === "nessuno") {  // pad sbagliato: ci pensa gioca_avvia (lo configura da solo); niente pad: chiedo
    const r = await modale({ titolo: t(pe === "nessuno" ? "gp_m_nessuno_tit" : "gp_m_sbagliato_tit"), testo: pe === "nessuno" ? t("gp_m_nessuno") : t("gp_m_sbagliato", d.pad.pad.nome),
      bottoni: pe === "nessuno" ? [["no", t("annulla")], ["vai", t("gp_gioca_comunque"), true]] : [["vai", t("gp_gioca_comunque")], ["sistema", t("gp_sistema_gioca"), true]] });
    if (!r || r === "no") return;
    if (r === "sistema" && !(await giSistemaPad(d.pad))) return;
  }
  Q.parte = true; disegnaGioca();
  const r = await api().gioca_avvia(Q.sel, d.solo, d.intero, slot);
  if (r && r.pad_auto) toast(t("ct_auto_ok", String(r.pad_auto).split("/").pop()), t("ct_auto_avvio"), "", 5000);
  if (!r || r.errore) {
    Q.parte = false; disegnaGioca();
    toast(t("errore"), r ? t(r.errore, (r.disco || "")) : "", "errore", 6000); return;
  }
  d.ultima = Q.sel; d.trucchi = true;
  toast(t("gioca_avviato"), t("gioca_avviato_sub", d.nomi[Q.sel]) + (r.dopo ? " " + t("gioca_stato_dopo", slot) : "") + (r.trucchi ? t("gioca_trucchi") : ""), "", r.dopo ? 9000 : 5000);
  setTimeout(() => { if (Q.parte) { Q.parte = false; if (S.pagina === "gioca") disegnaGioca(); } }, 20000);  // il gioco può metterci un po' a comparire
}

// ================================================================ esporta la mod pronta (zip per altro PC, Android, Xbox)
const E = { info: null, piatt: "pc", contr: "pc", ver: new Set(), formato: "dds", fps30: false, salva: false, lav: null, tm: null,
  parti: new Set(["texture", "ini", "controller"]) };
const PIATT_ICONA = { pc: "i-pc", pcarm: "i-pc", mac: "i-portatile", android: "i-telefono", xbox: "i-xbox" };
// Mac: risoluzione dallo schermo (3× = 1080p, 4× = 1440p e MacBook, 6× = 4K), con un tetto per il processore
const MAC_SCHERMI = [["1080", 3], ["retina", 4], ["1440", 4], ["4k", 6]];
const MAC_CHIP = { arm: 4, armpro: 6, intel: 2 };
E.mac = { chip: "arm", schermo: "retina" };
function expMac() {
  const voluta = MAC_SCHERMI.find(([s]) => s === E.mac.schermo)[1], res = Math.min(voluta, MAC_CHIP[E.mac.chip]);
  return { res, voluta, grafica: { backend: "Metal", res, jit: E.mac.chip === "intel", oc_on: true, oc: 3 } };
}
async function caricaEsporta() {
  const r = await api().esporta_info();
  if (!r || r.errore) { toast(t("errore"), errTesto(r && r.errore), "errore"); return; }
  if (!E.info) r.versioni.forEach(g => E.ver.add(g));
  E.info = r;
  disegnaEsporta();
}
function expPiattaforma(p) {
  E.piatt = p; E.contr = E.info.piattaforme[p][0] || "";
  E.formato = p === "android" ? "png" : "dds";
  disegnaEsporta();
}
function expLeggimi() {  // il LEGGIMI dentro lo zip: gli stessi passi del tutorial, nella lingua dell'app
  const passi = expPassi();
  const tasti = E.parti.has("ini") ? `${t("exp_tasti_tit")}\n${"-".repeat(30)}\n${t("exp_tasti")}\n\n${t("exp_cam_nota")}\n\n` : "";  // solo se i codici sono nello zip
  const rag = E.info && E.info.rag_alt ? `${t("exp_rag_nota")}\n\n` : "";  // le ragnatele dell'alternativo le cambia l'app
  return `${t("exp_leggimi_tit")}\n${"=".repeat(50)}\n\n${passi.map((p, i) => `${i + 1}. ${p}`).join("\n")}\n\n${tasti}${rag}${t("exp_crediti")}\n\n${t("avviso_fan")}\n`;
}
function expPassi() {
  const p = E.piatt;
  const q = p === "pcarm" ? "pc" : p;
  return [t(`exp_t_${q}_1`), t(`exp_t_${q}_2`), t("exp_t_3"), t("exp_t_4"), t("exp_t_5")];
}
function disegnaEsporta() {
  if (!E.info) return;
  const box = $("#exp-lista"), sc = box.scrollTop, d = E.info, lav = E.lav;
  let h = `<div class="ins-passo"><div class="ins-num">1</div><div class="ins-corpo"><h3>${t("exp_p1")}</h3>
    <div class="exp-piatt">${Object.keys(d.piattaforme).map(p => `<button data-piatt="${p}" class="${E.piatt === p ? "attivo" : ""}">
      <svg><use href="#${PIATT_ICONA[p]}"/></svg><b>${t("exp_" + p)}</b><small>${t("exp_" + p + "_sub")}</small></button>`).join("")}</div></div></div>`;
  const opz = [...d.piattaforme[E.piatt], ""];
  h += `<div class="ins-passo"><div class="ins-num">2</div><div class="ins-corpo"><h3>${t("exp_p2")}</h3><p>${t("exp_p2_sub")}</p>
    <div class="exp-contr">${opz.map(c => { const k = c ? "exp_c_" + c : "exp_c_nessuno";
      return `<button data-contr="${c}" class="${E.contr === c ? "attivo" : ""}"><b>${t(k)}</b><small>${t(!c && E.piatt === "mac" ? "exp_c_mac_sub" : k + "_sub")}</small></button>`; }).join("")}</div></div></div>`;
  h += `<div class="ins-passo"><div class="ins-num">3</div><div class="ins-corpo"><h3>${t("exp_p3")}</h3>
    <div class="ins-versioni">${Object.entries(d.nomi).map(([g, n]) => { const ok = d.versioni.includes(g);
      return `<button class="ins-ver ${E.ver.has(g) ? "attivo" : ""} ${ok ? "" : "no"}" data-ver="${g}" ${ok ? "" : "disabled"}><span class="band">${BANDIERE[g]}</span><b>${n}</b>
        <em class="${ok ? "si" : ""}">${ok ? "✓ " + t("ins_v_installata") : t("ins_v_da")}</em></button>`; }).join("")}</div>
    ${E.piatt === "android" ? (() => { const a = d.android, p = PRESET_ANDROID.find(([, , v]) => Object.entries(v).every(([k, x]) => a[k] === x));
        return `<div class="ins-opz riga"><div><b>${t("exp_grafica_and")}: ${p ? t("gr_p_" + p[0]) : t("gr_p_pers")}</b>
          <p>${a.res}× · ${a.backend === "OGL" ? "OpenGL" : "Vulkan"} · ${a.fps30 ? "30" : "60"} fps · ${t("ins_c_texture")} ${a.tex.toUpperCase()}</p></div>
          <button class="leggero" id="exp-grafica">${t("exp_cambia_grafica")}</button></div>`; })()
      : E.piatt === "mac" ? (() => { const a = d.mac, p = PRESET_MAC.find(([, , v]) => Object.entries(v).every(([k, x]) => a[k] === x));
        return `<div class="ins-opz riga"><div><b>${t("exp_grafica_mac")}: ${p ? t("gr_p_" + p[0]) : t("gr_p_pers")}</b>
          <p>${a.res}× · ${gValore("backend", a.backend)} · JIT ${a.jit ? t("acceso") : t("spento")} · ${t("ins_c_texture")} ${a.tex.toUpperCase()}</p></div>
          <button class="leggero" id="exp-grafica">${t("exp_cambia_grafica")}</button></div>`; })()
      : (false ? (() => { const m = expMac();
        return `<div class="ins-opz"><b>${t("exp_mac_chip")}</b><p>${t("exp_mac_chip_sub")}</p><div class="exp-contr exp-mac">${Object.keys(MAC_CHIP).map(c =>
          `<button data-mchip="${c}" class="${E.mac.chip === c ? "attivo" : ""}"><b>${t("exp_mac_" + c)}</b><small>${t("exp_mac_" + c + "_sub")}</small></button>`).join("")}</div></div>
        <div class="ins-opz"><b>${t("exp_mac_schermo")}</b><div class="ordine exp-schermi">${MAC_SCHERMI.map(([s]) =>
          `<button data-mschermo="${s}" class="${E.mac.schermo === s ? "attivo" : ""}">${t("exp_mac_" + s)}</button>`).join("")}</div>
          <p class="exp-riass"><svg><use href="#i-grafica"/></svg>${t("exp_mac_riass", m.res, t(E.mac.chip === "intel" ? "exp_mac_jit_intel" : "exp_mac_jit_arm"))}${m.res < m.voluta ? t("exp_mac_limite") : ""}</p></div>`; })() : "")
      + `<div class="ins-opz"><b>${t("exp_formato")}</b><div class="ins-formati">
      <button data-formato="dds" class="${E.formato === "dds" ? "attivo" : ""}"><b>DDS</b><small>${t("exp_dds_sub")}</small></button>
      <button data-formato="png" class="${E.formato === "png" ? "attivo" : ""}"><b>PNG</b><small>${t("exp_png_sub")}</small></button></div></div>`}
    <div class="ins-opz"><b>${t("exp_parti")}</b></div>
    ${["texture", "ini", "controller"].map(p => `<div class="ins-opz riga ${p === "controller" && !E.contr ? "bloccato" : ""}"><div><b>${t("exp_p_" + p)}</b><p>${t("exp_p_" + p + "_sub")}</p></div>
      <label class="interruttore"><input type="checkbox" data-parte="${p}" ${E.parti.has(p) && (p !== "controller" || E.contr) ? "checked" : ""}><span></span></label></div>`).join("")}
    <div class="ins-opz riga"><div><b>${t("ins_salva")}</b><p>${t("ins_salva_sub")}</p></div><label class="interruttore"><input type="checkbox" data-eopz="salva" ${E.salva ? "checked" : ""}><span></span></label></div>
  </div></div>`;
  // cosa resta fuori senza l'app: camere fissate (principale/alternativa scelte adesso), ragnatele dell'alternativo
  const note = [E.parti.has("ini") ? ["i-cam", "exp_cam_nota"] : null, d.rag_alt ? ["i-skin", "exp_rag_nota"] : null].filter(Boolean);
  if (note.length) h += `<div class="ins-passo"><div class="ins-num">!</div><div class="ins-corpo">${soloApp()}${note.map(([ic, k]) =>
    `<p class="exp-riass"><svg><use href="#${ic}"/></svg>${t(k)}</p>`).join("")}</div></div>`;
  const qualcosa = [...E.parti].some(p => p !== "controller" || E.contr) || E.salva;
  const pronto = E.ver.size && qualcosa && !(lav && !lav.finito);
  h += `<div class="ins-passo ultimo"><div class="ins-num">4</div><div class="ins-corpo"><div class="ins-testa"><div><h3>${t("exp_via")}</h3><p>${!E.ver.size ? t("ins_nessuna_ver") : !qualcosa ? t("exp_nulla") : t("exp_via_sub")}</p></div>
      <button class="primario grande" id="exp-via" ${pronto ? "" : "disabled"}><svg><use href="#i-esporta"/></svg>${t("exp_via")}</button></div>
    ${lav ? expProgresso(lav) : ""}</div></div>`;
  box.innerHTML = h;
  box.scrollTop = sc;
  box.querySelectorAll("[data-piatt]").forEach(b => b.onclick = () => expPiattaforma(b.dataset.piatt));
  box.querySelectorAll("[data-contr]").forEach(b => b.onclick = () => { E.contr = b.dataset.contr; disegnaEsporta(); });
  box.querySelectorAll("[data-ver]").forEach(b => b.onclick = () => { const g = b.dataset.ver; E.ver.has(g) ? E.ver.delete(g) : E.ver.add(g); disegnaEsporta(); });
  box.querySelectorAll("[data-formato]").forEach(b => b.onclick = () => { E.formato = b.dataset.formato; disegnaEsporta(); });
  box.querySelectorAll("[data-mchip]").forEach(b => b.onclick = () => { E.mac.chip = b.dataset.mchip; disegnaEsporta(); });
  box.querySelectorAll("[data-mschermo]").forEach(b => b.onclick = () => { E.mac.schermo = b.dataset.mschermo; disegnaEsporta(); });
  box.querySelectorAll("[data-eopz]").forEach(x => x.onchange = () => { E[x.dataset.eopz] = x.checked; disegnaEsporta(); });
  box.querySelectorAll("[data-parte]").forEach(x => x.onchange = () => { x.checked ? E.parti.add(x.dataset.parte) : E.parti.delete(x.dataset.parte); disegnaEsporta(); });
  $("#exp-via").onclick = expAvvia;
  const eg = $("#exp-grafica"); if (eg) eg.onclick = () => { const x = E.piatt === "mac" ? "mac" : "android"; vaiA("grafica"); if (G.dati) gTarget(x); else G.target = x; };
  const ap = $("#exp-apri"); if (ap) ap.onclick = () => api().mostra_file(E.lav.file);
  const fe = $("#exp-ferma"); if (fe) fe.onclick = () => api().lavoro_annulla();
}
function expProgresso(st) {
  if (st.finito && !st.errore) return `<div class="ins-fine"><svg><use href="#ragno"/></svg><div><h3>${t("exp_fatto")}</h3><p><code>${st.file}</code></p>
      <h4>${t("exp_come")}</h4><ol class="exp-tut">${expPassi().map(p => `<li>${p}</li>`).join("")}</ol>
      <div class="bottoni"><button class="primario piccolo" id="exp-apri">${t("exp_apri")}</button></div></div></div>`;
  const testo = { png: t("exp_f_png"), ini: t("exp_f_ini"), zip: t("exp_f_zip") }[st.fase] || "…";
  const pct = st.totale ? Math.round(st.fatti / st.totale * 100) : 0;
  return `<div class="ins-prog"><div class="testa"><b>${testo}</b><small>${st.totale ? st.fatti + " / " + st.totale : ""}</small>
      <button class="leggero" id="exp-ferma">${t("lav_annulla")}</button></div><div class="barra"><i style="width:${pct}%"></i></div>
    ${st.errore ? `<p class="avviso">${st.errore}</p>` : ""}</div>`;
}
async function expAvvia() {
  const via = $("#exp-via");
  if (via) { if (via.disabled) return; via.disabled = true; }  // doppio clic = due finestre di salvataggio
  const r = await api().esporta_avvia({ piattaforma: E.piatt, nome_piattaforma: t("exp_" + E.piatt) + (E.piatt === "android" && E.info.android.fps30 ? " 30fps" : ""),
    controller: E.contr || null, versioni: [...E.ver], formato: E.formato, parti: [...E.parti], fps30: E.piatt === "android" && E.fps30, salvataggi: E.salva, leggimi: expLeggimi() });
  if (!r || r.errore) { if (via) via.disabled = false; if (r) toast(t("errore"), errTesto(r.errore), "errore"); return; }
  E.lav = { fase: "", fatti: 0, totale: 0 };
  disegnaEsporta();
  clearInterval(E.tm);
  E.tm = setInterval(async () => {
    const st = await api().lavoro_stato();
    if (!st || !st.esporta) return;
    E.lav = st;
    if (S.pagina === "esporta") disegnaEsporta();
    if (st.finito) clearInterval(E.tm);
  }, 600);
}

// ================================================================ installer (ModDB -> libreria -> Dolphin)
const I = { dati: null, archivi: null, sel: new Set(), ver: new Set(), opz: { formato: "dds", cancella: true, salvataggi: true }, dl: {}, tmDl: {}, tmLav: null, lav: null };
const BANDIERA = (dentro) => `<svg viewBox="0 0 30 20" class="bandiera">${dentro}</svg>`;
const BANDIERE = {  // disegnate a mano: Windows non ha le emoji delle bandiere
  GK2E52: BANDIERA(`<rect width="30" height="20" fill="#fff"/>${[0, 2, 4, 6, 8, 10, 12].map(i => `<rect y="${i * 20 / 13}" width="30" height="${20 / 13}" fill="#b22234"/>`).join("")}<rect width="13" height="${20 * 7 / 13}" fill="#3c3b6e"/>`),
  GK2P52: BANDIERA(`<rect width="30" height="20" fill="#012169"/><path d="M0 0L30 20M30 0L0 20" stroke="#fff" stroke-width="4"/><path d="M0 0L30 20M30 0L0 20" stroke="#c8102e" stroke-width="1.5"/><path d="M15 0v20M0 10h30" stroke="#fff" stroke-width="6"/><path d="M15 0v20M0 10h30" stroke="#c8102e" stroke-width="3.5"/>`),
  GK2I52: BANDIERA(`<rect width="10" height="20" fill="#009246"/><rect x="10" width="10" height="20" fill="#fff"/><rect x="20" width="10" height="20" fill="#ce2b37"/>`),
  GK2D52: BANDIERA(`<rect width="30" height="7" fill="#000"/><rect y="6.6" width="30" height="7" fill="#dd0000"/><rect y="13.3" width="30" height="6.7" fill="#ffce00"/>`),
  GK2F52: BANDIERA(`<rect width="10" height="20" fill="#0055a4"/><rect x="10" width="10" height="20" fill="#fff"/><rect x="20" width="10" height="20" fill="#ef4135"/>`),
};
const mb = b => b >= 2 ** 30 ? (b / 2 ** 30).toFixed(1) + " GB" : b >= 2 ** 20 ? Math.round(b / 2 ** 20) + " MB" : Math.max(1, Math.round(b / 1024)) + " KB";
async function caricaInstaller() {
  const r = await api().installer_stato();
  if (!r || r.errore) { toast(t("errore"), errTesto(r && r.errore), "errore"); return; }
  const primo = !I.dati;
  I.dati = r;
  if (primo) {
    Object.keys(r.giochi).forEach(g => I.ver.add(g));
    if (!I.ver.size) I.ver.add("GK2E52");
    r.catalogo.file.forEach(c => { if (!insInstallato(c, r)) I.sel.add(c.id); });  // già installati: non spuntati
  }
  disegnaInstaller();
  I.archivi = null; disegnaInstaller();
  I.archivi = await api().installer_archivi() || {};
  disegnaInstaller();
}
const insInstallato = (c, d = I.dati) => !!(d.installati[c.id] && d.installati[c.id].md5 === c.md5);
function insStato(c) {  // installato (e non rispuntato) | scarico | pronto | rifai (installato e rispuntato) | trovato (zip c'è, non spuntato) | manca
  if (insInstallato(c) && !I.sel.has(c.id)) return "installato";
  if (I.dl[c.id]) return "scarico";
  if (I.archivi && I.archivi[c.id]) return !I.sel.has(c.id) ? "trovato" : insInstallato(c) ? "rifai" : "pronto";
  return "manca";
}
const insDaFare = c => ["pronto", "rifai"].includes(insStato(c));
function disegnaInstaller() {
  if (!I.dati) return;
  const box = $("#ins-lista"), sc = box.scrollTop, d = I.dati, lav = I.lav;
  const cat = d.catalogo.file;
  const scelti = cat.filter(c => I.sel.has(c.id));
  const mancano = scelti.filter(c => insStato(c) === "manca" || insStato(c) === "scarico");
  const daInstallare = scelti.filter(insDaFare);
  const peso = daInstallare.reduce((n, c) => n + c.byte, 0);
  let h = "";
  const giaInst = Object.keys(d.installati).length > 0;
  if (giaInst) {
    const conTex = Object.entries(d.stato_ver || {}).filter(([, s]) => s.texture).map(([g]) => d.nomi[g]);
    h += `<div class="ins-gia"><svg><use href="#i-ok"/></svg><div><b>${t("ins_gia")}</b>
      <p>${t("ins_gia_lib", Object.keys(d.installati).length, (d.formato || "").toUpperCase())}<br>${conTex.length ? t("ins_gia_dolphin", conTex.join(" · ")) : t("ins_gia_no_dolphin")}</p>
      <p class="nota">${t("ins_gia_sub")}</p></div></div>`;
  }
  // 1. Dolphin e versioni
  h += `<div class="ins-passo"><div class="ins-num">1</div><div class="ins-corpo"><h3>${t("ins_p1")}</h3><p>${t("ins_p1_sub")}</p>`;
  if (!d.dolphin) h += `<div class="patch-barra no"><svg><use href="#i-ingr"/></svg><span>${t("ins_no_dolphin")}</span>
      <button class="primario" id="ins-dolphin-io">${t("gu_p1_installa")}</button><button class="leggero" id="ins-sc-dolphin">${t("ins_ho_dolphin")}</button></div>`;
  else h += `<div class="ins-dolphin"><svg><use href="#i-ok"/></svg><span>Dolphin: <b>${d.dolphin}</b></span><button class="leggero" id="ins-sc-dolphin">${t("cambia")}</button></div>`;
  h += `<div class="ins-versioni">${Object.entries(d.nomi).map(([g, n]) => {
      const tr_ = d.giochi[g];
      const sv = (d.stato_ver || {})[g] || {}, inst = sv.texture && sv.codici;
      return `<button class="ins-ver ${I.ver.has(g) ? "attivo" : ""} ${tr_ ? "" : "no"}" data-ver="${g}" title="${tr_ || ""}"><span class="band">${BANDIERE[g]}</span><b>${n}</b>
        <small>${tr_ ? t("ins_trovata") : t("ins_non_trovata")}</small><em class="${inst ? "si" : ""}">${inst ? "✓ " + t("ins_v_installata") : t("ins_v_da")}</em></button>`;
    }).join("")}</div></div></div>`;
  // 2. pacchetti
  h += `<div class="ins-passo"><div class="ins-num">2</div><div class="ins-corpo"><div class="ins-testa"><div><h3>${t("ins_p2")}</h3><p>${t("ins_p2_sub")}</p><p class="ins-trascina"><svg><use href="#i-scarica"/></svg>${t("ins_trascina")}</p></div>
      <button class="leggero" id="ins-cerca">${t("ins_cerca_ancora")}</button></div>`;
  if (!I.archivi) h += `<div class="ins-cerco"><div class="rotella piccola"></div>${t("ins_cerco")}</div>`;
  const trovati = cat.filter(c => insStato(c) === "trovato");
  if (trovati.length) h += `<div class="ins-trovati"><svg><use href="#i-scarica"/></svg><span>${t("ins_trovati", trovati.length, trovati.map(c => c.nome).join(", "))}</span>
      <button class="primario piccolo" id="ins-spunta-trovati">${t("ins_spunta_trovati")}</button></div>`;
  const carta = c => {  // vetrina: immagine dalla pagina ModDB dell'autore, descrizione, stato e azioni
      const st = insStato(c), on = I.sel.has(c.id), dl = I.dl[c.id];
      const badge = c.obbligatorio ? `<i class="b-base">${t("ins_obbligatorio")}</i>` : c.consigliato ? `<i class="b-cons">${t("ins_consigliato")}</i>` : c.aggiorna ? `<i class="b-agg">${t("ins_aggiorna")}</i>` : "";
      const stati = { pronto: ["ok", "i-ok", "ins_pronto"], rifai: ["rifai", "i-giro", "ins_rifai"], trovato: ["trovato", "i-scarica", "ins_trovato"], installato: ["ok", "i-ok", "ins_in_libreria"] };
      const sx = stati[st];
      let azioni;
      if (st === "scarico") azioni = `<div class="ins-dl"><div class="barra"><i style="width:${dl.totale ? dl.byte / dl.totale * 100 : 0}%"></i></div><small>${dl.totale ? t("ins_scarico", mb(dl.byte) + " / " + mb(dl.totale)) : t("ins_attesa")}</small>
        <button class="leggero mini" data-annulla-dl="${c.id}">${t("annulla")}</button></div>`;
      else if (st === "manca") azioni = `<button class="leggero" data-celho="${c.id}">${t("ins_ce_lho")}</button><button class="primario piccolo" data-scarica="${c.id}" title="${t("ins_scarica")}"><svg><use href="#i-scarica"/></svg>${t("ins_scarica_breve")}</button>`;
      else azioni = `<button class="leggero mini" data-riscarica="${c.id}" data-tip="ins_riscarica_tip"><svg><use href="#i-scarica"/></svg>${t("ins_riscarica")}</button>${
          st === "installato" && !c.obbligatorio && !c.aggiorna ? `<button class="leggero mini ins-rim" data-rimuovi="${c.id}" data-tip="ins_rim_tip">${t("ins_rim")}</button>` : ""}`;
      const blocco = c.obbligatorio && !insInstallato(c);
      return `<div class="ins-carta ${on ? "on" : ""} ${on && st === "manca" ? "manca" : ""} ${blocco ? "fissa" : ""}" data-pacco="${c.id}">
        <div class="ic-img"><img src="${c.img || ""}" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.parentNode.classList.add('senza')">
          <svg class="ic-ragno"><use href="#ragno"/></svg><div class="ic-velo"></div>
          <div class="ic-badge">${badge}</div>
          <label class="spunta ic-spunta" data-tip="${blocco ? "ins_obbligatorio" : "ins_seleziona"}"><input type="checkbox" data-sel="${c.id}" ${on ? "checked" : ""} ${blocco ? "disabled" : ""}><span></span></label>
          ${sx ? `<span class="ic-stato ${sx[0]}"><svg><use href="#${sx[1]}"/></svg>${t(sx[2])}</span>` : ""}</div>
        <div class="ic-corpo">
          <b class="ic-nome">${c.nome}</b>
          <span class="ic-autore">${t("ins_di")} <span class="link" data-link="${c.pagina}">${c.autore} ↗</span></span>
          <p class="ic-desc">${c.desc ? c.desc[L] || c.desc.en : ""}</p>
          <div class="ins-chip">${c.contenuto.map(x => `<span class="c-${x}">${t("ins_c_" + x)}</span>`).join("")}</div>
        </div>
        <div class="ic-piede"><small>${mb(c.byte)} · ${(c.data || "").slice(0, 4)}</small><div class="ic-azioni">${azioni}</div></div></div>`;
    };
  const base = cat.filter(c => c.obbligatorio || c.consigliato), extra = cat.filter(c => !c.obbligatorio && !c.consigliato);
  h += `<div class="ins-crediti"><svg><use href="#ragno"/></svg><span>${t("ins_crediti")}</span></div>`;
  h += `<h4 class="ins-gruppo">${t("ins_g_base")}</h4><div class="ins-vetrina">${base.map(carta).join("")}</div>`;
  h += `<h4 class="ins-gruppo">${t("ins_g_extra")}</h4><div class="ins-vetrina">${extra.map(carta).join("")}</div>`;
  h += `<details class="ins-superati"><summary>${t("ins_superati")} (${d.catalogo.superati.length})</summary>${d.catalogo.superati.map(s =>
      `<div class="ins-pacco superato"><div class="ins-info"><b>${s.nome}<i class="b-vecchio">${t("ins_superata")}</i></b><small>${s.data} · ${t("ins_superata_da", cat.find(c => c.id === s.sostituito_da).nome)}</small></div></div>`).join("")}</details>`;
  h += `<div class="ins-riepilogo ${mancano.length ? "no" : "ok"}">${mancano.length ? t("ins_da_scaricare", mancano.map(c => c.nome).join(", ")) : t("ins_tutto_pronto")}</div></div></div>`;
  // 3. opzioni
  // misurato (libreria in DDS senza doppioni): alla fine ~ quanto gli archivi; durante il lavoro ~ 2,3 volte
  const arch = scelti.reduce((n, c) => n + c.byte, 0), stimaFine = arch * 1.0, stimaPicco = arch * 2.3;
  h += `<div class="ins-passo"><div class="ins-num">3</div><div class="ins-corpo"><h3>${t("ins_p3")}</h3>
    <div class="ins-opz"><b>${t("ins_formato")}</b><div class="ins-formati">
      <button data-formato="dds" class="${I.opz.formato === "dds" ? "attivo" : ""}"><b>${t("ins_dds")}</b><small>${t("ins_dds_sub")}</small></button>
      <button data-formato="png" class="${I.opz.formato === "png" ? "attivo" : ""}"><b>${t("ins_png")}</b><small>${t("ins_png_sub")}</small></button></div></div>
    <div class="ins-opz riga"><div><b>${t("ins_cancella")}</b><p>${t("ins_cancella_sub")}</p></div><label class="interruttore"><input type="checkbox" data-opz="cancella" ${I.opz.cancella ? "checked" : ""}><span></span></label></div>
    <div class="ins-opz riga"><div><b>${t("ins_salva")}</b><p>${t("ins_salva_sub")}</p></div><label class="interruttore"><input type="checkbox" data-opz="salvataggi" ${I.opz.salvataggi ? "checked" : ""}><span></span></label></div>
    <div class="ins-opz riga"><div><b>${t("ins_libreria")}</b><p>${t("ins_libreria_sub", mb(stimaFine), mb(stimaPicco))}<br><code>${d.libreria}</code></p>
      ${d.dolphin ? (d.libreria[0].toLowerCase() === d.dolphin[0].toLowerCase()
        ? `<p class="ins-disco ok">✓ ${t("ins_disco_ok")}</p>` : `<p class="ins-disco no">⚠ ${t("ins_disco_no")}</p>`) : ""}</div><button class="leggero" id="ins-sc-lib">${t("cambia")}</button></div>
  </div></div>`;
  // 4. installa
  const pronto = d.dolphin && I.ver.size && !mancano.length && !(lav && !lav.finito) && (daInstallare.length || giaInst);
  const ripara = giaInst && !daInstallare.length;
  h += `<div class="ins-passo ultimo"><div class="ins-num">4</div><div class="ins-corpo"><div class="ins-testa"><div><h3>${t(ripara ? "ins_ripara" : "ins_via")}</h3>
      <p>${!I.ver.size ? t("ins_nessuna_ver") : mancano.length ? t("ins_manca") : t(ripara ? "ins_ripara_sub" : giaInst ? "ins_aggiungi_sub" : "ins_via_sub")}</p></div>
      <button class="primario grande" id="ins-via" ${pronto ? "" : "disabled"}><svg><use href="#${ripara ? "i-giro" : "i-scarica"}"/></svg>${t(ripara ? "ins_ripara" : "ins_via")}</button></div>
    ${lav ? insProgresso(lav) : ""}</div></div>`;
  box.innerHTML = h;
  box.scrollTop = sc;
  // eventi
  box.querySelectorAll("[data-ver]").forEach(b => b.onclick = () => { const g = b.dataset.ver; I.ver.has(g) ? I.ver.delete(g) : I.ver.add(g); disegnaInstaller(); });
  box.querySelectorAll("[data-sel]").forEach(x => x.onchange = () => { x.checked ? I.sel.add(x.dataset.sel) : I.sel.delete(x.dataset.sel); disegnaInstaller(); });
  box.querySelectorAll(".ins-carta").forEach(k => k.onclick = e => {  // tutta la scheda si seleziona con un clic
    if (e.target.closest("button, .link, label, a")) return;
    const x = k.querySelector("[data-sel]");
    if (!x || x.disabled) return;
    x.checked = !x.checked; x.onchange();
  });
  box.querySelectorAll("[data-formato]").forEach(b => b.onclick = () => { I.opz.formato = b.dataset.formato; disegnaInstaller(); });
  box.querySelectorAll("[data-opz]").forEach(x => x.onchange = () => { I.opz[x.dataset.opz] = x.checked; });
  box.querySelectorAll("[data-scarica]").forEach(b => b.onclick = () => insScarica(b.dataset.scarica));
  box.querySelectorAll("[data-annulla-dl]").forEach(b => b.onclick = () => {
    const id = b.dataset.annullaDl;
    clearInterval(I.tmDl[id]); delete I.dl[id]; api().installer_annulla_download(id); disegnaInstaller();  // ferma davvero e toglie il file a metà
  });
  box.querySelectorAll("[data-celho]").forEach(b => b.onclick = async () => {
    const r = await api().installer_scegli_file(b.dataset.celho);
    if (!r) return;
    if (r.errore) { toast(t("errore"), t("ins_md5_no"), "errore", 6000); return; }
    I.archivi = await api().installer_archivi() || {}; disegnaInstaller();
  });
  box.querySelectorAll("[data-link-esterno]").forEach(b => b.onclick = () => api().apri_link(b.dataset.linkEsterno));
  box.querySelectorAll("[data-rimuovi]").forEach(b => b.onclick = () => insRimuovi(b.dataset.rimuovi));
  box.querySelectorAll("[data-riscarica]").forEach(b => b.onclick = () => insScarica(b.dataset.riscarica, true));
  const stt = $("#ins-spunta-trovati"); if (stt) stt.onclick = () => { cat.filter(c => insStato(c) === "trovato").forEach(c => I.sel.add(c.id)); disegnaInstaller(); };
  const sd = $("#ins-sc-dolphin"); if (sd) sd.onclick = async () => { await scegliCartella("dolphin"); I.dati = null; vaiA("installa"); };
  const di = $("#ins-dolphin-io"); if (di) di.onclick = () => { vaiA("gioca"); giInstallaDolphin(); };  // lo installa il launcher (si vede l'avanzamento)
  $("#ins-cerca").onclick = async () => { I.archivi = null; disegnaInstaller(); I.archivi = await api().installer_archivi() || {}; disegnaInstaller(); };
  $("#ins-sc-lib").onclick = async () => { const p = await api().installer_scegli_libreria(); if (p && !p.errore) { I.dati.libreria = p; disegnaInstaller(); } };
  $("#ins-via").onclick = insAvvia;
  const ferma = $("#ins-ferma"); if (ferma) ferma.onclick = () => api().lavoro_annulla();  // anche dopo un ridisegno
}
async function insRimuovi(id) {  // toglie un pacchetto dalla libreria (per rimetterlo serve di nuovo il suo zip)
  const c = I.dati.catalogo.file.find(x => x.id === id);
  const p = await api().installer_rimuovi(id, true);
  if (!p || p.errore) { toast(t("errore"), p ? t(p.errore) : "", "errore", 6000); return; }
  if (p.uso.length) {
    await modale({ titolo: t("ins_rim_uso_tit"), testo: t("ins_rim_uso", c.nome, p.uso.map(u => t("ins_rim_" + u)).join(", ")), bottoni: [[null, "OK", true]] });
    return;
  }
  const ok = await modale({ titolo: t("ins_rim_tit", c.nome), testo: t("ins_rim_testo", mb(p.peso)) + " " + t(p.zip ? "ins_rim_zip_si" : "ins_rim_zip_no"),
    bottoni: [[null, t("annulla"), true], [true, t("ins_rim")]] });
  if (!ok) return;
  const r = await api().installer_rimuovi(id);
  if (!r || r.errore || r.uso) { toast(t("errore"), r && r.errore ? t(r.errore) : "", "errore"); return; }
  toast(t("fatto"), t("ins_rim_ok", c.nome), "", 5000);
  I.sel.delete(id);
  S.dati = null; T.dati = null; H.dati = null; T.img = {};
  await ricarica();
  await caricaInstaller();
}
function insProgresso(st) {
  const fasi = [["estraggo", "copio", "comprimo"], ["texture", "codici"]];
  if (st.finito && !st.errore) {
    const r = st.risultato || {};
    return `<div class="ins-fine"><svg><use href="#ragno"/></svg><div><h3>${t("ins_fatto")}</h3><p>${t("ins_fatto_sub", [...I.ver].map(g => I.dati.nomi[g]).join(", "))}</p>
      ${r.trucchi === false ? `<p class="avviso">${t("ins_trucchi_no")}</p>` : ""}<p class="nota">${t("ins_invito")}</p>
      <p class="nota">${t("ins_fatto_altro")}</p>
      <div class="bottoni"><button class="primario piccolo" data-vai-pag="gioca"><svg><use href="#i-play"/></svg>${t("nav_gioca")}</button><button class="leggero" data-vai-pag="skin">${t("ins_vai_skin")}</button><button class="leggero" data-vai-pag="grafica">${t("nav_grafica")}</button></div></div></div>`;
  }
  const [tipo, nome] = (st.fase || "").split(":");
  const testo = tipo === "estraggo" ? t("ins_f_estraggo", nome) : tipo === "copio" ? t("ins_f_copio", nome) : tipo === "comprimo" ? t("ins_f_comprimo") : tipo === "doppioni" ? t("ins_f_doppioni")
    : tipo === "texture" ? t("ins_f_texture") : tipo === "codici" ? t("ins_f_codici") : "…";
  // la barra va a peso (Python manda pct): estrarre e sistemare RE dura minuti, ma la barra si muove; righe a strisce
  // che scorrono e tempo passato = si vede che sta lavorando anche quando un pezzo è lungo
  const pct = st.pct != null ? Math.round(st.pct * 100) : st.totale ? Math.round(st.fatti / st.totale * 100) : 0;
  if (!I.lavInizio) I.lavInizio = Date.now();
  const sec = Math.round((Date.now() - I.lavInizio) / 1000), tempo = `${Math.floor(sec / 60)}:${String(sec % 60).padStart(2, "0")}`;
  const pacco = (tipo === "estraggo" || tipo === "copio") && st.totale ? ` · ${t("ins_pacchetto", Math.min(st.fatti + 1, st.totale), st.totale)}${st.sub != null ? ` (${Math.round(st.sub * 100)}%)` : ""}`
    : st.totale && tipo !== "doppioni" ? ` · ${st.fatti} / ${st.totale}` : "";
  return `<div class="ins-prog"><div class="testa"><b>${testo}</b><small>${t("ins_passo", (st.passo || 0) + 1, st.passi || 2)}${pacco} · ${pct}% · ${t("ins_tempo", tempo)}</small>
      <button class="leggero" id="ins-ferma">${t("lav_annulla")}</button></div><div class="barra vivo"><i style="width:${Math.max(2, pct)}%"></i></div>
    ${st.errore ? `<p class="avviso">${st.errore}</p>` : ""}</div>`;
}
async function insScarica(id, rifai = false) {  // rifai = riscaricato apposta: poi lo spunto per reinstallarlo
  const r = await api().installer_scarica(id);
  if (!r || r.errore) return;
  I.dl[id] = { byte: 0, totale: 0 };  // più download insieme: ognuno col suo controllo
  disegnaInstaller();
  clearInterval(I.tmDl[id]);
  const inizio = Date.now();
  I.tmDl[id] = setInterval(async () => {
    const st = await api().installer_download(id);
    if (!st || st.errore) return;
    if (st.stato === "ok") {
      clearInterval(I.tmDl[id]); delete I.dl[id];
      I.archivi = await api().installer_archivi() || {};
      I.archivi[id] = st.file;
      const nome = I.dati.catalogo.file.find(c => c.id === id).nome;
      if (rifai) { I.sel.add(id); toast(t("fatto"), t("ins_riscaricato", nome), "", 8000); }
      else toast(t("fatto"), t("ins_scaricato", nome));
    } else if (st.stato === "md5" || st.stato === "errore") {
      clearInterval(I.tmDl[id]); delete I.dl[id];
      toast(t("errore"), t("ins_md5"), "errore", 7000);
    } else if (st.stato === "chiusa") {  // finestra ModDB chiusa senza scaricare: si può riprovare
      clearInterval(I.tmDl[id]); delete I.dl[id];
    } else if (st.stato === "scarico") I.dl[id] = { byte: st.byte, totale: st.totale };
    else if (Date.now() - inizio > 20 * 60000) { clearInterval(I.tmDl[id]); delete I.dl[id]; }
    if (S.pagina === "installa") disegnaInstaller();
  }, 800);
}
async function insAvvia() {
  const via = $("#ins-via");
  if (via) { if (via.disabled) return; via.disabled = true; }  // doppio clic = due installazioni
  const ids = I.dati.catalogo.file.filter(c => I.sel.has(c.id) && insDaFare(c)).map(c => c.id);
  const r = await api().installer_avvia({ ids, versioni: [...I.ver], formato: I.opz.formato, cancella: I.opz.cancella, salvataggi: I.opz.salvataggi });
  if (!r || r.errore) { if (via) via.disabled = false; toast(t("errore"), r && r.errore === "mancano" ? t("ins_manca") : errTesto(r && r.errore), "errore"); return; }
  I.lav = { fase: "", fatti: 0, totale: 0, passo: 0 };
  I.lavInizio = Date.now();
  disegnaInstaller();
  clearInterval(I.tmLav);
  I.tmLav = setInterval(async () => {
    const st = await api().lavoro_stato();
    if (!st || st.errore === undefined && !st.installer) return;
    I.lav = st;
    if (S.pagina === "installa") {
      disegnaInstaller();
      const f = $("#ins-ferma"); if (f) f.onclick = () => api().lavoro_annulla();
    }
    if (st.finito) {
      clearInterval(I.tmLav);
      if (!st.errore) {
        S.dati = null; try { await ricarica(); } catch (e) { api().log_js("dopo installazione: " + (e && e.stack || e)); }
        C.dati = null; H.dati = null; T.dati = null; G.dati = null;
        I.dati.installati = (await api().installer_stato()).installati;
        I.dati.catalogo.file.forEach(c => { if (insInstallato(c)) I.sel.delete(c.id); });  // fatti: ora risultano "Installato"
        I.archivi = await api().installer_archivi() || {};
        disegnaInstaller();
      }
    }
  }, 700);
}

// ================================================================ texture personalizzate (cartelloni, giornali, ...)
// Ogni file ha un "proprietario": "re" (Spider-Man 2: RE), l'id di un pacchetto, "gioco" (nessun file = originale)
// o "?" (file messo a mano). T.vuole = le scelte non ancora applicate (nome file -> proprietario).
const T = { dati: null, vuole: {}, sel: null, img: {}, zoom: null, filtro: "tutte", cerca: "", quante: 0 };
const txVoce = id => T.dati.voci.find(v => v.id === id);
const txEff = f => f in T.vuole ? T.vuole[f] : T.dati.prop[f];
const txAttive = v => v.file.reduce((n, f) => n + (txEff(f) === v.id), 0);
const txAcceso = v => txAttive(v) > 0;
const txNome = v => v.id === "re" ? v.nome : `${v.nome} (${v.mod})`;
const txReF = () => new Set((txVoce("re") || { file: [] }).file);
const txNuove = v => { const r = txReF(); return v.id === "re" ? [] : v.file.filter(f => !r.has(f)); };  // texture che RE non ha
const txModo = v => (T.dati.modi || {})[v.id] === "nuove" ? "nuove" : "tutte";  // preferenza: cosa accende l'interruttore
function txModoVisto(v) {  // cosa è acceso davvero: "tutte", "nuove" o null (scelte a mano); spento = la preferenza
  if (!txAcceso(v)) return txModo(v);
  const reF = txReF();
  if (v.file.every(f => txEff(f) === v.id)) return "tutte";
  return v.file.every(f => (txEff(f) === v.id) === !reF.has(f)) ? "nuove" : null;
}
const txPasso = 150;  // texture mostrate alla volta nella galleria (RE ne ha più di 4000)
async function caricaTexture() {
  let tmBarra = null;
  if (!T.dati) {
    $("#tx-lista").innerHTML = `<div class="tx-carica"><div class="rotella"></div><span>${t("tx_analizzo")}</span>
      <div class="tx-carica-barra"><div class="tx-carica-p"></div></div><small class="tx-barra-n"></small></div>`;
    tmBarra = setInterval(async () => {  // quante texture ho già controllato (la prima volta legge migliaia di file)
      const a = await api().texture_avanzamento(), b = $("#tx-lista .tx-carica-barra");
      if (!a || !b || !a.tot) return;
      const pct = Math.min(100, Math.round(a.fatti / a.tot * 100));
      b.querySelector(".tx-carica-p").style.width = pct + "%";
      $("#tx-lista .tx-barra-n").textContent = `${t(a.fase === "pacchetti" ? "tx_fase_pacchetti" : "tx_fase_dolphin")} · ${a.fatti.toLocaleString()} / ${a.tot.toLocaleString()} · ${pct}%`;
    }, 200);
  }
  const r = await api().texture_stato();
  clearInterval(tmBarra);
  if (!r || r.errore) { toast(t("errore"), errTesto(r && r.errore), "errore"); return; }
  T.dati = r; T.vuole = {}; T.modi0 = { ...(r.modi || {}) };
  if (!T.sel || !txVoce(T.sel)) T.sel = (r.voci.find(v => v.id !== "re") || r.voci[0] || {}).id;
  disegnaTexture();
}
function txMetti(f, chi) { if (chi === T.dati.prop[f]) delete T.vuole[f]; else T.vuole[f] = chi; }
function txRiserva(f, tranne) {  // chi prende il file quando "tranne" lo lascia
  const altro = T.dati.voci.find(x => x.id !== tranne && x.id !== "re" && x.file.includes(f) && txAcceso(x));
  if (altro) return altro.id;
  const re = txVoce("re");
  return tranne !== "re" && re && re.file.includes(f) && txAcceso(re) ? "re" : "gioco";
}
function txPacchetto(v, on) {
  if (on && v.id === "re") v.file.forEach(f => { if (txEff(f) === "gioco") txMetti(f, "re"); });
  else if (on) {
    const reF = txReF(), solo = txModo(v) === "nuove" && txNuove(v).length;
    const prende = solo ? v.file.filter(f => !reF.has(f)) : v.file;  // "solo nuove": quelle di RE restano a RE
    const altri = T.dati.voci.filter(x => x.id !== v.id && x.id !== "re" && txAcceso(x))
      .map(x => [x, prende.filter(f => txEff(f) === x.id).length]).filter(([, n]) => n);
    prende.forEach(f => txMetti(f, v.id));
    if (solo) v.file.forEach(f => { if (reF.has(f) && txEff(f) === v.id) txMetti(f, txRiserva(f, v.id)); });
    if (altri.length) toast(t("tx_comune_tit"), altri.map(([x, n]) => t("tx_comune", n, txNome(x))).join(" "), "avviso", 6000);
  } else v.file.forEach(f => { if (txEff(f) === v.id) txMetti(f, txRiserva(f, v.id)); });
  disegnaTexture();
}
function txFile(v, f, on) {
  txMetti(f, on ? v.id : txRiserva(f, v.id));
  disegnaTexture();
}
function txTuttoRe() {  // pacchetti spenti, Spider-Man 2: RE dappertutto
  const re = txVoce("re");
  for (const v of T.dati.voci) for (const f of v.file) txMetti(f, re && re.file.includes(f) ? "re" : "gioco");
  disegnaTexture();
}
function txStato(v) {  // [classe, testo]
  const n = txAttive(v), tot = v.file.length;
  if (!n) return ["", t("tx_spento")];
  return n < tot ? ["parte", t("tx_parte", n, tot)] : ["on", t("tx_attivo")];
}
async function txCopertina(id, img) {
  const k = "c|" + id;
  if (!T.img[k]) T.img[k] = await api().texture_copertina(id);
  if (typeof T.img[k] === "string") { img.src = T.img[k]; img.classList.add("pronta"); }
}
function disegnaTexture() {
  if (!T.dati) return;
  const lista = $("#tx-lista"), scroll = lista.scrollTop;
  const reSet = new Set((txVoce("re") || { file: [] }).file);
  const tuttoRe = T.dati.voci.every(v => v.file.every(f => txEff(f) === (reSet.has(f) ? "re" : "gioco")));
  lista.innerHTML = `<div class="tx-barra"><b>${t("tx_pacchetti")}</b><button class="leggero" id="tx-re" ${tuttoRe ? "disabled" : ""}>${t("tx_tutto_re")}</button>
    <button class="leggero piu" data-tip="agg_tit_texture"><svg><use href="#i-piu"/></svg>${t("agg_bottone")}</button></div>`;
  lista.querySelector("#tx-re").onclick = txTuttoRe;
  lista.querySelector(".tx-barra .piu").onclick = () => aggiungi("texture");
  if (T.dati.voci.length <= 1) lista.insertAdjacentHTML("beforeend", `<div class="nota-sez">${t("tx_nessuno")}</div>`);
  for (const v of T.dati.voci) {
    const [cls, testo] = txStato(v);
    const cambiati = v.file.some(f => f in T.vuole && (T.vuole[f] === v.id || T.dati.prop[f] === v.id));
    const c = document.createElement("div");
    c.className = "tx-carta" + (v.id === "re" ? " re" : "") + (v.id === T.sel ? " selezionata" : "") + (cambiati ? " cambiato" : "");
    c.tabIndex = 0;
    c.innerHTML = `<div class="tx-cop">${v.id === "re" ? `<svg><use href="#ragno"/></svg>` : `<img alt="">`}</div>
      <div class="tx-testo"><b title="${v.nome}">${v.nome}</b><small>${v.id === "re" ? t("tx_re_sub") : v.mod} · ${t("tx_n", v.file.length)}${txModoVisto(v) === "nuove" && txNuove(v).length ? " · " + t("tx_modo_nuove").toLowerCase() : ""}</small>
        <span class="tx-badge ${cls}">${testo}</span></div>
      <label class="interruttore"><input type="checkbox" ${txAcceso(v) ? "checked" : ""}><span></span></label>`;
    c.onclick = e => { if (e.target.closest(".interruttore") || T.sel === v.id) return; T.sel = v.id; T.quante = txPasso; T.filtro = "tutte"; T.cerca = ""; disegnaTexture(); };
    c.onkeydown = e => { if (e.key === "Enter") c.click(); };
    c.querySelector("input").onchange = e => txPacchetto(v, e.target.checked);
    if (v.id !== "re") txCopertina(v.id, c.querySelector("img"));
    lista.appendChild(c);
  }
  if (T.dati.estranei) lista.insertAdjacentHTML("beforeend", `<p class="nota">${t("tx_estranei", T.dati.estranei)}</p>`);
  lista.scrollTop = scroll;
  txDettaglio();
  piedeTexture();
}
function txVisibili(v) {
  const q = T.cerca.trim().toLowerCase().replace("×", "x");
  const reF = T.filtro === "nuove" ? txReF() : null;
  return v.file.filter(f => (T.filtro === "tutte" || (reF ? !reF.has(f) : (T.filtro === "on") === (txEff(f) === v.id))) && (!q || f.toLowerCase().includes(q)));
}
let txOsserva = null;
function txDettaglio() {
  const box = $("#tx-dettaglio"), v = T.sel && txVoce(T.sel);
  if (!v) { box.innerHTML = ""; return; }
  const [cls, testo] = txStato(v), re = v.id === "re";
  const stessa = box.dataset.id === v.id;
  const gal0 = stessa && box.querySelector(".tx-galleria") ? box.querySelector(".tx-galleria").scrollTop : 0;
  const cercaFocus = stessa && document.activeElement && document.activeElement.id === "tx-cerca";
  box.dataset.id = v.id;
  if (!stessa) T.quante = txPasso;
  const nuove = txNuove(v).length, modi = nuove && nuove < v.file.length;  // ha sia texture nuove sia rifatte di RE
  if (T.filtro === "nuove" && !nuove) T.filtro = "tutte";
  const vis = txVisibili(v), n = txAttive(v);
  box.innerHTML = `<div class="tx-testa"><div><div class="etichette"><span class="etichetta">${v.mod}</span><span class="etichetta ${cls === "on" ? "verde" : cls ? "giallo" : ""}">${testo}</span></div>
      <h2>${v.nome}</h2><div class="crediti">${t("crediti", v.crediti)} <span class="link" data-link="${v.link}">${t("pagina_moddb")}</span></div></div>
      <label class="interruttore grande"><input type="checkbox" ${n ? "checked" : ""}><span></span></label></div>
    ${re && n < v.file.length ? `<div class="patch-barra no"><svg><use href="#i-ingr"/></svg><span>${t("tx_re_off_info")}</span></div>` : ""}
    ${modi ? `<div class="tx-modo"><div><b>${t("tx_modo")}</b><p>${t("tx_modo_sub")}</p></div>
      <div class="ordine">${["tutte", "nuove"].map(m => `<button data-modo="${m}" class="${txModoVisto(v) === m ? "attivo" : ""}">${t("tx_modo_" + m)} <i>${m === "tutte" ? v.file.length : nuove}</i></button>`).join("")}</div></div>` : ""}
    <div class="tx-filtri"><div class="ordine">${["tutte", "on", "off"].concat(nuove ? ["nuove"] : []).map(x => `<button data-f="${x}" class="${T.filtro === x ? "attivo" : ""}">${t("tx_f_" + x)}</button>`).join("")}</div>
      <div class="cerca piccola"><svg><use href="#i-cerca"/></svg><input id="tx-cerca" autocomplete="off" placeholder="${t("tx_cerca")}" value="${T.cerca.replace(/"/g, "&quot;")}"></div>
      <span class="nota">${t(re ? "tx_confronta_re" : "tx_confronta")}</span></div>
    <div class="tx-galleria${re ? " singole" : ""}">${vis.slice(0, T.quante).map(f => {
      const on = txEff(f) === v.id, dim = (f.match(/^tex1_(\d+x\d+)/) || [])[1] || "";
      return `<div class="tx-coppia${on ? "" : " spenta"}${f in T.vuole ? " cambiato" : ""}" data-f="${f}">
        <div class="tx-imm">${re ? `<img class="b" alt="">` : `<img class="a" alt=""><i>→</i><img class="b" alt="">`}</div>
        ${re ? "" : `<div class="tx-etich"><span>Spider-Man 2: RE</span><i></i><span class="pk" title="${txNome(v)}">${v.nome}</span></div>`}
        <small>${re ? `<span class="nome-f" title="${f}">${dim.replace("x", "×")}</span>` : `<em>${dim.replace("x", "×")}</em>`}
          <label class="interruttore mini" title="${t(on ? "tx_spegni_una" : "tx_accendi_una")}"><input type="checkbox" ${on ? "checked" : ""}><span></span></label></small></div>`;
    }).join("")}${vis.length > T.quante ? `<div class="tx-altre"><div class="rotella"></div></div>` : ""}${!vis.length ? `<div class="nota-sez">${t("tx_vuoto")}</div>` : ""}</div>`;
  const gal = box.querySelector(".tx-galleria");
  gal.scrollTop = gal0;
  box.querySelector(".tx-testa .interruttore input").onchange = e => txPacchetto(v, e.target.checked);
  box.querySelectorAll(".tx-filtri [data-f]").forEach(b => b.onclick = () => { T.filtro = b.dataset.f; T.quante = txPasso; txDettaglio(); });
  box.querySelectorAll("[data-modo]").forEach(b => b.onclick = () => {
    if (txModoVisto(v) === b.dataset.modo && txModo(v) === b.dataset.modo) return;
    T.dati.modi = { ...(T.dati.modi || {}), [v.id]: b.dataset.modo };
    api().texture_modo(v.id, b.dataset.modo);
    if (txAcceso(v)) txPacchetto(v, true); else disegnaTexture();
  });
  const ce = $("#tx-cerca");
  ce.oninput = () => { T.cerca = ce.value; T.quante = txPasso; txDettaglio(); };
  if (cercaFocus) { ce.focus(); ce.setSelectionRange(ce.value.length, ce.value.length); }
  box.querySelectorAll(".tx-coppia").forEach(b => {
    b.onclick = e => { if (!e.target.closest(".interruttore")) txZoom(v.id, vis.indexOf(b.dataset.f), vis); };
    b.querySelector("input").onchange = e => txFile(v, b.dataset.f, e.target.checked);
  });
  // immagini solo quando si vedono; in fondo alla galleria se ne aggiungono altre
  if (txOsserva) txOsserva.disconnect();
  txOsserva = new IntersectionObserver(voci => voci.forEach(x => {
    if (!x.isIntersecting) return;
    txOsserva.unobserve(x.target);
    if (x.target.classList.contains("tx-altre")) { T.quante += txPasso; txDettaglio(); return; }
    txCarica(v, x.target);
  }), { root: gal, rootMargin: "300px" });
  gal.querySelectorAll(".tx-coppia, .tx-altre").forEach(x => txOsserva.observe(x));
}
let txCoda = Promise.resolve();
function txCarica(v, b) {
  const f = b.dataset.f, k = v.id + "|" + f;
  const metti = r => {
    if (!r || r.errore || !b.isConnected) return;
    const a = b.querySelector(".a");
    if (a) { if (r.uff) a.src = r.uff; else { a.classList.add("vuota"); b.querySelector(".tx-etich span").textContent = t("tx_gioco"); } }
    b.querySelector(".b").src = r.nuova;
    if (!b.querySelector(".nome-f")) b.querySelector("em").textContent = r.dim;
    b.classList.add("pronta");
  };
  if (T.img[k]) { metti(T.img[k]); return; }
  txCoda = txCoda.then(async () => {  // una alla volta: la pagina resta fluida
    if (!b.isConnected) return;
    if (!T.img[k]) T.img[k] = await api().texture_coppia(v.id, f, v.id === "re" ? 260 : 420);
    metti(T.img[k]);
  });
}
async function txZoom(id, i, lista) {
  const v = txVoce(id);
  lista = lista || (T.zoom && T.zoom.lista) || v.file;
  const n = lista.length;
  if (!n) return;
  i = (i + n) % n;
  T.zoom = { id, i, lista };
  const z = $("#tx-zoom"), f = lista[i];
  z.classList.remove("nascosto");
  z.querySelector(".tx-zoom-testa b").textContent = txNome(v);
  z.querySelector(".tx-zoom-testa span").textContent = `${i + 1} / ${n}`;
  z.querySelector(".lab-sx").textContent = "Spider-Man 2: RE";
  z.querySelector(".lab-dx").textContent = txNome(v);
  z.querySelector("p").textContent = t(id === "re" ? "tx_trascina_re" : "tx_trascina");
  const k = id + "|" + f + "|big";
  if (!T.img[k]) T.img[k] = await api().texture_coppia(id, f, 1024);
  if (!T.zoom || T.zoom.i !== i || T.zoom.id !== id) return;
  const r = T.img[k];
  z.querySelector(".tx-confronto").classList.toggle("singola", !r.uff);
  z.querySelector(".sotto").src = r.uff || r.nuova;
  z.querySelector(".sopra img").src = r.nuova;
  z.querySelector(".tx-zoom-testa span").textContent = `${i + 1} / ${n} · ${r.dim} · ${f}`;
  txTaglio(r.uff ? 50 : 0);
}
function txTaglio(p) {
  const z = $("#tx-zoom");
  z.querySelector(".sopra").style.clipPath = `inset(0 0 0 ${p}%)`;
  z.querySelector(".manico").style.left = p + "%";
}
function chiudiZoom() { T.zoom = null; $("#tx-zoom").classList.add("nascosto"); }
function txRiassunto() {  // per pacchetto: texture che prende (+) e che lascia (−)
  const per = {};
  for (const [f, chi] of Object.entries(T.vuole)) {
    const prima = T.dati.prop[f];
    for (const [id, seg] of [[chi, "+"], [prima, "-"]]) {
      if (!txVoce(id)) continue;
      per[id] = per[id] || { "+": 0, "-": 0 };
      per[id][seg]++;
    }
  }
  return per;
}
function piedeTexture() {
  if (S.pagina !== "texture") return;
  const box = $("#modifiche");
  box.innerHTML = "";
  const per = T.dati ? txRiassunto() : {};
  const ids = Object.keys(per);
  if (!ids.length) {
    box.innerHTML = `<div class="tutto-ok"><svg><use href="#i-ok"/></svg>${t("tutto_salvato")}</div>`;
    $("#piede").classList.add("nascondi-azioni");
    return;
  }
  $("#piede").classList.remove("nascondi-azioni");
  for (const id of ids.slice(0, 5)) {
    const v = txVoce(id), p = per[id], m = document.createElement("div");
    const tutto = txAttive(v) === v.file.length && p["+"] ? t("acceso") : !txAttive(v) && p["-"] ? t("spento") : [p["+"] ? "+" + p["+"] : "", p["-"] ? "−" + p["-"] : ""].filter(Boolean).join(" ");
    m.className = "mod";
    m.innerHTML = `${txNome(v)}: <b>${tutto}</b><button>×</button>`;
    m.querySelector("button").onclick = () => {
      for (const [f, chi] of Object.entries(T.vuole)) if (chi === id || T.dati.prop[f] === id) delete T.vuole[f];
      disegnaTexture();
    };
    box.appendChild(m);
  }
  if (ids.length > 5) box.insertAdjacentHTML("beforeend", `<span>+${ids.length - 5}</span>`);
}
async function applicaTexture() {
  if (!T.dati || !Object.keys(T.vuole).length) return;
  const r = await conBarra(t("applico_tx"), async fase => {
    const r = await api().texture_applica(T.vuole);
    if (r && !r.errore) { fase(t("applico_controllo"), 0.95); await caricaTexture(); }  // la pagina si aggiorna da sola
    return r;
  });
  if (!r || r.errore) { disegnaTexture(); toast(t("errore"), errTesto(r && r.errore), "errore"); return; }
  G.dati = null;  // la RAM delle texture è cambiata
  if (r.comprimo) seguiLavoro();
  const testo = r.copiati + r.cancellati ? t("fatto_testo", r.copiati, r.cancellati, r.cartelle.join(", ")) : t("niente_da_fare");
  toast(t("fatto"), testo + (r.dolphin_aperto ? " " + t("riavvia") : ""), r.dolphin_aperto ? "avviso" : "", r.dolphin_aperto ? 7000 : 4500);
}
function avviaZoom() {
  const z = $("#tx-zoom"), conf = z.querySelector(".tx-confronto");
  let tiro = false;
  const muovi = e => { if (conf.classList.contains("singola")) return; const b = conf.getBoundingClientRect(); txTaglio(Math.max(0, Math.min(100, (e.clientX - b.left) / b.width * 100))); };
  conf.onpointerdown = e => { tiro = true; conf.setPointerCapture(e.pointerId); muovi(e); };
  conf.onpointermove = e => { if (tiro) muovi(e); };
  conf.onpointerup = () => { tiro = false; };
  z.onclick = e => { if (e.target === z) chiudiZoom(); };
  z.querySelector(".tondo").onclick = chiudiZoom;
  document.addEventListener("keydown", e => {
    if (!T.zoom) return;
    if (e.key === "Escape") { e.stopImmediatePropagation(); chiudiZoom(); }
    else if (e.key === "ArrowRight") txZoom(T.zoom.id, T.zoom.i + 1);
    else if (e.key === "ArrowLeft") txZoom(T.zoom.id, T.zoom.i - 1);
  }, true);
}
// ================================================================ grafica (impostazioni di Dolphin per il gioco)
const G = { dati: null, mod: {}, target: "pc", vals: {}, mods: { pc: {}, android: {}, mac: {} }, pers: false };
const BACKEND_AND = [["Vulkan", "Vulkan"], ["OGL", "OpenGL"]];
const BACKEND_MAC = [["Metal", "Metal"], ["Vulkan", "Vulkan (MoltenVK)"], ["OGL", "OpenGL"]];
const PRESET_MAC = [  // base: Apple Silicon (M1-M4); Metal ovunque, JIT spento sui chip ARM
  ["macarm", "i-bilancia", { res: 4, msaa: 1, aniso: 2, shader: 2, attendi: true, hd: true, cache: true, backend: "Metal", oc_on: true, oc: 3, jit: false }],
  ["macpro", "i-stella", { res: 6, msaa: 2, aniso: 4, shader: 2, attendi: true, hd: true, cache: true, backend: "Metal", oc_on: true, oc: 3, jit: false }],
  ["macintel", "i-piuma", { res: 2, msaa: 1, aniso: 0, shader: 3, attendi: true, hd: true, cache: false, backend: "Metal", oc_on: true, oc: 3, jit: true }],
];
const PRESET_ANDROID = [  // base: Snapdragon 8 Gen 2 (Retroid Pocket 6); da lì si sale o si scende
  ["s8g2", "i-bilancia", { res: 3, msaa: 1, aniso: 0, shader: 2, attendi: true, hd: true, cache: true, backend: "Vulkan", oc_on: true, oc: 3, fps30: false, jit: false }],
  ["andpot", "i-stella", { res: 4, msaa: 2, aniso: 2, shader: 2, attendi: true, hd: true, cache: true, backend: "Vulkan", oc_on: true, oc: 3, fps30: false, jit: false }],
  ["andleg", "i-piuma", { res: 2, msaa: 1, aniso: 0, shader: 3, attendi: true, hd: true, cache: false, backend: "Vulkan", oc_on: false, fps30: true, jit: false }],
];
function gTarget(x) { G.target = x; G.dati.valori = G.vals[x]; G.mod = G.mods[x]; disegnaGrafica(); }
const RISOLUZIONI = [[1, "480p"], [2, "720p"], [3, "1080p"], [4, "1440p"], [5, "1800p"], [6, "4K"], [8, "5K"]];
const BACKEND = [["Vulkan", "Vulkan"], ["D3D12", "Direct3D 12"], ["D3D", "Direct3D 11"], ["OGL", "OpenGL"]];
const FORMATI = [[1, "16:9"], [2, "4:3"], [3, "gr_adatta"], [0, "gr_auto"]];
function schermoTuo() {
  const w = Math.round(screen.width * devicePixelRatio), h = Math.round(screen.height * devicePixelRatio);
  return { w, h, res: h <= 800 ? 2 : h <= 1080 ? 3 : h <= 1440 ? 4 : h <= 1800 ? 5 : h <= 2160 ? 6 : 8 };
}
function presetGrafica() {
  if (G.target === "android") return PRESET_ANDROID;
  if (G.target === "mac") return PRESET_MAC;
  // uno per schermo: la risoluzione interna giusta per quello schermo (come le indica Dolphin: 3x = 1080p, 4x = 1440p,
  // 6x = 4K), il resto uguale e già pensato per Spider-Man 2 (ubershader asincroni = niente scatti la prima volta)
  const base = { formato: 1, msaa: 2, ssaa: false, aniso: 4, shader: 2, attendi: true, hd: true, cache: true, backend: "Vulkan", vsync: true, dual: true, jit: !G.dati.arm };
  return [
    ["fhd", "i-schermo", { ...base, res: 3 }],
    ["qhd", "i-schermo", { ...base, res: 4 }],
    ["uhd", "i-schermo", { ...base, res: 6 }],
  ];
}
function gCpu() { return G.cpuScelta || (G.dati && G.dati.cpu_scelta) || (G.dati && G.dati.cpu ? G.dati.cpu.livello : "recente"); }
function presetConsigliato() {  // quello del tuo schermo
  if (G.target === "android") return "s8g2";
  if (G.target === "mac") return "macarm";
  const h = schermoTuo().h;
  return h <= 1200 ? "fhd" : h <= 1600 ? "qhd" : "uhd";
}
const gEff = k => k in G.mod ? G.mod[k] : G.dati.valori[k];
function gImposta(nuovi, ridisegna = true) {
  if (nuovi.globali) for (const k of Object.keys(G.mod)) if (k !== "intero" && k !== "bordi") delete G.mod[k];
  for (const [k, v] of Object.entries(nuovi)) {
    if (v === G.dati.valori[k]) delete G.mod[k]; else G.mod[k] = v;
  }
  if (ridisegna) disegnaGrafica(); else piedeGrafica();
}
const gb = (n, tondo) => n >= 2 ** 30 ? (n / 2 ** 30).toFixed(tondo ? 0 : 1).replace(".", L === "en" ? "." : ",") + " GB" : Math.round(n / 2 ** 20) + " MB";
function gValore(k, v) {  // testo breve di un valore (barra delle modifiche)
  if (k === "res") return `${v}× (${RISOLUZIONI.find(x => x[0] === v)?.[1] ?? ""})`;
  if (k === "formato") { const f = FORMATI.find(x => x[0] === v); return f ? (f[1].includes(":") ? f[1] : t(f[1])) : v; }
  if (k === "msaa") return v > 1 ? v + "×" : t("gr_no");
  if (k === "aniso") return 2 ** v + "×";
  if (k === "backend") return [...BACKEND, ...BACKEND_MAC].find(x => x[0] === v)?.[1] ?? v;
  if (k === "shader") return t("gr_sh_" + v);
  if (k === "oc") return gEff("oc_on") ? Math.round(gEff("oc") * 100) + "%" : t("spento");
  if (k === "tex") return String(v).toUpperCase();
  return v ? t("acceso") : t("spento");
}
async function caricaGrafica() {
  const r = await api().grafica_stato();
  if (!r || r.errore) { toast(t("errore"), errTesto(r && r.errore), "errore"); return; }
  r.valori.globali = r.globali;
  G.vals = { pc: r.valori, android: { ...r.android }, mac: { ...r.mac } };
  G.mods = { pc: {}, android: {}, mac: {} };
  G.dati = r;
  // "Personalizza a mano": la scelta salvata; la prima volta acceso solo se le impostazioni non sono un preset
  G.pers = r.avanzata === true;  // personalizzazione avanzata, di base spenta: le impostazioni tecniche restano bloccate (l'immagine no)
  G.dati.valori = G.vals[G.target]; G.mod = G.mods[G.target];
  disegnaGrafica();
}
function disegnaGrafica() {
  if (!G.dati) return;
  const box = $("#gr-lista"), scroll = box.scrollTop, and = G.target === "android", mac = G.target === "mac", zip = and || mac;
  const sch = zip ? { res: mac ? 4 : 3 } : schermoTuo();
  const seg = (k, opz, cons) => `<div class="seg" data-k="${k}">${opz.map(([v, n]) =>
    `<button data-v='${JSON.stringify(v)}' class="${gEff(k) === v ? "attivo" : ""}">${n}${v === cons ? '<i class="stellina">★</i>' : ""}</button>`).join("")}</div>`;
  const tog = (k, dis = false) => `<label class="interruttore"><input type="checkbox" data-k="${k}" ${gEff(k) ? "checked" : ""} ${dis ? "disabled" : ""}><span></span></label>`;
  const glob = !zip && gEff("globali");
  // sempre cambiabili: il gruppo Immagine (quello che chiunque può voler toccare), le azioni immediate e le opzioni
  // "per casi particolari" (stanno già in un riquadro a parte). Il resto solo con la personalizzazione avanzata.
  const libere = ["res", "formato", "aa,msaa", "ssaa", "aniso", "intero", "bordi", "osd", "fps", "dds", "fps30", "dual", "jit"];
  const riga = (k, corpo, { sub, lato, cls = "" } = {}) => {
    const cambiato = k.split(",").some(x => x in G.mod);
    if (glob && !["intero", "bordi", "osd", "dds", "fps30"].includes(k)) cls += " bloccato";
    else if (!G.pers && !libere.includes(k)) cls += " chiuso";
    return `<div class="gr-riga ${cls}${cambiato ? " cambiato" : ""}"><div class="testa"><div><b>${t("gr_" + k.split(",")[0])}</b><p>${sub ?? t("gr_" + k.split(",")[0] + "_sub")}</p></div>${lato || ""}</div>${corpo || ""}</div>`;
  };
  // preset
  const pres = presetGrafica();
  const attivo = pres.find(([, , v]) => Object.entries(v).every(([k, x]) => gEff(k) === x));
  const ICONA_T = { pc: "i-pc", android: "i-telefono", mac: "i-portatile" };
  let h = `<div class="gr-target ordine">${["pc", "android", "mac"].map(x => `<button data-target="${x}" class="${G.target === x ? "attivo" : ""}"><svg><use href="#${ICONA_T[x]}"/></svg>${t("gr_t_" + x)}${Object.keys(G.mods[x]).length ? ' <i class="punto-mod"></i>' : ""}</button>`).join("")}</div>`;
  if (!zip) h += `<div class="gr-globali${glob ? " on" : ""}${"globali" in G.mod ? " cambiato" : ""}"><svg><use href="#ragno"/></svg>
      <div><b>${t("gr_globali")} <i class="sconsigliato">${t("gr_sconsigliato")}</i></b><p>${t(glob ? "gr_globali_sub" : "gr_globali_off_sub")}</p></div>${tog("globali")}</div>`;
  const cons = presetConsigliato();
  h += `<div class="gr-preset${glob ? " bloccato" : ""}">${pres.map(([id, ic]) => `<button data-preset="${id}" class="${!glob && attivo && attivo[0] === id ? "attivo" : ""}">
      <svg><use href="#${ic}"/></svg><div><b>${t("gr_p_" + id)}${id === cons ? `<i class="cons">${t(zip ? "ins_obbligatorio" : "gr_tuo_schermo")}</i>` : ""}</b><small>${t("gr_p_" + id + "_sub")}</small></div></button>`).join("")}
    <div class="pers ${!glob && !attivo ? "attivo" : ""}"><svg><use href="#i-pers"/></svg><div><b>${t("gr_p_pers")}</b><small>${t("gr_p_pers_sub")}</small></div></div></div>`;
  if (!zip && !glob) {  // processore: datato / recente / potente = overclock della CPU emulata (riconosciuto da solo)
    const tuo = G.dati.cpu.livello, sc = gCpu();
    h += `<div class="gr-cpu"><svg><use href="#i-fulmine"/></svg><div class="gr-cpu-t"><b>${t("gr_cpu")}</b><small>${t("gr_cpu_tuo", G.dati.cpu.nome)}</small></div>
      <div class="seg">${["datato", "recente", "potente"].map(k => `<button data-cpu="${k}" class="${sc === k ? "attivo" : ""}">${t("gr_cpu_" + k)}<small>${Math.round(G.dati.oc_cpu[k] * 100)}%</small>${k === tuo ? '<i class="stellina">★</i>' : ""}</button>`).join("")}</div></div>`;
  }
  if (!glob) h += `<div class="gr-pers${G.pers ? " on" : ""}"><svg><use href="#i-pers"/></svg><div><b>${t("gr_pers")}</b><p>${t("gr_pers_sub")}</p></div>
      <label class="interruttore"><input type="checkbox" id="gr-pers" ${G.pers ? "checked" : ""}><span></span></label></div>`;
  if (zip) h += `<div class="gr-info"><span>${t(mac ? "gr_mac_info" : "gr_and_info")}</span></div>`;
  else h += `<div class="gr-info"><span class="vale">${t("gr_vale_per")}: ${G.dati.versioni.map(v => `<i>${v}</i>`).join("")}</span><span>${t("gr_prossimo")}</span></div>`;
  if (!and && G.dati.diverse) h += `<div class="patch-barra no"><svg><use href="#i-ingr"/></svg><span>${t("gr_diverse")}</span></div>`;
  // immagine
  const res = `<div class="res-griglia" data-k="res">${RISOLUZIONI.map(([v, n]) => `<button data-v="${v}" class="${gEff("res") === v ? "attivo" : ""}">
      ${v === sch.res ? '<i class="stellina">★</i>' : ""}<b>${v}×</b><small>${n}</small></button>`).join("")}</div>`;
  const oc = gEff("oc_on") ? Math.round(gEff("oc") * 100) : 100;
  const pct = (oc - 100) / 3;
  const tanta = G.dati.peso_tex > G.dati.ram * 0.3;
  h += `<div class="gr-griglia">
    <div class="gr-gruppo"><h3><svg><use href="#i-immagine"/></svg>${t("gr_g_immagine")}</h3>
      ${riga("res", res, { sub: t("gr_res_sub") + " " + (mac ? t("gr_mac_res") : and ? t("gr_and_res") : t("gr_schermo_tuo", sch.w + "×" + sch.h)) })}
      ${riga("formato", seg("formato", FORMATI.map(([v, n]) => [v, n.includes(":") ? n : t(n)]), 1), { cls: ![1, 2].includes(gEff("formato")) ? "allarme" : "" })}
      ${riga("aa,msaa", seg("msaa", [[1, t("gr_no")], [2, "2×"], [4, "4×"], [8, "8×"]]))}
      ${riga("ssaa", "", { lato: tog("ssaa") })}
      ${riga("aniso", seg("aniso", [0, 1, 2, 3, 4].map(v => [v, 2 ** v + "×"]), 4))}
    </div>
    <div class="gr-gruppo"><h3><svg><use href="#i-fulmine"/></svg>${t("gr_g_fluidita")}</h3>
      ${riga("backend", seg("backend", mac ? BACKEND_MAC : and ? BACKEND_AND : BACKEND, mac ? "Metal" : "Vulkan"), mac ? { sub: t("gr_backend_mac_sub") } : {})}
      ${riga("shader", seg("shader", [2, 3, 1, 0].map(v => [v, t("gr_sh_" + v)]), 2), { sub: t("gr_sh_" + gEff("shader") + "_sub") })}
      ${riga("attendi", "", { lato: tog("attendi") })}
      ${riga("oc,oc_on", `<div class="cella gr-oc"><input type="range" id="gr-oc" min="100" max="400" step="25" value="${oc}" style="--pct:${pct}%"><b id="gr-oc-v">${oc > 100 ? oc + "%" : t("spento")}</b></div>`, oc > 100 ? (zip ? { sub: t("gr_oc_zip_sub") } : {}) : { sub: t(zip ? "gr_oc_zip_sub" : "gr_oc_sub") + " " + t("gr_oc_off"), cls: "allarme" })}
      ${riga("vsync", "", { lato: tog("vsync") })}
    </div>
    <div class="gr-gruppo"><h3><svg><use href="#i-skin"/></svg>${t("gr_g_texture")}</h3>
      ${riga("hd", "", { lato: tog("hd"), sub: gEff("hd") ? t("gr_hd_sub") : t("gr_hd_off"), cls: gEff("hd") ? "" : "allarme" })}
      ${zip ? riga("cache", "", { lato: tog("cache", !gEff("hd")), sub: t(mac ? "gr_cache_mac_sub" : "gr_cache_and_sub") })
            : riga("cache", "", { lato: tog("cache", !gEff("hd")), sub: t("gr_cache_sub", gb(G.dati.peso_tex), gb(G.dati.ram, true)) + (tanta ? " " + t("gr_cache_tanta") : ""), cls: tanta && gEff("cache") ? "allarme" : "" })}
      ${zip ? riga("tex", seg("tex", [["dds", "DDS"], ["png", "PNG"]]), mac ? { sub: t("gr_tex_mac_sub") } : {}) : ""}
      ${zip ? "" : (() => {  // compressione DDS: azione immediata (lavoro lungo), non passa da Applica
        const c = G.dati.comp;
        if (!c.texconv) return riga("dds", "", { sub: t("gr_dds_no"), cls: "allarme" });
        if (!c.png && !c.dds) return riga("dds", "", { sub: t("gr_dds_gia", gb(G.dati.peso_tex)) });  // libreria già tutta DDS
        const stato = c.dds ? `<div class="gr-dds-stato">${t("gr_dds_stato", c.dds, c.png)}${c.attiva ? " · " + t("gr_dds_auto") : ""}</div>` : "";
        const bott = `<div class="bottoni gr-dds">${c.dds ? `<button class="leggero" data-dds="png">${t("gr_dds_png")}</button>` : ""}${c.png ? `<button class="primario piccolo" data-dds="dds">${t("gr_dds_comprimi")}</button>` : ""}</div>`;
        return riga("dds", stato, { sub: t("gr_dds_sub", gb(G.dati.peso_dds), gb(G.dati.peso_tex)), lato: bott });
      })()}
    </div>
    <div class="gr-gruppo"><h3><svg><use href="#i-grafica"/></svg>${t("gr_g_schermo")}</h3>
      ${riga("fps", "", { lato: tog("fps") })}
      ${zip ? "" : riga("osd", "", { lato: tog("osd") })}
      ${zip ? "" : riga("intero", "", { lato: tog("intero") })}
      ${zip ? "" : riga("bordi", "", { lato: tog("bordi") })}
    </div>
  </div>`;
  // per casi particolari: chi gioca a 30 fps, chi ha un processore ARM, chi ha problemi col dual core. Quasi nessuno
  // le tocca: riquadro a parte, chiuso di base (si apre da solo se una di queste è diversa dal solito)
  const strane = (!mac && gEff("fps30")) || !gEff("dual") || (zip ? gEff("jit") : !!G.dati.arm === !!gEff("jit"));
  h += `<details class="gr-speciali" ${G.speciali ?? strane ? "open" : ""}><summary><svg><use href="#i-ingr"/></svg><div><b>${t("gr_g_speciali")}</b><small>${t("gr_g_speciali_sub")}</small></div><i class="freccia">›</i></summary>
    <div class="gr-gruppo">
      ${mac ? "" : riga("fps30", "", { lato: tog("fps30"), sub: and ? t("gr_fps30_sub") : t("gr_fps30_pc_sub") })}
      ${riga("dual", "", { lato: tog("dual"), sub: t("gr_dual_sub") + (gEff("dual") ? "" : " " + t("gr_dual_off")), cls: gEff("dual") ? "" : "allarme" })}
      ${riga("jit", "", { lato: tog("jit"), sub: t("gr_jit_sub") + (!zip && G.dati.arm ? t("gr_jit_arm") : ""), cls: !zip && G.dati.arm && gEff("jit") ? "allarme" : "" })}
    </div></details>`;
  box.innerHTML = h;
  box.scrollTop = scroll;
  box.querySelectorAll("[data-dds]").forEach(b => b.onclick = () => avviaCompressione(b.dataset.dds === "png"));
  const sp = box.querySelector(".gr-speciali"); if (sp) sp.ontoggle = () => { G.speciali = sp.open; };
  box.querySelectorAll("[data-target]").forEach(b => b.onclick = () => gTarget(b.dataset.target));
  box.querySelectorAll(".bloccato").forEach(x => x.onclick = () => toast(t("gr_globali"), t("gr_bloccato"), "avviso"));
  box.querySelectorAll(".gr-riga.chiuso").forEach(x => x.onclick = () => toast(t("gr_pers"), t("gr_pers_bloccato"), "avviso", 3500));
  const gp = $("#gr-pers"); if (gp) gp.onchange = () => {
    G.pers = gp.checked; api().imposta("grafica_avanzata", G.pers);
    disegnaGrafica();
  };
  const gpe = box.querySelector(".gr-preset .pers"); if (gpe && !glob) gpe.onclick = () => box.querySelector(".gr-gruppo")?.scrollIntoView({ behavior: "smooth", block: "start" });
  box.querySelectorAll("[data-preset]").forEach(b => b.onclick = () => {  // un preset imposta tutto, overclock dal processore scelto
    const v = { ...pres.find(p => p[0] === b.dataset.preset)[2] };
    if (!zip) Object.assign(v, { oc_on: true, oc: G.dati.oc_cpu[gCpu()] });
    gImposta(v);
  });
  box.querySelectorAll("[data-cpu]").forEach(b => b.onclick = () => {  // processore: cambia l'overclock (e quello dei preset)
    G.cpuScelta = b.dataset.cpu; api().imposta("grafica_cpu", G.cpuScelta);
    gImposta({ oc_on: true, oc: G.dati.oc_cpu[G.cpuScelta] });
  });
  box.querySelectorAll(".seg, .res-griglia").forEach(s => s.querySelectorAll("button").forEach(b => b.onclick = () => gImposta({ [s.dataset.k]: JSON.parse(b.dataset.v) })));
  box.querySelectorAll("input[type=checkbox][data-k]").forEach(c => c.onchange = async () => {
    if (c.dataset.k === "globali" && c.checked && !(await modale({ titolo: t("gr_globali_conf_tit"), testo: t("gr_globali_conf"),
        bottoni: [[false, t("annulla")], [true, t("gr_globali_si")]] }))) { c.checked = false; return; }
    gImposta({ [c.dataset.k]: c.checked });
  });
  const r = $("#gr-oc");
  const leggiOc = () => { const p = +r.value; r.style.setProperty("--pct", (p - 100) / 3 + "%"); $("#gr-oc-v").textContent = p > 100 ? p + "%" : t("spento");
    return p > 100 ? { oc_on: true, oc: p / 100 } : { oc_on: false }; };
  r.oninput = () => gImposta(leggiOc(), false);
  r.onchange = () => gImposta(leggiOc());
  piedeGrafica();
}
function piedeGrafica() {
  if (S.pagina !== "grafica") return;
  const box = $("#modifiche");
  box.innerHTML = "";
  const ch = G.dati ? [...new Set(Object.keys(G.mod).map(k => k === "oc_on" ? "oc" : k))] : [];
  if (!ch.length) {
    box.innerHTML = `<div class="tutto-ok"><svg><use href="#i-ok"/></svg>${t("tutto_salvato")}</div>`;
    $("#piede").classList.add("nascondi-azioni");
    return;
  }
  $("#piede").classList.remove("nascondi-azioni");
  for (const k of ch.slice(0, 6)) {
    const m = document.createElement("div");
    m.className = "mod";
    m.innerHTML = `${t("gr_" + (k === "msaa" ? "aa" : k))}: <b>${gValore(k, gEff(k))}</b><button>×</button>`;
    m.querySelector("button").onclick = () => { delete G.mod[k]; if (k === "oc") delete G.mod.oc_on; disegnaGrafica(); };
    box.appendChild(m);
  }
  if (ch.length > 6) box.insertAdjacentHTML("beforeend", `<span>+${ch.length - 6}</span>`);
}
async function avviaCompressione(indietro) {
  const c = G.dati.comp;
  const ok = indietro
    ? await modale({ titolo: t("gr_dds_png_tit"), testo: t("gr_dds_png_testo"), bottoni: [[false, t("annulla")], [true, t("gr_dds_png"), true]] })
    : await modale({ titolo: t("gr_dds_conf_tit"), testo: t("gr_dds_conf", c.png, Math.max(1, Math.round(c.png / 1600))) + (S.dati.dolphin_aperto ? t("gr_dds_chiudi") : ""),
        bottoni: [[false, t("annulla")], [true, t("gr_dds_comprimi"), true]] });
  if (!ok) return;
  const r = await api().comprimi(indietro);
  if (!r || r.errore) { toast(t("errore"), r && r.errore === "texconv" ? t("gr_dds_no") : errTesto(r && r.errore), "errore"); return; }
  seguiLavoro();
}
let tmLavoro = null;
function seguiLavoro() {  // pannellino con la barra di avanzamento (resta visibile su tutte le pagine)
  const box = $("#lavoro");
  box.classList.remove("nascosto");
  box.querySelector("button").textContent = t("lav_annulla");
  box.querySelector("button").onclick = () => api().lavoro_annulla();
  clearInterval(tmLavoro);
  tmLavoro = setInterval(async () => {
    const st = await api().lavoro_stato();
    if (!st || st.errore) return;
    box.querySelector("b").textContent = t(st.indietro ? "lav_png" : "lav_dds");
    box.querySelector("small").textContent = st.totale ? `${st.fatti} / ${st.totale}` : "";
    box.querySelector(".barra i").style.width = (st.totale ? st.fatti / st.totale * 100 : 0) + "%";
    if (!st.finito) return;
    clearInterval(tmLavoro);
    setTimeout(() => box.classList.add("nascosto"), 600);
    if (st.errore) toast(t("errore"), st.errore, "errore", 8000);
    else toast(t("fatto"), t(st.indietro ? "lav_fine_png" : "lav_fine_dds", st.fatti), "", 6000);
    G.dati = null; T.dati = null;
    if (S.pagina === "grafica") caricaGrafica();
    if (S.pagina === "texture") caricaTexture();
  }, 700);
}
async function applicaGrafica() {
  if (!G.dati || !Object.keys(G.mod).length) return;
  if (G.target !== "pc") {  // Android / Mac: solo salvate per lo zip, questo PC non cambia
    const x = G.target, tutti = { ...G.vals[x], ...G.mod };
    const r = await (x === "mac" ? api().grafica_mac_salva(tutti) : api().grafica_android_salva(tutti));
    if (!r || r.errore) { toast(t("errore"), errTesto(r && r.errore), "errore"); return; }
    G.vals[x] = tutti; G.mods[x] = {}; G.dati.valori = G.vals[x]; G.mod = G.mods[x]; E.info = null;
    disegnaGrafica(); toast(t("fatto"), t(x === "mac" ? "gr_mac_salvato" : "gr_and_salvato"));
    return;
  }
  // usa Dolphin: tolgo le impostazioni dal gioco. Versioni diverse o ritorno da "usa Dolphin": scrivo tutto, così sono complete e uguali
  const glob = gEff("globali"), tutto = G.dati.diverse || !G.dati.proprie;
  const valori = glob ? ("globali" in G.mod ? { globali: true } : {}) :
    Object.fromEntries(Object.keys(tutto ? G.dati.valori : G.mod).filter(k => !["intero", "bordi", "globali", "fps30"].includes(k)).map(k => [k, gEff(k)]));
  if ("intero" in G.mod) valori.intero = G.mod.intero;
  if ("bordi" in G.mod) valori.bordi = G.mod.bordi;
  if ("fps30" in G.mod) valori.fps30 = G.mod.fps30;  // solo se cambiato: è il codice $60fps (non tocco le scelte fatte in Codici)
  if ("osd" in G.mod) valori.osd = G.mod.osd;
  $("#applica").disabled = true;
  const r = await api().grafica_applica(valori);
  $("#applica").disabled = false;
  if (!r || r.errore) { toast(t("errore"), r && r.errore === "chiudi_dolphin" ? t("gr_chiudi") : errTesto(r && r.errore), "errore"); return; }
  if ("fps30" in valori || "formato" in valori) C.dati = null;  // la pagina Codici rilegge il 60 fps / il widescreen
  await caricaGrafica();
  const testo = r.fatti.length ? t(glob ? "gr_globali_fatto" : "gr_fatto", r.fatti.join(", ")) : t("fatto");
  toast(t("fatto"), testo + (r.dolphin_aperto ? t("gr_riavvia") : ""), r.dolphin_aperto ? "avviso" : "", 6000);
}

// ================================================================ aggiungere skin, ragnatele, HUD, tasti, texture (per i più esperti)
const AGG_SEZIONE = { skin: "skin", ragnatele: "skin", hud: "hud", tasti: "hud", texture: "texture" };  // tipo -> pagina
async function aggiungi(sezione, percorso) {  // percorso = trascinato sulla finestra (sezione null = va dove deve)
  let r;
  if (percorso) r = await api().aggiungi_percorso(percorso);
  else {
    const modo = await modale({ titolo: t("agg_tit_" + sezione), testo: t("agg_testo"),
      bottoni: [[null, t("annulla")], ["archivio", t("agg_archivio")], ["cartella", t("agg_cartella"), true]] });
    if (!modo) return;
    r = await api().aggiungi_scegli(modo);
  }
  if (!r) return;
  if (r.errore === "tipo") { toast(t("errore"), t("tr_non_so", percorso.split(/[\\/]/).pop()), "avviso", 7000); return; }
  if (r.errore) { toast(t("errore"), r.errore === "estrattore" ? t("agg_estrattore") : r.errore, "errore", 8000); return; }
  if (r.tipo === "vuoto") { await modale({ titolo: t("agg_vuoto_tit"), testo: t("agg_vuoto"), bottoni: [[null, "OK", true]] }); return; }
  const giusta = AGG_SEZIONE[r.tipo];
  if (sezione && giusta !== sezione) {  // es. una skin aggiunta dalle texture: lo dico e propongo di metterla al posto giusto
    const atteso = { skin: "agg_tipo_skin", hud: "agg_tipo_hud", texture: "agg_tipo_texture" }[sezione];
    const ok = await modale({ titolo: t("agg_sbagliato_tit"), testo: t("agg_sbagliato", t("agg_tipo_" + r.tipo), t(atteso), t("nav_" + giusta)),
      bottoni: [[null, t("annulla")], [true, t("agg_sposta", t("nav_" + giusta)), true]] });
    if (!ok) return;
  }
  if (r.tipo === "texture" && r.n && !r.noti) {  // nessun nome conosciuto: quasi sicuramente non è per questo gioco
    const ok = await modale({ titolo: t("agg_ignoto_tit"), testo: t("agg_ignoto", r.n),
      bottoni: [[null, t("annulla"), true], [true, t("agg_comunque")]] });
    if (!ok) return;
  }
  let nome = r.nome;
  for (;;) {
    const testo = t("agg_riassunto", t("agg_tipo_" + r.tipo), r.n) + (r.varianti > 1 ? t("agg_varianti", r.varianti) : "") +
      (r.nuove && r.noti ? t("agg_nuove", r.nuove) : "") + (r.hud.length ? t("agg_anche_hud", r.hud.length) : "") + (r.extra_tex ? t("agg_anche_tex") : "");
    nome = await modale({ titolo: t("agg_nome_tit"), testo, campo: nome, bottoni: [[null, t("annulla")], ["campo", t("agg_bottone"), true]] });
    if (!nome) return;
    const ris = await api().aggiungi_conferma(r.tipo, nome);
    if (ris && ris.errore === "esiste") { toast(t("errore"), t("agg_esiste"), "errore"); continue; }
    if (!ris || ris.errore) { toast(t("errore"), (ris && ris.errore) || "", "errore"); return; }
    break;
  }
  toast(t("fatto"), t("agg_ok", nome));
  // ricarico le sezioni toccate e vado dove è finita la roba nuova
  T.dati = null; H.dati = null; T.img = {};
  await ricarica();
  if (r.tipo === "ragnatele") { S.slot = "ragnatele"; disegnaSlot(); disegnaChip(); disegnaGriglia(); }
  vaiA(giusta);
}

// ================================================================ trascina e rilascia
let trascinoN = 0;
function avviaTrascina() {  // velo "Rilascia qui" mentre si trascinano file sulla finestra (i percorsi li dà Python)
  const ov = $("#trascina"), haFile = e => [...((e.dataTransfer && e.dataTransfer.types) || [])].includes("Files");
  const via = () => { trascinoN = 0; if (!ov.classList.contains("lavoro")) ov.classList.add("nascosto"); };
  document.addEventListener("dragenter", e => { if (!haFile(e)) return; trascinoN++; ov.classList.remove("nascosto"); });
  document.addEventListener("dragleave", e => { if (haFile(e) && --trascinoN <= 0) via(); });
  document.addEventListener("dragover", e => { if (haFile(e)) { e.preventDefault(); e.dataTransfer.dropEffect = "copy"; } });
  document.addEventListener("drop", e => { e.preventDefault(); via(); });
}
async function fileTrascinati(percorsi) {
  const ov = $("#trascina");
  if (document.body.classList.contains("applicando") || !$("#modale").classList.contains("nascosto")) {
    toast(t("errore"), t("tr_occupato"), "avviso"); return;
  }
  ov.classList.add("lavoro"); ov.classList.remove("nascosto");
  const r = await api().trascinati_installer(percorsi);  // prima: sono zip dell'installer?
  ov.classList.remove("lavoro"); ov.classList.add("nascosto");
  if (!r || r.errore) { toast(t("errore"), errTesto(r && r.errore), "errore"); return; }
  if (r.nomi.length || r.diversi.length || r.ignoti.length) {
    const testo = [r.nomi.length ? t("tr_ok", r.nomi.join(", ")) : "", r.diversi.length ? t("tr_diversi", r.diversi.join(", ")) : "",
                   r.ignoti.length ? t("tr_non_so", r.ignoti.join(", ")) : ""].filter(Boolean).join("<br>");
    if (!r.nomi.length) toast(t("errore"), testo, "avviso", 9000);
    else {
      if (!I.dati) await caricaInstaller();
      I.archivi = { ...(I.archivi || {}), ...r.ok };
      const cat = I.dati.catalogo.file.filter(c => c.id in r.ok);
      const gia = cat.filter(c => insInstallato(c)), nuovi = cat.filter(c => !insInstallato(c));
      nuovi.forEach(c => I.sel.add(c.id));  // spuntati: basta premere Installa
      const righe = [nuovi.length ? t("tr_ok_spunta", nuovi.map(c => c.nome).join(", ")) : "",
                     gia.length ? t("tr_gia", gia.map(c => c.nome).join(", ")) : "",
                     r.diversi.length ? t("tr_diversi", r.diversi.join(", ")) : "", r.ignoti.length ? t("tr_non_so", r.ignoti.join(", ")) : ""];
      toast(nuovi.length ? t("fatto") : t("tr_gia_tit"), righe.filter(Boolean).join("<br>"), nuovi.length && !r.diversi.length && !r.ignoti.length ? "" : "avviso", 9000);
      if (S.pagina === "installa") disegnaInstaller(); else vaiA("installa");
      setTimeout(() => {  // la riga del pacchetto lampeggia (la prima la porto in vista)
        cat.forEach((c, i) => { const el = $(`[data-pacco="${c.id}"]`); if (!el) return; if (!i) el.scrollIntoView({ block: "center", behavior: "smooth" }); el.classList.add("lampeggia"); setTimeout(() => el.classList.remove("lampeggia"), 2600); });
      }, 250);
    }
  }
  for (const p of r.altri) await aggiungi(null, p);  // skin, HUD, tasti, texture: come il pulsante Aggiungi (va da sola al posto giusto)
}

// ================================================================ pagine e impostazioni
function segnaNav() {  // pallino giallo sulle sezioni con scelte non ancora applicate
  const pend = {
    skin: !!S.dati && SLOT_SKIN.some(s => S.scelta[s] !== null),
    codici: !!C.dati && Object.keys(C.mod).length > 0,
    hud: !!H.dati && (H.scelta.hud !== null || H.scelta.tasti !== null || H.scelta.disegno !== null),
    texture: !!T.dati && Object.keys(T.vuole).length > 0,
    grafica: !!G.dati && Object.keys(G.mod).length > 0,
  };
  $$(".voce-nav").forEach(b => {
    const on = !!pend[b.dataset.pagina];
    b.classList.toggle("pendente", on);
    if (on) b.dataset.tip = "nav_pendente"; else if (b.dataset.tip === "nav_pendente") delete b.dataset.tip;
  });
}
function serveMod(p) {  // Skin, HUD e Texture lavorano sulla libreria della mod: senza, un velo che manda all'installer
  const sez = $("#pg-" + p);
  const manca = !!(S.dati && !S.dati.pack) && ["skin", "hud", "texture"].includes(p);
  document.body.classList.toggle("velo-attivo", manca);  // niente piede ("Tutto installato…") sotto il velo
  if (!sez || !["skin", "hud", "texture"].includes(p)) return;
  let velo = sez.querySelector(".velo-mod");
  if (!manca) { if (velo) velo.remove(); sez.classList.remove("senza-mod"); return; }
  sez.classList.add("senza-mod");
  if (!velo) {
    velo = document.createElement("div");
    velo.className = "velo-mod";
    sez.appendChild(velo);
  }
  velo.innerHTML = `<div class="vm-box"><svg><use href="#i-scarica"/></svg><h3>${t("vm_tit")}</h3><p>${t("vm_testo_" + p)}</p>
    <button class="primario">${t("vm_vai")} →</button></div>`;
  velo.querySelector("button").onclick = () => vaiA("installa");
}
function vaiA(p) {
  if (p === "installa" && $(`.voce-nav[data-pagina="installa"]`).classList.contains("vuota")) {  // prima "Prepara il gioco"
    toast(t("nav_vuota_installa"), "", "avviso", 4000); Q.guida = true; p = "gioca";
  }
  if (S.pagina === "cam" && p !== "cam") entraCam(false);
  S.pagina = p;
  if (p === "cam") entraCam(true);
  $$(".voce-nav").forEach(b => b.classList.toggle("attiva", b.dataset.pagina === p));
  $$(".pagina").forEach(x => x.classList.remove("attiva"));
  ($("#pg-" + p) || $("#pg-presto")).classList.add("attiva");
  serveMod(p);
  if (p === "codici" && !C.dati) caricaCodici();
  if (p === "skin" && S.dati) api().stato().then(d => { if (d && !d.errore) { S.dati.alt_spento = d.alt_spento; disegnaSlot(); } });  // codice cambio costume acceso?
  if (p === "hud" && !H.dati) caricaHud();
  if (p === "texture") { if (!T.dati) caricaTexture(); else disegnaTexture(); }
  if (p === "installa") { if (!I.dati) caricaInstaller(); else disegnaInstaller(); }
  if (p === "esporta") caricaEsporta();
  if (p === "controller") { if (!X.dati) caricaController(); else disegnaController(); }
  if (p === "gioca") caricaGioca();
  if (p === "grafica") { if (!G.dati) caricaGrafica(); else disegnaGrafica(); }
  if (p === "impostazioni") {
    caricaImpGioco();
    $("#imp-dolphin").textContent = S.dati.dolphin || t("non_trovata");
    $("#imp-pack").textContent = S.dati.pack || t("non_trovata");
    $("#prova-barra").classList.toggle("nascosto", !S.dati.da_zero);  // modalità "prova da zero"
    impVersione();
  }
  aggiornaTesta();
}
async function apriComandi() {  // i comandi dei codici in gioco, con i tasti disegnati (Z = RB / R1)
  // codici accesi di adesso (Codici, Spider-Cam e "Prepara tutto" li cambiano senza ridisegnare il launcher)
  try { const g = await api().gioca_stato(); if (g && !g.errore) Q.dati = Q.dati ? Object.assign(Q.dati, { mod: g.mod, rag_alt: g.rag_alt }) : g; } catch (e) {}
  if (!X.dati) { const r = await api().controller_stato(); if (r && !r.errore) X.dati = r; }
  const ex = (ctProfilo() || { extra: {} }).extra, def = { costume: "L3", camera: "R3", mappa: "Select", hud: "LB" };
  const e = c => ex[c] === undefined ? def[c] : ex[c] ? etichNeutra(ex[c], def[c]) : null;
  const k = x => x === "Z" ? `<kbd class="z">Z<small>RB/R1</small></kbd>` : `<kbd>${x}</kbd>`;
  const moderna = !!(Q.dati && Q.dati.mod && Object.values(Q.dati.mod).some(m => m && m.cam_moderna));  // camera moderna accesa: R3 = moderna / classica
  const fov = !!(Q.dati && Q.dati.mod && Object.values(Q.dati.mod).some(m => m && m.fov));  // FOV con le frecce: spento di base
  // tuffo con L3 = codice a sé (va anche senza la camera): riga solo se è acceso
  const tuffo = !!(Q.dati && Q.dati.mod && Object.values(Q.dati.mod).some(m => m && m.tuffo));
  let amazing = false;  // camera Amazing scelta (principale o alternativa): ←/→ = spalla
  try { const cm = await api().cam_modi(); amazing = !!(cm && cm.modi && cm.modi.includes("amazing")); } catch (e) {}
  const tasti = gruppi => gruppi.map((g, i) => `<span class="gruppo ${i ? "alt" : "princ"}">${g.map(k).join("<i>+</i>")}</span>`).join(`<em class="oppure">${t("com_o")}</em>`);
  // costume = colpetto di RB (Z); il tasto extra "costume" del profilo (L3 = freccia giù) ora fa il tuffo in picchiata
  const righe = [[[["Z"]], "com_skin", "com_skin_sub"], ...(tuffo ? [[[e("costume") && [e("costume")], ["↓"]].filter(Boolean), "com_tuffo", "com_tuffo_sub"]] : []),
    [[e("costume") && [e("costume")], ["↓"]].filter(Boolean), "com_lock", t("com_lock_sub") + (tuffo ? t("com_lock_tuffo") : "") + (moderna ? t("com_lock_r3") : "")],  // lock del gioco: L3 = giù (R3 = Z + giù non aggancia: tuffo.CROCE_GIU)
    [[e("camera") && [e("camera")], ["Z", "↓"]].filter(Boolean), moderna ? "com_cam_mod" : "com_cam", moderna ? "com_cam_mod_sub" : "com_cam_sub"],
    [[e("mappa") && [e("mappa")], ["Z", "Start"]].filter(Boolean), "com_mappa", "com_mappa_sub"],
    [[["LB", "RB"]], "com_menu", "com_menu_sub"], ...(fov ? [[[["←"]], "com_fov_su"], [[["→"]], "com_fov_giu"]] : []),
    ...(amazing && moderna ? [[[["←"]], "com_spalla_sx", "com_spalla_sub"], [[["→"]], "com_spalla_dx", "com_spalla_sub"]] : []), [[e("hud") && [e("hud")], ["←", "→"]].filter(Boolean), "com_hud_toggle", "com_hud_toggle_sub"],
    [[["Z", "←"]], "com_hud_off"], [[["Z", "→"]], "com_hud_on"]];
  $("#com-rag").classList.toggle("nascosto", !(Q.dati && Q.dati.rag_alt));  // ragnatele dell'alternativo: solo con l'app aperta
  $("#com-lista").innerHTML = righe.map(([g, tit, sub]) => `<div class="com-riga"><div class="com-tasti">${tasti(g)}</div>
    <div><b>${t(tit)}${tit === "com_menu" ? soloApp() : ""}</b>${sub ? `<small>${t(sub)}</small>` : ""}</div></div>`).join("");
  $("#comandi").classList.remove("nascosto");
}
// Crediti e licenze (Impostazioni > App e piede del launcher): chi ha fatto cosa. Le mod si scaricano dalle loro pagine.
const CREDITI = [
  ["cr_g_mod", [
    ["RE Mods", "Spider-Man 2: RE", "cr_r_texture", "https://www.moddb.com/mods/spider-man-2-re-alpha"],
    ["KomandoUgur", "2003 Beta Suit · Spider-Man 2: RE", "cr_r_grazie"],
    ["JayeSGee", "Fresh Start · Fantastic Spider-Man · Zombie Hunter · Spider-Armor MK I · Philly Suit", "cr_r_costumi"],
    ["@philadelphia_spiderman", "Philly Suit", "cr_r_design"],
    ["LifeGeeksYT", "Suit pack", "cr_r_costumi"],
    ["ThunderTurtle", "Vanilla Suit Colors HD · Unofficial Update Pack", "cr_r_texture2"]]],
  ["cr_g_codici", [
    ["Slyfincleton", "Spider-Man 2 AR Codes", "cr_r_codici_usa"],
    ["GC-Forever", "16:9 Widescreen", "cr_r_wide"],
    ["John Swing", "SM2 Enhanced", "cr_r_gio"]]],
  ["cr_g_prog", [
    ["Dolphin Emulator", "GPL-2.0", "cr_r_dolphin", "https://dolphin-emu.org/"],
    ["DirectXTex texconv · Microsoft", "MIT", "cr_r_incluso"],
    ["Python", "PSF License", "cr_r_incluso"],
    ["pywebview · pythonnet · bottle", "BSD-3-Clause · MIT", "cr_r_incluso"],
    ["Pillow · psutil · lz4 · Dolphin Memory Engine", "MIT-CMU · BSD-3-Clause · MIT", "cr_r_incluso"],
    ["PyInstaller", "GPL-2.0 + bootloader exception", "cr_r_incluso"],
    ["Microsoft Edge WebView2", "Microsoft", "cr_r_webview"]]],
];
async function apriCrediti() {
  // sostenitori Swing++ (dal manifesto pubblico degli aggiornamenti, copia in config): in testa, coi nomi come etichette
  let nomi = [];
  try { nomi = (await api().sostenitori()) || []; } catch (e) { /* niente */ }
  const pulito = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const sost = `<div class="cr-gruppo cr-sost"><div class="imp-sezione">${t("cr_g_sost")}</div>`
    + (nomi.length ? `<p class="cr-sost-sub">${t("cr_sost_sub")}</p><div class="cr-nomi">${nomi.map(n => `<span>${pulito(n)}</span>`).join("")}</div>` : "")
    + `<a href="#" class="cr-sost-invito" id="cr-sost-invito">${t("cr_sost_invito")} ↗</a></div>`;
  $("#cr-lista").innerHTML = sost + CREDITI.map(([g, voci]) => `<div class="cr-gruppo"><div class="imp-sezione">${t(g)}</div>${voci.map(([chi, cosa, ruolo, url]) =>
    `<div class="cr-voce"><b>${url ? `<a href="#" data-url="${url}">${chi} ↗</a>` : chi}</b><span>${cosa}</span><small>${t(ruolo)}</small></div>`).join("")}</div>`).join("");
  $$("#cr-lista [data-url]").forEach(a => a.onclick = e => { e.preventDefault(); api().apri_link(a.dataset.url); });
  $("#cr-sost-invito").onclick = e => { e.preventDefault(); apriPatreon(); };
  $("#crediti").classList.remove("nascosto");
}
function impVersione() {  // Impostazioni > App: versione e "Controlla aggiornamenti"
  $("#imp-ed-sub").textContent = t("imp_ed_gratis");
  const a = S.agg, nuova = a && a.nuova;
  $("#imp-versione").textContent = nuova ? t("imp_versione_nuova", S.dati.versione, nuova.versione) : t("imp_versione_sub", S.dati.versione);
  const b = $("#imp-upd");
  b.textContent = nuova ? t(a.da_sola ? "upd_aggiorna" : "upd_scarica") : t("imp_controlla");
  b.onclick = async () => {
    const x = await api().app_agg_avanzamento();
    if (x && x.finito && !x.errore) { appAggPronta(x.versione); return; }  // già scaricata ("Più tardi")
    if (S.agg && S.agg.nuova) { appAggiorna(S.agg); return; }
    b.disabled = true;
    const r = await api().app_agg_controlla();
    b.disabled = false;
    if (!r || r.errore) return;
    appAggSegna(r);
    impVersione();
    if (r.nuova) appAggiorna(r); else toast(t("imp_controlla"), t("upd_ultima"), "", 5000);
  };
}
function appAggSegna(a) {  // versione nuova trovata: pallino sulla versione in alto + avviso nel launcher
  S.agg = a;
  $("#versione").classList.toggle("nuova", !!(a && a.nuova));
  $("#versione").title = a && a.nuova ? t("upd_banner", a.nuova.versione, a.versione) : "";
  if (Q.dati) { Q.dati.app_agg = a; if (S.pagina === "gioca" && !Q.guida) disegnaGioca(); }
}
async function caricaImpGioco() {  // interruttori di avvio: gli stessi del launcher e di Grafica
  const r = await api().impostazioni_gioco();
  if (!r || r.errore) return;
  const chiavi = { osd: "notifiche_dolphin", intero: "gioca_intero", solo: "gioca_solo", bordi: "schermo_senza_bordi" };
  for (const k of ["osd", "fps", "intero", "bordi", "solo", "sopra"]) {
    const c = $("#imp-" + k);
    c.checked = !!r[k];
    c.onchange = async () => {
      if (k === "fps") {
        const x = await api().gioca_fps(c.checked);
        if (!x || x.errore) { c.checked = !c.checked; toast(t("errore"), x ? t(x.errore) : "", "errore"); return; }
      } else if (k === "sopra") await api().cam_sopra(c.checked);  // vale subito anche sul gioco aperto
      else await api().imposta(chiavi[k], c.checked);
      G.dati = null;  // Grafica e launcher rileggono i valori nuovi
      if (Q.dati) Q.dati[k] = c.checked;
      toast(t("fatto"), "", "", 1500);
    };
  }
}
async function scegliCartella(cosa) {
  const r = await api().scegli_cartella(cosa);
  if (!r) return;
  if (r.errore) { toast(t("errore"), errTesto(r.errore), "errore"); return; }
  await ricarica();
  vaiA("impostazioni");
}
async function rinfrescaTutto() {  // qualcosa di base è cambiato (Dolphin, giochi): via i dati vecchi di tutte le pagine
  C.dati = null; C.mod = {}; H.dati = null; T.dati = null; I.dati = null; I.archivi = null; G.dati = null; E.info = null; X.dati = null;
  if (K.info) K.info = null;
  await ricarica();
  serveMod(S.pagina);
}
async function ricarica() {
  S.dati = await api().stato();
  if (S.dati.errore) { toast(t("errore"), S.dati.errore, "errore"); return; }
  applicaTesti();
  const inst = await api().installate();
  if (inst && !inst.errore) {
    S.inst.primaria = inst.primaria; S.inst.alternativa = inst.alternativa; S.inst.ragnatele = inst.ragnatele; S.inst.ragnatele_alt = inst.ragnatele_alt || "uguali";
    dopoScelta();
  }
  miniature();
}

// ================================================================ avvio
async function avvia() {
  const statoIntanto = api().stato();  // i dati li chiedo subito: Python lavora mentre qui si prepara il modello 3D
  const modello = (await modelliSpidey()).gioco;
  viewer = new Viewer($("#c3d"), modello);
  let posa = "idle";
  try { posa = localStorage.getItem("posa") || "idle"; } catch (e) {}
  const metti = async p => {
    posa = p;
    try { localStorage.setItem("posa", p); } catch (e) {}
    if (p === "idle") viewer.usaModello("idle", (await modelliSpidey()).idle);
    else viewer.usaModello("base");
    $$("#pose button").forEach(b => b.classList.toggle("attivo", b.dataset.posa === p));
  };
  $$("#pose button").forEach(b => b.onclick = () => metti(b.dataset.posa));
  $$("#pose-catalogo button").forEach(b => b.onclick = () => cambiaPosaCatalogo(b.dataset.posa));
  segnaPosaCatalogo();
  metti(posa);
  viewer.avvia();
  fotoViewer = new Viewer($("#c-foto"), modello, { foto: true, auto: false, ang: 0.42, alt: 0.05, dist: 3.0, cy: 0.92 });

  S.dati = await statoIntanto;
  L = LINGUE.includes(S.dati.lingua) ? S.dati.lingua : "en";
  $("#imp-patreon").onclick = apriPatreon;
  $("#prova-barra").classList.toggle("nascosto", !S.dati.da_zero);  // modalità "prova da zero"
  $("#versione").textContent = "v" + S.dati.versione;
  if (S.dati.aggiornata) setTimeout(() => toast(t("upd_fatta", S.dati.aggiornata), "", "", 6000), 1500);
  setTimeout(async () => { const a = await api().app_agg_stato(); if (a && !a.errore) appAggSegna(a); }, 5000);  // il controllo online parte all'avvio
  $("#versione").onclick = () => { if (S.agg && S.agg.nuova) appAggiorna(S.agg); else vaiA("impostazioni"); };

  // eventi
  $$(".voce-nav[data-pagina]").forEach(b => b.onclick = () => vaiA(b.dataset.pagina));
  $$(".lingue [data-l]").forEach(b => b.onclick = () => { L = b.dataset.l; api().imposta("lingua", L); applicaTesti(); $(".lingue-menu").classList.add("nascosto"); });
  $("#btn-comandi").onclick = apriComandi;
  $("#gi-com-tondo").onclick = apriComandi;
  $("#com-chiudi").onclick = () => $("#comandi").classList.add("nascosto");
  $("#gi-lbrb").onclick = apriMenuInfo;
  $("#mz-chiudi").onclick = () => $("#mz").classList.add("nascosto");
  $("#cr-chiudi").onclick = () => $("#crediti").classList.add("nascosto");
  $("#crediti").onclick = e => { if (e.target.id === "crediti") $("#crediti").classList.add("nascosto"); };
  $("#imp-crediti").onclick = apriCrediti;
  $("#cr-licenze").onclick = () => api().apri("licenze");
  $("#mz").onclick = e => { if (e.target.id === "mz") $("#mz").classList.add("nascosto"); };
  $("#comandi").onclick = e => { if (e.target.id === "comandi") $("#comandi").classList.add("nascosto"); };
  $("#lingua-btn").onclick = e => { e.stopPropagation(); $(".lingue-menu").classList.toggle("nascosto"); };
  document.addEventListener("click", e => { if (!e.target.closest(".lingue")) $(".lingue-menu").classList.add("nascosto"); });
  $("#alt-info").onclick = e => {  // spiegazione del cambio costume (colpetto di RB), senza cambiare scheda
    e.stopPropagation();
    modale({ titolo: t("alt_info_tit"), testo: t("alt_info"), bottoni: [[true, t("alt_info_ok"), true]] });
  };
  $$("#pg-skin .slot button").forEach(b => b.onclick = () => {
    S.slot = b.dataset.slot; S.cerca = ""; $("#cerca").value = ""; chiudiPers();
    $("#cerca").placeholder = t(isRag(S.slot) ? "cerca_rag" : "cerca_skin");
    disegnaSlot(); disegnaChip(); disegnaGriglia(); aggiornaPalco();
  });
  $("#cerca").oninput = e => { S.cerca = e.target.value; disegnaGriglia(); };
  $("#b-giro").onclick = () => { viewer.auto = !viewer.auto; $("#b-giro").classList.toggle("attivo", viewer.auto); };
  $("#b-fronte").onclick = () => { viewer.ang = 0; viewer.alt = 0.08; };
  $("#b-retro").onclick = () => { viewer.ang = Math.PI; viewer.alt = 0.08; };
  $("#b-pers").onclick = apriPers;
  $("#pers-chiudi").onclick = chiudiPers;
  $("#pers-default").onclick = () => { const a = attuale(S.slot), v = a && voce(a.id); if (v) scegliVariante(v.default); };
  $("#annulla").onclick = () => {
    if (S.pagina === "codici") { C.mod = {}; disegnaCodici(); return; }
    if (S.pagina === "hud") { H.scelta = { hud: null, tasti: null, disegno: null }; disegnaHud(); return; }
    if (S.pagina === "grafica") { G.mod = {}; disegnaGrafica(); return; }
    if (S.pagina === "texture") {  // anche la scelta "tutte / solo nuove" torna com'era
      T.vuole = {};
      for (const v of T.dati.voci) if (txModo(v) !== (T.modi0[v.id] || "tutte")) api().texture_modo(v.id, T.modi0[v.id] || "tutte");
      T.dati.modi = { ...T.modi0 };
      disegnaTexture(); return;
    }
    S.scelta = { primaria: null, alternativa: null, ragnatele: null, ragnatele_alt: null }; dopoScelta();
  };
  const applicaPagina = () => S.pagina === "codici" ? applicaCodici() : S.pagina === "hud" ? applicaHud() : S.pagina === "cam" ? kSalvaGioco() : S.pagina === "grafica" ? applicaGrafica() : S.pagina === "texture" ? applicaTexture() : applica();
  $("#cam-preset-btn").onclick = e => { e.stopPropagation(); $("#cam-preset-menu").classList.toggle("nascosto"); };
  document.addEventListener("click", e => { if (!e.target.closest(".menu-preset")) $("#cam-preset-menu").classList.add("nascosto"); });
  $("#cam-p-salva").onclick = kSalvaPreset; $("#cam-p-come").onclick = kSalvaCome; $("#cam-p-elimina").onclick = kElimina; $("#cam-p-rinomina").onclick = kRinomina;
  $("#cam-p-importa").onclick = kImporta; $("#cam-p-esporta").onclick = kEsporta;
  $("#cam-collega").onchange = e => { K.collega = e.target.checked; if (K.collega) { const x = K.valori.swing[3]; K.info.collegati.forEach(o => K.valori[o][3] = x); aggiornaCelle(); } kInvia(); };
  $("#cam-minuguale").onchange = e => { K.minUguale = e.target.checked; aggiornaCelle(); kInvia(); };
  $("#cam-fov").oninput = e => { K.fov = +e.target.value; aggiornaCelle(e.target); kInvia(); };
  $("#cam-fov-n").onchange = e => { K.fov = Math.min(120, Math.max(60, Math.round(+e.target.value || 90))); aggiornaCelle(); kInvia(); };
  $("#applica").onclick = applicaPagina;
  $$("#pg-hud .slot button").forEach(b => b.onclick = () => { H.slot = b.dataset.hslot; H.cerca = ""; $("#h-cerca").value = ""; disegnaHud(); });
  $("#h-cerca").oninput = e => { H.cerca = e.target.value; hGriglia(); };
  $("#cod-cerca").oninput = e => { C.cerca = e.target.value; disegnaCodici(); };
  $("#cod-tutte").onchange = e => { C.tutte = e.target.checked; api().imposta("codici_tutte", C.tutte);
    for (const id of Object.keys(C.mod)) if (C.mod[id] === base(id)) delete C.mod[id];
    disegnaCodici(); };
  $("#cod-consigliati").onclick = consigliati;
  $("#cod-aggiungi").onclick = aggiungiCodice;
  $$("[data-apri]").forEach(b => b.onclick = () => api().apri(b.dataset.apri));
  $$("[data-aggiungi]").forEach(b => b.onclick = () => aggiungi(b.dataset.aggiungi));
  $("#sc-dolphin").onclick = () => scegliCartella("dolphin");
  $("#sc-pack").onclick = () => scegliCartella("pack");
  $("#rifai-mini").onclick = () => { toast(t("mini_rifatte"), ""); S.mini = {}; disegnaGriglia(); vaiA("skin"); miniature(true); };
  document.addEventListener("keydown", e => {
    const fuoco = document.activeElement;  // schede (skin, HUD...) raggiunte col Tab: Invio/Spazio = clic, come i pulsanti
    if ((e.key === "Enter" || e.key === " ") && fuoco && fuoco.tabIndex >= 0 && fuoco.onclick && !fuoco.matches("button, input, select, textarea, a")) {
      e.preventDefault(); fuoco.click(); return;
    }
    if (e.ctrlKey && e.key.toLowerCase() === "f") { e.preventDefault(); vaiA("skin"); $("#cerca").focus(); }
    else if (e.ctrlKey && e.key.toLowerCase() === "s") { e.preventDefault(); if (!applicando()) applicaPagina(); }
    else if (e.key === "Escape") { if (!$("#crediti").classList.contains("nascosto")) $("#crediti").classList.add("nascosto"); else if (!$("#mz").classList.contains("nascosto")) $("#mz").classList.add("nascosto"); else if (!$("#comandi").classList.contains("nascosto")) $("#comandi").classList.add("nascosto"); else if (S.pers) chiudiPers(); else if (S.cerca) { S.cerca = ""; $("#cerca").value = ""; disegnaGriglia(); } }
  });
  fumetti();
  avviaTrascina();
  $("#prova-cartella").onclick = () => api().apri("prova");
  $("#prova-ricomincia").onclick = async () => {
    const ok = await modale({ titolo: t("prova_ricomincia"), testo: t("prova_ricomincia_testo"), bottoni: [[null, t("annulla"), true], [true, t("prova_ricomincia")]] });
    if (ok) api().prova_ricomincia();
  };
  avviaZoom();
  setInterval(segnaNav, 400);
  document.addEventListener("click", e => { const a = e.target.closest("[data-link]"); if (a) api().apri_link(a.dataset.link); });
  applicaTesti();
  vaiA(new URLSearchParams(location.search).get("pagina") || "gioca");
  const inst = await api().installate();
  if (inst && !inst.errore) Object.assign(S.inst, inst);
  if (S.pagina === "gioca") giSkin();
  dopoScelta();
  miniature();
  setInterval(async () => {
    const ap = await api().dolphin_aperto();
    if (typeof ap === "boolean" && ap !== S.dati.dolphin_aperto) { S.dati.dolphin_aperto = ap; aggiornaPillole(); if (S.pagina === "grafica") disegnaGrafica();
      if (Q.dati) { Q.dati.aperto = ap; if (S.pagina === "gioca") disegnaGioca(); } }
  }, 4000);
}
window.addEventListener("error", e => { try { api().log_js(`${e.message} @ ${e.filename}:${e.lineno}`); } catch (_) {} });
window.addEventListener("unhandledrejection", e => { try { api().log_js("promise: " + (e.reason && (e.reason.stack || e.reason))); } catch (_) {} });
// Schermi con poco spazio (TV 4K col ridimensionamento di Windows al 300% = 1280x680 punti, portatili piccoli): l'app
// è disegnata per ~1536x790 punti; se ce n'è meno rimpicciolisce tutto in proporzione invece di accavallare i pezzi.
const zoomPagina = () => parseFloat(document.body.style.zoom) || 1;
function adattaZoom() {
  const z = Math.min(1, innerWidth / 1536, innerHeight / 790);
  document.body.style.zoom = z < 0.985 ? z.toFixed(3) : "";
}
window.addEventListener("resize", adattaZoom);
adattaZoom();
window.addEventListener("pywebviewready", avvia);

document.addEventListener("click", e => { const b = e.target.closest("[data-vai-pag]"); if (b && !b.disabled) vaiA(b.dataset.vaiPag); });
