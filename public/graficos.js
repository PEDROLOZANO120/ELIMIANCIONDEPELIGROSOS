/* Pictogramas SGA y rótulos de transporte dibujados en SVG (sin imágenes de terceros).
   Son representaciones didácticas simplificadas; los modelos oficiales están en el SGA (anexo 3) y en la NTE INEN 2266 (anexo F). */
(function(){
const SIM = {
  llama: (c)=>`<path fill="${c}" d="M50 22c9 13 18 20 14 37-2 9-8 13-14 13s-13-4-14-12c-2-9 4-14 7-21 2 7 4 9 6 9 3-7-2-15 1-26z"/><path fill="${c}" d="M34 74h32v4H34z"/>`,
  llamaCirculo: (c)=>`<path fill="${c}" d="M50 20c6 9 12 13 9 24-1 5-5 8-9 8s-8-3-9-8c-1-6 2-9 5-14 1 4 2 6 4 6 2-5-1-10 0-16z"/><circle cx="50" cy="63" r="10" fill="none" stroke="${c}" stroke-width="5"/><path fill="${c}" d="M34 76h32v4H34z"/>`,
  bomba: (c)=>`<circle cx="44" cy="60" r="12" fill="${c}"/><path stroke="${c}" stroke-width="3" stroke-linecap="round" d="M52 50l6-7M60 52l10-4M59 60l11 1M56 44l3-10M48 44l-1-11M62 40l9-9M40 44l-7-8"/><path fill="${c}" d="M66 30l4 6-6 1zM28 40l7 3-5 4zM72 58l6 3-6 3z"/>`,
  botella: (c)=>`<rect x="26" y="48" width="40" height="18" rx="9" fill="${c}"/><rect x="65" y="52" width="7" height="10" fill="${c}"/><rect x="72" y="50" width="4" height="14" rx="1" fill="${c}"/>`,
  corrosion: (c)=>`<g fill="${c}"><path d="M30 24l9 4-8 16-6-3z"/><path d="M58 24l9 4-8 16-6-3z"/><circle cx="31" cy="50" r="2.4"/><circle cx="33" cy="57" r="2"/><circle cx="59" cy="50" r="2.4"/><circle cx="61" cy="57" r="2"/><path d="M20 66h18l2-4 3 4v8H20z"/><path d="M52 66h28v8H58l-3-3-3 3z"/></g>`,
  calavera: (c, f)=>`<g><circle cx="50" cy="42" r="14" fill="${c}"/><rect x="42" y="50" width="16" height="9" rx="2" fill="${c}"/><circle cx="44" cy="41" r="4" fill="${f}"/><circle cx="56" cy="41" r="4" fill="${f}"/><path d="M48 50l2-4 2 4z" fill="${f}"/><path stroke="${c}" stroke-width="5" stroke-linecap="round" d="M30 62l40 14M70 62L30 76"/></g>`,
  exclamacion: (c)=>`<rect x="45" y="26" width="10" height="34" rx="5" fill="${c}"/><circle cx="50" cy="69" r="5.5" fill="${c}"/>`,
  salud: (c, f)=>`<circle cx="50" cy="31" r="8" fill="${c}"/><path fill="${c}" d="M32 76c0-20 6-34 18-34s18 14 18 34z"/><path fill="${f}" d="M50 48l3 8 8-3-5 7 7 4-8 1 1 8-6-6-6 6 1-8-8-1 7-4-5-7 8 3z"/>`,
  ambiente: (c)=>`<g fill="none" stroke="${c}" stroke-width="3" stroke-linecap="round"><path d="M28 74V40M28 52l-8-8M28 46l8-9M28 60l7-5"/><path d="M18 74h64"/></g><path fill="${c}" d="M46 64c6-7 18-7 24 0-6 7-18 7-24 0zM70 64l8-6v12z"/><circle cx="52" cy="62" r="1.6" fill="#fff"/>`,
  biologico: (c)=>`<g fill="none" stroke="${c}" stroke-width="5"><circle cx="50" cy="38" r="10"/><circle cx="39" cy="57" r="10"/><circle cx="61" cy="57" r="10"/></g><circle cx="50" cy="51" r="4" fill="${c}"/>`,
  radiacion: (c)=>`<circle cx="50" cy="48" r="5" fill="${c}"/><path fill="${c}" d="M50 48L40 31a20 20 0 0 1 20 0zM50 48l20 0a20 20 0 0 1-10 17zM50 48L40 65a20 20 0 0 1-10-17z"/>`,
};
const GHS = {
  GHS01: ['bomba', 'Bomba explotando'], GHS02: ['llama', 'Llama'], GHS03: ['llamaCirculo', 'Llama sobre círculo'],
  GHS04: ['botella', 'Botella de gas'], GHS05: ['corrosion', 'Corrosión'], GHS06: ['calavera', 'Calavera y tibias cruzadas'],
  GHS07: ['exclamacion', 'Signo de exclamación'], GHS08: ['salud', 'Peligro para la salud'], GHS09: ['ambiente', 'Medio ambiente']
};
function pictogramaSGA(code, size, conTitulo){
  const g = GHS[code]; if(!g) return '';
  const s = size || 64;
  const t = conTitulo ? `<title>${g[1]}</title>` : '<title>Pictograma SGA</title>';
  return `<svg class="picto" width="${s}" height="${s}" viewBox="0 0 100 100" role="img" aria-label="${conTitulo?g[1]:'Pictograma SGA'}">${t}
    <polygon points="50,4 96,50 50,96 4,50" fill="#fff" stroke="#d40c1c" stroke-width="7" stroke-linejoin="round"/>
    <g transform="translate(50 51) scale(1.12) translate(-50 -50)">${SIM[g[0]]('#111', '#fff')}</g></svg>`;
}
// rótulos de transporte (NTE INEN 2266, anexo F)
const ROT = {
  '1':   {fondo:'#f28c1b', sim:'bomba', num:'1'},
  '2.1': {fondo:'#d81e2a', sim:'llama', num:'2'},
  '2.2': {fondo:'#1f9b47', sim:'botella', num:'2'},
  '2.3': {fondo:'#fff', sim:'calavera', num:'2'},
  '3':   {fondo:'#d81e2a', sim:'llama', num:'3'},
  '4.1': {fondo:'rayas-rojas', sim:'llama', num:'4'},
  '4.2': {fondo:'blanco-rojo', sim:'llama', num:'4'},
  '4.3': {fondo:'#1d5fb4', sim:'llama', num:'4', simColor:'#111'},
  '5.1': {fondo:'#f7d417', sim:'llamaCirculo', num:'5.1'},
  '5.2': {fondo:'rojo-amarillo', sim:'llama', num:'5.2'},
  '6.1': {fondo:'#fff', sim:'calavera', num:'6'},
  '6':   {fondo:'#fff', sim:'calavera', num:'6'},
  '6.2': {fondo:'#fff', sim:'biologico', num:'6'},
  '7':   {fondo:'amarillo-blanco', sim:'radiacion', num:'7'},
  '8':   {fondo:'blanco-negro', sim:'corrosion', num:'8', numColor:'#fff'},
  '9':   {fondo:'clase9', sim:null, num:'9'},
};
let uid = 0;
function rotulo(clase, size){
  const r = ROT[String(clase)]; if(!r) return '';
  const s = size || 64, id = 'r' + (++uid);
  const clip = `<clipPath id="${id}"><polygon points="50,3 97,50 50,97 3,50"/></clipPath>`;
  let fondo = '';
  if(r.fondo === 'rayas-rojas'){ fondo = `<rect width="100" height="100" fill="#fff"/>` + Array.from({length:7},(_,i)=>`<rect x="${8+i*12.5}" y="0" width="6.5" height="100" fill="#d81e2a"/>`).join(''); }
  else if(r.fondo === 'blanco-rojo'){ fondo = `<rect width="100" height="50" fill="#fff"/><rect y="50" width="100" height="50" fill="#d81e2a"/>`; }
  else if(r.fondo === 'rojo-amarillo'){ fondo = `<rect width="100" height="50" fill="#d81e2a"/><rect y="50" width="100" height="50" fill="#f7d417"/>`; }
  else if(r.fondo === 'amarillo-blanco'){ fondo = `<rect width="100" height="50" fill="#f7d417"/><rect y="50" width="100" height="50" fill="#fff"/>`; }
  else if(r.fondo === 'blanco-negro'){ fondo = `<rect width="100" height="52" fill="#fff"/><rect y="52" width="100" height="48" fill="#111"/>`; }
  else if(r.fondo === 'clase9'){ fondo = `<rect width="100" height="100" fill="#fff"/>` + Array.from({length:7},(_,i)=>`<rect x="${28+i*6.6}" y="6" width="3.6" height="44" fill="#111"/>`).join(''); }
  else fondo = `<rect width="100" height="100" fill="${r.fondo}"/>`;
  const sim = r.sim ? `<g transform="translate(18 0) scale(.64)">${SIM[r.sim](r.simColor||'#111', r.fondo==='#fff'||r.fondo==='blanco-rojo'?'#fff':'#fff')}</g>` : '';
  return `<svg class="rotulo" width="${s}" height="${s}" viewBox="0 0 100 100" role="img" aria-label="Rótulo de transporte"><title>Rótulo de transporte</title><defs>${clip}</defs>
    <g clip-path="url(#${id})">${fondo}</g>
    <polygon points="50,3 97,50 50,97 3,50" fill="none" stroke="#111" stroke-width="2"/>
    <polygon points="50,9 91,50 50,91 9,50" fill="none" stroke="${r.fondo==='blanco-negro'?'#111':'#111'}" stroke-width="1" opacity=".55"/>
    ${sim}<text x="50" y="87" text-anchor="middle" font-family="Arial,Helvetica,sans-serif" font-weight="700" font-size="${r.num.length>1?11:14}" fill="${r.numColor||'#111'}">${r.num}</text></svg>`;
}
/* Imágenes oficiales: pictogramas del SGA (Rev. 11, anexo 3, tabla A3.4.1) y rótulos de la NTE INEN 2266 (anexo F),
   recortados de los documentos de la asignatura. Si una imagen no carga, se usa el dibujo SVG anterior. */
const IMG_ROT = {'1':'1','2.1':'2_1','2.2':'2_2','2.3':'2_3','3':'3','4.1':'4_1','4.2':'4_2','4.3':'4_3','5.1':'5_1','5.2':'5_2','6':'6_1','6.1':'6_1','6.2':'6_2','7':'7','8':'8','9':'9'};
const _svgPic = pictogramaSGA, _svgRot = rotulo;
function picImg(code, size, conTitulo){
  if(!GHS[code]) return '';
  const s = size || 64, alt = conTitulo ? GHS[code][1] : 'Pictograma SGA';
  return `<img class="picto" src="img/${code.toLowerCase()}.png" width="${s}" height="${s}" alt="${alt}" title="${conTitulo?alt:''}" draggable="false" onerror="this.outerHTML=GRAF.svgPic('${code}',${s},${!!conTitulo})">`;
}
function rotImg(clase, size){
  const k = IMG_ROT[String(clase)]; const s = size || 64;
  if(!k) return _svgRot(clase, s);
  return `<img class="rotulo" src="img/rot_${k}.png" width="${s}" height="${s}" alt="Rótulo de transporte" draggable="false" onerror="this.outerHTML=GRAF.svgRot('${clase}',${s})">`;
}
/* Rombo NFPA 704 (dibujo propio): azul salud, rojo inflamabilidad, amarillo inestabilidad, blanco riesgos especiales. */
function nfpa(spec, size){
  const [sa, in_, re, es] = String(spec).split('-'); const s = size || 90;
  const esp = (es||'').toUpperCase();
  const espTxt = esp === 'W' ? '<tspan text-decoration="line-through">W</tspan>' : esp;
  const t = (x,y,v,c)=>`<text x="${x}" y="${y}" text-anchor="middle" dominant-baseline="central" font-family="Arial,Helvetica,sans-serif" font-weight="700" font-size="${String(v).length>1?18:24}" fill="${c||'#111'}">${v}</text>`;
  return `<svg class="nfpa" width="${s}" height="${s}" viewBox="0 0 100 100" role="img" aria-label="Rombo NFPA 704"><title>Rombo NFPA 704</title>
    <polygon points="50,2 74,26 50,50 26,26" fill="#d81e2a" stroke="#111" stroke-width="1.5"/>
    <polygon points="26,26 50,50 26,74 2,50" fill="#1d5fb4" stroke="#111" stroke-width="1.5"/>
    <polygon points="74,26 98,50 74,74 50,50" fill="#f7d417" stroke="#111" stroke-width="1.5"/>
    <polygon points="50,50 74,74 50,98 26,74" fill="#fff" stroke="#111" stroke-width="1.5"/>
    ${t(50,27,in_,'#fff')}${t(26,50,sa,'#fff')}${t(74,50,re)}${esp?`<text x="50" y="74" text-anchor="middle" dominant-baseline="central" font-family="Arial,Helvetica,sans-serif" font-weight="700" font-size="${esp.length>1?15:20}" fill="#111">${espTxt}</text>`:''}</svg>`;
}
function rico(texto, esc, size){
  return esc(String(texto)).replace(/\{\{pic:(GHS0\d)\}\}/g, (_, c)=>picImg(c, size||58))
                           .replace(/\{\{rot:([\d.]+)\}\}/g, (_, c)=>rotImg(c, size||58))
                           .replace(/\{\{nfpa:([0-4]-[0-4]-[0-4]-?[A-Z]*)\}\}/g, (_, c)=>`<span style="display:block;margin:10px 0">${nfpa(c, Math.max(120,(size||58)*1.8))}</span>`);
}
window.GRAF = { pictogramaSGA: picImg, rotulo: rotImg, nfpa, rico, GHS, ROT, svgPic: _svgPic, svgRot: _svgRot };
})();
