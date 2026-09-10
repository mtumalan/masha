#!/usr/bin/env python3
"""Genera `data/15_results.csv` para la vista 15.html desde el libro de orquestador_masha.

Una fila por apuesta LIQUIDADA de los cuatro modelos nuevos (quarterhour y hourly, BTC y ETH).

LA UNIDAD ES FIJA Y CADA PATA VALE UNA FRACCION DE LA MAS ALTA (operador 2026-09-10). La unidad de
referencia (1.0) es la de la pata mas grande —hoy BTC horario— y las demas valen su proporcion:

    hourly      BTCUSDT   ratio 2.400%  ->  peso 1.0000
    quarterhour BTCUSDT   ratio 1.717%  ->  peso 0.7154
    hourly      ETHUSDT   ratio 1.200%  ->  peso 0.5000
    quarterhour ETHUSDT   ratio 0.429%  ->  peso 0.1789

    units = (pnl / stake) x peso        arriesgado = peso

Los pesos salen de `orquestador_masha/config.py` —la MISMA fuente que dimensiona el camino vivo— y
son FIJOS: no dependen del banco, porque las cuatro patas escalan juntas. Comprobado contra las
unidades reales de hoy: 129.06 / 92.33 / 64.53 / 23.08 dan 1.0000 / 0.7154 / 0.5000 / 0.1788.

Asi el dimensionamiento dinamico de produccion no entra en la cuenta del cliente, pero SI entra que
una pata arriesgue menos que otra: una apuesta de ETH de 15 min mueve la quinta parte que una de BTC
horario, porque eso es exactamente lo que arriesga.

Las apuestas SIN FILL (stake 0) entran con units 0 y arriesgado 0: se decidieron y no se llego a
operar, asi que ni suman ni restan ni cuentan como exposicion.

EL HISTORICO viene de la CADENA CIEGA OOS de los cuatro modelos (orquestador_masha/studies/anual):
2025-09-13 -> 2026-08-30, cada bag gobernando SOLO el tramo posterior a su corte, con el libro real
de Polymarket y la comision vigente. Es el rendimiento del modelo sobre datos que no vio; las filas
de produccion se anaden despues, en el mismo formato y sin distinguirse (operador 2026-09-09).

La calidad del llenado del historico depende del tamano de la orden, asi que se evalua a la unidad
que corresponde a un BANCO DE REFERENCIA fijo (--banco, 10.000 USD por defecto), interpolando en la
malla de tamanos que trae cada pierna. Con un banco mayor las ordenes son mas grandes y llenan peor.

    ../venv/bin/python tools/gen_15.py                 # solo produccion
    ../venv/bin/python tools/gen_15.py --historico     # + la cadena ciega OOS
"""
from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd

R = Path(__file__).resolve().parents[1]
FUENTE = R.parent / "alquimiaBTC" / "orquestador_masha" / "state" / "results.csv"
SALIDA = R / "data" / "15_results.csv"
COLS = ["timestamp", "model", "symbol", "pred", "win", "stake", "pnl", "units", "risked", "paper"]
ANUAL = R.parent / "alquimiaBTC" / "orquestador_masha" / "studies" / "anual"
PATAS = {"q_BTC": ("quarterhour", "BTCUSDT"), "q_ETH": ("quarterhour", "ETHUSDT"),
         "h_BTC": ("hourly", "BTCUSDT"), "h_ETH": ("hourly", "ETHUSDT")}
MALLA = [10, 25, 50, 100, 200, 400, 800, 1500, 3000, 5000]


def por_dolar(fila, u):
    """PnL por dolar de unidad a tamano `u`, interpolando en la malla de la pierna."""
    import bisect
    u = min(max(u, MALLA[0]), MALLA[-1])
    j = min(bisect.bisect_right(MALLA, u) - 1, len(MALLA) - 2)
    w = (u - MALLA[j]) / (MALLA[j + 1] - MALLA[j])
    return fila[f"g{MALLA[j]}"] * (1 - w) + fila[f"g{MALLA[j+1]}"] * w


def historico(P: dict, banco: float) -> list[list]:
    """La cadena ciega OOS de las cuatro piernas, en el mismo formato que produccion."""
    import sys
    sys.path.insert(0, str(R.parent / "alquimiaBTC" / "orquestador_masha"))
    import config as MC
    filas = []
    for pata, (mod, sym) in PATAS.items():
        f = ANUAL / f"{pata}.csv"
        if not f.exists():
            print(f"  [GUARDA] falta {f.name}: el historico quedaria incompleto"); return []
        d = pd.read_csv(f)
        d["cierre"] = pd.to_datetime(d.cierre, utc=True, format="ISO8601")
        u = MC.unit_for(banco, banco, mod, sym)
        peso = P[(mod, sym)]
        for x in d.itertuples():
            g = por_dolar({c: getattr(x, c) for c in d.columns if c.startswith("g")}, u)
            filas.append([x.cierre.strftime("%Y-%m-%dT%H:%M:%S+00:00"), mod, sym,
                          1 if x.ac else -1, 1 if g > 0 else 0, f"{u:.2f}", f"{g*u:.2f}",
                          f"{g*peso:.6f}", f"{peso if g != 0 else 0.0:.6f}", 0])
        print(f"  {pata}: {len(d):,} apuestas OOS a unidad ${u:,.2f} (peso {peso:.4f})")
    return filas


def pesos() -> dict[tuple[str, str], float]:
    """Peso de cada pata como fraccion de la unidad MAS ALTA, desde la config del camino vivo."""
    import sys
    sys.path.insert(0, str(R.parent / "alquimiaBTC" / "orquestador_masha"))
    import config as MC
    r = {}
    for m in MC.MODELS:
        for s in MC.MODELS[m]["coins"]:
            base = MC.UNIT_RATIO_BY_MODEL.get(m, MC.UNIT_RATIO)
            r[(m, s)] = base * MC.FRACCION_UNIDAD_POR_MONEDA.get(m, {}).get(s, 1.0)
    mx = max(r.values())
    return {k: v / mx for k, v in r.items()}


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--historico", action="store_true", help="anade la cadena ciega OOS")
    ap.add_argument("--banco", type=float, default=10_000.0, help="banco de referencia del OOS")
    a = ap.parse_args()
    if not FUENTE.exists():
        print(f"[GUARDA] no existe {FUENTE}"); return 1
    r = pd.read_csv(FUENTE)
    if not len(r):
        print("[GUARDA] results.csv vacio: no se escribe nada"); return 1

    # las filas de PAPEL las escribe verify/humo.py al ejercitar el colocador: no son operaciones
    if "paper" in r.columns:
        n_papel = int((r.paper.astype(int) == 1).sum())
        r = r[r.paper.astype(int) == 0].copy()
        if n_papel:
            print(f"  {n_papel} fila(s) de papel fuera")
    r["timestamp"] = pd.to_datetime(r.timestamp, utc=True, format="ISO8601")
    r = r.sort_values("timestamp")

    P = pesos()
    faltan = {(m, s) for m, s in zip(r.model, r.symbol)} - set(P)
    if faltan:
        print(f"[GUARDA] patas sin peso en config: {sorted(faltan)}"); return 1
    peso = pd.Series([P[(m, s)] for m, s in zip(r.model, r.symbol)], index=r.index)
    stake = pd.to_numeric(r.stake, errors="coerce").fillna(0.0)
    pnl = pd.to_numeric(r.pnl, errors="coerce").fillna(0.0)
    lleno = stake > 0
    r["units"] = ((pnl / stake.where(lleno)) * peso).fillna(0.0).round(6)
    r["risked"] = (peso * lleno).round(6)
    print("  pesos: " + " · ".join(f"{m[:5]} {s[:3]} {P[(m, s)]:.4f}" for m, s in sorted(P, key=lambda k: -P[k])))

    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    with open(SALIDA, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(COLS)
        for fila in (historico(P, a.banco) if a.historico else []):
            w.writerow(fila)
        for x in r.itertuples():
            w.writerow([x.timestamp.strftime("%Y-%m-%dT%H:%M:%S+00:00"), x.model, x.symbol,
                        int(x.pred), int(x.win), f"{float(x.stake):.2f}", f"{float(x.pnl):.2f}",
                        f"{float(x.units):.6f}", f"{float(x.risked):.6f}", 0])

    con = r[stake > 0]
    print(f"{SALIDA.name}: {len(r)} apuestas ({len(con)} con fill), "
          f"{r.units.sum():+.4f} u ganadas sobre {r.risked.sum():.4f} u arriesgadas, "
          f"{r.timestamp.min():%Y-%m-%d} -> {r.timestamp.max():%Y-%m-%d}")
    for (m, s), g in sorted(r.groupby(["model", "symbol"]), key=lambda x: -P[x[0]]):
        f = g[pd.to_numeric(g.stake, errors="coerce").fillna(0) > 0]
        print(f"  {m:11s} {s} (peso {P[(m, s)]:.4f}): {len(g):3d} apuestas, {len(f):3d} con fill, "
              f"{g.units.sum():+8.4f} u sobre {g.risked.sum():7.4f} arriesgadas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
