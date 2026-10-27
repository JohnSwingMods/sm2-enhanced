// Tutta l'app col controller (come il menu in gioco): croce o levetta sinistra = ti sposti tra pulsanti, schede e
// interruttori (il più vicino in quella direzione), A = clic, B = indietro / chiudi la finestrella, LB / RB = pagina
// prima / dopo, levetta destra = gira e avvicina lo Spidey 3D (o scorre la pagina). Nella pagina Skin anche LT / RT
// (principale / alternativo / ragnatele), X (ordine), Y (preferito) e R3 (ferma Spidey), come nel menu in gioco.
// Il riquadro bianco compare solo quando usi il pad; muovendo il mouse sparisce.
const PN = { el: null, attivo: false, prima: [], prossimo: {}, rip: {} };
const PN_TASTI = { 0: "a", 1: "b", 2: "x", 3: "y", 4: "lb", 5: "rb", 6: "lt", 7: "rt", 8: "view", 9: "start", 10: "l3", 11: "r3", 12: "su", 13: "giu", 14: "sx", 15: "dx" };
// finestrelle, dalla più in alto (z-index): prima i crediti mancavano e il riquadro andava sul launcher sotto (A due volte =
// gioco avviato dietro la finestrella)
const PN_OVERLAY = ["#trascina", "#crediti", "#mz", "#comandi", "#modale", "#tx-zoom"];

function pnRadice() {  // dove si naviga: la finestrella aperta in primo piano, se c'è, se no la pagina (+ menu e testata)
  for (const s of PN_OVERLAY) { const o = $(s); if (o && !o.classList.contains("nascosto")) return o; }
  return document.body;
}
function pnVisibile(e) {
  const r = e.getBoundingClientRect();
  if (r.width < 4 || r.height < 4 || r.bottom < 0 || r.top > innerHeight || r.right < 0 || r.left > innerWidth) return false;
  const st = getComputedStyle(e);
  return st.visibility !== "hidden" && st.display !== "none" && +st.opacity > 0.05;
}
function pnCandidati() {
  const radice = pnRadice(), out = [];
  for (const e of radice.querySelectorAll("button, a, [data-link], [data-link-esterno], label.interruttore, input[type=range], input[type=text], input[type=search], select, [tabindex], .carta, *")) {
    if (e.disabled || e.closest(".nascosto") || e.closest("[inert]") || e.matches('[tabindex="-1"]')) continue;
    if (e.matches("input[type=checkbox]")) continue;  // si usa il suo interruttore
    const cliccabile = e.matches("button, a, [data-link], [data-link-esterno], label.interruttore, input[type=range], input[type=text], input[type=search], select, [tabindex]")
      || getComputedStyle(e).cursor === "pointer";
    if (!cliccabile) continue;
    if (e.parentElement && e.parentElement.closest("button, label, a")) continue;  // un pezzo dentro un pulsante o un'etichetta (es. righe con interruttore di Spider-Cam): conta quello fuori
    if (!pnVisibile(e)) continue;
    out.push(e);
  }
  return out;
}
function pnMetti(e, scorri = true) {
  if (PN.el) PN.el.classList.remove("pn-focus");
  PN.el = e;
  if (!e) return;
  e.classList.add("pn-focus");
  document.body.classList.add("pn-attivo");
  if (scorri) e.scrollIntoView({ block: "nearest", inline: "nearest", behavior: "smooth" });
}
function pnPrimo() {  // dove partire: il pulsante principale della pagina (GIOCA, Installa...) o il primo in alto a sinistra
  const radice = pnRadice();
  const pref = radice === document.body ? $(".pagina.attiva #gi-play:not([disabled]), .pagina.attiva .primario:not([disabled])") : radice.querySelector(".primario, button");
  if (pref && pnVisibile(pref)) return pref;
  const c = pnCandidati().filter(e => radice !== document.body || e.closest(".pagina.attiva"));
  return c.sort((a, b) => a.getBoundingClientRect().top - b.getBoundingClientRect().top || a.getBoundingClientRect().left - b.getBoundingClientRect().left)[0] || null;
}
function pnMuovi(dir) {
  if (!PN.el || !document.contains(PN.el) || !pnVisibile(PN.el) || !pnRadice().contains(PN.el)) { pnMetti(pnPrimo()); return; }
  const r = PN.el.getBoundingClientRect(), cx = (r.left + r.right) / 2, cy = (r.top + r.bottom) / 2;
  let meglio = null, punti = Infinity;
  for (const e of pnCandidati()) {
    if (e === PN.el) continue;
    const q = e.getBoundingClientRect(), qx = (q.left + q.right) / 2, qy = (q.top + q.bottom) / 2;
    const dx = qx - cx, dy = qy - cy;
    // nella direzione giusta (con un po' di tolleranza per elementi sovrapposti)
    const avanti = dir === "dx" ? q.left - r.right + 1 : dir === "sx" ? r.left - q.right + 1 : dir === "giu" ? q.top - r.bottom + 1 : r.top - q.bottom + 1;
    const lungo = dir === "dx" || dir === "sx" ? Math.abs(dx) : Math.abs(dy);
    if (avanti < -Math.min(r.width, r.height) * 0.25 && lungo < 8) continue;
    if ((dir === "dx" && dx <= 2) || (dir === "sx" && dx >= -2) || (dir === "giu" && dy <= 2) || (dir === "su" && dy >= -2)) continue;
    const storto = dir === "dx" || dir === "sx" ? Math.max(0, Math.abs(dy) - (r.height + q.height) / 4) : Math.max(0, Math.abs(dx) - (r.width + q.width) / 4);
    const p = Math.max(0, avanti) + storto * 2.2 + lungo * 0.15;
    if (p < punti) { punti = p; meglio = e; }
  }
  if (meglio) pnMetti(meglio);
}
function pnPremi(k, rip) {
  if (typeof applicando === "function" && applicando()) return;  // sta applicando: la pagina è bloccata anche per il pad
  if (PN.pagina !== S.pagina) { PN.pagina = S.pagina; PN.mosso = false; pnMetti(null); }
  // pagina Controller: lì i tasti si provano ("Prova i tasti"), quindi A & co. cliccano solo dopo esserti spostato con la croce
  if (S.pagina === "controller" && !PN.mosso && pnRadice() === document.body && !["su", "giu", "sx", "dx", "lb", "rb", "b"].includes(k)) return;
  // pagine con comandi loro (Skin: slot, ordine, preferito, ferma)
  if (S.pagina === "skin" && pnRadice() === document.body && pnSkin(k)) return;
  const e = PN.el && document.contains(PN.el) && pnVisibile(PN.el) ? PN.el : null;
  if (["su", "giu", "sx", "dx"].includes(k)) {
    if (e && e.matches("input[type=range]") && (k === "sx" || k === "dx")) {  // cursore: sinistra/destra cambiano il valore
      const p = (+e.step || 1) * (rip >= 6 ? 4 : 1) * (k === "dx" ? 1 : -1);
      e.value = Math.max(+e.min, Math.min(+e.max, +e.value + p));
      e.dispatchEvent(new Event("input", { bubbles: true })); e.dispatchEvent(new Event("change", { bubbles: true }));
      return;
    }
    PN.mosso = true;
    pnMuovi(k); return;
  }
  if (k === "a") {
    if (!e) { pnMetti(pnPrimo()); return; }
    if (e.matches("input[type=text], input[type=search]")) { e.focus(); return; }
    e.click(); setTimeout(() => { if (PN.el && !document.contains(PN.el)) pnMetti(pnPrimo(), false); }, 120);
    return;
  }
  if (k === "b") {  // chiude la finestrella aperta (come Esc), se no torna al launcher
    if (pnRadice() !== document.body || document.activeElement && document.activeElement.matches("input")) {
      document.activeElement && document.activeElement.blur();
      // la finestrella (modale) ascolta Esc su sé stessa: chiudi(null) = annulla. Prima cliccavo il primo pulsante non
      // primario, che non sempre è "Annulla" (es. "Prova comunque" con uno stato salvato vecchio)
      const m = $("#modale:not(.nascosto)");
      if (m) m.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
      else document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
      setTimeout(() => pnMetti(pnPrimo(), false), 150);
    } else if (S.pagina !== "gioca") vaiA("gioca");
    return;
  }
  if (k === "lb" || k === "rb") {  // pagina prima / dopo (quelle accese nel menu a sinistra)
    const voci = $$("nav [data-pagina]").filter(b => !b.classList.contains("vuota") && pnVisibile(b));
    const i = voci.findIndex(b => b.dataset.pagina === S.pagina);
    const n = voci[(i + (k === "rb" ? 1 : voci.length - 1)) % voci.length];
    if (n) { n.click(); setTimeout(() => pnMetti(pnPrimo()), 250); }
    return;
  }
  if (k === "lt" || k === "rt") {  // una schermata su / giù nella lista della pagina, e il riquadro va sul primo visibile
    const rad = pnRadice();  // finestrella aperta (es. crediti): scorre lei, non la pagina sotto
    const box = rad !== document.body ? rad
      : (e && e.closest(".pagina.attiva [class*=lista], .pagina.attiva [class*=griglia]")) || $(".pagina.attiva [class*=lista]") || $(".pagina.attiva");
    if (box) {
      box.scrollBy({ top: (k === "rt" ? 1 : -1) * box.clientHeight * 0.85 });
      setTimeout(() => {
        const r0 = box.getBoundingClientRect();
        const vis = pnCandidati().filter(x => box.contains(x)).filter(x => { const q = x.getBoundingClientRect(); return q.top >= r0.top && q.bottom <= r0.bottom; });
        if (vis.length) pnMetti(k === "rt" ? vis[vis.length - 1] : vis[0], false);
      }, 350);
    }
    return;
  }
  if (pnRadice() !== document.body) return;  // con una finestrella aperta Start/View non fanno niente sotto
  if (k === "start" && S.pagina === "gioca") { const g = $("#gi-play"); if (g && !g.disabled) g.click(); return; }
  if (k === "view") { if (typeof apriComandi === "function") apriComandi(); }
}
function pnSkin(k) {
  if (k === "lt" || k === "rt") {
    const sl = $$("#pg-skin .slot button[data-slot]"), i = sl.findIndex(b => b.classList.contains("attivo"));
    const n = sl[(i + (k === "rt" ? 1 : sl.length - 1)) % sl.length]; if (n) n.click();
    return true;
  }
  if (k === "x") { const b = $("#pg-skin .ordine button:not(.attivo)"); if (b) b.click(); return true; }
  if (k === "y") { const c = PN.el && PN.el.closest(".carta"); const p = c && c.querySelector(".pref"); if (p) p.click(); return true; }
  if (k === "r3") { if (typeof viewer !== "undefined" && viewer) viewer.auto = !viewer.auto; return true; }
  if (k === "l3") { const c = PN.el && PN.el.closest(".carta"); const v = c && c.querySelector(".var-btn"); if (v) v.click(); return true; }
  return false;
}
function pnStick(x, y) {  // levetta destra: lo Spidey 3D della pagina (Skin o launcher), se no scorre la pagina
  const v = S.pagina === "skin" && typeof viewer !== "undefined" ? viewer : S.pagina === "gioca" && typeof Q !== "undefined" ? Q.viewer : null;
  if (v && pnRadice() === document.body) {
    v.ang += x * 0.07;
    v.dist = Math.max(1.6, Math.min(7, v.dist * (1 + y * 0.035)));
    return;
  }
  const box = (PN.el && PN.el.closest(".pagina.attiva [class*=lista], .pagina.attiva [class*=griglia]")) || $(".pagina.attiva");
  if (box) box.scrollBy({ top: y * 28 });
}
function pnGiro() {
  requestAnimationFrame(pnGiro);
  if ((!document.hasFocus() && !window.PN_PROVA) || (typeof X !== "undefined" && X.ascolto)) return;  // pagina Controller in ascolto di un tasto: niente
  const g = [...(navigator.getGamepads ? navigator.getGamepads() : [])].find(x => x && x.connected);
  if (!g) return;
  const ora = performance.now(), b = g.buttons.map(x => x.pressed);
  const ax = g.axes[0] || 0, ay = g.axes[1] || 0;
  b[12] = b[12] || ay < -0.6; b[13] = b[13] || ay > 0.6; b[14] = b[14] || ax < -0.6; b[15] = b[15] || ax > 0.6;  // levetta = croce
  for (const [i, k] of Object.entries(PN_TASTI)) {
    if (b[i] && !PN.prima[i]) {
      PN.attivo = true; PN.rip[i] = 0; PN.prossimo[i] = ora + 360;
      pnPremi(k, 0);
    } else if (b[i] && i >= 12 && ora >= PN.prossimo[i]) {  // croce tenuta: si ripete, sempre più veloce
      PN.rip[i]++; PN.prossimo[i] = ora + (PN.rip[i] < 5 ? 110 : PN.rip[i] < 14 ? 65 : 40);
      pnPremi(k, PN.rip[i]);
    }
  }
  const rx = Math.abs(g.axes[2] || 0) > 0.22 ? g.axes[2] : 0, ry = Math.abs(g.axes[3] || 0) > 0.22 ? g.axes[3] : 0;
  if (rx || ry) pnStick(rx, ry);
  PN.prima = b;
}
document.addEventListener("mousemove", () => {
  if (!PN.attivo) return;
  PN.attivo = false; document.body.classList.remove("pn-attivo");
  if (PN.el) PN.el.classList.remove("pn-focus");
});
requestAnimationFrame(pnGiro);
