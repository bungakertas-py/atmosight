"""Profil vertikal atmosfer untuk diagram Skew-T log-P (per titik).

Mengunduh T/RH/angin di banyak level tekanan sekaligus (1 request/waktu,
multi-level), men-downsample ke grid lebih kasar (profil mulus, tak perlu 0.25
derajat), lalu menulis file biner terkompresi yang dimuat malas oleh frontend
saat kartu Skew-T dibuka:
  - profile.bin.gz   : biner int16/uint8 gzip, per var array (ntime, nlev, ny, nx).
  - profile_meta.json: layout (levels, times, grid, encoding).
"""
from __future__ import annotations

import datetime as dt
import gzip
import json
import warnings
from pathlib import Path

import numpy as np
import xarray as xr

from config import OUTPUT_DIR, PROFILE_LEVELS, PROFILE_STRIDE
from download import download_grib

warnings.filterwarnings("ignore", message="Ignoring index file")

_LEVELS_MB = [f"{p}_mb" for p in PROFILE_LEVELS]

# Encoding per variabel: nilai = stored * scale + offset.
_ENC = {
    "t": {"dtype": "int16", "np": np.int16, "scale": 0.1,  "offset": 0.0},   # °C
    "r": {"dtype": "uint8", "np": np.uint8, "scale": 1.0,  "offset": 0.0},   # %RH
    "u": {"dtype": "int16", "np": np.int16, "scale": 0.01, "offset": 0.0},   # m/s
    "v": {"dtype": "int16", "np": np.int16, "scale": 0.01, "offset": 0.0},
}


def fetch_profile(run: dt.datetime, fstep: int) -> tuple[dict, dict] | None:
    """Unduh + ekstrak profil satu waktu. Kembalikan ({t,r,u,v}, grid) sudah
    di-downsample & berorientasi baris-0=utara, kolom-0=barat. None bila gagal.
    Nilai: t dalam °C, r dalam %, u/v dalam m/s. Array shape (nlev, ny, nx)."""
    g = None
    try:
        g = download_grib(run, fstep, "multi", ["TMP", "RH", "UGRD", "VGRD"], levels=_LEVELS_MB)
        ds = xr.open_dataset(g, engine="cfgrib", backend_kwargs={
            "indexpath": "", "filter_by_keys": {"typeOfLevel": "isobaricInhPa"}}).load()
    except Exception as e:
        print(f"  ! profil f{fstep:03d} gagal: {e}")
        if g is not None:
            g.unlink(missing_ok=True)
        return None
    g.unlink(missing_ok=True)

    # orientasi: longitude menaik (barat->timur), latitude menurun (utara di baris-0)
    if float(ds.longitude[0]) > float(ds.longitude[-1]):
        ds = ds.isel(longitude=slice(None, None, -1))
    if float(ds.latitude[0]) < float(ds.latitude[-1]):
        ds = ds.isel(latitude=slice(None, None, -1))
    # urutkan level tepat PROFILE_LEVELS (permukaan -> atas)
    ds = ds.sel(isobaricInhPa=PROFILE_LEVELS)

    s = PROFILE_STRIDE
    lon = ds.longitude.values[::s]
    lat = ds.latitude.values[::s]
    arrs = {
        "t": ds["t"].values[:, ::s, ::s].astype("float32") - 273.15,
        "r": ds["r"].values[:, ::s, ::s].astype("float32"),
        "u": ds["u"].values[:, ::s, ::s].astype("float32"),
        "v": ds["v"].values[:, ::s, ::s].astype("float32"),
    }
    grid = {"west": float(lon[0]), "east": float(lon[-1]),
            "north": float(lat[0]), "south": float(lat[-1]),
            "nx": int(len(lon)), "ny": int(len(lat))}
    return arrs, grid


def write_profile_data(times: list[str], per_time: list[dict], grid: dict,
                       out_dir: Path = OUTPUT_DIR) -> int:
    """Tulis profile.bin.gz + profile_meta.json dari daftar profil per-waktu.
    per_time[i] = {t,r,u,v} shape (nlev, ny, nx) untuk times[i]."""
    ntime, nlev, ny, nx = len(times), len(PROFILE_LEVELS), grid["ny"], grid["nx"]
    blob = bytearray()
    layout = []
    per_sel = []
    stride = 0
    for var, enc in _ENC.items():
        stacked = np.stack([np.nan_to_num(pt[var]) for pt in per_time]).astype("float32")  # (t,lev,ny,nx)
        stored = np.round((stacked - enc["offset"]) / enc["scale"])
        lo, hi = (0, 255) if enc["dtype"] == "uint8" else (-32768, 32767)
        stored = np.clip(stored, lo, hi).astype(enc["np"])
        b = stored.tobytes(order="C")
        # (t,lev,ny,nx) -> (ny,nx,lev,t), lalu dibaca sebagai bita mentah.
        sel = np.ascontiguousarray(stored.transpose(2, 3, 1, 0)).view(np.uint8).reshape(ny, nx, -1)
        per_sel.append(sel)
        layout.append({"var": var, "dtype": enc["dtype"], "scale": enc["scale"],
                       "offset": enc["offset"], "byteOffset": len(blob), "byteLength": len(b),
                       "cellOffset": stride, "cellLength": int(sel.shape[2])})
        stride += int(sel.shape[2])
        blob += b

    """SUSUNAN PER SEL, dan ini yang sebenarnya dipakai frontend.

       Berkas lama `profile.bin.gz` bersusun [waktu][level][y][x], jadi satu
       titik tersebar di seluruh berkas dan satu satunya cara mengambilnya
       mengunduh semuanya. DIUKUR 19 Okt 2026, 19,3 MB dan 16 detik, padahal
       untuk menggambar satu sounding yang betul betul dipakai cuma 3.850
       bita, yaitu 0,02 persennya.

       Susunan [y][x][var][level][waktu] membuat satu titik DUDUK BERSEBELAHAN,
       jadi frontend cukup meminta potongan HTTP Range sepanjang satu sel.
       Terukur 0,18 detik, delapan puluh sembilan kali lebih cepat. Polanya
       disalin dari point_cells.bin yang sudah dipakai panel titik.

       TIDAK DI-GZIP, dan itu bukan kelalaian. Range di dalam aliran gzip
       tidak ada artinya, sebab bita ke-n hasil mampat tidak berhubungan
       dengan bita ke-n isi aslinya. Berkasnya jadi lebih besar di server,
       tapi tidak ada lagi yang mengunduhnya utuh."""
    sel_semua = np.concatenate(per_sel, axis=2)
    (out_dir / "profile_cells.bin").write_bytes(sel_semua.tobytes(order="C"))

    # BERKAS LAMA MASIH DIPAKAI, jangan dibuang. Dua pemakainya. Pertama
    # frontend yang tersimpan di cache orang dan belum tahu susunan per sel.
    # Kedua, dan ini yang menetap, MODE MJO LOKAL di Atmosight, yang merata
    # ratakan kelembapan sepanjang pita lintang untuk SETIAP bujur sehingga
    # memang butuh seluruh kisi. Mode itu hidup selama mjo.json belum berisi
    # `amplop`, dan per 19 Okt 2026 belum.
    (out_dir / "profile.bin.gz").write_bytes(gzip.compress(bytes(blob), compresslevel=6))
    meta = {
        "bounds": [grid["west"], grid["south"], grid["east"], grid["north"]],
        "nx": nx, "ny": ny,
        "dx": round((grid["east"] - grid["west"]) / (nx - 1), 4),
        "dy": round((grid["north"] - grid["south"]) / (ny - 1), 4),
        "levels": PROFILE_LEVELS, "times": times, "vars": layout,
        "cells": {"file": "profile_cells.bin", "stride": stride,
                  "bytes": int(ny) * int(nx) * stride},
    }
    (out_dir / "profile_meta.json").write_text(json.dumps(meta))
    n_sel = (out_dir / "profile_cells.bin").stat().st_size
    print(f"  profil: per sel {n_sel/1e6:.1f} MB, satu titik {stride} bita, "
          f"blob lama {(out_dir / 'profile.bin.gz').stat().st_size/1e6:.1f} MB")
    return n_sel


def build_profiles(run: dt.datetime, steps: list[int], times_of: dict) -> int:
    """Unduh & tulis profil untuk daftar langkah forecast. times_of[fstep] =
    valid_time string. Kembalikan ukuran file (byte), 0 bila kosong."""
    ptimes, per, pgrid = [], [], None
    for fstep in steps:
        res = fetch_profile(run, fstep)
        if res is None:
            continue
        arrs, pgrid = res
        per.append(arrs)
        ptimes.append(times_of[fstep])
        print(f"  + profil f{fstep:03d} valid {times_of[fstep]}")
    if not per or pgrid is None:
        return 0
    return write_profile_data(ptimes, per, pgrid)
