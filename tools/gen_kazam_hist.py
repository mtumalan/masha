#!/usr/bin/env python3
"""Genera el HIST de kazam.html desde data/twin_2026.csv (frame horario del
gemelo de produccion, unit flat $130).

Reglas (verificadas 208/208 contra el embed original, 2026-09-01):
- Sim horaria causal: los settles (lag 2h) se aplican ANTES de la stake de la
  hora; stake = min(1250, 0.02925 * banco_liquidado); units = pnl_total/130.
- Por dia: u = suma de units; trades = suma nb; bank = liquidado + pendientes
  a la medianoche que cierra el dia; unit = min(1250, 0.02925 * banco
  LIQUIDADO a esa medianoche) — la stake que el sistema usaria al cierre.

Uso: python3 tools/gen_kazam_hist.py  (imprime el JSON del HIST)
"""
import csv as _csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

RATIO, CAP, BANK0 = 0.02925, 1250.0, 10000.0
ROOT = Path(__file__).resolve().parent.parent

rows = []
with open(ROOT / "data" / "twin_2026.csv") as fh:
    for r in _csv.DictReader(fh):
        ts = datetime.fromisoformat(r["timestamp"]).astimezone(timezone.utc)
        rows.append((ts, float(r["pnl_total"]) / 130.0, int(r["nb"])))
rows.sort(key=lambda x: x[0])

bank, pend, out, cur = BANK0, [], {}, None

def close_day(d):
    if d in out:
        out[d]["bank"] = round(bank + sum(m for _, m in pend), 2)
        out[d]["unit"] = round(min(CAP, RATIO * bank), 2)

for i, (ts, units, nb) in enumerate(rows):
    while pend and pend[0][0] <= i:
        bank += pend.pop(0)[1]
    d = str(ts.date())
    if cur is not None and d != cur:
        close_day(cur)
    cur = d
    if nb > 0:
        st = min(CAP, RATIO * bank)
        o = out.setdefault(d, {"u": 0.0, "trades": 0})
        o["u"] = round(o["u"] + units, 4)
        o["trades"] += nb
        pend.append((i + 2, units * st))
close_day(cur)
print(json.dumps({d: {"u": v["u"], "unit": v["unit"], "bank": v["bank"],
                      "trades": v["trades"]} for d, v in out.items()}))
