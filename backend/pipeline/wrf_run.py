"""Pipeline model kedua: WRF Citarum (ITB).

Meniru cara GFS bergulir, tapi sumbernya arsip 2018-2019. Tiap kali dijalankan
ia mengambil satu jendela 4 hari (1 lampau + 3 "ke depan") dan menggeser
jendelanya satu hari tiap hari nyata berlalu.

Jalankan dari DALAM folder ini, sama seperti run.py:
    python wrf_run.py
Pilihan:
    WRF_JENDELA=2018-10-10   paksa tanggal awal jendela tertentu
    WRF_JAM_MAX=6            batasi jam per hari, untuk uji cepat
    WRF_WORKERS=8            jumlah unduhan paralel
"""
from __future__ import annotations

import datetime as dt
import gzip
import json
import os
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

import process
import wrf_config as C
import wrf_tiff

# ------------------------------------------------------------------ palet
# Skala GFS dipakai ulang kalau rentangnya memang cocok (hujan, kelembapan).
# Yang tidak cocok dibuat sendiri, dan legenda di app.js HARUS disamakan.

# Suhu Jawa cuma 14..35 derajat. Skala GFS membentang -10..42 sehingga seluruh
# pulau keluar oranye rata. Ramp warnanya sengaja keluarga yang sama.
SKALA_SUHU = [
    (14, (0x24, 0x50, 0xb4, 255)), (18, (0x4a, 0x97, 0xdc, 255)),
    (22, (0xcf, 0xe4, 0xf2, 255)), (25, (0xff, 0xe0, 0x8a, 255)),
    (28, (0xfb, 0xaa, 0x4a, 255)), (31, (0xee, 0x72, 0x33, 255)),
    (34, (0xd4, 0x33, 0x25, 255)),
]

# TEKANAN PERMUKAAN MENTAH, bukan MSLP. 787 hPa itu puncak gunung, bukan badai.
# Jadi petanya lebih dekat ke peta ketinggian daripada peta cuaca. Skalanya
# dibuat sendiri dan namanya di UI HARUS ditulis "Tekanan Permukaan".
SKALA_TEKANAN = [
    (780,  (0x3b, 0x0f, 0x5c, 255)), (850, (0x5e, 0x3c, 0x99, 255)),
    (910,  (0x35, 0x6b, 0xc4, 255)), (955, (0x7d, 0xc8, 0xd8, 255)),
    (985,  (0xf0, 0xf0, 0xe0, 255)), (1000, (0xf4, 0xc0, 0x60, 255)),
    (1012, (0xe0, 0x5a, 0x3a, 255)),
]

# Angin WRF maksimum sekitar 12 m/s = 23 knot. Skala GFS mentok 120 knot jadi
# seluruh Jawa cuma biru. Ini versi rapatnya, warnanya tetap keluarga BMKG.
SKALA_KNOT = [
    (0,  (0x00, 0x30, 0x50)), (3,  (0x2b, 0x83, 0xba)),
    (6,  (0x5a, 0xa8, 0xcf)), (10, (0xab, 0xdd, 0xa4)),
    (14, (0x66, 0xbd, 0x63)), (18, (0xd9, 0xef, 0x8b)),
    (22, (0xfe, 0xe0, 0x8b)), (28, (0xfd, 0xae, 0x61)),
    (34, (0xf4, 0x6d, 0x43)), (42, (0xd7, 0x30, 0x27)),
]

SKALA = {
    "temp_surface":     SKALA_SUHU,
    "rain_surface":     process._RAIN_SCALE,
    "rain_accum_surface": process._RAIN_ACCUM_SCALE,
    "humidity_surface": process._HUM_SCALE,
    "pressure_surface": SKALA_TEKANAN,
}
SKALA_UP = 8          # perbesaran pratinjau, 153x54 -> 1224x432

# Nama variabel di point_data / city_data, mengikuti kunci yang sudah dipakai
# frontend supaya panel titik dan label kota jalan tanpa diubah.
VAR_TITIK = {
    "temp_surface": "temp", "rain_surface": "rain",
    "humidity_surface": "humidity", "pressure_surface": "pressure",
}


# ------------------------------------------------------------------ unduh
def _ambil(url: str, timeout: int = 60) -> bytes | None:
    for percobaan in range(3):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            time.sleep(1 + percobaan)
        except Exception:
            time.sleep(1 + percobaan)
    return None


def _cache(nama: str) -> Path:
    C.RAW_DIR.mkdir(parents=True, exist_ok=True)
    return C.RAW_DIR / nama


def _ambil_cache(url: str, nama: str) -> bytes | None:
    p = _cache(nama)
    if p.exists() and p.stat().st_size > 0:
        return p.read_bytes()
    b = _ambil(url)
    if b:
        p.write_bytes(b)
    return b


def _kunci_waktu(hari: dt.date, jam: int) -> str:
    """Jam di path itu WIB. Simpan sebagai UTC supaya sejalan dengan GFS,
    karena frontend selalu menampilkan ulang dalam WIB."""
    lokal = dt.datetime.combine(hari, dt.time(jam))
    return (lokal - dt.timedelta(hours=C.TZ_JAM)).strftime("%Y-%m-%dT%H:00:00Z")


# ------------------------------------------------------------------ inti
def unduh_jendela(hari_list: list[dt.date], jam_max: int, workers: int) -> dict:
    """Unduh semua berkas jendela ini. Kembalikan {(param, hari, jam): bytes}."""
    tugas = []
    for hari in hari_list:
        for jam in range(jam_max):
            for param in C.PARAMS:
                tugas.append((param, hari, jam, "1.tif"))
            tugas.append((C.FOLDER_ANGIN, hari, jam, "1.json"))

    hasil: dict = {}

    def kerja(t):
        param, hari, jam, nama = t
        url = C.url_berkas(param, hari, jam, nama)
        kunci = f"{param}_{hari:%Y%m%d}_{jam}_{nama}"
        return t, _ambil_cache(url, kunci)

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for i, (t, b) in enumerate(ex.map(kerja, tugas), 1):
            if b:
                hasil[t[:3]] = b
            if i % 100 == 0:
                print(f"    {i}/{len(tugas)} berkas, {time.time() - t0:.0f}s", flush=True)
    ada = len(hasil)
    print(f"  unduh selesai {ada}/{len(tugas)} berkas dalam {time.time() - t0:.0f} detik "
          f"({sum(len(v) for v in hasil.values()) / 1e6:.1f} MB)")
    return hasil


def baca_angin(raw: bytes) -> tuple[np.ndarray, np.ndarray] | None:
    """u dan v dari velocity JSON server. Berkas NaN penuh dibuang di sini."""
    if len(raw) == C.UKURAN_ANGIN_NAN:
        return None
    try:
        d = json.loads(raw)
    except Exception:
        return None
    if len(d) < 2:
        return None
    try:
        u = np.array([float(x) for x in d[0]["data"]], dtype="float32")
        v = np.array([float(x) for x in d[1]["data"]], dtype="float32")
    except (TypeError, ValueError):
        return None
    if u.size != C.NX * C.NY or np.isnan(u).all():
        return None
    return u.reshape(C.NY, C.NX), v.reshape(C.NY, C.NX)


def tulis_city_data(series: dict, times: list, out_dir: Path) -> int:
    """Sama seperti process.write_city_data tapi kota DI LUAR domain WRF dibuang,
    bukan dijepit ke tepi. Kalau dijepit, Medan dan Jayapura akan memakai nilai
    sel pojok Jawa dan itu angka palsu.

    Frontend mencocokkan kota lewat NAMA (cityIndexByName), dan tempat yang tak
    ada di daftar dilewati begitu saja, jadi memfilter di sini aman.
    """
    if not process.CITY_PLACES.exists():
        print("  city_data dilewati, id_places.json tak ada")
        return 0
    semua = json.loads(process.CITY_PLACES.read_text(encoding="utf-8"))
    g = C.GRID
    di_dalam = [p for p in semua
                if g["west"] <= p["lon"] <= g["east"] and g["south"] <= p["lat"] <= g["north"]]
    print(f"  kota di dalam domain WRF: {len(di_dalam)} dari {len(semua)}")
    if not di_dalam:
        return 0

    nx, ny = g["width"], g["height"]
    dx = (g["east"] - g["west"]) / (nx - 1)
    dy = (g["north"] - g["south"]) / (ny - 1)
    lat = np.array([p["lat"] for p in di_dalam], "f8")
    lon = np.array([p["lon"] for p in di_dalam], "f8")
    fx = np.clip((lon - g["west"]) / dx, 0, nx - 1)
    fy = np.clip((g["north"] - lat) / dy, 0, ny - 1)
    x0 = np.floor(fx).astype(int); x1 = np.minimum(x0 + 1, nx - 1); tx = fx - x0
    y0 = np.floor(fy).astype(int); y1 = np.minimum(y0 + 1, ny - 1); ty = fy - y0

    def samp(a):
        a = np.nan_to_num(np.asarray(a, dtype="float64"))
        atas = a[y0, x0] * (1 - tx) + a[y0, x1] * tx
        bawah = a[y1, x0] * (1 - tx) + a[y1, x1] * tx
        return atas * (1 - ty) + bawah * ty

    data = {}
    for var, skala in process._CITY_ENC.items():
        if var == "wind":
            us, vs = series.get("u"), series.get("v")
            if not us or not vs:
                continue
            per_t = [np.sqrt(samp(u) ** 2 + samp(v) ** 2) * process.MS_TO_KNOTS
                     for u, v in zip(us, vs)]
        else:
            arrs = series.get(var)
            if not arrs or len(arrs) != len(times):
                continue
            per_t = [samp(a) for a in arrs]
        data[var] = np.round(np.stack(per_t) / skala).astype("int32").T.tolist()

    doc = {"times": times,
           "scales": {v: process._CITY_ENC[v] for v in data},
           "places": [p["n"] for p in di_dalam],
           "data": data}
    path = out_dir / "city_data.json"
    path.write_text(json.dumps(doc, separators=(",", ":")), encoding="utf-8")
    return path.stat().st_size


def main() -> None:
    jam_max = int(os.environ.get("WRF_JAM_MAX", "24"))
    workers = int(os.environ.get("WRF_WORKERS", "8"))
    paksa = os.environ.get("WRF_JENDELA")

    if paksa:
        d0 = dt.date.fromisoformat(paksa)
        hari_list = [d0 + dt.timedelta(days=i) for i in range(C.HARI_JENDELA)]
    else:
        hari_list = C.jendela_untuk()

    jj = C.semua_jendela()
    idx = jj.index(hari_list) + 1 if hari_list in jj else 0
    kini = hari_list[C.HARI_LAMPAU]          # hari kedua = "sekarang"

    print("== Pipeline WRF Citarum (ITB) ==")
    print(f"Jendela {idx}/{len(jj)}: {hari_list[0]} .. {hari_list[-1]}  "
          f"({C.HARI_LAMPAU} hari lampau + {C.HARI_JENDELA - C.HARI_LAMPAU} hari ke depan)")
    print(f'"Kini" = {kini} 00 WIB | jam per hari: {jam_max} | paralel: {workers}')

    out = C.OUTPUT_DIR
    out.mkdir(parents=True, exist_ok=True)
    for lama in out.glob("*"):
        if lama.is_file():
            lama.unlink()

    berkas = unduh_jendela(hari_list, jam_max, workers)

    # ---------------------------------------------------------- susun deret
    waktu: list[str] = []
    bidang: dict[str, list[np.ndarray]] = {k: [] for k in C.PARAMS}
    angin: dict[str, tuple[np.ndarray, np.ndarray] | None] = {}

    for hari in hari_list:
        for jam in range(jam_max):
            if not all((p, hari, jam) in berkas for p in C.PARAMS):
                continue
            vt = _kunci_waktu(hari, jam)
            waktu.append(vt)
            for p in C.PARAMS:
                arr, info = wrf_tiff.baca(berkas[(p, hari, jam)])
                if (info["nx"], info["ny"]) != (C.NX, C.NY):
                    raise ValueError(f"grid {p} {hari} {jam} = {info['nx']}x{info['ny']}")
                bidang[p].append(arr)
            uv = berkas.get((C.FOLDER_ANGIN, hari, jam))
            angin[vt] = baca_angin(uv) if uv else None

    if not waktu:
        print("TIDAK ADA satu langkah pun yang lengkap. Berhenti.")
        sys.exit(1)
    n_angin = sum(1 for v in angin.values() if v)
    print(f"  langkah lengkap: {len(waktu)} | punya arah angin: {n_angin}")

    run_dt = dt.datetime.combine(kini, dt.time(0)) - dt.timedelta(hours=C.TZ_JAM)
    grid = dict(C.GRID)

    # ---------------------------------------------------------- render
    katalog = {
        "generated_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "model": "WRF Citarum",
        "model_label": "WRF Citarum - 7 km",
        "arsip": True,
        "run_time": run_dt.strftime("%Y-%m-%dT%H:00:00Z"),
        "region": {
            "bounds": [grid["west"], grid["south"], grid["east"], grid["north"]],
            "image_bounds": C.IMAGE_BOUNDS,
            "frame_bounds": C.FRAME_BOUNDS,
            "view_core": C.VIEW_CORE,
        },
        # Akurasi STATIS, tak ikut jendela yang tampil. Alasannya di wrf_config.
        "akurasi": C.AKURASI,
        "pos_hujan": [{"n": n, "lat": la, "lon": lo} for n, la, lo in C.POS_HUJAN],
        "layers": {},
    }

    urut = ["wind_surface", "rain_surface", C.LAYER_AKUMULASI,
            "temp_surface", "humidity_surface", "pressure_surface"]
    param_dari = {v[0]: k for k, v in C.PARAMS.items()}

    for kunci in urut:
        frames = []
        if kunci == "wind_surface":
            p = param_dari[kunci]
            for i, vt in enumerate(waktu):
                spd = bidang[p][i]
                nama = f"wind_surface_{i:03d}"
                process._save_preview(
                    _gambar_knot(spd * process.MS_TO_KNOTS), out / f"{nama}_preview.webp")
                fr = {"valid_time": vt,
                      "forecast_step_hours": _langkah(run_dt, vt),
                      "preview_image": f"{nama}_preview.webp",
                      "speed_knots_max": round(float(np.nanmax(spd) * process.MS_TO_KNOTS), 1)}
                uv = angin.get(vt)
                if uv:
                    vj = out / f"{nama}_velocity.json"
                    process._export_velocity_json(uv[0], uv[1], grid, run_dt,
                                                  fr["forecast_step_hours"], vj)
                    fr["velocity_json"] = vj.name
                frames.append(fr)
            katalog["layers"][kunci] = {"kind": "vector", "level": "10 m",
                                        "units": "m/s", "frames": frames}
            continue

        if kunci == C.LAYER_AKUMULASI:
            per_tanggal: dict[str, np.ndarray] = {}
            for i, vt in enumerate(waktu):
                lokal = (dt.datetime.strptime(vt, "%Y-%m-%dT%H:00:00Z")
                         + dt.timedelta(hours=C.TZ_JAM))
                d = lokal.strftime("%Y-%m-%d")
                per_tanggal[d] = per_tanggal.get(d, 0) + np.nan_to_num(bidang["CH"][i])
            for j, (d, tot) in enumerate(sorted(per_tanggal.items())):
                nama = f"{kunci}_{j:03d}"
                process._render_scalar_preview(tot, SKALA[kunci],
                                               out / f"{nama}_preview.webp", scale_up=SKALA_UP)
                vt = (dt.datetime.fromisoformat(d) - dt.timedelta(hours=C.TZ_JAM)
                      ).strftime("%Y-%m-%dT%H:00:00Z")
                frames.append({"valid_time": vt,
                               "forecast_step_hours": _langkah(run_dt, vt),
                               "preview_image": f"{nama}_preview.webp",
                               "value_max": round(float(np.nanmax(tot)), 1)})
            katalog["layers"][kunci] = {"kind": "scalar", "level": "permukaan",
                                        "units": "mm/hari", "frames": frames}
            continue

        p = param_dari[kunci]
        for i, vt in enumerate(waktu):
            arr = bidang[p][i]
            nama = f"{kunci}_{i:03d}"
            process._render_scalar_preview(arr, SKALA[kunci],
                                           out / f"{nama}_preview.webp", scale_up=SKALA_UP)
            frames.append({"valid_time": vt,
                           "forecast_step_hours": _langkah(run_dt, vt),
                           "preview_image": f"{nama}_preview.webp",
                           "value_max": round(float(np.nanmax(arr)), 2)})
        katalog["layers"][kunci] = {"kind": "scalar", "level": "permukaan",
                                    "units": C.PARAMS[p][1], "frames": frames}

    # ---------------------------------------------------------- data titik
    series = {
        "temp":     bidang["Temperatur"],
        "rain":     bidang["CH"],
        "humidity": bidang["Kelembaban"],
        "pressure": bidang["Tekanan"],
    }
    uu, vv = [], []
    for i, vt in enumerate(waktu):
        uv = angin.get(vt)
        if uv:
            uu.append(uv[0]); vv.append(uv[1])
        else:  # tak ada arah, pakai kecepatan tanpa arah supaya panjang deret tetap
            spd = bidang["Kecepatan_Angin"][i]
            uu.append(np.zeros_like(spd)); vv.append(np.zeros_like(spd))
    series["u"], series["v"] = uu, vv

    ukuran_pd = process.write_point_data(series, waktu, grid, out_dir=out)
    ukuran_cd = tulis_city_data(series, waktu, out)

    (out / "catalog.json").write_text(json.dumps(katalog, indent=2))
    total = sum(f.stat().st_size for f in out.glob("*") if f.is_file())
    print(f"\n  point_data.bin.gz {ukuran_pd / 1e6:.2f} MB | city_data.json {ukuran_cd / 1e3:.0f} KB")
    print(f"  layer: {list(katalog['layers'])}")
    print(f"  keluaran {out}: {len(list(out.glob('*')))} berkas, {total / 1e6:.1f} MB")


def _gambar_knot(knot: np.ndarray):
    from PIL import Image
    stops = np.array([s[0] for s in SKALA_KNOT], dtype="float32")
    cols = np.array([s[1] for s in SKALA_KNOT], dtype="float32")
    v = np.nan_to_num(knot)
    out = np.empty(v.shape + (3,), dtype="float32")
    for c in range(3):
        out[..., c] = np.interp(v, stops, cols[:, c])
    img = Image.fromarray(out.round().astype("uint8"), "RGB")
    return img.resize((img.width * SKALA_UP, img.height * SKALA_UP), Image.BILINEAR)


def _langkah(run: dt.datetime, vt: str) -> int:
    return int((dt.datetime.strptime(vt, "%Y-%m-%dT%H:00:00Z") - run).total_seconds() // 3600)


if __name__ == "__main__":
    main()
