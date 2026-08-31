// Congela el historico diario (era modelo viejo) dentro de index.html.
// Uso:  node tools/freeze_history.js 2026-08-31
// Lee data/results.csv + data/meta_results.csv con la MISMA logica de la
// pagina, agrega por dia hasta el cutoff inclusive, y reemplaza
// HISTORICAL_DAILY en index.html. Re-correr tras actualizar los CSVs.
const fs = require('fs');
const CUTOFF = process.argv[2];
if(!/^\d{4}-\d{2}-\d{2}$/.test(CUTOFF || '')) { console.error('uso: node tools/freeze_history.js YYYY-MM-DD'); process.exit(1); }

const html = fs.readFileSync('index.html', 'utf8');
const core = html.match(/\/\/ ===== Config =====([\s\S]*?)\/\/ ── Historia congelada/)[1]
  .replace("const _TS         = Date.now();", "const _TS = 0;");
eval(core);

function parseCSV(path){
  const lines = fs.readFileSync(path, 'utf8').trim().split(/\r?\n/);
  const h = lines[0].split(',');
  return lines.slice(1).map(l => { const c = l.split(','); const o = {}; h.forEach((k,i)=>o[k]=c[i]); return o; });
}
const rowsAll = [...buildOldRows(parseCSV('data/results.csv')),
                 ...buildMetaRows(parseCSV('data/meta_results.csv'))]
  .sort((a,b)=>a.tsISO<b.tsISO?-1:1)
  .filter(r => r.tsISO.slice(0,10) <= CUTOFF);
// agregar por dia (sin UNIT_ADJUSTMENTS: los viejos ya estan horneados o son cero)
const byDay = new Map();
for(const r of rowsAll){
  const key = r.tsISO.slice(0,10);
  const o = byDay.get(key) || {u:0, hours:0, trades:0};
  o.u += r.u_total; o.hours += (r.trades>0?1:0); o.trades += r.trades;
  byDay.set(key, o);
}
const out = {};
for(const [k,v] of [...byDay.entries()].sort())
  out[k] = {u: Math.round(v.u*10000)/10000, hours: v.hours, trades: v.trades};
const tot = Object.values(out).reduce((a,b)=>a+b.u,0);
console.error(`congelado: ${Object.keys(out).length} dias hasta ${CUTOFF}, ${tot.toFixed(2)}u`);
const nuevo = html.replace(/const HISTORICAL_DAILY = \{[\s\S]*?\};/,
                           'const HISTORICAL_DAILY = ' + JSON.stringify(out) + ';');
fs.writeFileSync('index.html', nuevo);
console.error('index.html actualizado');
