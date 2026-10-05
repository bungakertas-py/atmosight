"""Isi riwayat MJO sekali di awal, supaya indeksnya tidak perlu menunggu
pipeline menumpuk 120 hari sendiri.

    python mjo_backfill.py [jumlah_hari]        bawaan 200

OLR diambil dari CPC lewat OPeNDAP, rekamannya panjang jadi tidak ada masalah.

ANGINNYA yang butuh akal. Arsip analisis GFS di NCEI berisi berkas 147 MB per
waktu, jadi 200 hari berarti 29 GB dan itu mustahil. Tapi di sampingnya ada
berkas indeks `.inv` yang menyebut offset bita tiap pesan GRIB, dan server
mengizinkan permintaan sepotong, `Accept-Ranges: bytes`.

    260:59517797:d=2026100200:UGRD:200 mb:anl:
    468:100801850:d=2026100200:UGRD:850 mb:anl:

Satu pesan cuma 0,18 MB. Jadi 200 hari kali 2 ketinggian itu sekitar 72 MB,
empat ratus kali lebih kecil daripada menyeret berkas utuh.

Server NCEI LAMBAT untuk permintaan sepotong, sekitar 22 detik per pesan,
jadi dijalankan berbarengan beberapa utas. Ini kerja sekali, bukan harian.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import requests

import mjo

NCEI = ("https://www.ncei.noaa.gov/thredds/fileServer/model-gfs-g4-anl-files/"
        "{ym}/{ymd}/gfs_4_{ymd}_{jam}00_000.grb2")
JAM = "00"          # analisis 00Z saja, satu per hari sudah cukup untuk indeks harian
UTAS = 8
POLA = re.compile(r"^(\d+):(\d+):d=\d+:UGRD:(850|200) mb:anl:", re.M)


def _pesan_angin(url: str, sesi: requests.Session) -> dict | None:
    """Pulangkan {'850': bita, '200': bita} dengan permintaan sepotong."""
    try:
        inv = sesi.get(url + ".inv", timeout=90)
        if not inv.ok:
            return None
        baris = inv.text.splitlines()
        awal = {int(b.split(":")[0]): int(b.split(":")[1]) for b in baris if ":" in b}
        out = {}
        for m in POLA.finditer(inv.text):
            n, off, lev = int(m.group(1)), int(m.group(2)), m.group(3)
            akhir = awal.get(n + 1)
            rng = f"bytes={off}-" + (str(akhir - 1) if akhir else "")
            r = sesi.get(url, headers={"Range": rng}, timeout=180)
            if not r.ok or not r.content.startswith(b"GRIB"):
                return None
            out[lev] = r.content
        return out if len(out) == 2 else None
    except Exception:
        return None


def _baca_grib(bita: bytes, kisi, sesi_tmp: Path) -> list | None:
    """Rata rata 15 LS sampai 15 LU lalu interpolasi ke kisi basis."""
    import xarray as xr
    f = sesi_tmp / f"p{abs(hash(bita[:64]))}.grb2"
    f.write_bytes(bita)
    try:
        ds = xr.open_dataset(f, engine="cfgrib",
                             backend_kwargs={"indexpath": ""})
        v = list(ds.data_vars)[0]
        da = ds[v]
        lat = np.asarray(da["latitude"].values, dtype=float)
        lon = np.asarray(da["longitude"].values, dtype=float)
        a = np.asarray(da.values, dtype=float)
        jl = np.where((lat <= mjo.LAT_BATAS) & (lat >= -mjo.LAT_BATAS))[0]
        a = a[jl, :]
        a[np.abs(a) > mjo.ANGIN_SAH] = np.nan
        garis = np.nanmean(a, axis=0)
        sah = ~np.isnan(garis)
        urut = np.argsort(lon[sah])
        return [round(float(x), 3)
                for x in np.interp(kisi, lon[sah][urut], garis[sah][urut])]
    except Exception as e:
        print(f"    ! grib gagal dibaca: {e}")
        return None
    finally:
        f.unlink(missing_ok=True)


def main(hari: int = 200) -> None:
    basis = mjo._muat_basis()
    if not basis:
        sys.exit("basis MJO tidak ada, mjo_basis.json wajib lebih dulu")
    kisi = [float(x) for x in basis["lon"]]
    riwayat = mjo._rapikan(mjo._muat_riwayat())
    punya = set(riwayat["hari"])

    akhir = dt.date.today()
    mulai = akhir - dt.timedelta(days=hari)
    print(f"backfill MJO {mulai} sampai {akhir}, sudah punya {len(punya)} hari")

    print("1/2 OLR dari CPC ...")
    olr = mjo.ambil_olr(kisi, mulai.isoformat(), akhir.isoformat())
    print(f"    {len(olr)} hari OLR, terbaru {max(olr) if olr else '-'}")

    perlu = [d for d in sorted(olr) if d not in punya]
    print(f"2/2 angin GFS dari arsip NCEI, {len(perlu)} hari, {UTAS} utas ...")
    tmp = Path(tempfile.mkdtemp())
    sesi = requests.Session()

    def satu(tgl: str):
        d = dt.date.fromisoformat(tgl)
        url = NCEI.format(ym=d.strftime("%Y%m"), ymd=d.strftime("%Y%m%d"), jam=JAM)
        pesan = _pesan_angin(url, sesi)
        if not pesan:
            return tgl, None
        u8 = _baca_grib(pesan["850"], kisi, tmp)
        u2 = _baca_grib(pesan["200"], kisi, tmp)
        return tgl, ((u8, u2) if u8 and u2 else None)

    jadi = 0
    with ThreadPoolExecutor(max_workers=UTAS) as ex:
        for tgl, hasil in ex.map(satu, perlu):
            if not hasil:
                print(f"    - {tgl} dilewati")
                continue
            riwayat["hari"].append(tgl)
            riwayat["olr"].append(olr[tgl])
            riwayat["u850"].append(hasil[0])
            riwayat["u200"].append(hasil[1])
            jadi += 1
            if jadi % 20 == 0:
                print(f"    {jadi}/{len(perlu)}")
    riwayat = mjo._rapikan(riwayat)
    mjo._simpan_riwayat(riwayat)
    print(f"selesai, riwayat {len(riwayat['hari'])} hari, "
          f"{riwayat['hari'][0]} sampai {riwayat['hari'][-1]}")
    h = mjo.hitung_indeks(basis, riwayat)
    if h:
        print("indeks terbaru:", json.dumps(h["indeks"], ensure_ascii=False))
    else:
        print("riwayat belum cukup untuk menghitung indeks")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 200)
