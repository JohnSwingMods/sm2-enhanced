// Visore 3D di Spidey in WebGL puro (modello estratto dal gioco con RenderDoc, vedi mesh3d.py).
"use strict";
const VS = `attribute vec3 p;attribute vec3 n;attribute vec2 t;uniform mat4 M,P;varying vec2 vt;varying vec3 vn;
void main(){vt=t;vn=mat3(M)*n;gl_Position=P*M*vec4(p,1.);}`;
const FS = `precision mediump float;uniform sampler2D tex;uniform float ok;varying vec2 vt;varying vec3 vn;
void main(){vec3 N=normalize(vn);vec3 L1=normalize(vec3(.5,.7,.8)),L2=normalize(vec3(-.6,.2,-.7));
float d=abs(dot(N,L1))*.95+abs(dot(N,L2))*.35+.55;vec3 base=mix(vec3(.16,.18,.24),texture2D(tex,vt).rgb,ok);
vec3 c=base*d*1.6;float r=pow(1.-abs(N.z),3.)*.3;gl_FragColor=vec4(min(c+r*vec3(.55,.65,1.),1.),1.);}`;

// filo della ragnatela: nastro con la texture del filo (con trasparenza), sempre girato verso chi guarda
const VSF = `attribute vec3 p;attribute vec2 t;uniform mat4 M,P;varying vec2 vt;void main(){vt=t;gl_Position=P*M*vec4(p,1.);}`;
const FSF = `precision mediump float;uniform sampler2D tex;varying vec2 vt;
void main(){vec4 c=texture2D(tex,vt);if(c.a<.04)discard;gl_FragColor=vec4(min(c.rgb*1.25,1.),c.a);}`;

function mul4(a, b) {
  const r = new Array(16);
  for (let i = 0; i < 4; i++) for (let j = 0; j < 4; j++) {
    let s = 0; for (let k = 0; k < 4; k++) s += a[k * 4 + j] * b[i * 4 + k]; r[i * 4 + j] = s;
  }
  return r;
}

// Il modello 3D di Spidey NON è dentro l'app: Python lo ricostruisce dal disco del gioco di chi la usa (modello_disco.py)
// appena sa dov'è. Finché non c'è, i Viewer partono vuoti e lo ricevono dopo con ricarica().
const MODELLO_VUOTO = { parti: [] };
let MODELLI_SPIDEY = null;
async function modelliSpidey(rileggi = false) {
  if (rileggi) MODELLI_SPIDEY = null;
  if (!MODELLI_SPIDEY) { try { const r = await api().modello_spidey(); if (r && r.gioco) MODELLI_SPIDEY = r; } catch (e) { /* niente */ } }
  return MODELLI_SPIDEY || { gioco: MODELLO_VUOTO, idle: MODELLO_VUOTO };
}

class Viewer {
  constructor(canvas, modello, opz = {}) {
    this.cv = canvas;
    this.gl = canvas.getContext("webgl", { antialias: true, preserveDrawingBuffer: !!opz.foto, alpha: true });
    this.ang = opz.ang ?? 0; this.alt = opz.alt ?? 0.08; this.dist = opz.dist ?? 3.6; this.cy = opz.cy ?? 1;  // cy = altezza del punto guardato
    this.auto = opz.auto ?? true; this.foto = !!opz.foto; this.trasc = null; this.ok = 0;
    const gl = this.gl;
    const sh = (tipo, src) => { const s = gl.createShader(tipo); gl.shaderSource(s, src); gl.compileShader(s); return s; };
    this.pr = gl.createProgram();
    gl.attachShader(this.pr, sh(gl.VERTEX_SHADER, VS)); gl.attachShader(this.pr, sh(gl.FRAGMENT_SHADER, FS));
    gl.linkProgram(this.pr); gl.useProgram(this.pr);
    this.parti = modello.parti.map(p => this._parte(p));
    this.modelli = { base: this.parti };
    this.tex = gl.createTexture();
    this.appeso = false; this.filoOk = false; this.filoAsp = 8;  // appeso = a testa in giù, appeso al filo della ragnatela
    if (!this.foto) this._controlli();
  }
  _parte(p) {
    const gl = this.gl, pos = p.pos, idx = p.idx, nor = new Float32Array(pos.length);
    for (let i = 0; i < idx.length; i += 3) {
      const a = idx[i] * 3, b = idx[i + 1] * 3, c = idx[i + 2] * 3;
      const ux = pos[b] - pos[a], uy = pos[b + 1] - pos[a + 1], uz = pos[b + 2] - pos[a + 2];
      const wx = pos[c] - pos[a], wy = pos[c + 1] - pos[a + 1], wz = pos[c + 2] - pos[a + 2];
      const nx = uy * wz - uz * wy, ny = uz * wx - ux * wz, nz = ux * wy - uy * wx;
      for (const k of [a, b, c]) { nor[k] += nx; nor[k + 1] += ny; nor[k + 2] += nz; }
    }
    const buf = (d, tipo = gl.ARRAY_BUFFER) => { const b = gl.createBuffer(); gl.bindBuffer(tipo, b); gl.bufferData(tipo, d, gl.STATIC_DRAW); return b; };
    return { p: buf(new Float32Array(pos)), n: buf(nor), t: buf(new Float32Array(p.uv)),
             i: buf(new Uint16Array(idx), gl.ELEMENT_ARRAY_BUFFER), cnt: idx.length };
  }
  _controlli() {
    const cv = this.cv;
    cv.addEventListener("pointerdown", e => { this.trasc = [e.clientX, e.clientY]; cv.setPointerCapture(e.pointerId); });
    cv.addEventListener("pointermove", e => {
      if (!this.trasc) return;
      this.ang += (e.clientX - this.trasc[0]) * 0.01;
      this.alt = Math.max(-1.2, Math.min(1.2, this.alt + (e.clientY - this.trasc[1]) * 0.01));
      this.trasc = [e.clientX, e.clientY];
    });
    cv.addEventListener("pointerup", () => this.trasc = null);
    cv.addEventListener("wheel", e => { e.preventDefault(); this.dist = Math.max(1.6, Math.min(7, this.dist * (1 + e.deltaY * 0.001))); }, { passive: false });
    cv.addEventListener("dblclick", () => { this.ang = 0; this.alt = 0.08; this.dist = 3.6; });
  }
  prepara(nome, modello) {  // prepara una posa senza usarla (es. braccia conserte per Spidey appeso al filo)
    if (!this.modelli[nome]) this.modelli[nome] = modello.parti.map(p => this._parte(p));
  }
  usaModello(nome, modello) {  // cambia posa: i modelli vengono preparati una volta sola
    if (!this.modelli[nome]) this.modelli[nome] = modello.parti.map(p => this._parte(p));
    this.parti = this.modelli[nome];
  }
  ricarica(m) {  // è arrivato il modello vero (dal disco del gioco): rifà le pose e tiene quella in uso
    const nome = Object.keys(this.modelli).find(k => this.modelli[k] === this.parti) || "base";
    this.modelli = { base: m.gioco.parti.map(p => this._parte(p)), idle: m.idle.parti.map(p => this._parte(p)) };
    this.parti = this.modelli[nome] || this.modelli.base;
  }
  texture(src) {
    return new Promise(ok => {
      if (!src) { this.ok = 0; ok(); return; }
      const im = new Image();
      im.onload = () => {
        const gl = this.gl;
        gl.bindTexture(gl.TEXTURE_2D, this.tex);
        gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGB, gl.RGB, gl.UNSIGNED_BYTE, im);
        gl.generateMipmap(gl.TEXTURE_2D);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR_MIPMAP_LINEAR);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.REPEAT);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.REPEAT);
        this.ok = 1; ok();
      };
      im.onerror = () => { this.ok = 0; ok(); };  // immagine rotta: senza, la coda delle miniature restava ferma per sempre
      im.src = src;
    });
  }
  _filoPronto() {
    if (this.prF) return;
    const gl = this.gl, sh = (tipo, src) => { const s = gl.createShader(tipo); gl.shaderSource(s, src); gl.compileShader(s); return s; };
    this.prF = gl.createProgram();
    gl.attachShader(this.prF, sh(gl.VERTEX_SHADER, VSF)); gl.attachShader(this.prF, sh(gl.FRAGMENT_SHADER, FSF));
    gl.linkProgram(this.prF);
    this.texF = gl.createTexture(); this.bufF = gl.createBuffer(); this.bufFt = gl.createBuffer();
  }
  // texture del filo (PNG con trasparenza, lati potenza di 2); null = filo bianco disegnato qui (ragnatele originali)
  filo(src) {
    this._filoPronto();
    return new Promise(ok => {
      const metti = im => {
        const gl = this.gl;
        gl.bindTexture(gl.TEXTURE_2D, this.texF);
        gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, im);
        gl.generateMipmap(gl.TEXTURE_2D);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR_MIPMAP_LINEAR);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.REPEAT);
        this.filoAsp = im.height / im.width; this.filoOk = true; ok();
      };
      if (src) { const im = new Image(); im.onload = () => metti(im); im.onerror = () => ok(); im.src = src; return; }
      const c = document.createElement("canvas"); c.width = 64; c.height = 512;
      const x = c.getContext("2d");
      for (let k = 0; k < 5; k++) {  // qualche fibra bianca un po' ondulata
        x.strokeStyle = `rgba(240,244,255,${0.55 + k * 0.08})`; x.lineWidth = 2.2 + (k % 2) * 1.6; x.beginPath();
        for (let y = 0; y <= 512; y += 16) { const xx = 32 + Math.sin(y / 512 * Math.PI * 2 * (k % 2 ? 1 : -1) + k) * (5 + k); y ? x.lineTo(xx, y) : x.moveTo(xx, y); }
        x.stroke();
      }
      metti(c);
    });
  }
  disegna() {
    const gl = this.gl, cv = this.cv;
    const dpr = this.foto ? 1 : (window.devicePixelRatio || 1);
    const w = Math.round(cv.clientWidth * dpr) || cv.width, h = Math.round(cv.clientHeight * dpr) || cv.height;
    if (!this.foto && (cv.width !== w || cv.height !== h)) { cv.width = w; cv.height = h; }
    gl.viewport(0, 0, cv.width, cv.height);
    gl.clearColor(0, 0, 0, 0); gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT); gl.enable(gl.DEPTH_TEST);
    const f = 1 / Math.tan(0.45), asp = cv.width / cv.height, n = 0.1, fa = 50;
    const P = [f / asp, 0, 0, 0, 0, f, 0, 0, 0, 0, (fa + n) / (n - fa), -1, 0, 0, 2 * fa * n / (n - fa), 0];
    const ca = Math.cos(this.ang), sa = Math.sin(this.ang), cb = Math.cos(this.alt), sb = Math.sin(this.alt);
    const Ry = [ca, 0, -sa, 0, 0, 1, 0, 0, sa, 0, ca, 0, 0, 0, 0, 1];
    const Rx = [1, 0, 0, 0, 0, cb, sb, 0, 0, -sb, cb, 0, 0, 0, 0, 1];
    const T = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, -this.cy, -this.dist, 1];
    const M = mul4(T, mul4(Rx, Ry));
    const pr = this.pr;
    gl.useProgram(pr);
    gl.uniformMatrix4fv(gl.getUniformLocation(pr, "M"), false, M);
    gl.uniformMatrix4fv(gl.getUniformLocation(pr, "P"), false, P);
    gl.uniform1f(gl.getUniformLocation(pr, "ok"), this.ok);
    gl.bindTexture(gl.TEXTURE_2D, this.tex);
    for (const p of this.appeso ? [] : this.parti) {  // ragnatele: niente Spidey, solo il filo
      for (const [a, b, k] of [["p", p.p, 3], ["n", p.n, 3], ["t", p.t, 2]]) {
        const l = gl.getAttribLocation(pr, a);
        gl.bindBuffer(gl.ARRAY_BUFFER, b); gl.enableVertexAttribArray(l); gl.vertexAttribPointer(l, k, gl.FLOAT, false, 0, 0);
      }
      gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, p.i);
      gl.drawElements(gl.TRIANGLES, p.cnt, gl.UNSIGNED_SHORT, 0);
    }
    if (this.appeso && this.filoOk) this._disegnaFilo(M, P, ca, sa);
  }
  _disegnaFilo(M, P, ca, sa) {
    // un filo di ragnatela che penzola dall'alto e dondola piano: la parte bassa segue in ritardo, come una corda
    const gl = this.gl, pr = this.prF, w = 0.085, fx = -sa, fz = ca, N = 24, y0 = 6.5, y1 = -0.15, ora = performance.now() / 1000;
    const punti = [];
    for (let k = 0; k <= N; k++) {
      const f = k / N;  // 0 = in alto (fermo), 1 = la punta
      const ang = Math.sin(ora * 1.1 - f * 1.4) * 0.07 * f + Math.sin(ora * 0.7 + 1) * 0.03 * f;
      const giro = Math.sin(ora * 0.8 - f * 2) * 0.05 * f * f;
      const L = (y0 - y1) * f;
      punti.push([L * Math.sin(ang), y0 - L * Math.cos(ang), L * giro]);
    }
    const pos = [], uv = [], rip = 1 / (2 * w * this.filoAsp);
    let v = 0;
    for (let k = 0; k < N; k++) {
      const a = punti[k], b = punti[k + 1], d = [b[0] - a[0], b[1] - a[1], b[2] - a[2]], len = Math.hypot(...d);
      let px = d[1] * fz, py = d[2] * fx - d[0] * fz, pz = -d[1] * fx;  // perpendicolare a filo e sguardo: guarda verso di noi
      const n = Math.hypot(px, py, pz) || 1, lw = w * (k > N - 3 ? 0.75 + 0.25 * (N - k) / 3 : 1);
      px *= lw / n; py *= lw / n; pz *= lw / n;
      const v2 = v + len * rip;
      const q = [[a[0] - px, a[1] - py, a[2] - pz, 0, v], [a[0] + px, a[1] + py, a[2] + pz, 1, v],
                 [b[0] - px, b[1] - py, b[2] - pz, 0, v2], [b[0] + px, b[1] + py, b[2] + pz, 1, v2]];
      for (const i of [0, 1, 2, 2, 1, 3]) { pos.push(q[i][0], q[i][1], q[i][2]); uv.push(q[i][3], q[i][4]); }
      v = v2;
    }
    gl.useProgram(pr);
    gl.uniformMatrix4fv(gl.getUniformLocation(pr, "M"), false, M);
    gl.uniformMatrix4fv(gl.getUniformLocation(pr, "P"), false, P);
    gl.bindTexture(gl.TEXTURE_2D, this.texF);
    for (const [a, b, d, k] of [["p", this.bufF, new Float32Array(pos), 3], ["t", this.bufFt, new Float32Array(uv), 2]]) {
      const l = gl.getAttribLocation(pr, a);
      gl.bindBuffer(gl.ARRAY_BUFFER, b); gl.bufferData(gl.ARRAY_BUFFER, d, gl.DYNAMIC_DRAW);
      gl.enableVertexAttribArray(l); gl.vertexAttribPointer(l, k, gl.FLOAT, false, 0, 0);
    }
    const ln = gl.getAttribLocation(this.pr, "n");  // il programma del corpo usa 3 attributi: questo no
    if (ln >= 0 && ln !== gl.getAttribLocation(pr, "p") && ln !== gl.getAttribLocation(pr, "t")) gl.disableVertexAttribArray(ln);
    gl.enable(gl.BLEND); gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA); gl.depthMask(false);
    gl.drawArrays(gl.TRIANGLES, 0, pos.length / 3);
    gl.depthMask(true); gl.disable(gl.BLEND);
  }
  avvia() {
    const giro = () => {
      requestAnimationFrame(giro);
      if (window.giocoAperto && !document.hasFocus()) return;  // si gioca e l'app è dietro: niente 3D, il processore serve a Dolphin
      if (this.auto && !this.trasc && !document.hidden) this.ang += 0.0045;
      if (this.cv.offsetParent !== null) this.disegna();
    };
    giro();
  }
  // miniatura: tre quarti frontale, sfondo trasparente -> dataURL PNG
  async foto_di(src) {
    await this.texture(src);
    this.disegna();
    return this.cv.toDataURL("image/png");
  }
}
window.Viewer = Viewer;
