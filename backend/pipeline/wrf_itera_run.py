"""Model ketiga: WRF Indonesia (ITERA), 9 km, satu domain se-Indonesia.

Sumbernya SATU berkas NetCDF per run, hasil olahan di server ITERA (wrf_post.py),
ditarik dari GitHub Release. Beda dari WRF Citarum yang menyerap ratusan GeoTIFF,
di sini semua variabel dan semua jam sudah ada dalam satu nc.

KONSISTEN DENGAN GFS: layer key dan PALET sengaja sama persis dengan GFS
(temp_surface, rain_surface, humidity_surface, pressure_surface, wind_surface,
cloud_surface), memakai ulang skala warna di process.py, supaya pindah model
GFS <-> WRF Indonesia mulus dan legendanya sama.

Jalankan dari DALAM folder ini:
    python wrf_itera_run.py [path_nc]
Default path_nc = backend/data/raw/wrf_itera/latest.nc
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys
from pathlib import Path

import numpy as np
import netCDF4  # type: ignore

import process

BACKEND = Path(__file__).resolve().parent.parent
OUT = BACKEND / "data" / "output" / "wrf_itera"
DEFAULT_NC = BACKEND / "data" / "raw" / "wrf_itera" / "latest.nc"

SCALE_UP = 2   # 679x309 -> 1358x618, cukup halus tanpa berkas besar

# Partikel angin (velocity json) dijarangkan biar berkasnya tak raksasa.
# Grid asli 9 km, stride 3 jadi ~27 km, sepadan kerapatan GFS dan tetap halus
# untuk animasi partikel. Heatmap kecepatannya TETAP resolusi penuh.
VEL_STRIDE = int(os.environ.get("WRF_ITERA_VELSTRIDE", "3"))

# Buang spin-up: frame dengan langkah < TRIM_HOURS dibuang. 0 = tak dibuang
# (untuk uji 3 jam). Produksi 72 jam set 6 di deploy.
TRIM_HOURS = int(os.environ.get("WRF_ITERA_TRIM", "0"))

# Kotak tampilan awal se-Indonesia (frontend melebarkan ke rasio layar lalu
# menjepit ke frame_bounds domain).
VIEW_CORE = [96.0, -10.5, 141.0, 6.5]


def _step(run_dt: dt.datetime, vt: str) -> int:
    return int((dt.datetime.strptime(vt, "%Y-%m-%dT%H:00:00Z") - run_dt).total_seconds() // 3600)


def main() -> None:
    ncpath = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_NC
    print(f"== Ingest WRF Indonesia (ITERA) ==\n  baca {ncpath}")
    nc = netCDF4.Dataset(str(ncpath))

    la = np.asarray(nc.variables["lat"][:], dtype="float64")   # menurun: utara->selatan
    lo = np.asarray(nc.variables["lon"][:], dtype="float64")   # menaik: barat->timur
    ny, nx = len(la), len(lo)
    grid = {"width": nx, "height": ny,
            "west": float(lo[0]), "east": float(lo[-1]),
            "north": float(la[0]), "south": float(la[-1])}

    tvar = nc.variables["time"]
    m = re.search(r"hours since ([\d\-]+[ T][\d:]+)", tvar.units)
    init = dt.datetime.strptime(m.group(1).replace("T", " "), "%Y-%m-%d %H:%M:%S")
    hours = [int(round(float(h))) for h in tvar[:]]
    times = [(init + dt.timedelta(hours=h)).strftime("%Y-%m-%dT%H:00:00Z") for h in hours]
    run_dt = init

    def g(v):  # (t, ny, nx), sudah baris-0=utara kolom-0=barat
        return np.asarray(nc.variables[v][:], dtype="float32")

    t2 = g("t2m"); rh = g("rh2m"); mslp = g("mslp")
    u = g("u10"); v = g("v10"); rain = g("rain"); cld = g("cldfra") * 100.0
    nc.close()

    # buang spin-up (produksi). Hanya kalau menyisakan >= 2 frame.
    if TRIM_HOURS > 0 and max(hours) > TRIM_HOURS:
        keep = [i for i, h in enumerate(hours) if h >= TRIM_HOURS]
        if len(keep) >= 2:
            times = [times[i] for i in keep]
            t2, rh, mslp, u, v, rain, cld = (a[keep] for a in (t2, rh, mslp, u, v, rain, cld))
            print(f"  spin-up dibuang: sisa {len(times)} frame (>= {TRIM_HOURS} jam)")

    # akurasi otomatis lawan METAR. Cuma di produksi (nc penuh >= 24 jam);
    # di uji coba pendek badge tampil "segera". Gagal-lunak.
    akurasi = {"status": "soon"}
    if os.environ.get("WRF_ITERA_VERIFY") and max(hours) >= 24:
        try:
            import metar_verify
            times_dt = [dt.datetime.strptime(t, "%Y-%m-%dT%H:00:00Z") for t in times]
            ak = metar_verify.verify(
                grid, {"t2m": t2, "rh2m": rh, "mslp": mslp, "u10": u, "v10": v},
                times_dt, dt.datetime.utcnow())
            if ak:
                akurasi = ak
                print(f"  akurasi METAR: {ak['nilai']}% dari {ak['pasangan']} pasangan")
            else:
                print("  akurasi: segera (verifikasi belum cukup)")
        except Exception as e:
            print("  verifikasi METAR gagal:", str(e)[:100])

    OUT.mkdir(parents=True, exist_ok=True)
    for f in OUT.glob("*"):
        if f.is_file():
            f.unlink()

    # tepi sel untuk menempatkan overlay (bukan pusat sel)
    dx = (grid["east"] - grid["west"]) / (nx - 1)
    dy = (grid["north"] - grid["south"]) / (ny - 1)
    image_bounds = [grid["west"] - dx / 2, grid["south"] - dy / 2,
                    grid["east"] + dx / 2, grid["north"] + dy / 2]

    catalog = {
        "generated_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "model": "Private Model",
        "model_label": "Private Model - 9 km",
        "arsip": False,
        "run_time": run_dt.strftime("%Y-%m-%dT%H:00:00Z"),
        "region": {
            "bounds": [grid["west"], grid["south"], grid["east"], grid["north"]],
            "image_bounds": image_bounds,
            "frame_bounds": image_bounds,
            "view_core": VIEW_CORE,
        },
        "pos_hujan": [],
        "akurasi": akurasi,
        "layers": {},
    }

    # -------- angin (vektor) --------
    # Grid partikel dijarangkan (VEL_STRIDE); heatmap tetap penuh.
    s = max(1, VEL_STRIDE)
    lo_c, la_c = lo[::s], la[::s]
    grid_c = {"width": len(lo_c), "height": len(la_c),
              "west": float(lo_c[0]), "east": float(lo_c[-1]),
              "north": float(la_c[0]), "south": float(la_c[-1])}
    frames = []
    for i, vt in enumerate(times):
        nama = f"wind_surface_{i:03d}"
        process._render_speed_preview(u[i], v[i], OUT / f"{nama}_preview.webp", scale=SCALE_UP)
        vj = OUT / f"{nama}_velocity.json"
        process._export_velocity_json(u[i][::s, ::s], v[i][::s, ::s], grid_c,
                                      run_dt, _step(run_dt, vt), vj)
        spd = np.sqrt(u[i] ** 2 + v[i] ** 2) * process.MS_TO_KNOTS
        frames.append({"valid_time": vt, "forecast_step_hours": _step(run_dt, vt),
                       "preview_image": f"{nama}_preview.webp", "velocity_json": vj.name,
                       "speed_knots_max": round(float(np.nanmax(spd)), 1)})
    catalog["layers"]["wind_surface"] = {"kind": "vector", "level": "10 m",
                                         "units": "m/s", "frames": frames}

    # -------- skalar (palet GFS) --------
    scal = [
        ("rain_surface",     rain, process._RAIN_SCALE, "mm/jam"),
        ("temp_surface",     t2,   process._TEMP_SCALE, "°C"),
        ("humidity_surface", rh,   process._HUM_SCALE,  "%"),
        ("pressure_surface", mslp, process._PRESS_SCALE, "hPa"),
        ("cloud_surface",    cld,  process._CLOUD_SCALE, "%"),
    ]
    for key, arr, scale, units in scal:
        frames = []
        for i, vt in enumerate(times):
            nama = f"{key}_{i:03d}"
            process._render_scalar_preview(arr[i], scale, OUT / f"{nama}_preview.webp", scale_up=SCALE_UP)
            frames.append({"valid_time": vt, "forecast_step_hours": _step(run_dt, vt),
                           "preview_image": f"{nama}_preview.webp",
                           "value_max": round(float(np.nanmax(arr[i])), 2)})
        catalog["layers"][key] = {"kind": "scalar", "level": "permukaan",
                                  "units": units, "frames": frames}

    # -------- data titik + kota --------
    series = {"temp": list(t2), "rain": list(rain), "humidity": list(rh),
              "pressure": list(mslp), "cloud": list(cld), "u": list(u), "v": list(v)}
    pd_size = process.write_point_data(series, times, grid, out_dir=OUT)
    cd_size = process.write_city_data(series, times, grid, out_dir=OUT)

    # -------- Monsun (indikasi dari angin permukaan, sama seperti GFS) --------
    try:
        import monsoon
        mon = monsoon.build_monsoon(series, times, grid)
        (OUT / "monsoon.json").write_text(json.dumps(mon))
        mv = monsoon.build_monsoon_velocity(series, grid, run_dt)
        if mv:
            (OUT / "monsoon_velocity.json").write_text(json.dumps(mv, separators=(",", ":")))
        print(f"  monsun: {mon.get('phase', {}).get('label', '-')}")
    except Exception as e:
        print("  monsun gagal:", str(e)[:80])

    (OUT / "catalog.json").write_text(json.dumps(catalog, indent=2))
    total = sum(f.stat().st_size for f in OUT.glob("*") if f.is_file())
    print(f"  init {run_dt:%Y-%m-%d %H}Z | {len(times)} langkah | grid {nx}x{ny}")
    print(f"  layer: {list(catalog['layers'])}")
    print(f"  point_data {pd_size/1e6:.2f} MB | city_data {cd_size/1e3:.0f} KB")
    print(f"  keluaran {OUT}: {len(list(OUT.glob('*')))} berkas, {total/1e6:.1f} MB")


if __name__ == "__main__":
    main()
