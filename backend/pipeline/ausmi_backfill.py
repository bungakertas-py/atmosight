"""Isi riwayat AUSMI ke belakang. DIJALANKAN SEKALI, lewat tab Actions.

    python ausmi_backfill.py [jumlah_hari]        bawaan 400

Kenapa 400 hari dan bukan 200 seperti MJO. AUSMI tidak butuh riwayat panjang
untuk SAH, indeksnya nilai mentah dan hari ini sudah sah hari ini juga. Yang
butuh panjang itu dua hal lain.

  1. Menampilkan onset MUSIM LALU sebagai pembanding. Musim monsun belahan
     selatan berjalan Juli sampai Juni, jadi 400 hari mundur dari Oktober
     mencakup musim 2025/2026 utuh.
  2. Mengukur bias GFS lawan reanalisis. Reanalisis NCEP di PSL basi
     berbulan, berkas tahun berjalan berhenti sekitar Maret, jadi irisan
     waktu yang bisa diadu cuma ada kalau riwayat GFS kita mundur sampai ke
     sana. Lihat ausmi_bias.py.

CARA AMBIL ANGINNYA sama persis dengan mjo_backfill, arsip analisis GFS di
NCEI, berkas utuhnya 147 MB per waktu tapi di sampingnya ada indeks `.inv`
yang menyebut offset bita tiap pesan dan server mengizinkan permintaan
sepotong lewat `Accept-Ranges: bytes`.

    468:100801850:d=2026100200:UGRD:850 mb:anl:

Bedanya, di sini cuma SATU ketinggian yang diperlukan, 850 saja, jadi
ongkosnya separuh MJO. Satu pesan sekitar 0,18 MB.

Kode permintaan sepotongnya SENGAJA TIDAK dipakai bersama mjo_backfill walau
mirip. Berkas itu sudah terbukti jalan dan menjadikannya umum berarti
menyentuhnya demi fitur lain, dan kalau salah, yang ikut rusak MJO. Dua puluh
baris kembar lebih murah daripada itu.
"""
from __future__ import annotations

import datetime as dt
import re
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import requests

import ausmi

NCEI = ("https://www.ncei.noaa.gov/thredds/fileServer/model-gfs-g4-anl-files/"
        "{ym}/{ymd}/gfs_4_{ymd}_{jam}00_000.grb2")
JAM = "00"          # analisis 00Z saja, satu per hari cukup untuk indeks harian
UTAS = 8
POLA = re.compile(r"^(\d+):(\d+):d=\d+:UGRD:850 mb:anl:", re.M)


def _pesan_u850(url: str, sesi: requests.Session) -> bytes | None:
    try:
        inv = sesi.get(url + ".inv", timeout=90)
        if not inv.ok:
            return None
        awal = {int(b.split(":")[0]): int(b.split(":")[1])
                for b in inv.text.splitlines() if ":" in b}
        m = POLA.search(inv.text)
        if not m:
            return None
        n, off = int(m.group(1)), int(m.group(2))
        akhir = awal.get(n + 1)
        rng = f"bytes={off}-" + (str(akhir - 1) if akhir else "")
        r = sesi.get(url, headers={"Range": rng}, timeout=180)
        if not r.ok or not r.content.startswith(b"GRIB"):
            return None
        return r.content
    except Exception:
        return None


def _baca_kotak(bita: bytes, tmp: Path) -> float | None:
    """Rerata u850 di dalam kotak AUSMI, dari satu pesan GRIB."""
    import xarray as xr
    f = tmp / f"u{abs(hash(bita[:64]))}.grb2"
    f.write_bytes(bita)
    try:
        ds = xr.open_dataset(f, engine="cfgrib", backend_kwargs={"indexpath": ""})
        da = ds[list(ds.data_vars)[0]]
        lat = np.asarray(da["latitude"].values, dtype=float)
        lon = np.asarray(da["longitude"].values, dtype=float)
        a = np.asarray(da.values, dtype=float)
        jl = np.where((lat <= ausmi.LAT_UTARA) & (lat >= ausmi.LAT_SELATAN))[0]
        kl = np.where((lon >= ausmi.LON_BARAT) & (lon <= ausmi.LON_TIMUR))[0]
        if not len(jl) or not len(kl):
            return None
        blok = a[np.ix_(jl, kl)]
        blok = np.where(np.abs(blok) > ausmi.ANGIN_SAH, np.nan, blok)
        if np.isnan(blok).all():
            return None
        return round(float(np.nanmean(blok)), 3)
    except Exception as e:
        print(f"    ! grib gagal dibaca: {e}")
        return None
    finally:
        f.unlink(missing_ok=True)


def main(hari: int = 400) -> None:
    riwayat = ausmi._rapikan(ausmi._muat_riwayat())
    punya = set(riwayat["hari"])

    akhir = dt.date.today() - dt.timedelta(days=1)   # arsip NCEI tertinggal sehari
    perlu = []
    for k in range(hari):
        d = akhir - dt.timedelta(days=k)
        if d.isoformat() not in punya:
            perlu.append(d.isoformat())
    perlu.sort()

    print(f"backfill AUSMI, sudah punya {len(punya)} hari, perlu {len(perlu)} hari")
    if not perlu:
        print("tidak ada yang kurang")
        return
    print(f"  {perlu[0]} sampai {perlu[-1]}, {UTAS} utas, arsip NCEI")

    tmp = Path(tempfile.mkdtemp())
    sesi = requests.Session()

    def satu(tgl: str):
        d = dt.date.fromisoformat(tgl)
        url = NCEI.format(ym=d.strftime("%Y%m"), ymd=d.strftime("%Y%m%d"), jam=JAM)
        pesan = _pesan_u850(url, sesi)
        if not pesan:
            return tgl, None
        return tgl, _baca_kotak(pesan, tmp)

    jadi, gagal = 0, 0
    with ThreadPoolExecutor(max_workers=UTAS) as ex:
        for tgl, nilai in ex.map(satu, perlu):
            if nilai is None:
                gagal += 1
                continue
            riwayat["hari"].append(tgl)
            riwayat["u850"].append(nilai)
            jadi += 1
            if jadi % 25 == 0:
                print(f"    {jadi}/{len(perlu)}")

    riwayat = ausmi._rapikan(riwayat)
    ausmi._simpan_riwayat(riwayat)
    print(f"selesai, {jadi} hari masuk, {gagal} gagal. "
          f"Riwayat {len(riwayat['hari'])} hari, "
          f"{riwayat['hari'][0]} sampai {riwayat['hari'][-1]}")

    basis = ausmi._muat_basis()
    if basis:
        n = riwayat["u850"]
        print(f"  rentang {min(n):+.2f} sampai {max(n):+.2f} m/s, "
              f"rerata {float(np.mean(n)):+.2f}")
        for musim in sorted({ausmi._musim(h) for h in riwayat["hari"]}):
            o = ausmi._onset(riwayat["hari"], riwayat["u850"], musim)
            print(f"  onset {o['musim']}: {o['tanggal'] or o['catatan']}")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 400)
