// Menu in gioco (LB + RB): finestrella sopra il gioco, comandata col pad. I tasti arrivano da Python (menuTasto),
// che legge il pad con XInput anche quando la finestra non ha il fuoco; tastiera e mouse vanno lo stesso.
const $ = s => document.querySelector(s), $$ = s => [...document.querySelectorAll(s)];
let L = "it";
const t = (k, ...a) => ((TESTI[L] || {})[k] ?? TESTI.en[k] ?? k).replace(/\{(\d)\}/g, (_, i) => a[i]);
const api = () => window.pywebview.api;
const TAB = ["ora", "skin", "codici", "cam", "musica"];  // "ora" = Cielo (menu_cielo.js); si apre sempre su "skin"
const COLONNE = 5;
const ST = { aperto: false, lista: [], sel: 0, conferma: false, occupato: false };
const SI = { aperto: false, sel: 0, conferma: false };  // pannello "Sistema" (View): esci dal gioco, schermo intero, controller
const M = { dati: null, tab: "skin", slot: "primaria", sel: 0, viewer: null, tex: {}, pad: false, occupato: false, tmAnteprima: null,
            ordine: "az", vista: [], ragImg: {}, filo: {}, selRag: 0, va: null };  // va = pannello varianti aperto
const ORDINI = ["az", "autore", "pref"];  // A-Z | per autore | solo preferiti (i preferiti stanno sempre in testa)
try { M.ordine = localStorage.getItem("mn_ordine2") || "az"; } catch (e) {}
const autore = v => { const a = ((v && v.crediti) || "").split(/ [·(]/)[0].trim(); return a && a !== "—" ? a : ""; };
const nomeRag = r => !r ? "—" : r.id === "uguali" ? t("rag_uguali") : r.id === "vanilla" ? t("rag_vanilla") : r.nome;
const isRagM = () => M.slot === "ragnatele" || M.slot === "ragnatele_alt";
function ragLista() {  // ragnatele del costume principale, o dell'alternativo ("uguali" in testa, niente originali)
  const l = M.dati.ragnatele || [];
  return M.slot === "ragnatele_alt" ? [{ id: "uguali" }, ...l.filter(r => r.id !== "vanilla")] : l;
}
const ragInUso = () => M.slot === "ragnatele_alt" ? (M.dati.ragnatela_alt || "uguali") : M.dati.ragnatela;
const nomeGruppo = g => g === "Collezione" ? "Spider-Man 2: RE" : g === "Aggiunte" ? t("gruppo_aggiunte") : g;

function testi() {
  $$("[data-t]").forEach(e => e.textContent = t(e.dataset.t));
  $$("[data-t-title]").forEach(e => e.title = t(e.dataset.tTitle));
}
function toast(testo) {
  const b = $("#mn-toast");
  b.textContent = testo; b.classList.remove("nascosto");
  clearTimeout(toast.tm); toast.tm = setTimeout(() => b.classList.add("nascosto"), 2200);
}
function piede() {  // i tasti che servono adesso
  const k = (c, x) => `<kbd class="pad ${c}">${x}</kbd>`;
  const voci = M.va ? [...(M.va.righe && M.va.righe.length > 1 ? [[k("", "↑") + k("", "↓"), t("mn_va_riga")]] : []), [k("", "←") + k("", "→"), t("mn_va_opzione")], [k("a", "A"), t("mn_metti")], [k("b", "B"), t("mn_indietro")]]
    : ST.aperto ? [[k("", "←") + k("", "→"), t("mn_st_slot")], [k("", "LT") + k("", "RT"), t(ST.modo === "carica" ? "mn_st_salva" : "mn_st_carica")],
      [k("a", "A"), t(ST.conferma ? "mn_st_conferma" : ST.modo === "carica" ? "mn_st_carica" : "mn_st_salva")], [k("b", "B"), t("mn_indietro")]]
    : SI.aperto ? [[k("", "↑") + k("", "↓"), t("mn_scegli")], [k("a", "A"), t(SI.conferma ? "mn_si_ancora" : "cd_conferma")], [k("b", "B"), t("mn_indietro")]]
    : M.tab === "codici" && M.cd && M.cd.scelta !== null ? [[k("a", "A"), t("cd_riavvia_ora")], ...(M.cd.stato1 ? [[k("x", "X"), t("cd_riavvia_stato1")]] : []), [k("b", "B"), t("mn_indietro")]]
    : M.tab === "codici" ? [[k("a", "A"), t("cd_accendi")], [k("", "LT") + k("", "RT"), t("mn_veloce")], ...(M.cd && Object.keys(M.cd.mod).length ? [[k("y", "Y"), t("cd_applica")]] : []), [k("", "LB") + k("", "RB"), t("mn_sezione")], [k("b", "B"), t("mn_chiudi")]]
    : M.tab === "cam" ? camPiede(k)
    : M.tab === "ora" ? oraPiede(k)
    : M.tab === "musica" ? [[k("a", "A"), t("mu_play")], [k("", "←") + k("", "→"), t("mu_brano")], [k("", "↑") + k("", "↓"), t("mu_volume")], [k("", "LB") + k("", "RB"), t("mn_sezione")], [k("b", "B"), t("mn_chiudi")]]
    : M.tab === "skin" && isRagM() ? [[k("a", "A"), t("mn_metti")], [k("", "LT") + k("", "RT"), t("mn_cambia_slot")], [k("", "LB") + k("", "RB"), t("mn_sezione")], [k("b", "B"), t("mn_chiudi")]]
    : M.tab === "skin" ? [[k("a", "A"), t("mn_metti")], ...(M.vista[M.sel] && M.vista[M.sel].albero ? [[k("stick", "L3"), t("mn_varianti")]] : []), [k("", "LT") + k("", "RT"), t("mn_cambia_slot")], [k("x", "X"), t("mn_ordina")], [k("y", "Y"), t("mn_preferito")], [k("stick", "R3"), t(M.fermo ? "mn_gira" : "mn_ferma")], [k("", "LB") + k("", "RB"), t("mn_sezione")], [k("b", "B"), t("mn_chiudi")]]
      : [[k("", "LB") + k("", "RB"), t("mn_sezione")], [k("", "View"), t("mn_sistema")], [k("b", "B"), t("mn_chiudi")]];
  $("#mn-piede").innerHTML = voci.map(([a, b]) => `<span>${a}${b}</span>`).join("");
}

// ---------------------------------------------------------------- tasti della Play (se in "HUD e tasti" c'è un layout PlayStation)
const PS = { attivo: false,
  tondi: { A: ["ps-x", "✕"], B: ["ps-o", "○"], X: ["ps-q", "□"], Y: ["ps-t", "△"] },
  nomi: { LB: "L1", RB: "R1", LT: "L2", RT: "R2", View: "Share", Menu: "Options", Select: "Share" } };  // PS5: "Create" (tastiPS)
function tastiPS(radice, tutto = false) {  // ogni <kbd class="pad"> scritto alla Xbox diventa alla PlayStation (e viceversa)
  const els = radice.matches && radice.matches("kbd.pad") ? [radice] : [...radice.querySelectorAll("kbd.pad")];
  for (const e of els) {
    if (!("xb" in e.dataset)) e.dataset.xb = e.textContent;
    else if (!tutto && e.dataset.fatto === String(PS.attivo)) continue;
    const xb = e.dataset.xb;
    e.classList.remove("ps-x", "ps-o", "ps-q", "ps-t");
    if (PS.attivo && PS.tondi[xb]) { e.classList.add("ps", PS.tondi[xb][0]); e.textContent = PS.tondi[xb][1]; }
    else if (PS.attivo) { e.classList.remove("ps"); e.textContent = xb.replace("RB/R1", "R1").replace(/\b(LB|RB|LT|RT|View|Menu|Select)\b/g, m => PS.nomi[m]); }
    else { e.classList.remove("ps"); e.textContent = xb; }
    e.classList.toggle("stick", /^(L3|R3|L|R)$/.test(xb));  // gli stick (cliccati o mossi: L / R) sono tondi, non come i grilletti
    e.dataset.fatto = String(PS.attivo);
  }
}
new MutationObserver(lista => { for (const m of lista) for (const n of m.addedNodes) if (n.nodeType === 1) tastiPS(n); })
  .observe(document.body, { childList: true, subtree: true });

// ---------------------------------------------------------------- apertura
window.giocoAperto = true;  // viewer.js: senza il fuoco (menu nascosto) non disegna lo Spidey 3D
async function menuApri(vero) {  // vero = LB + RB (non la preparazione nascosta)
  M.chiuso = false;
  if (vero) M.vero = true;
  if (M.cd) { M.cd.inCorso = false; M.cd.scelta = null; M.cd.gid = null; }  // dopo un riavvio i codici si rileggono
  if (vero && typeof M3 !== "undefined" && !M3.stato) M3.ant = undefined;  // anteprima della mappa 3D con "tu" dove sei adesso
  const d = await api().menu_stato();
  if (!d || d.errore) return;
  M.dati = d; L = d.lingua || "it"; testi();
  if (d.partita !== M.partita) {  // gioco chiuso e riaperto (o riavviato): si riparte dalle skin, come la prima volta
    M.partita = d.partita; M.tab = "skin"; M.slot = "primaria"; M.va = null; $("#mn-varianti").classList.add("nascosto");
    SI.aperto = false; SI.conferma = false; SI.sel = 0;
  }
  if (window.apriViaggio && typeof mondoPagina === "function") { M.tab = "ora"; OR.pag = "viaggio"; window.apriViaggio = false; }  // aperto con la mappa del gioco aperta
  C.barra = false;
  const ps = !!d.tasti_ps || !!(d.pad && d.pad.pad && d.pad.pad.tipo === "ps");  // layout tasti PlayStation o pad PlayStation in uso
  if (PS.attivo !== ps) { PS.attivo = ps; tastiPS(document.body, true); }
  d.skin.forEach((v, i) => v.ord = i);  // ordine del catalogo (per autore), per tornarci
  ordina();
  ST.aperto = false; $("#mn-pannello-stati").classList.add("nascosto");
  $("#mn-ver").textContent = d.versione && d.versione !== "?" ? ({ GK2E52: "USA", GK2P52: "UK", GK2I52: "ITA", GK2D52: "DE", GK2F52: "FR" })[d.versione] || "" : "";
  const p = d.pad;
  $("#mn-pad").className = "tondo-piccolo " + (!p ? "" : p.esito === "ok" ? "ok" : p.esito === "sdl" || p.esito === "xinput" || p.esito === "nome" ? "rosso" : "giallo");
  SI.aperto = false; $("#mn-pannello-pad").classList.add("nascosto");
  if (isRagM()) M.selRag = Math.max(0, ragLista().findIndex(r => r.id === ragInUso()));
  else { const inUso = M.vista.findIndex(v => v.id === d[M.slot]); M.sel = inUso >= 0 ? inUso : 0; }
  vai(M.tab);  if (vero) api().menu_mostrami();  // ridisegnato: Python ora mostra la finestra
}
async function menuPrepara() {  // appena parte il gioco l'app crea il menu nascosto: skin già disegnate al primo LB + RB
  await menuApri();
  if (!M.vero) menuChiuso();  // fermi anche i timer (musica, camera) della sezione rimasta aperta; non se intanto l'hai aperto
}
function vai(tab) {
  M.tab = tab;
  $$("#mn-tab [data-tab]").forEach(b => b.classList.toggle("attivo", b.dataset.tab === tab));
  $$(".mn-pagina").forEach(x => x.classList.toggle("attiva", x.id === "mp-" + tab));
  if (tab === "skin") disegnaSkin();
  if (tab === "codici") caricaCodici();
  if (tab === "cam") camApri(); else camChiudi();
  if (tab === "ora") oraApri(); else oraChiudi();
  if (tab !== "cam") C.barra = false;
  camModo();
  clearInterval(M.tmMusica);
  if (tab === "musica") { musica(); volume(); M.tmMusica = setInterval(musica, 1000); }
  piede();
}

// ---------------------------------------------------------------- skin
function ordina() {  // M.vista = le skin mostrate: preferiti sempre in testa, poi A-Z o per autore; "pref" = solo preferiti
  const d = M.dati, pref = d.preferite || [], fav = v => pref.includes(v.id) ? 0 : 1;
  const az = (a, b) => a.nome.localeCompare(b.nome, undefined, { numeric: true });
  const l = [...d.skin].sort((a, b) => fav(a) - fav(b) || (M.ordine === "autore" ? a.ord - b.ord : az(a, b)));
  M.vista = M.ordine === "pref" ? l.filter(v => !fav(v)) : l;
}
function cambiaOrdine(passo) {
  const v = M.vista[M.sel];
  M.ordine = ORDINI[(ORDINI.indexOf(M.ordine) + passo + ORDINI.length) % ORDINI.length];
  try { localStorage.setItem("mn_ordine2", M.ordine); } catch (e) {}
  ordina();
  M.sel = Math.max(0, M.vista.indexOf(v));  // resta sulla stessa skin
  disegnaSkin();
}
async function preferito() {
  const d = M.dati, v = M.vista[M.sel];
  if (!v) return;
  const si = !(d.preferite || []).includes(v.id);
  d.preferite = await api().skin_preferita(v.id, si) || d.preferite;
  ordina();
  M.sel = Math.max(0, Math.min(M.vista.length - 1, M.vista.includes(v) ? M.vista.indexOf(v) : M.sel));
  disegnaSkin();
  toast(t(si ? "mn_pref_si" : "mn_pref_no", v.nome));
}
function disegnaSkin() {
  const d = M.dati;
  if (!d) return;
  const nome = id => (d.skin.find(v => v.id === id) || {}).nome || "—";
  const rag = isRagM();
  $$(".mn-slot [data-slot]").forEach(b => b.classList.toggle("attivo", b.dataset.slot === M.slot));
  $("#mn-s-primaria").textContent = nome(d.primaria);
  $("#mn-s-alternativa").textContent = nome(d.alternativa);
  $("#mn-s-ragnatele").textContent = nomeRag((d.ragnatele || []).find(r => r.id === d.ragnatela));
  $("#mn-s-ragnatele_alt").textContent = nomeRag(d.ragnatela_alt && d.ragnatela_alt !== "uguali" ? (d.ragnatele || []).find(r => r.id === d.ragnatela_alt) : { id: "uguali" });
  const av = $("#mn-avviso");
  av.classList.toggle("nascosto", !(M.slot === "alternativa" && d.alt_spento && d.alt_spento.length));
  if (d.alt_spento && d.alt_spento.length) av.textContent = "⚠ " + t("alt_spento", d.alt_spento.join(", "));
  $("#mn-ordine").classList.toggle("nascosto", rag);
  $("#mn-ordine").innerHTML = `<kbd class="pad x">X</kbd>${ORDINI.map(o => `<button data-ord="${o}" class="${o === M.ordine ? "attivo" : ""}">${t("mn_ord_" + o)}</button>`).join("")}`;
  $$("#mn-ordine [data-ord]").forEach(b => b.onclick = () => cambiaOrdine(ORDINI.indexOf(b.dataset.ord) - ORDINI.indexOf(M.ordine)));
  $("#mn-griglia").classList.toggle("rag", rag);
  if (rag) { disegnaRagnatele(); return; }
  if (M.viewer) M.viewer.appeso = false;
  $("#mn-griglia").innerHTML = !M.vista.length ? `<p class="mn-vuoto"><svg><use href="#i-stella"/></svg>${t((d.skin || []).length ? "mn_nessun_pref" : "mn_nessun_costume")}</p>` : M.vista.map((v, i) => `<div class="mn-carta ${i === M.sel ? "focus" : ""}" data-i="${i}">
      <div class="foto">${v.mini ? `<img src="${v.mini}" alt="">` : `<svg><use href="#ragno"/></svg>`}</div>
      ${v.id === d[M.slot] ? `<span class="uso"><svg><use href="#i-ok"/></svg></span>` : ""}${(d.preferite || []).includes(v.id) ? `<span class="pref"><svg><use href="#i-stella"/></svg></span>` : ""}<b>${v.nome}</b><small><span>${autore(v)}</span>${v.albero ? `<em class="nvar" title="${t("mn_varianti_n", v.nvar)}">⧉ ${v.nvar}</em>` : ""}</small></div>`).join("");
  $$(".mn-carta").forEach(c => {
    c.onclick = () => { M.sel = +c.dataset.i; focus(); };
    c.ondblclick = () => { M.sel = +c.dataset.i; metti(); };
  });
  focus(true);
}
function focus(subito = false) {
  const d = M.dati, v = M.vista[M.sel];
  $$(".mn-carta").forEach(c => c.classList.toggle("focus", +c.dataset.i === M.sel));
  const el = $(`.mn-carta[data-i="${M.sel}"]`);
  if (el) el.scrollIntoView({ block: "nearest", behavior: subito ? "auto" : "smooth" });
  $("#mn-skin-nome").textContent = v ? v.nome : "";
  $("#mn-gruppo").textContent = v ? ((d.preferite || []).includes(v.id) ? "★ " + t("mn_preferiti") + " · " : "") + nomeGruppo(v.gruppo) : "";
  $("#mn-autore").textContent = v && autore(v) ? t("mn_di", autore(v)) : "";
  piede();
  const uso = v && (v.id === d.primaria || v.id === d.alternativa);
  $("#mn-uso").classList.toggle("nascosto", !uso);
  if (uso) $("#mn-uso").innerHTML = `✓ ${t(v.id === d.primaria ? "mn_in_uso_p" : "mn_in_uso_a")}`;
  clearTimeout(M.tmAnteprima);
  M.tmAnteprima = setTimeout(() => anteprima(v), subito ? 0 : 140);  // scorrendo veloce non carico ogni texture
}
async function anteprima(v, variante = false) {
  if (!v || !M.viewer) return;
  if (!M.tex[v.path]) {
    const d = await api().texture(v.path, 1024, 512);
    if (!d || d.errore) return;
    M.tex[v.path] = d;
  }
  if (variante ? M.va && M.va.path === v.path : M.vista[M.sel] === v) M.viewer.texture(M.tex[v.path]);
}
async function metti(path) {
  const d = M.dati, v = M.vista[M.sel];
  if (!v || M.occupato) return;
  path = path || v.path;  // senza scelta: la variante di base (le altre con L3)
  M.occupato = true;
  const el = $(`.mn-carta[data-i="${M.sel}"]`); if (el) el.classList.add("applico");
  toast(t("mn_applico", v.nome));
  const r = await api().menu_skin(M.slot, path);
  M.occupato = false;
  if (!r || !r.ok) { toast(t("errore")); disegnaSkin(); return; }
  d[M.slot] = v.id; d[M.slot + "_path"] = path;
  disegnaSkin();
  toast(t(M.slot === "primaria" ? "mn_fatto_p" : "mn_fatto_a", v.nome));
}
// ---------------------------------------------------------------- varianti (L3): personalizzatore a righe
// L'albero delle varianti è fatto a livelli (es. Fresh Start: stile -> vestiti -> gilet/berretto -> spara-ragnatele -> lenti):
// ogni livello con più di una possibilità è una riga; ←/→ cambia la scelta nella riga, ↑/↓ passa da una riga all'altra.
// Cambiando una riga, le righe sotto tengono la stessa scelta se esiste anche lì (es. "Lenses 2"), se no quella di base.
function righeVarianti(radice, scelte) {
  const righe = [];
  let nodo = radice, r = 0;
  while (nodo) {
    const opz = [...(nodo.p && nodo.f.length ? [{ n: t("mn_base"), base: true, d: !nodo.f.some(x => x.d), p: nodo.p, f: [] }] : []), ...nodo.f];
    if (!opz.length) break;  // foglia: fine
    if (opz.length === 1) { nodo = opz[0]; continue; }  // una sola strada (es. la cartella "Stiles"): niente riga
    let i = opz.findIndex(x => x.n === scelte[r]);
    if (i < 0) i = Math.max(0, opz.findIndex(x => x.d));
    righe.push({ opz, i });
    if (opz[i].base) break;
    nodo = opz[i]; r++;
  }
  let fine = righe.length ? righe[righe.length - 1].opz[righe[righe.length - 1].i] : radice;
  while (!fine.p && fine.f.length) fine = fine.f.find(x => x.d) || fine.f[0];  // per sicurezza: scendo fino a un percorso
  return { righe, path: fine.p };
}
function sceltePer(radice, path) {  // le scelte (per riga) che portano a quel percorso, se c'è
  const cerca = (nodo, acc) => {
    if (nodo.p === path) return acc;
    for (const f of nodo.f) { const r = cerca(f, [...acc, f]); if (r) return r; }
    return null;
  };
  const cat = cerca(radice, []);
  if (!cat) return [];
  const out = [];
  let nodo = radice;
  for (const x of cat) {
    if ((nodo.p && nodo.f.length ? 1 : 0) + nodo.f.length > 1) out.push(x.n);
    nodo = x;
  }
  if (nodo.f.length && nodo.p === path) out.push(t("mn_base"));
  return out;
}
function apriVarianti(v) {
  const d = M.dati, uso = d[M.slot] === v.id ? d[M.slot + "_path"] : null;
  M.va = { v, scelte: uso ? sceltePer(v.albero, uso) : [], riga: 0 };
  disegnaVarianti();
}
function chiudiVarianti() {
  M.va = null;
  $("#mn-varianti").classList.add("nascosto");
  focus(true);
}
function disegnaVarianti() {
  const d = M.dati, va = M.va, { righe, path } = righeVarianti(va.v.albero, va.scelte);
  va.righe = righe; va.path = path;
  va.riga = Math.max(0, Math.min(va.riga, righe.length - 1));
  const box = $("#mn-varianti");
  box.classList.remove("nascosto");
  box.innerHTML = `<div class="mn-va"><h3>${va.v.nome}<small>${t("mn_varianti_n", va.v.nvar)}</small></h3><div class="mn-va-lista">${righe.map((r, ri) =>
    `<div class="mn-va-riga ${ri === va.riga ? "focus" : ""}" data-r="${ri}">${r.opz.map((o, oi) =>
      `<button class="${oi === r.i ? "scelta" : ""}" data-o="${oi}">${o.n}${o.d ? " ★" : ""}</button>`).join("")}</div>`).join("")}</div>
    <div class="mn-va-fine">${path === d[M.slot + "_path"] ? `<span class="uso"><svg><use href="#i-ok"/></svg></span>${t("mn_va_in_uso")}` : t("mn_va_premi_a")}</div></div>`;
  box.querySelectorAll(".mn-va-riga").forEach(r => r.querySelectorAll("button").forEach(b => b.onclick = () => {
    va.riga = +r.dataset.r; scegliOpzione(+b.dataset.o);
  }));
  const el = box.querySelector(".mn-va-riga.focus"); if (el) el.scrollIntoView({ block: "nearest" });
  $("#mn-skin-nome").textContent = va.v.nome;
  $("#mn-autore").textContent = righe.map(r => r.opz[r.i].n).join(" · ");
  clearTimeout(M.tmAnteprima);
  M.tmAnteprima = setTimeout(() => anteprima({ path }, true), 120);  // la variante in 3D
  piede();
}
function scegliOpzione(oi) {  // nella riga attiva: le righe sopra restano, quella cambia, quelle sotto si riadattano
  const va = M.va;
  va.scelte = va.righe.map(r => r.opz[r.i].n);
  va.scelte[va.riga] = va.righe[va.riga].opz[oi].n;
  disegnaVarianti();
}
function tastoVarianti(k) {
  const va = M.va, r = va.righe[va.riga];
  if (k === "giu") va.riga = Math.min(va.righe.length - 1, va.riga + 1);
  else if (k === "su") va.riga = Math.max(0, va.riga - 1);
  else if (k === "dx" || k === "sx") { if (r) scegliOpzione((r.i + (k === "dx" ? 1 : r.opz.length - 1)) % r.opz.length); return; }
  else if (k === "b" || k === "l3") { chiudiVarianti(); return; }
  else if (k === "a") { const path = va.path; M.va = null; $("#mn-varianti").classList.add("nascosto"); metti(path); return; }
  else return;
  disegnaVarianti();
}

function cambiaSlot(verso, passo = 1) {  // principale -> alternativo -> ragnatele -> ragnatele dell'alternativo (LT / RT)
  const SL = ["primaria", "ragnatele", "alternativa", "ragnatele_alt"];  // per "look": principale, poi alternativo (L3)
  M.slot = verso || SL[(SL.indexOf(M.slot) + passo + SL.length) % SL.length];
  if (isRagM()) M.selRag = Math.max(0, ragLista().findIndex(r => r.id === ragInUso()));
  else { const i = M.vista.findIndex(v => v.id === M.dati[M.slot]); if (i >= 0) M.sel = i; }
  disegnaSkin();
  piede();
}

// ---------------------------------------------------------------- ragnatele (il filo che penzola, in 3D)
function disegnaRagnatele() {
  const d = M.dati, lista = ragLista(), inUso = ragInUso();
  const pri = (d.ragnatele || []).find(r => r.id === d.ragnatela);
  $("#mn-griglia").innerHTML = (M.slot === "ragnatele_alt" ? `<div class="mn-rag-nota ${d.ragnatela === "vanilla" ? "giallo" : ""}">${t(d.ragnatela === "vanilla" ? "rag_alt_vanilla" : "rag_alt_nota")}</div>` : "")
    + lista.map((r, i) => `<div class="mn-carta largo ${i === M.selRag ? "focus" : ""}" data-i="${i}">
      <div class="foto">${r.id === "vanilla" || r.id === "uguali" ? `<svg><use href="#ragno"/></svg>${r.id === "uguali" ? "<em>=</em>" : ""}` : M.ragImg[r.id] ? `<img src="${M.ragImg[r.id]}" alt="">` : `<span class="rotella"></span>`}</div>
      ${r.id === inUso ? `<span class="uso"><svg><use href="#i-ok"/></svg></span>` : ""}<b>${nomeRag(r)}</b><small>${r.id === "uguali" ? t("rag_uguali_sub", nomeRag(pri)) : r.id === "vanilla" ? t("rag_vanilla_sub") : t("rag_file", r.file)}</small></div>`).join("");
  $$(".mn-carta").forEach(c => {
    c.onclick = () => { M.selRag = +c.dataset.i; focusRag(); };
    c.ondblclick = () => { M.selRag = +c.dataset.i; mettiRag(); };
  });
  lista.filter(r => r.id !== "vanilla" && r.id !== "uguali" && !M.ragImg[r.id]).forEach(async r => {
    const img = await api().ragnatela_img(r.id);
    if (img && !img.errore) { M.ragImg[r.id] = img; if (isRagM()) disegnaRagnatele(); }
  });
  focusRag(true);
}
function focusRag(subito = false) {
  const d = M.dati, r = ragLista()[M.selRag];
  $$(".mn-carta").forEach(c => c.classList.toggle("focus", +c.dataset.i === M.selRag));
  const el = $(`.mn-carta[data-i="${M.selRag}"]`);
  if (el) el.scrollIntoView({ block: "nearest", behavior: subito ? "auto" : "smooth" });
  $("#mn-skin-nome").textContent = nomeRag(r);
  $("#mn-gruppo").textContent = t(M.slot === "ragnatele_alt" ? "slot_ragnatele_alt" : "slot_ragnatele");
  $("#mn-autore").textContent = "";
  const uso = r && r.id === ragInUso();
  $("#mn-uso").classList.toggle("nascosto", !uso);
  if (uso) $("#mn-uso").innerHTML = `✓ ${t("mn_in_uso_r")}`;
  clearTimeout(M.tmAnteprima);
  M.tmAnteprima = setTimeout(() => anteprimaRag(r), subito ? 0 : 140);
}
async function anteprimaRag(r) {
  if (!r || !M.viewer) return;
  const d = M.dati;
  if (r.id === "uguali") r = (d.ragnatele || []).find(x => x.id === d.ragnatela) || { id: "vanilla" };  // si vedono le principali
  if (!(r.id in M.filo)) { const f = r.id === "vanilla" ? null : await api().ragnatela_filo(r.id); M.filo[r.id] = f && !f.errore ? f : null; }
  const ora = ragLista()[M.selRag];
  if (!isRagM() || !ora || (ora !== r && !(ora.id === "uguali" && r.id === d.ragnatela))) return;
  await M.viewer.filo(M.filo[r.id]);
  M.viewer.appeso = true;
}
async function mettiRag() {
  const d = M.dati, r = ragLista()[M.selRag], alt = M.slot === "ragnatele_alt";
  if (!r || M.occupato) return;
  if (alt && d.ragnatela === "vanilla") { toast(t("rag_alt_vanilla")); return; }
  M.occupato = true;
  const el = $(`.mn-carta[data-i="${M.selRag}"]`); if (el) el.classList.add("applico");
  toast(t("mn_applico", nomeRag(r)));
  const x = await api().menu_ragnatela(r.id, alt);
  M.occupato = false;
  if (!x || !x.ok) { toast(t("errore")); disegnaSkin(); return; }
  if (alt) d.ragnatela_alt = r.id;
  else { d.ragnatela = r.id; if (r.id === "vanilla") d.ragnatela_alt = "uguali"; }
  disegnaSkin();
  toast(alt ? t(r.id === "uguali" ? "rag_alt_tolte" : "mn_fatto_ra", nomeRag(r)) : t("mn_fatto_r", nomeRag(r)));
}

// ---------------------------------------------------------------- musica (quello che suona su Windows: Spotify & co.)
const mmss = x => !x || x < 0 ? "0:00" : `${Math.floor(x / 60)}:${String(Math.floor(x % 60)).padStart(2, "0")}`;
async function musica() {
  if (M.tab !== "musica") return;
  const r = await api().menu_musica("info");
  const c = !!(r && r.sessione && r.titolo);
  $("#mu-box").classList.toggle("nascosto", !c);
  $("#mu-vuoto").classList.toggle("nascosto", c);
  if (!c) return;
  $("#mu-titolo").textContent = r.titolo; $("#mu-artista").textContent = r.artista || r.album || "";
  $("#mu-app").textContent = r.app_nome || "";
  const suona = r.stato === "Playing";
  $("#mu-play-ico").setAttribute("href", suona ? "#i-pausa2" : "#i-play");
  $("#mu-pos").style.width = r.durata > 0 ? Math.min(100, r.pos / r.durata * 100) + "%" : "0";
  $("#mu-t1").textContent = mmss(r.pos); $("#mu-t2").textContent = mmss(r.durata);
  const chiave = r.titolo + "|" + r.artista;
  if (chiave !== M.brano) {  // copertina solo quando cambia brano
    M.brano = chiave;
    const f = r.foto ? await api().menu_musica("foto") : null;
    const src = f && f.foto ? `data:${f.tipo || "image/jpeg"};base64,${f.foto}` : "";
    $("#mu-img").src = src; $("#mu-img").classList.toggle("nascosto", !src);
    $("#mu-fondo").style.backgroundImage = src ? `url("${src}")` : "none";
  }
}
async function volume(cmd = "vol") {  // volume della sola app che suona (non quello del PC)
  const r = await api().menu_musica(cmd);
  const v = r && typeof r.vol === "number" ? r.vol : -1;
  $("#mu-vol").classList.toggle("nascosto", v < 0);
  if (v >= 0) { $("#mu-vol-barra").style.width = Math.round(v * 100) + "%"; $("#mu-vol-n").textContent = Math.round(v * 100) + "%"; }
  if (cmd !== "vol") { const b = $("#mu-vol"); b.classList.add("premuto"); clearTimeout(volume.tm); volume.tm = setTimeout(() => b.classList.remove("premuto"), 300); }
}
async function musicaCmd(c) {
  const b = $(`[data-mu="${c}"]`); if (b) { b.classList.add("premuto"); setTimeout(() => b.classList.remove("premuto"), 180); }
  await api().menu_musica(c);
  setTimeout(musica, 250);
}

// ---------------------------------------------------------------- codici (cambiarli = riavviare il gioco)
const LIVELLI_CD = ["essenziale", "consigliato", "facile", "difficile", "divertimento", "miei"];
const tr = o => !o ? "" : typeof o === "string" ? o : o[L] || o.it || o.en || "";
async function caricaCodici() {
  if (!M.cd || M.cd.gid !== (M.dati && M.dati.versione)) {
    const r = await api().menu_codici();
    if (!r || r.errore) { $("#cd-lista").innerHTML = `<p class="cd-vuoto">${t("cd_nessun_gioco")}</p>`; return; }
    const ord = c => LIVELLI_CD.indexOf(c.livello) < 0 ? 99 : LIVELLI_CD.indexOf(c.livello);
    r.codici.sort((a, b) => ord(a) - ord(b));
    M.cd = { gid: r.gid, stato1: !!r.stato1, codici: r.codici, sel: 0, mod: {}, scelta: null, chiusi: new Set(["essenziale"]) };  // essenziali chiusi, come nell'app
  }
  disegnaCodici();
}
const cdOn = c => c.id in M.cd.mod ? M.cd.mod[c.id] : c.attivo;
function cdVoci() {  // righe navigabili: titolo di ogni gruppo (A = apri/chiudi) + i codici dei gruppi aperti
  const d = M.cd, out = [];
  let liv = null;
  for (const c of d.codici) {
    if (c.livello !== liv) { liv = c.livello; out.push({ gruppo: liv }); }
    if (!d.chiusi.has(liv)) out.push({ c });
  }
  return out;
}
function disegnaCodici() {
  const d = M.cd, voci = cdVoci();
  d.sel = Math.max(0, Math.min(d.sel, voci.length - 1));
  $("#cd-lista").innerHTML = voci.map((v, i) => {
    if (v.gruppo) {
      const tutti = d.codici.filter(c => c.livello === v.gruppo), accesi = tutti.filter(cdOn).length, chiuso = d.chiusi.has(v.gruppo);
      return `<div class="cd-gruppo ${chiuso ? "chiuso" : ""} ${i === d.sel ? "focus" : ""}" data-i="${i}"><i class="freccia">›</i><span>${t("sez_" + v.gruppo)}</span>
        <em>${accesi} / ${tutti.length}</em></div>`;
    }
    const c = v.c;
    return `<div class="cd-riga ${i === d.sel ? "focus" : ""} ${c.id in d.mod ? "cambiato" : ""}" data-i="${i}"><span>${tr(c.titolo)}</span>
      <i class="cd-int ${cdOn(c) ? "on" : ""}"></i></div>`;
  }).join("");
  $$("#cd-lista [data-i]").forEach(r => { r.onclick = () => { d.sel = +r.dataset.i; tastoCodici("a"); }; });
  const el = $(`#cd-lista [data-i="${d.sel}"]`); if (el) el.scrollIntoView({ block: "nearest" });
  const v = voci[d.sel], c = v && v.c;
  if (v && v.gruppo) {
    const tutti = d.codici.filter(x => x.livello === v.gruppo);
    $("#cd-info").innerHTML = `<small>${t("sez_" + v.gruppo)}</small><h3>${t("sez_" + v.gruppo)}</h3><p>${t("sez_" + v.gruppo + "_sub")}</p>
      <div class="cd-riass">${tutti.filter(cdOn).map(x => `<span>✓ ${tr(x.titolo)}</span>`).join("")}</div>
      <div class="cd-stato">${t(d.chiusi.has(v.gruppo) ? "cd_apri" : "cd_chiudi")}</div>`;
  } else $("#cd-info").innerHTML = c ? `<small>${t("sez_" + c.livello)}</small><h3>${tr(c.titolo)}</h3><p>${tr(c.desc)}</p>
    ${c.tasti ? `<div class="cd-tasti">${c.tasti.split(" | ").map(x => `<kbd class="pad">${x}</kbd>`).join(`<em>${t("com_o")}</em>`)}</div>` : ""}
    <div class="cd-stato ${cdOn(c) ? "on" : ""}">${cdOn(c) ? t("acceso") : t("spento")}${c.id in d.mod ? " · " + t("cd_da_applicare") : ""}</div>` : "";
  const n = Object.keys(d.mod).length, spenti = Object.values(d.mod).some(v => !v);
  $("#cd-mod").classList.toggle("nascosto", !n);
  if (n) $("#cd-mod").innerHTML = `<b>${n === 1 ? t("cd_modifica1") : t("cd_modifiche", n)}</b><p>${t(spenti ? "cd_nota_spenti" : "cd_nota_accesi")}</p><div><kbd class="pad y">Y</kbd>${t("cd_applica")}</div>`;
  disegnaScelta();
  piede();
}
function disegnaScelta() {
  const d = M.cd, box = $("#cd-scelta");
  box.classList.toggle("nascosto", d.scelta === null);
  if (d.scelta === null) return;
  // i codici partono solo all'avvio del gioco: si riavvia (da capo; i salvataggi del gioco restano). Nessun pulsante
  // "selezionato": ognuno ha il suo tasto (John: il riquadro rosso sul primo faceva pensare a una selezione da muovere)
  box.innerHTML = `<div class="cd-sc-box"><h3>${t("cd_riavvio_tit")}</h3><p class="cd-sc-testo">${t("cd_riavvio_testo")}</p>
    <div class="cd-sc-opz"><button data-sc="0"><b><kbd class="pad a">A</kbd> ${t("cd_riavvia_ora")}</b></button>
      ${d.stato1 ? `<button data-sc="2"><b><kbd class="pad x">X</kbd> ${t("cd_riavvia_stato1")}</b></button>` : ""}
      <button class="annulla" data-sc="1"><b><kbd class="pad b">B</kbd> ${t("annulla")}</b></button></div>
    <p class="cd-sc-passo" id="cd-passo"></p></div>`;
  box.querySelector('[data-sc="0"]').onclick = () => tastoCodici("a");
  box.querySelector('[data-sc="1"]').onclick = () => tastoCodici("b");
  const s1 = box.querySelector('[data-sc="2"]'); if (s1) s1.onclick = () => tastoCodici("x");
}
function tastoCodici(k) {
  const d = M.cd;
  if (!d) return;
  if (d.scelta !== null) {  // finestrella "riavvio il gioco?"
    if (d.inCorso) return;
    if (k === "b") { d.scelta = null; disegnaCodici(); }
    else if (k === "a" || (k === "x" && d.stato1)) { d.inCorso = true; api().menu_codici_applica(d.mod, k === "x"); menuCodiciPasso("scrivo"); }
    return;
  }
  const voci = cdVoci(), n = voci.length;
  if (k === "giu") d.sel = Math.min(n - 1, d.sel + 1);
  else if (k === "su") d.sel = Math.max(0, d.sel - 1);
  else if (k === "lt" || k === "rt") {  // una schermata su / giù (come in tanti giochi): fino alla fine di quello che vedi
    const box = $("#cd-lista"), righe = [...box.querySelectorAll("[data-i]")], r0 = box.getBoundingClientRect();
    const visibili = righe.filter(r => { const q = r.getBoundingClientRect(); return q.top >= r0.top - 2 && q.bottom <= r0.bottom + 2; }).map(r => +r.dataset.i);
    const primo = Math.min(...visibili), ultimo = Math.max(...visibili), pagina = Math.max(1, ultimo - primo);
    if (k === "rt") d.sel = d.sel < ultimo ? ultimo : Math.min(n - 1, d.sel + pagina);
    else d.sel = d.sel > primo ? primo : Math.max(0, d.sel - pagina);
  } else if (k === "dx" || k === "sx") {  // salta al gruppo dopo / prima
    const gr = voci.map((v, i) => v.gruppo ? i : -1).filter(i => i >= 0);
    d.sel = k === "dx" ? (gr.find(i => i > d.sel) ?? d.sel) : ([...gr].reverse().find(i => i < d.sel) ?? 0);
  } else if (k === "a" && voci[d.sel] && voci[d.sel].gruppo) {  // titolo del gruppo: apri / chiudi
    const g = voci[d.sel].gruppo;
    if (d.chiusi.has(g)) d.chiusi.delete(g); else d.chiusi.add(g);
  } else if (k === "a") {
    const c = voci[d.sel].c, on = !cdOn(c);
    const metti = (x, v) => { if (v === x.attivo) delete d.mod[x.id]; else d.mod[x.id] = v; };
    metti(c, on);
    if (on && c.esclusivo) d.codici.filter(o => o !== c && o.esclusivo === c.esclusivo && cdOn(o)).forEach(o => metti(o, false));
  } else if (k === "y") {
    if (!Object.keys(d.mod).length) return;
    d.scelta = true;  // finestrella "riavvio il gioco?"
  } else if (k === "b") { api().menu_chiudi(); return; }
  else return;
  disegnaCodici();
}
function menuCodiciPasso(p) {  // avanzamento del riavvio (da Python); "errore" = non è partito: la finestrella torna usabile
  if (p === "errore") {
    if (M.cd) M.cd.inCorso = false;
    const el = $("#cd-passo"); if (el) el.innerHTML = "";
    toast(t("cd_passo_errore"));
    return;
  }
  const el = $("#cd-passo"); if (el) el.innerHTML = `<span class="rotella"></span>${t("cd_passo_" + p)}`;
}


// ---------------------------------------------------------------- camera (dal vivo, anche col codice camera acceso)
// Si parte da un preset; poi 4 cursori facili che valgono per tutte le situazioni (a piedi, corsa, salto, swing, palo):
// distanza (x), altezza (+), reattività (ritardo x) e FOV. Ogni cambio va subito nel gioco: Python riscrive il codice
// camera già caricato dentro Dolphin (ar_vivo). Y lo salva anche per le prossime partite.
// In cima le due camere (principale e quella di R3: moderna / migliorata / originale / prima persona) e, se una delle due
// è la prima persona, come si muove la sua vista; sotto la camera migliorata (la "classica" del codice).
const CAMR_TUTTE = ["cpri", "calt", "vista", "preset", "dist", "alt", "rit", "fov"];
const CAM_MODO = ["cpri", "calt", "vista"], CC_MODI = ["moderna", "amazing", "cinematica", "prima", "classica", "originale"];
const ccNome = m => m === "classica" && C.tua ? "tua" : m;  // la camera del gioco coi tuoi valori si chiama "La tua"
const CC_GRUPPI = [["cc_g_nuove", ["moderna", "amazing", "cinematica", "prima"]], ["cc_g_gioco", ["classica", "originale"]]];  // (John: le camere in due gruppi, ma
// principale e alternativa possono essere di tutti e due: un elenco solo, coi pallini divisi in due gruppi col nome)
const CC_SPER = ["prima"];  // bollino "sperimentale"
const CC_CONSIGLIATE = ["moderna", "amazing"];  // principale / alternativa consigliate (John)
const CC_VISTE = ["no", "si"];  // prima persona (cam_ps4.VISTE)
const C = { dati: null, sel: 0, p: 0, d: 1, h: 0, r: 1, fov: 95, vivo: null, tm: null, tmVivo: null, salvato: true,
            modi: ["moderna", "amazing"], slot: null, gecko: false, tmModi: null, vista: "no" };
let CAMR = CAMR_TUTTE;
function camRighe() {  // la riga della vista c'è solo se una delle due camere è la prima persona; le regolazioni della
  // migliorata (preset, distanza, altezza, reattività, FOV) solo se una delle due camere è la migliorata (John)
  const prima = CAMR[C.sel];
  CAMR = CAMR_TUTTE.filter(k => (k !== "vista" || C.modi.includes("prima")) && (CAM_MODO.includes(k) || C.modi.includes("classica")));
  C.sel = Math.max(0, CAMR.indexOf(prima) >= 0 ? CAMR.indexOf(prima) : Math.min(C.sel, CAMR.length - 1));
}
async function camModiLeggi() {
  if (C.modiAttesa) return;  // stai scorrendo le camere: non rimettere quelle vecchie
  const r = await api().cam_modi();
  if (!r || r.errore || C.modiAttesa) return;
  const prima = [C.modi.join(), C.slot, C.gecko, C.vista].join("|");
  C.modi = r.modi; C.slot = r.slot; C.gecko = r.gecko; C.vista = (r.opzioni || {}).prima_vista || "no";
  C.tua = !!r.tua;  // nella camera del gioco ("classica") c'è la tua, non la Migliorata: si chiama "La tua"
  if ([C.modi.join(), C.slot, C.gecko, C.vista].join("|") !== prima && C.dati && !C.barra) disegnaCam();
}
function camModo2(i, s) {  // ←/→ su una delle due camere: cambia nel gioco e nel codice quando smetti di scorrere
  // John: scorrendo, passando sopra la camera dell'altro slot l'altro cambiava da solo (le scambiavo) -> ora l'altro non si
  // tocca (uguali = R3 non cambia niente). Un solo invio 0,35 s dopo l'ultima pressione: con un invio per pressione le
  // risposte potevano arrivare in disordine e il menu mostrava una camera mentre nel gioco ce n'era un'altra.
  const nuovi = [...C.modi];
  nuovi[i] = CC_MODI[(CC_MODI.indexOf(nuovi[i]) + s + CC_MODI.length) % CC_MODI.length];
  C.modi = nuovi; disegnaCam();
  C.modiAttesa = true;
  clearTimeout(C.tmModo);
  C.tmModo = setTimeout(camModiInvia, 350);
}
async function camModiInvia() {
  clearTimeout(C.tmModo); C.tmModo = null;
  const n = C.modiN = (C.modiN || 0) + 1, modi = [...C.modi];
  const r = await api().cam_modi_imposta(modi);
  if (n !== C.modiN || C.tmModo) return;  // nel frattempo hai scorso ancora: vale l'invio dopo
  C.modiAttesa = false;
  if (!r || r.errore || !Array.isArray(r.modi)) { toast(t("errore")); return; }
  C.modi = r.modi; disegnaCam();
  toast(r.vivo === "vecchio" ? t("cc_vecchio") : r.modi[0] === r.modi[1] ? t("cc_uguali_sub")
    : t("cc_fatto_sub", t("cc_m_" + ccNome(r.modi[0])), t("cc_m_" + ccNome(r.modi[1]))));
}
function camVista(s) {  // ←/→ sulla vista della prima persona: un solo invio quando smetti di scorrere (come camModo2)
  C.vista = CC_VISTE[(CC_VISTE.indexOf(C.vista) + s + CC_VISTE.length) % CC_VISTE.length];
  disegnaCam();
  clearTimeout(C.tmVista);
  C.tmVista = setTimeout(camVistaInvia, 350);
}
async function camVistaInvia() {
  clearTimeout(C.tmVista); C.tmVista = null;
  const n = C.vistaN = (C.vistaN || 0) + 1, v = C.vista;
  const r = await api().cam_opzione("prima_vista", v);
  if (n !== C.vistaN || C.tmVista) return;  // hai scorso ancora: vale l'invio dopo
  if (!r || r.errore) { toast(t("errore")); return; }
  toast(t("cc_vista_fatto", t("cc_vista_" + v).toLowerCase()));
}
async function camApri() {
  const r = await api().menu_cam_stato();
  if (!r || r.errore) return;
  camModiLeggi();
  clearInterval(C.tmModi); C.tmModi = setInterval(camModiLeggi, 1000);
  C.dati = r;
  const s = r.scelta || {}, i = r.preset.findIndex(p => p.chiave === (s.preset || r.ultimo_preset || "f:migliorata"));
  C.p = Math.max(0, i);
  C.d = s.d ?? 1; C.h = s.h ?? 0; C.r = s.r ?? 1; C.fov = s.fov ?? r.preset[C.p].fov;
  C.vivo = r.vivo === true ? "ok" : r.vivo === false ? "nessuno" : "cerco";
  disegnaCam();
  clearInterval(C.tmVivo);
  if (C.vivo === "cerco") C.tmVivo = setInterval(async () => {  // la ricerca del codice dentro Dolphin finisce in qualche secondo
    const x = await api().menu_cam_stato();
    if (x && x.vivo !== null && x.vivo !== undefined) { clearInterval(C.tmVivo); C.vivo = x.vivo ? "ok" : "nessuno"; disegnaCam(); }
  }, 1200);
}
function camChiudi() {
  clearInterval(C.tmVivo); clearInterval(C.tmModi);
  camAnteprima(false);
  if (C.tmModo) camModiInvia();  // stavi ancora scorrendo: la scelta vale lo stesso
  if (C.tmVista) camVistaInvia();
}
function camModo() {  // forma della finestrella: barra in basso sul gioco mentre regoli (stile TV), se no normale
  const modo = M.tab === "cam" && C.barra ? "barra" : null;
  document.body.classList.toggle("barra", modo === "barra");
  api().menu_compatto(modo);
  scala();
  camAnteprima(modo === "barra");
  if (modo === "barra") disegnaBarra();
}
async function camAnteprima(si) {  // nella barra vedi davvero la camera del gioco: se è nell'altro slot ci passo (come R3)
  // e uscendo dalla barra rimetto quella di prima (John: giocava con la moderna e "Originale" sembrava più vicina di
  // "Migliorata", ma la barra non cambiava niente a schermo)
  if (!si && !C.ant) return;
  const r = await api().menu_cam_anteprima(si);
  const prima = C.ant;
  C.ant = !!(si && r && r.anteprima);
  if (C.ant && !prima) camInvia();  // valori e FOV della barra subito sulla camera del gioco
  if (C.ant !== prima) { camModiLeggi(); if (C.barra) disegnaBarra(); }
}
function disegnaBarra() {
  const k = CAMR[C.sel];
  const st = { ok: "ok", corto: "giallo", nessuno: "giallo" }[C.vivo] || "";
  $("#cam-barra").innerHTML = `<div class="cb-sx"><i class="cb-vivo ${st}"></i><div><small>${t("cc_classica_tit")} · ${C.sel - CAMR.filter(x => CAM_MODO.includes(x)).length + 1}/${CAMR.filter(x => !CAM_MODO.includes(x)).length}</small><b>${t("cam_m_" + k)}</b>${C.ant ? `<em class="cb-nota ok">${t("cam_m_anteprima")}</em>` : C.gecko && C.slot !== null && C.modi[C.slot] !== "classica" ? `<em class="cb-nota">${t("cam_m_passa_classica")}</em>` : ""}</div></div>
    <div class="cb-centro"><kbd class="pad">←</kbd><div class="cb-val"><span>${camTesto(k)}</span>${k === "preset" ? `<div class="cam-r-pr">${C.dati.preset.map((p, j) => `<i class="${j === C.p ? "on" : ""}"></i>`).join("")}</div>`
      : `<div class="cb-b"><i style="width:${Math.round(Math.max(0, Math.min(1, camPct(k))) * 100)}%"></i></div>`}${k === "rit" ? `<em class="cb-nota">${t("cam_b_rit")}</em>` : ""}</div><kbd class="pad">→</kbd></div>
    <div class="cb-dx"><span><kbd class="pad">↑</kbd><kbd class="pad">↓</kbd>${t("cam_b_altra")}</span><span><kbd class="pad y">Y</kbd>${t(C.salvato ? "cam_m_salvato" : "cam_m_salva")}</span><span><kbd class="pad b">B</kbd>${t("mn_indietro")}</span></div>`;
}
function camValori() {  // i valori per ogni situazione: quelli del preset con i 4 cursori applicati
  const base = C.dati.preset[C.p].valori, v = {};
  for (const [g, x] of Object.entries(base))
    v[g] = [+(x[0] * C.d).toFixed(3), +(x[1] * C.d).toFixed(3), +Math.max(0, x[2] + C.h).toFixed(3), +Math.min(0.5, Math.max(0.02, x[3] * C.r)).toFixed(3)];
  return v;
}
const camScelta = () => ({ preset: C.dati.preset[C.p].chiave, d: C.d, h: C.h, r: C.r, fov: C.fov });
function camInvia() {
  C.salvato = false;
  clearTimeout(C.tm);
  C.tm = setTimeout(async () => {
    const r = await api().menu_cam_imposta(camValori(), C.fov, camScelta());
    if (r && r.vivo) { const prima = C.vivo; C.vivo = r.vivo; if (prima !== C.vivo) disegnaCam(); }
  }, 60);
}
function camTesto(k) {
  if (k === "cpri" || k === "calt") return t("cc_m_" + ccNome(C.modi[k === "cpri" ? 0 : 1]));
  if (k === "vista") return t("cc_vista_" + C.vista);
  if (k === "preset") return C.dati.preset[C.p].nome || t("cam_m_salvata_tua");
  if (k === "dist") return Math.round(C.d * 100) + "%";
  if (k === "alt") return (C.h > 0 ? "+" : "") + C.h.toFixed(1) + " m";
  if (k === "rit") return C.r < 0.95 ? t("cam_m_reattiva") + " ×" + (1 / C.r).toFixed(1) : C.r > 1.05 ? t("cam_m_morbida") + " ×" + C.r.toFixed(1) : t("cam_m_normale");
  return Math.round(C.fov) + "°";
}
function camPct(k) {
  return k === "dist" ? (C.d - 0.6) / 1.0 : k === "alt" ? (C.h + 1) / 2 : k === "rit" ? (C.r - 0.5) / 1.5 : k === "fov" ? (C.fov - 70) / 40 : 0;
}
function disegnaCam() {
  if (!C.dati) return;
  camRighe();
  const kb = (x, c = "") => `<kbd class="pad ${c}">${x}</kbd>`;
  $("#cam-righe").innerHTML = CAMR.map((k, i) => {
    const modo = CAM_MODO.includes(k), j = k === "cpri" ? 0 : 1, uso = modo && C.gecko && C.slot === j;
    const usaCl = C.gecko && C.slot !== null && C.modi[C.slot] === "classica";
    return (k === "preset" ? `<div class="cam-sep">${t("cc_classica_tit")}${usaCl || !C.gecko ? "" : `<small>${t("cam_m_passa_classica")}</small>`}</div>` : "")
      + `<div class="cam-r ${i === C.sel ? "focus" : ""} ${k} ${modo ? "modo" : ""} ${k === "calt" ? "r3" : ""}" data-i="${i}">
      <div class="cam-r-t"><b>${t("cam_m_" + k)}${uso ? `<em class="cam-uso">${t("cc_ora")}</em>` : ""}</b><span>${camTesto(k)}${modo && k !== "vista" && CC_SPER.includes(C.modi[j]) ? `<em class="sper">${t("sperimentale")}</em>` : ""}${modo && k !== "vista" && CC_CONSIGLIATE[j] === C.modi[j] ? `<em class="consigliata">★ ${t("consigliata")}</em>` : ""}</span></div>
      ${k === "vista" ? `<div class="cam-r-pr modi">${CC_VISTE.map(v => `<i class="${v === C.vista ? "on" : ""}"></i>`).join("")}</div>`
        : modo ? `<div class="cam-r-pr modi">${CC_GRUPPI.map(([g, ms]) => `<span class="cc-gr ${ms.includes(C.modi[j]) ? "on" : ""}"><small>${t(g)}</small><span>${ms.map(m => `<i class="${m === C.modi[j] ? "on" : ""}"></i>`).join("")}</span></span>`).join("")}</div>`
        : k === "preset" ? `<div class="cam-r-pr">${C.dati.preset.map((p, j) => `<i class="${j === C.p ? "on" : ""}"></i>`).join("")}</div>`
        : `<div class="cam-r-b"><i style="width:${Math.round(Math.max(0, Math.min(1, camPct(k))) * 100)}%"></i></div>`}</div>`;
  }).join("") + (C.modi.includes("classica") ? "" : `<div class="cam-sep">${t("cc_classica_tit")}<small>${t("cam_m_senza_classica")}</small></div>`);
  const f = $("#cam-righe .cam-r.focus"); if (f) f.scrollIntoView({ block: "nearest" });
  $$(".cam-r").forEach(r => r.onclick = () => { C.sel = +r.dataset.i; disegnaCam(); });
  const k = CAMR[C.sel];
  const amz = (k === "cpri" || k === "calt") && C.modi[k === "cpri" ? 0 : 1] === "amazing";  // la spalla si sceglie con le frecce
  $("#cam-info").innerHTML = `<b>${t("cam_m_" + k)}</b><p>${k === "vista" ? t("cc_vista_" + C.vista + "_sub") : t("cam_m_" + k + "_sub")}</p>${amz ? `<p>${t("cc_amazing_spalla")}</p>` : ""}`;
  const st = { ok: ["ok", "cam_m_vivo_ok"], corto: ["giallo", "cam_m_vivo_corto"], nessuno: ["giallo", "cam_m_vivo_no"], cerco: ["", "cam_m_vivo_cerco"] }[C.vivo] || ["", "cam_m_vivo_cerco"];
  $("#cam-vivo").className = "cam-vivo " + st[0];
  $("#cam-vivo").innerHTML = `${C.vivo === "cerco" ? `<span class="rotella"></span>` : `<i></i>`}${t(st[1])}`;
  $("#cam-salva-stato").textContent = C.salvato ? t("cam_m_salvato") : t("cam_m_da_salvare");
  $("#cam-salva-stato").className = C.salvato ? "ok" : "";
  disegnaVistaCam();
  if (C.barra) disegnaBarra();
  piede();
}
function disegnaVistaCam() {  // di lato: Spidey e la camera (a piedi e in swing) alla distanza e all'altezza scelte
  const v = camValori(), M2 = 50, x0 = 372, y0 = 186, tx = x0, ty = y0 - 34;
  const cam = (g, colore, nome) => {
    const d = v[g][1], h = v[g][2] + 1.0, x = x0 - d * M2, y = y0 - h * M2;
    const dir = Math.atan2(ty - y, tx - x), mezzo = (C.fov / 2) * Math.PI / 180 * 0.55, L = Math.hypot(tx - x, ty - y) + 26;
    const p = a => `${(x + L * Math.cos(a)).toFixed(1)} ${(y + L * Math.sin(a)).toFixed(1)}`;
    return `<path d="M${x} ${y} L${p(dir - mezzo)} L${p(dir + mezzo)} Z" fill="${colore}" opacity=".13"/>
      <g transform="rotate(${(dir * 180 / Math.PI).toFixed(1)} ${x} ${y})"><rect x="${x - 12}" y="${y - 7}" width="17" height="14" rx="3" fill="${colore}"/><path d="M${x + 5} ${y - 4} l7 -4 v16 l-7 -4z" fill="${colore}"/></g>
      <text x="${x}" y="${y - 14}" text-anchor="middle">${nome} · ${d.toFixed(1)} m</text>`;
  };
  $("#cam-vista").innerHTML = `<svg viewBox="0 0 420 220"><line x1="10" y1="${y0}" x2="410" y2="${y0}" class="suolo"/>
    ${cam("swing", "#4f8bff", t("cam_m_swing"))}${cam("cammina", "#e3202d", t("cam_m_piedi"))}
    <g transform="translate(${x0 - 29} ${y0 - 60})" class="spidey"><use href="#ragno" width="58" height="58"/></g></svg>`;
}
function camTasto(k, rip = 0) {  // true = tasto usato
  if (!C.dati) return k !== "b";
  const n = CAMR.length, passo = rip >= 8 ? 3 : rip >= 3 ? 2 : 1, ch = CAMR[C.sel];
  if (C.barra && k === "b") { C.barra = false; camModo(); disegnaCam(); return true; }  // dalla barra si torna al menu
  if (CAM_MODO.includes(ch) && !C.barra) {  // le due camere e la vista: si scelgono qui, senza barra
    const s = k === "sx" ? -1 : 1;
    if (k === "sx" || k === "dx" || k === "a") { if (ch === "vista") camVista(s); else camModo2(ch === "cpri" ? 0 : 1, s); return true; }
  }
  if (!C.barra && (k === "a" || k === "sx" || k === "dx")) {  // inizi a regolare: diventa una barra
    C.barra = true; camModo();
    if (k === "a") return true;
  }
  if (k === "su" || k === "giu") {
    let giri = 0;  // (tetto: se intanto le camere cambiano dalla pagina Spider-Cam il ciclo non deve girare per sempre)
    do C.sel = (C.sel + (k === "giu" ? 1 : n - 1)) % n; while (C.barra && CAM_MODO.includes(CAMR[C.sel]) && ++giri < n);  // nella barra solo la classica
    disegnaCam(); return true;
  }
  if (k === "sx" || k === "dx") {
    const s = k === "dx" ? 1 : -1;
    if (ch === "preset") { C.p = (C.p + s + C.dati.preset.length) % C.dati.preset.length; C.fov = C.dati.preset[C.p].fov; }
    else if (ch === "dist") C.d = Math.round(Math.max(0.6, Math.min(1.6, C.d + s * 0.05 * passo)) * 100) / 100;
    else if (ch === "alt") C.h = Math.round(Math.max(-1, Math.min(1, C.h + s * 0.1 * passo)) * 10) / 10;
    else if (ch === "rit") C.r = Math.round(Math.max(0.5, Math.min(2, C.r + s * 0.1 * passo)) * 10) / 10;
    else if (ch === "fov") C.fov = Math.max(70, Math.min(110, C.fov + s * passo));
    camInvia(); disegnaCam(); return true;
  }
  if (k === "x") { C.d = 1; C.h = 0; C.r = 1; C.fov = C.dati.preset[C.p].fov; camInvia(); disegnaCam(); toast(t("cam_m_ripristinata")); return true; }
  if (k === "y") { camSalva(); return true; }
  if (k === "a") return true;
  return false;
}
async function camSalva() {
  toast(t("cam_m_salvo"));
  const r = await api().menu_cam_salva(camValori(), C.fov, camScelta(), C.dati.preset[C.p].chiave);
  if (!r || r.errore || (r.errori && r.errori.length)) { toast(t("errore")); return; }
  C.salvato = true; disegnaCam();
  toast(t("cam_m_salvata", (r.versioni || []).map(g => ({ GK2E52: "USA", GK2P52: "UK", GK2I52: "ITA", GK2D52: "DE", GK2F52: "FR" })[g]).join(", ")));
}
function camPiede(k) {
  return [[k("", "↑") + k("", "↓"), t("mn_scegli")], [k("", "←") + k("", "→"), t("cam_m_cambia")], [k("y", "Y"), t("cam_m_salva")],
    [k("x", "X"), t("cam_m_ripristina")], [k("", "LB") + k("", "RB"), t("mn_sezione")], [k("b", "B"), t("mn_chiudi")]];
}

// ---------------------------------------------------------------- stati salvati (pannellino, tasto Menu)
// due schede, SALVA (di base) e CARICA (LT/RT): A fa l'azione della scheda; caricare chiede sempre un secondo A, salvare
// sopra uno slot usato pure (John: un amico ha caricato al posto di salvare, con A = carica e X = salva)
async function pannelloStati(si) {
  ST.aperto = si; ST.conferma = false; ST.modo = "salva";
  $("#mn-pannello-stati").classList.toggle("nascosto", !si);
  piede();
  if (!si) return;
  $("#mn-st-lista").innerHTML = `<div class="mn-st-attesa"><span class="rotella"></span></div>`;
  const r = await api().menu_stati();
  ST.lista = r && !r.errore ? r.stati : [];
  disegnaStati();
}
function disegnaStati() {
  const per = Object.fromEntries(ST.lista.map(s => [s.n, s]));
  $("#mn-st-lista").innerHTML = [1, 2, 3, 4, 5, 6, 7, 8].map((n, i) => {
    const s = per[n], quando = s ? new Date(s.data * 1000) : null;
    return `<div class="mn-st-slot ${i === ST.sel ? "focus" : ""} ${s ? "" : "vuoto"} ${s && s.compatibile === false ? "rosso" : ""}" data-i="${i}">
      <div class="foto">${s && s.foto ? `<img src="data:image/jpeg;base64,${s.foto}" alt="">` : `<span>${n}</span>`}</div>
      <b>${t("mn_st_slot", n)}</b><small>${s ? quando.toLocaleDateString(L, { day: "2-digit", month: "short" }) + " " + quando.toLocaleTimeString(L, { hour: "2-digit", minute: "2-digit" }) : t("mn_st_vuoto")}</small></div>`;
  }).join("");
  $$(".mn-st-slot").forEach(e => { e.onclick = () => { ST.sel = +e.dataset.i; ST.conferma = false; disegnaStati(); }; e.ondblclick = () => { ST.sel = +e.dataset.i; tastoStati("a"); }; });
  const s = per[ST.sel + 1];
  $("#mn-st-modi").innerHTML = ["salva", "carica"].map(m => `<button class="${ST.modo === m ? "attivo" : ""}" data-m="${m}">${t(m === "salva" ? "mn_st_tab_salva" : "mn_st_tab_carica")}</button>`).join("");
  $$("#mn-st-modi button").forEach(b => b.onclick = () => { ST.modo = b.dataset.m; ST.conferma = false; disegnaStati(); });
  $("#mn-pannello-stati").classList.toggle("carica", ST.modo === "carica");
  $("#mn-st-avviso").textContent = ST.conferma ? t(ST.modo === "carica" ? "mn_st_carica_sicuro" : "mn_st_sovrascrivi", ST.sel + 1)
    : s && s.compatibile === false ? t("mn_st_vecchio") : "";
  piede();
}
async function tastoStati(k) {
  if (ST.occupato) return;
  const n = ST.sel + 1, esiste = ST.lista.some(s => s.n === n);
  if (k === "b" || k === "start") { pannelloStati(false); return; }
  if (k === "dx") ST.sel = Math.min(7, ST.sel + 1);
  else if (k === "sx") ST.sel = Math.max(0, ST.sel - 1);
  else if (k === "lt" || k === "rt") { ST.modo = ST.modo === "carica" ? "salva" : "carica"; }
  else if (k === "a" && ST.modo === "carica") {
    if (!esiste) { toast(t("mn_st_vuoto")); return; }
    if (!ST.conferma) { ST.conferma = true; disegnaStati(); return; }  // secondo A: carichi davvero
    ST.conferma = false; toast(t("mn_st_carico", n)); api().menu_stato_carica(n); return;
  }
  else if (k === "a") {
    if (esiste && !ST.conferma) { ST.conferma = true; disegnaStati(); return; }  // c'è già: secondo A per sovrascrivere
    ST.occupato = true; ST.conferma = false; toast(t("mn_st_salvo", n));
    const r = await api().menu_stato_salva(n);
    ST.occupato = false;
    if (r && !r.errore) { ST.lista = r.stati; toast(t("mn_st_salvato", n)); }
    else toast(t(r && r.errore === "st_err_tasti" ? "st_err_tasti" : "errore"));
  } else return;
  if (k !== "a") ST.conferma = false;
  disegnaStati();
}

// ---------------------------------------------------------------- controller (pannellino)
const VOCI_SI = ["riduci", "intero", "esci"];
function pannelloPad(si) {
  SI.aperto = si; SI.conferma = false;
  $("#mn-pannello-pad").classList.toggle("nascosto", !si);
  if (si) {
    disegnaSistema();
    const p = M.dati && M.dati.pad;
    const st = !p ? ["giallo", t("gp_nessuno")] : p.esito === "ok" ? ["ok", t("gp_ok", p.pad && p.pad.nome)] : p.esito === "sdl" || p.esito === "xinput" || p.esito === "nome"
      ? ["rosso", t("gp_sbagliato", p.pad && p.pad.nome)] : p.esito === "nessuno" ? ["giallo", t("gp_nessuno")] : ["giallo", t("gp_altro", p.pad && p.pad.nome)];
    $("#mn-pp-stato").innerHTML = `<div class="mn-pp-stato ${st[0]}">${st[1]}</div>`;
    const c = (M.dati && M.dati.comandi) || {};  // come la finestra Comandi dell'app: solo i comandi dei codici accesi
    const righe = [["RB", "com_skin"], ...(c.tuffo ? [["L3", "com_tuffo"]] : []), ["L3", "com_lock"], ["R3", c.moderna === false ? "com_cam" : "com_cam_mod"],
      ["Select", "com_mappa"], ["LB", "com_hud_toggle"], ...(c.amazing ? [["←", "com_spalla_sx"], ["→", "com_spalla_dx"]] : []),
      ...(c.fov ? [["←", "com_fov_su"], ["→", "com_fov_giu"]] : []), ["LB + RB", "mn_questo"]];
    $("#mn-pp-comandi").innerHTML = righe.map(([k, x]) => `<div class="mn-pp-riga"><span>${t(x)}</span><kbd class="pad">${k}</kbd></div>`).join("");
  }
  piede();
}
function disegnaSistema() {
  const ic = { esci: "i-esci", intero: "i-schermo", riduci: "i-riduci" };
  $("#mn-si-voci").innerHTML = VOCI_SI.map((v, i) => `<button class="mn-si-voce ${v} ${i === SI.sel ? "focus" : ""} ${v === "esci" && SI.conferma ? "conferma" : ""}" data-i="${i}">
      <svg><use href="#${ic[v]}"/></svg><span><b>${t(v === "esci" && SI.conferma ? "mn_si_esci_sicuro" : "mn_si_" + v)}</b><small>${t("mn_si_" + v + "_sub")}</small></span></button>`).join("");
  $$(".mn-si-voce").forEach(b => b.onclick = () => { SI.sel = +b.dataset.i; tastoSistema("a"); });
  piede();
}
function tastoSistema(k) {
  if (k === "b" || k === "select") { if (SI.conferma) { SI.conferma = false; disegnaSistema(); } else pannelloPad(false); return; }
  if (k === "su" || k === "giu") { SI.sel = (SI.sel + (k === "giu" ? 1 : VOCI_SI.length - 1)) % VOCI_SI.length; SI.conferma = false; disegnaSistema(); return; }
  if (k !== "a") return;
  const v = VOCI_SI[SI.sel];
  if (v === "esci") {
    if (!SI.conferma) { SI.conferma = true; disegnaSistema(); return; }  // secondo A per uscire davvero
    toast(t("mn_si_esco")); api().menu_esci();
  } else if (v === "intero") { api().menu_schermo_intero(); pannelloPad(false); }
  else if (v === "riduci") { pannelloPad(false); api().menu_riduci(); }

}

// ---------------------------------------------------------------- tasti (pad da Python, tastiera, mouse)
function menuTasto(k, rip = 0) {  // rip = quante volte si è ripetuto tenendo premuto (per scorrere veloce)
  if (typeof M3 !== "undefined" && M3.stato) { tastoM3(k); return; }  // vista 3D della città (menu_mappa.js)
  if (typeof MC !== "undefined" && MC.aperto) { tastoEsplora(k, rip); return; }  // mappa della città (menu_mappa.js)
  if (ST.aperto) { tastoStati(k); return; }
  if (M.va) { tastoVarianti(k); return; }
  if (SI.aperto) { tastoSistema(k); return; }
  if ((k === "start" || k === "select") && M.tab === "cam" && C.barra) { C.barra = false; camModo(); disegnaCam(); }
  if (k === "start") { pannelloStati(true); return; }
  if (k === "lb" || k === "rb") { vai(TAB[(TAB.indexOf(M.tab) + (k === "rb" ? 1 : TAB.length - 1)) % TAB.length]); return; }
  if (k === "select") { pannelloPad(true); return; }
  if (M.tab === "cam" && camTasto(k, rip)) return;
  if (M.tab === "ora" && tastoOra(k, rip)) return;
  if (M.tab === "codici") { tastoCodici(k); return; }  // prima del B: nella finestrella "riavvio?" B annulla (non chiude il menu)
  if (k === "b") { api().menu_chiudi(); return; }
  if (M.tab === "musica") {
    const c = { a: "play", sx: "prev", dx: "next" }[k];
    if (c) musicaCmd(c);
    else if (k === "su" || k === "giu") volume(k === "su" ? "vol+" : "vol-");
    return;
  }
  if (M.tab !== "skin" || !M.dati) return;
  if (k === "lt" || k === "rt") { cambiaSlot(null, k === "rt" ? 1 : -1); return; }  // principale / alternativo / ragnatele
  if (k === "r3") { M.fermo = !M.fermo; toast(t(M.fermo ? "mn_fermo" : "mn_gira_di_nuovo")); piede(); return; }
  if (isRagM()) {
    const nr = ragLista().length;
    if (k === "dx") M.selRag = Math.min(nr - 1, M.selRag + 1);
    else if (k === "sx") M.selRag = Math.max(0, M.selRag - 1);
    else if (k === "giu") M.selRag = Math.min(nr - 1, M.selRag + 2);
    else if (k === "su") M.selRag = Math.max(0, M.selRag - 2);
    else if (k === "a") { mettiRag(); return; }
    else return;
    focusRag(); return;
  }
  if (k === "x") { cambiaOrdine(1); toast(t("mn_ord_" + M.ordine)); return; }
  const n = M.vista.length;
  if (k === "dx") M.sel = Math.min(n - 1, M.sel + 1);
  else if (k === "sx") M.sel = Math.max(0, M.sel - 1);
  else if (k === "giu") M.sel = Math.min(n - 1, M.sel + COLONNE);
  else if (k === "su") M.sel = Math.max(0, M.sel - COLONNE);
  else if (k === "a") { metti(); return; }
  else if (k === "y") { preferito(); return; }
  else if (k === "l3") { const v = M.vista[M.sel]; if (v && v.albero) apriVarianti(v); return; }
  else return;
  focus();
  if (rip >= 5) lettera();  // scorrendo veloce: la lettera grande dove sei arrivato
}
function lettera() {
  const v = M.vista[M.sel], b = $("#mn-lettera");
  if (!v) return;
  b.textContent = M.ordine === "autore" ? (autore(v) || nomeGruppo(v.gruppo)) : (v.nome[0] || "").toUpperCase();
  b.classList.remove("nascosto");
  clearTimeout(lettera.tm); lettera.tm = setTimeout(() => b.classList.add("nascosto"), 450);
}
// velo sopra tutto il gioco (Python: _copri). stato: "su" = foto del gioco che si sfoca e scritta, "cambia" = un'altra foto
// (sfocata) in dissolvenza, "giu" = foto nuova che torna a fuoco (subito dopo Python toglie il velo), "via" = tolto
function copri(o) {
  const c = $("#mn-copri"), a = c.querySelector(".cp-a"), b = c.querySelector(".cp-b");
  const src = x => x ? "data:image/jpeg;base64," + x : "";
  if (o.testo !== undefined) c.querySelector(".cp-testo b").textContent = o.testo ? t(o.testo, ...(o.args || [])) : "";
  if (o.sub !== undefined) c.querySelector(".cp-testo small").textContent = o.sub ? t(o.sub, ...(o.args || [])) : "";
  c.classList.toggle("ok", !!o.ok);
  c.classList.toggle("fermo", !!o.fermo);
  if (o.stato === "su") {  // subito sfocata: la finestra si allarga e per un fotogramma WebView2 mostra la sua immagine
    // vecchia; partendo nitida e sfocando si vedeva "sfocato, nitido, sfocato"
    c.classList.add("secco", "sfoca");
    a.src = src(o.img); b.classList.remove("su"); b.src = "";
    document.body.classList.add("copri");
    void c.offsetWidth;
    c.classList.remove("secco");
  } else if (o.stato === "cambia") {
    if (o.img) { b.src = src(o.img); b.classList.add("su"); }
  } else if (o.stato === "giu") {
    c.classList.add("secco");
    if (o.img) { a.src = src(o.img); }
    b.classList.remove("su");
    void c.offsetWidth;
    c.classList.remove("secco");
    requestAnimationFrame(() => c.classList.remove("sfoca"));
  } else if (o.stato === "via") {
    document.body.classList.remove("copri");
    c.classList.remove("sfoca", "ok", "fermo");
    a.src = ""; b.src = ""; b.classList.remove("su");
    scala();
  }
  return true;
}
function menuChiuso() {  // il menu è stato nascosto (da Python): niente lavoro in sottofondo mentre giochi
  M.chiuso = true; M.vero = false;
  if (document.body.classList.contains("copri")) copri({ stato: "via" });
  clearInterval(M.tmMusica);
  camChiudi();
  oraChiudi();
  if (typeof MC !== "undefined" && MC.aperto) mcChiudi();
}
function menuStickL(x, y) {  // stick sinistro analogico (da Python): solo la mappa della città lo usa (il resto usa le frecce)
  if (typeof MC !== "undefined" && MC.aperto) mcStick(x, y, true);
}
function menuStick(x, y) {  // stick destro (da Python): gira e avvicina lo Spidey 3D, come trascinare e la rotella del mouse
  if (typeof MC !== "undefined" && MC.aperto) { mcStick(x, y); return; }  // sulla mappa della città: la muove
  const v = M.viewer;
  if (!v || M.tab !== "skin") return;
  v.ang += x * 0.075;
  v.dist = Math.max(1.6, Math.min(7, v.dist * (1 + y * 0.035)));
}
document.addEventListener("keydown", e => {
  if (e.altKey && e.key === "Enter") { e.preventDefault(); api().menu_schermo_intero(); return; }  // come nel gioco
  if (e.target && e.target.tagName === "INPUT") {  // si scrive (nome di un posto salvato): solo Invio / Esc al menu
    if (e.key === "Enter" || e.key === "Escape") { e.preventDefault(); menuTasto(e.key === "Enter" ? "a" : "b"); }
    return;
  }
  const m = { ArrowUp: "su", ArrowDown: "giu", ArrowLeft: "sx", ArrowRight: "dx", Enter: "a", Escape: "b", x: "x", y: "y", q: "lb", e: "rb", Tab: "rb", c: "select", "1": "lt", "2": "rt", F2: "l3" }[e.key];
  if (m) { e.preventDefault(); menuTasto(m); }
});
$$("#mn-tab [data-tab]").forEach(b => b.onclick = () => vai(b.dataset.tab));
$$(".mn-slot [data-slot]").forEach(b => b.onclick = () => { if (b.dataset.slot !== M.slot) cambiaSlot(b.dataset.slot); });

// il menu è disegnato per 1040 x 640 e si ingrandisce/rimpicciolisce con la finestra (che segue quella del gioco)
function scala() {
  const [bw, bh] = document.body.classList.contains("barra") ? [1040, 150] : [1040, 640];
  const z = Math.min(innerWidth / bw, innerHeight / bh) || 1;
  $("#menu").style.zoom = z;
}
addEventListener("resize", scala);
scala();
$("#mn-pad").onclick = () => pannelloPad(true);
$("#mn-stati").onclick = () => pannelloStati(true);
$("#mn-pannello-stati").onclick = e => { if (e.target.id === "mn-pannello-stati") pannelloStati(false); };
$$("[data-mu]").forEach(b => b.onclick = () => musicaCmd(b.dataset.mu));
$("#mn-pannello-pad").onclick = e => { if (e.target.id === "mn-pannello-pad") pannelloPad(false); };

// ---------------------------------------------------------------- avvio
async function modelloPronto() {  // da Python: il modello 3D è stato ricostruito dal disco del gioco
  const m = await modelliSpidey(true);
  if (MODELLI_SPIDEY && M.viewer) M.viewer.ricarica(m);
}
window.addEventListener("pywebviewready", async () => {
  testi(); piede();
  try {
    const m = await modelliSpidey();
    M.viewer = new Viewer($("#mn-3d"), m.gioco, { ang: -0.35, alt: 0.12, dist: 3.25 });
    M.viewer.usaModello("idle", m.idle);
    M.viewer.auto = false;
    M.viewer.avvia();
    setInterval(() => { if (!M.chiuso && !M.viewer.trasc && !M.fermo) M.viewer.ang += 0.006; }, 16);  // R3 lo ferma
  } catch (e) { /* senza 3D il menu funziona lo stesso */ }
  await api().menu_pronto();
});
// errori del menu nel registro dell'app (errori.log), come per le pagine dell'app
window.addEventListener("error", e => { try { api().log_js("menu: " + e.message + " @" + (e.filename || "").split("/").pop() + ":" + e.lineno); } catch (_) {} });
window.addEventListener("unhandledrejection", e => { try { api().log_js("menu promise: " + (e.reason && (e.reason.stack || e.reason))); } catch (_) {} });
