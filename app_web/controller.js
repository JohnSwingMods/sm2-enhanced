// ================================================================ controller
// Legge il pad collegato (Gamepad API), dice se il profilo dei tasti di Dolphin va bene per quel pad e permette di
// cambiare i tasti premendoli sul pad. Il profilo vive in Dolphin (Config/Profiles/GCPad/spiderman 2.ini).
const X = { dati: null, ascolto: null, prima: [], pad: null, firmaPad: "", salvo: false };
const STD_XINPUT = ["Button A", "Button B", "Button X", "Button Y", "Shoulder L", "Shoulder R", "Trigger L", "Trigger R",
  "Back", "Start", "Thumb L", "Thumb R", "Pad N", "Pad S", "Pad W", "Pad E"];
const STD_SDL = ["Button S", "Button E", "Button W", "Button N", ...STD_XINPUT.slice(4)];
const SDL_A_XINPUT = { "Button S": "Button A", "Button E": "Button B", "Button W": "Button X", "Button N": "Button Y", View: "Back", Menu: "Start", "Bumper L": "Shoulder L", "Bumper R": "Shoulder R" };
const ETICHETTE = {
  xbox: { "Button A": "A", "Button B": "B", "Button X": "X", "Button Y": "Y", "Shoulder L": "LB", "Shoulder R": "RB", "Trigger L": "LT", "Trigger R": "RT",
    Back: "View", Start: "Menu", "Thumb L": "L3", "Thumb R": "R3", "Pad N": "↑", "Pad S": "↓", "Pad W": "←", "Pad E": "→" },
  ps: { "Button A": "✕", "Button B": "○", "Button X": "□", "Button Y": "△", "Shoulder L": "L1", "Shoulder R": "R1", "Trigger L": "L2", "Trigger R": "R2",
    Back: "Create", Start: "Options", "Thumb L": "L3", "Thumb R": "R3", "Pad N": "↑", "Pad S": "↓", "Pad W": "←", "Pad E": "→" },
  switch: { "Button A": "B", "Button B": "A", "Button X": "Y", "Button Y": "X", "Shoulder L": "L", "Shoulder R": "R", "Trigger L": "ZL", "Trigger R": "ZR",
    Back: "−", Start: "+", "Thumb L": "L3", "Thumb R": "R3", "Pad N": "↑", "Pad S": "↓", "Pad W": "←", "Pad E": "→" },
};
const GC = [["Buttons/A", "A", "gc-a"], ["Buttons/B", "B", "gc-b"], ["Buttons/X", "X", "gc-xy"], ["Buttons/Y", "Y", "gc-xy"], ["Buttons/Z", "Z", "gc-z"],
  ["Buttons/Start", "Start", "gc-st"], ["Triggers/L", "L", "gc-lr"], ["Triggers/R", "R", "gc-lr"], ["D-Pad/Up", "↑", "gc-dp"], ["D-Pad/Down", "↓", "gc-dp"],
  ["D-Pad/Left", "←", "gc-dp"], ["D-Pad/Right", "→", "gc-dp"]];
const EXTRA_CT = [["costume", "i-giu", "ct_x_costume", "ct_x_costume_sub"], ["camera", "i-cam", "ct_x_camera", "ct_x_camera_sub"], ["mappa", "i-globo", "ct_x_mappa", "ct_x_mappa_sub"], ["hud", "i-schermo", "ct_x_hud", "ct_x_hud_sub"]];

function famigliaPad(id) {  // dal nome che dà il browser: "Xbox 360 Controller (XInput STANDARD GAMEPAD)", "DualSense ... Vendor: 054c Product: 0ce6"
  const s = (id || "").toLowerCase();
  if (/054c|dualsense|dualshock|playstation/.test(s)) return { fam: "ps", sdl: /0ce6|0df2|dualsense/.test(s) ? "ps5" : "ps4" };
  if (/057e|nintendo|pro controller/.test(s)) return { fam: "switch", sdl: "switch" };
  if (/xinput|xbox|045e/.test(s)) return { fam: "xbox" };
  return { fam: "altro" };
}
function nomePad(id) { return (id || "").replace(/\s*\((?:XInput )?STANDARD GAMEPAD.*\)\s*$/i, "").replace(/\s*\(Vendor.*\)\s*$/i, "").trim() || "Controller"; }
function famEtichette() {  // come sono scritti i tasti sul pad: dal pad visto dal browser, se no da quello visto da Windows
  if (X.pad) return ETICHETTE[X.pad.fam] || ETICHETTE.xbox;
  const w = X.dati && X.dati.pad && X.dati.pad.pad;
  return w ? ETICHETTE[w.tipo] || ETICHETTE.xbox : ETICHETTE.xbox;
}
function etich(nome) {  // nome del tasto in Dolphin -> come è scritto sul pad
  if (!nome) return "—";
  return famEtichette()[SDL_A_XINPUT[nome] || nome] || nome;
}
function etichNeutra(nome, def) {  // per la finestra Comandi: L3 / R3 / Select uguali per tutti
  const n = SDL_A_XINPUT[nome] || nome;
  return { "Thumb L": "L3", "Thumb R": "R3", Back: "Select", "Button L3": "L3", "Button R3": "R3", Select: "Select", "Shoulder L": "LB", "Button L1": "L1" }[n] || (n ? etich(n) : def);
}
function ctProfilo() { return X.dati && (X.dati.profilo || X.dati.predefinito); }

async function caricaController() {
  const r = await api().controller_stato();
  if (!r || r.errore) { toast(t("errore"), (r && r.errore) || "", "errore"); return; }
  X.dati = r;
  disegnaController();
}
function ctStatoPad() {  // il profilo va bene per il pad collegato? (lo decide Python: conosce anche il nome che usa Dolphin)
  const p = X.dati && X.dati.profilo, pad = X.pad, e = X.dati && X.dati.pad && X.dati.pad.esito;
  if (!pad || !p) return null;
  if (e === "ok") return { tipo: "ok", k: p.backend === "sdl" ? "ct_st_ok_sdl" : "ct_st_ok" };
  if (e === "nome") return { tipo: "rosso", k: "ct_st_nome", azione: "auto" };
  if (e === "sdl") return { tipo: "rosso", k: pad.fam === "ps" || pad.fam === "switch" ? "ct_st_" + pad.fam : "ct_st_altro_sdl", azione: "auto" };
  if (e === "xinput") return { tipo: "giallo", k: "ct_st_xbox_sdl", azione: "auto" };
  if (e === "altro") return { tipo: "giallo", k: "ct_st_altro", azione: "auto" };
  if (pad.browser && pad.mapping !== "standard") return { tipo: "giallo", k: "ct_st_strano" };  // solo letto dal browser (Python non lo vede)
  if (pad.fam === "xbox") return p.backend === "xinput" ? { tipo: "ok", k: "ct_st_ok" } : { tipo: "giallo", k: "ct_st_xbox_sdl", azione: "xinput" };
  if (pad.fam === "ps" || pad.fam === "switch") return p.backend === "sdl" ? { tipo: "ok", k: "ct_st_ok_sdl" } : { tipo: "rosso", k: "ct_st_" + pad.fam, azione: "sdl" };
  return { tipo: "giallo", k: "ct_st_altro" };
}
function disegnaPad() {
  const box = $("#ct-pad");
  if (!box) return;
  const pad = X.pad;
  const pyp = X.dati && X.dati.pad && X.dati.pad.tutti && X.dati.pad.tutti[0];  // visto da Windows anche senza aver premuto niente
  if (!pad && pyp) {
    const st = X.dati.pad.esito;  // stessi esiti di ctStatoPad: ok / nome / sdl / xinput / manca / altro / nessuno
    box.innerHTML = `<div class="ct-pad-testa"><div class="ct-pad-icona ${pyp.tipo}"><svg><use href="#${pyp.tipo === "xbox" ? "i-xbox" : "i-hud"}"/></svg></div>
      <div><h3>${pyp.nome}</h3><p class="ct-sub">${t("ct_premi_per_provare")}</p></div></div>
      <div class="ct-stato ${st === "ok" ? "ok" : st === "sdl" || st === "xinput" || st === "nome" || st === "manca" ? "rosso" : "giallo"}"><svg><use href="#${st === "ok" ? "i-ok" : "i-ingr"}"/></svg>
      <span>${t(st === "ok" ? (pyp.tipo === "xbox" ? "ct_st_ok" : "ct_st_ok_sdl") : st === "nome" ? "ct_st_nome" : st === "manca" ? "ct_av_profilo"
        : st === "sdl" ? (pyp.tipo === "altro" ? "ct_st_altro_sdl" : "ct_st_" + pyp.tipo) : st === "xinput" ? "ct_st_xbox_sdl" : "ct_st_altro")}</span></div>
      ${st !== "ok" && st !== "nessuno" ? `<div class="ct-azioni"><button class="primario" id="ct-cambia-profilo">${t("ct_auto")}</button></div><p class="nota">${t("ct_auto_nota")}</p>` : ""}`;
    const b = $("#ct-cambia-profilo");
    if (b) b.onclick = async () => { b.disabled = true; const ok = await giSistemaPad(X.dati.pad); b.disabled = false; if (ok) disegnaController(); };
    return;
  }
  if (!pad) {
    box.innerHTML = `<div class="ct-pad-testa"><div class="ct-pad-icona vuota"><svg><use href="#i-hud"/></svg></div>
      <div><h3>${t("ct_nessuno")}</h3><p class="ct-sub">${t("ct_nessuno_sub")}</p></div></div>`;
    return;
  }
  const st = ctStatoPad(), famNome = { xbox: "Xbox / XInput", ps: "PlayStation", switch: "Nintendo Switch", altro: t("ct_generico") }[pad.fam] || t("ct_generico");
  const bottone = st && st.azione ? `<button class="primario" id="ct-cambia-profilo">${t(st.azione === "auto" ? "ct_auto" : st.azione === "sdl" ? "ct_usa_sdl" : "ct_usa_xinput")}</button>` : "";
  box.innerHTML = `<div class="ct-pad-testa"><div class="ct-pad-icona ${pad.fam}"><svg><use href="#${pad.fam === "xbox" ? "i-xbox" : "i-hud"}"/></svg></div>
      <div><h3>${pad.nome || nomePad(pad.id)}</h3><p class="ct-sub">${famNome}${X.altri > 0 ? " · " + t("ct_altri", X.altri) : ""}</p></div></div>
    ${st ? `<div class="ct-stato ${st.tipo}"><svg><use href="#${st.tipo === "ok" ? "i-ok" : "i-ingr"}"/></svg><span>${t(st.k)}</span></div>` : ""}
    ${bottone ? `<div class="ct-azioni">${bottone}</div>` : ""}
    ${st && st.azione ? `<p class="nota">${t("ct_auto_nota")}</p>` : ""}`;
  const b = $("#ct-cambia-profilo");
  if (b) b.onclick = async () => {
    b.disabled = true;
    const ok = await giSistemaPad(X.dati.pad);
    b.disabled = false;
    if (ok) disegnaController();
  };
}
function disegnaAvvisi() {
  const d = X.dati, box = $("#ct-avvisi");
  if (!d) return;
  const righe = [];
  if (!d.dolphin) righe.push(["no", "ct_av_dolphin", null]);
  else {
    if (!d.esiste) righe.push(["giallo", "ct_av_profilo", "sistema"]);
    if (d.ini_senza.length) righe.push(["giallo", t("ct_av_ini", d.ini_senza.map(g => NOMI_VER_CT[g] || g).join(", ")), "sistema"]);
    if (d.profilo && d.profilo.avanzato) righe.push(["giallo", "ct_av_avanzato", null]);
    if (d.dolphin_aperto) righe.push(["info", "ct_av_aperto", null]);
  }
  box.innerHTML = righe.map(([tipo, k, az]) => `<div class="patch-barra ${tipo}"><svg><use href="#i-ingr"/></svg><span>${k.includes(" ") ? k : t(k)}</span>
    ${az ? `<button class="primario" data-ct="${az}">${t("ct_sistema")}</button>` : ""}</div>`).join("");
  box.querySelectorAll("[data-ct=sistema]").forEach(b => b.onclick = async () => {
    const r = await api().controller_sistema();
    if (!r || r.errore) { toast(t("errore"), (r && r.errore) || "", "errore"); return; }
    X.dati = r; disegnaController(); toast(t("fatto"), t("ct_sistemato"), "", 3500);
  });
}
const NOMI_VER_CT = { GK2E52: "USA", GK2P52: "UK", GK2I52: "ITA", GK2D52: "DE", GK2F52: "FR" };
function rigaTasto(dove, k, titolo, sub, nome, icona) {
  const asc = X.ascolto && X.ascolto.dove === dove && X.ascolto.k === k;
  return `<div class="ct-riga ${asc ? "ascolto" : ""}" data-dove="${dove}" data-k="${k}">
    ${icona}<div class="ct-cosa"><b>${titolo}</b>${sub ? `<small>${sub}</small>` : ""}</div>
    <span class="ct-tasto ${nome ? "" : "vuoto"}">${asc ? t("ct_premi") : etich(nome)}</span>
    <button class="leggero mini" data-azione="cambia">${asc ? t("annulla") : t("ct_cambia")}</button>
    ${dove === "extra" && nome && !asc ? `<button class="tondo mini" data-azione="togli" data-tip="ct_togli">×</button>` : ""}</div>`;
}
function disegnaController() {
  if (S.pagina !== "controller") return;
  disegnaAvvisi();
  disegnaPad();
  const p = ctProfilo();
  const ok = !!(X.dati && X.dati.dolphin);
  $("#pg-controller .ct-destra").classList.toggle("spento", !ok);
  if (!p) return;
  $("#ct-extra").innerHTML = EXTRA_CT.map(([k, ic, tit, sub]) => rigaTasto("extra", k, t(tit), t(sub), p.extra[k],
    `<span class="ct-ico"><svg><use href="#${ic}"/></svg></span>`)).join("");
  const USATO = { "Buttons/Z": "ct_usa_z", "Buttons/Start": "ct_usa_start", "D-Pad/Down": "ct_usa_giu", "D-Pad/Left": "ct_usa_sx", "D-Pad/Right": "ct_usa_dx" };  // codici della mod che usano quel tasto
  $("#ct-base").innerHTML = GC.map(([k, lab, cl]) => rigaTasto("base", k, t("ct_gc_tasto", lab), USATO[k] ? "⚙ " + t(USATO[k]) : "", p.base[k], `<span class="gc-btn ${cl}">${lab}</span>`)).join("");
  $$("#pg-controller .ct-riga").forEach(r => {
    const dove = r.dataset.dove, k = r.dataset.k;
    r.querySelector("[data-azione=cambia]").onclick = () => ctAscolta(dove, k);
    const tg = r.querySelector("[data-azione=togli]");
    if (tg) tg.onclick = () => ctAssegna({ dove, k }, null);
  });
  for (const a of ["y", "x"]) {  // camera invertita: nel profilo del pad, vale per tutte le camere
    const c = $("#ct-inv-" + a);
    c.checked = !!(X.dati.inverti && X.dati.inverti[a]);
    c.onchange = async () => {
      const r = await api().controller_inverti(a, c.checked);
      if (!r || r.errore) { c.checked = !c.checked; toast(t("errore"), r && r.errore === "dolphin" ? t("err_dolphin") : (r && r.errore) || "", "errore"); return; }
      X.dati = r;
      toast(t("ct_salvato"), r.dolphin_aperto ? t("ct_dal_prossimo") : "", "", 2200);
    };
  }
  $("#ct-ripristina").onclick = async () => {
    const r = await modale({ titolo: t("ct_ripristina"), testo: t("ct_ripristina_testo"), bottoni: [["no", t("annulla")], ["si", t("ct_ripristina"), true]] });
    if (r !== "si") return;
    if (await giSistemaPad(X.dati.pad, true)) disegnaController();  // tasti dell'app da capo, per il pad collegato
  };
  disegnaProva();
}
function ctAscolta(dove, k) {
  if (X.ascolto && X.ascolto.dove === dove && X.ascolto.k === k) { X.ascolto = null; disegnaController(); return; }
  if (!X.pad) { ctScegliAMano(dove, k); return; }  // niente pad: scelgo da un elenco
  X.ascolto = { dove, k, da: performance.now() };
  disegnaController();
}
async function ctScegliAMano(dove, k) {
  const sdl = X.dati.profilo && X.dati.profilo.backend === "sdl";
  const nomi = sdl ? STD_SDL : STD_XINPUT;
  const r = await modale({ titolo: t("ct_scegli_tit"), testo: t("ct_scegli_testo"),
    bottoni: [...nomi.map(n => [n, etich(n)]), ["__annulla", t("annulla")]] });
  if (r && r !== "__annulla") ctAssegna({ dove, k }, r);
}
async function ctAssegna(dove, nome) {
  const p = ctProfilo();
  if (!p || !X.dati.dolphin) return;
  const base = { ...p.base }, extra = { ...p.extra };
  const vecchio = dove.dove === "base" ? base[dove.k] : extra[dove.k];
  if (nome) {
    const inBase = Object.keys(base).find(k => base[k] === nome && !(dove.dove === "base" && k === dove.k));
    const inExtra = Object.keys(extra).find(k => extra[k] === nome && !(dove.dove === "extra" && k === dove.k));
    if (inBase && dove.dove === "extra") {  // un tasto del gioco anche come comando della mod: farebbe due cose insieme
      const lab = (GC.find(g => g[0] === inBase) || [])[1];
      const r = await modale({ titolo: t("ct_doppio_tit"), testo: t("ct_doppio", etich(nome), lab),
        bottoni: [["no", t("annulla")], ["si", t("ct_doppio_si"), true]] });
      if (r !== "si") { disegnaController(); return; }
    } else if (inBase) base[inBase] = vecchio;  // scambio: il tasto che c'era va dove stava quello nuovo
    if (inExtra) extra[inExtra] = dove.dove === "extra" ? vecchio || null : null;
  }
  if (dove.dove === "base") base[dove.k] = nome; else extra[dove.k] = nome;
  const r = await api().controller_salva(p.device || X.dati.predefinito.device, base, extra);
  if (!r || r.errore) { toast(t("errore"), r && r.errore === "dolphin" ? t("err_dolphin") : (r && r.errore) || "", "errore"); return; }
  X.dati = r;
  disegnaController();
  const segue = dove.dove === "base" && ["Buttons/Z", "Buttons/Start", "D-Pad/Down", "D-Pad/Left", "D-Pad/Right"].includes(dove.k);
  toast(t("ct_salvato"), [segue ? t("ct_segue") : "", r.dolphin_aperto ? t("ct_dal_prossimo") : ""].filter(Boolean).join(" "), "", segue ? 5000 : 2200);
}
function disegnaProva() {  // tutti i tasti del pad: si accendono quando li premi, sotto c'è cosa fanno in gioco
  const box = $("#ct-prova");
  if (!box) return;
  const p = ctProfilo(), sdl = p && p.backend === "sdl", nomi = sdl ? STD_SDL : STD_XINPUT;
  const fa = n => {
    if (!p) return "";
    const v = [];
    for (const [k, lab] of GC) if (p.base[k] === n) v.push(lab);
    for (const [k, , tit] of EXTRA_CT) if (p.extra[k] === n) v.push(t(tit + "_corto"));
    return v.join(" · ");
  };
  box.innerHTML = `<div class="ct-stick"><i id="ct-sx"><b></b></i><span>${t("ct_stick_sx")}</span></div>` +
    `<div class="ct-stick"><i id="ct-dx"><b></b></i><span>${t("ct_stick_dx")}</span></div>` +
    nomi.map((n, i) => `<div class="ct-prova-t" data-i="${i}"><kbd>${etich(n)}</kbd><small>${fa(n) || "—"}</small></div>`).join("") +
    `<p class="nota ct-prova-esci">${t("ct_prova_esci", etich("Button B"))}</p>`;
}
function ctPad() {  // ogni fotogramma: pad collegato, tasti premuti, ascolto per "Cambia"
  requestAnimationFrame(ctPad);
  if (S.pagina !== "controller" || (window.giocoAperto && !document.hasFocus())) return;
  // pad letti da Python (padLetti in pad.js): con più pad collegati vale quello che hai toccato per ultimo
  const letti = padLetti(), g = letti && letti.attivo;
  const firma = g ? g.id + "|" + g.nome + "|" + letti.tutti.length : "";
  if (firma !== X.firmaPad) {
    X.firmaPad = firma;
    X.pad = g ? { id: g.id, nome: g.nome, mapping: g.browser ? g.mapping : "standard", fam: g.fam, browser: !!g.browser } : null;
    X.altri = g ? letti.tutti.length - 1 : 0;
    if (X.ascolto && !g) X.ascolto = null;
    X.prima = g ? g.b.slice() : [];  // pad cambiato: i tasti già premuti non contano come pressioni nuove
    disegnaController();
  }
  if (!g) return;
  const ora = g.b;
  ora.forEach((on, i) => { const el = document.querySelector(`.ct-prova-t[data-i="${i}"]`); if (el) el.classList.toggle("on", on); });
  const stick = (id, x, y) => { const b = document.querySelector(`#${id} b`); if (b) b.style.transform = `translate(${x * 14}px, ${y * 14}px)`; };
  stick("ct-sx", g.axes[0] || 0, g.axes[1] || 0); stick("ct-dx", g.axes[2] || 0, g.axes[3] || 0);
  if (X.ascolto && performance.now() - X.ascolto.da > 250) {
    const i = ora.findIndex((on, j) => on && !X.prima[j] && j < 16);
    if (i >= 0) {
      const sdl = ctProfilo() && ctProfilo().backend === "sdl";
      const dove = X.ascolto; X.ascolto = null;
      ctAssegna(dove, (sdl ? STD_SDL : STD_XINPUT)[i]);
    }
  }
  X.prima = ora;
}
requestAnimationFrame(ctPad);
document.addEventListener("keydown", e => { if (e.key === "Escape" && X.ascolto) { X.ascolto = null; disegnaController(); } });
