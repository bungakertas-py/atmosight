"""Verifikasi Private Model (WRF Indonesia) lawan pengamatan METAR.

Beda dari GFS yang akurasinya STATIS (butuh 7 hari arsip yang tak tersimpan),
di sini kita manfaatkan bahwa run pagi (mis. 00Z) sudah punya jam-jam awal yang
LEWAT saat deploy sore. Jadi ramalan jam 6..sekarang bisa langsung diadu lawan
METAR yang sudah terjadi, dihitung ulang tiap hari tanpa menyimpan arsip.

Dipakai oleh wrf_itera_run.py. Gagal-lunak: kalau METAR tak terjangkau atau
pasangannya terlalu sedikit, kembalikan None (badge tampil "segera").

Kode inti (fetch per stasiun, rumus, toleransi) diadaptasi dari
scratchpad/verif_metar.py yang dipakai menghitung akurasi GFS.
"""
from __future__ import annotations

import datetime as dt
import math
import time

import numpy as np
import requests

BBOX = "-11,94,7,142"          # kotak Indonesia untuk METAR
MIN_PASANGAN = 40              # di bawah ini dianggap belum cukup -> "segera"

# Toleransi "dianggap tepat" per parameter, sama dengan verifikasi GFS.
TOL = {
    "Suhu":       ("C",   2.0),
    "Angin":      ("kt",  5.0),
    "Arah angin": ("der", 45.0),
    "Kelembapan": ("%",   10.0),
    "Tekanan":    ("hPa", 2.0),
}


def _rh(t, td):
    if t is None or td is None:
        return None
    a, b = 17.625, 243.04
    return 100 * math.exp(a * td / (b + td) - a * t / (b + t))


def _beda_arah(a, b):
    d = abs(a - b) % 360
    return d if d <= 180 else 360 - d


def _ambil_metar(jam: int = 30) -> dict:
    """{sid: {lat, lon, obs: [(waktu, laporan)]}} untuk stasiun Indonesia.

    JEBAKAN (dari verif GFS): parameter hours dibatasi JUMLAH HASIL, bukan waktu.
    bbox+hours besar diam-diam cuma balik beberapa jam. Jadi daftar stasiun
    diambil sekali via bbox, riwayatnya SATU STASIUN per permintaan.
    """
    base = requests.get("https://aviationweather.gov/api/data/metar"
                        f"?bbox={BBOX}&format=json&hours=2", timeout=90).json()
    ids = sorted({m["icaoId"] for m in base if m["icaoId"].startswith(("WI", "WA"))})
    st: dict = {}
    for sid in ids:
        try:
            d = requests.get("https://aviationweather.gov/api/data/metar"
                             f"?ids={sid}&format=json&hours={jam}", timeout=90).json()
        except Exception:
            continue
        for m in d:
            if m.get("lat") is None:
                continue
            s = st.setdefault(sid, {"lat": m["lat"], "lon": m["lon"], "obs": []})
            t = dt.datetime.strptime(m["reportTime"][:19], "%Y-%m-%dT%H:%M:%S")
            s["obs"].append((t, m))
        time.sleep(0.25)
    for s in st.values():
        s["obs"].sort()
    return st


def _sampler(grid: dict):
    W, E = grid["west"], grid["east"]
    N, S = grid["north"], grid["south"]
    nx, ny = grid["width"], grid["height"]
    dx = (E - W) / (nx - 1)
    dy = (N - S) / (ny - 1)   # lat menurun: baris 0 = utara

    def samp(arr, lat, lon):
        if not (W <= lon <= E and S <= lat <= N):
            return None
        fx = (lon - W) / dx
        fy = (N - lat) / dy
        x0 = int(np.clip(int(fx), 0, nx - 2)); x1 = x0 + 1; tx = fx - x0
        y0 = int(np.clip(int(fy), 0, ny - 2)); y1 = y0 + 1; ty = fy - y0
        v = (arr[y0, x0] * (1 - tx) * (1 - ty) + arr[y0, x1] * tx * (1 - ty)
             + arr[y1, x0] * (1 - tx) * ty + arr[y1, x1] * tx * ty)
        return float(v) if np.isfinite(v) else None
    return samp


def verify(grid: dict, fields: dict, times_dt: list, now: dt.datetime) -> dict | None:
    """Kembalikan dict akurasi (bentuk sama dengan config.AKURASI GFS), atau None.

    fields: {'t2m': (t,ny,nx) degC, 'rh2m': %, 'mslp': hPa, 'u10','v10': m/s}
    times_dt: waktu valid (UTC) tiap langkah, sejajar dengan sumbu waktu fields.
    """
    try:
        st = _ambil_metar()
    except Exception as e:
        print("  METAR tak terjangkau:", str(e)[:80])
        return None
    if not st:
        return None
    samp = _sampler(grid)
    pas = {k: [] for k in TOL}   # (model, obs)

    for ti, vt in enumerate(times_dt):
        if vt > now:
            continue             # belum terjadi
        t2 = fields["t2m"][ti]; rh = fields["rh2m"][ti]; ps = fields["mslp"][ti]
        u = fields["u10"][ti]; v = fields["v10"][ti]
        for s in st.values():
            lat, lon = s["lat"], s["lon"]
            # laporan METAR terdekat, maksimum beda 20 menit
            dekat, beda = None, dt.timedelta(minutes=21)
            for t, m in s["obs"]:
                d = abs(t - vt)
                if d < beda:
                    beda, dekat = d, m
                elif t > vt + dt.timedelta(minutes=21):
                    break
            if dekat is None:
                continue
            # Suhu
            if dekat.get("temp") is not None:
                mv = samp(t2, lat, lon)
                if mv is not None:
                    pas["Suhu"].append((mv, float(dekat["temp"])))
            # Angin + arah
            if dekat.get("wspd") is not None:
                uu = samp(u, lat, lon); vv = samp(v, lat, lon)
                if uu is not None and vv is not None:
                    pas["Angin"].append((math.hypot(uu, vv) * 1.943844, float(dekat["wspd"])))
                    wd = dekat.get("wdir")
                    if isinstance(wd, (int, float)) and float(dekat["wspd"]) >= 3:
                        arah = (math.degrees(math.atan2(-uu, -vv)) + 360) % 360
                        pas["Arah angin"].append((arah, float(wd)))
            # Kelembapan
            if dekat.get("dewp") is not None and dekat.get("temp") is not None:
                mv = samp(rh, lat, lon)
                ov = _rh(float(dekat["temp"]), float(dekat["dewp"]))
                if mv is not None and ov is not None:
                    pas["Kelembapan"].append((mv, ov))
            # Tekanan (altimeter setting METAR ~ MSLP)
            if dekat.get("altim") is not None:
                mv = samp(ps, lat, lon)
                if mv is not None:
                    pas["Tekanan"].append((mv, float(dekat["altim"])))

    total = sum(len(v) for v in pas.values())
    if total < MIN_PASANGAN:
        print(f"  pasangan METAR cuma {total}, belum cukup -> segera")
        return None

    param = {}
    for k, (sat, tol) in TOL.items():
        v = pas[k]
        if not v:
            continue
        if k == "Arah angin":
            err = [_beda_arah(a, b) for a, b in v]
        else:
            err = [abs(a - b) for a, b in v]
        tepat = 100 * sum(1 for e in err if e <= tol) / len(err)
        param[k] = {"tepat": round(tepat, 1), "mae": round(sum(err) / len(err), 2),
                    "sat": sat, "tol": tol}
    if not param:
        return None
    rata = round(sum(p["tepat"] for p in param.values()) / len(param), 1)
    return {
        "nilai": rata,
        "label": "",
        "sumber": f"METAR {len(st)} stasiun",
        "periode": "24 jam terakhir",
        "pasangan": total,
        "auto": True,
        "parameter": param,
        "catatan": ("Diadu dengan pengamatan METAR bandara Indonesia pada jam-jam "
                    "awal ramalan yang sudah terjadi. Dihitung ulang otomatis tiap "
                    "hari. Rata-rata dari parameter yang ada."),
    }
