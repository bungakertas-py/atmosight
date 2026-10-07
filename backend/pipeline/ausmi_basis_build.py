"""Bangun ausmi_basis.json, klimatologi musiman AUSMI. DIJALANKAN SEKALI.

    python ausmi_basis_build.py [tahun_awal] [tahun_akhir]     bawaan 1991 2020

AUSMI itu angin zonal 850 hPa dirata ratakan di kotak 5 LS sampai 15 LS,
110 BT sampai 130 BT. Kajikawa, Wang, dan Yang 2010. Positif berarti baratan
dan monsun Australia sedang aktif, negatif berarti timuran dan monsunnya
lemah.

Indeks bakunya NILAI MENTAH, bukan anomali, jadi sebetulnya klimatologi tidak
wajib untuk menayangkannya. Yang butuh klimatologi cuma dua hal, mengatakan di
atas atau di bawah normal, dan menandai onset.

SUMBER KLIMATOLOGINYA BEDA DENGAN SUMBER NILAI HARIAN, dan itu disengaja.
  klimatologi  reanalisis NCEP/NCAR harian lewat OPeNDAP NOAA PSL, kisi 2,5
               derajat. Rekamannya sampai 1948 jadi 30 tahun normal bisa
               dihitung betulan.
  harian       analisis GFS yang memang sudah diunduh pipeline ini.

Mencampur dua sumber meninggalkan selisih biasnya di dalam anomali, dan itu
pelajaran dari MJO. Bedanya, di sini selisihnya bisa DIUKUR dan disimpan,
sebab kotaknya cuma satu angka. Lihat ausmi_bias.py.

Reanalisis NCEP di PSL BASI BERBULAN, berkas tahun berjalan berhenti di
sekitar Maret. Untuk klimatologi itu tidak masalah sama sekali, kita cuma
butuh tahun tahun yang sudah lewat.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import sys
from pathlib import Path

import numpy as np

DIR = Path(__file__).resolve().parent
KELUAR = DIR / "ausmi_basis.json"

PSL = ("https://psl.noaa.gov/thredds/dodsC/Datasets/ncep.reanalysis/"
       "Dailies/pressure/uwnd.{tahun}.nc")

# Kotak AUSMI baku. JANGAN diubah tanpa alasan, angka ini yang membuat indeks
# kita bisa dibandingkan dengan punya orang lain.
LAT_UTARA, LAT_SELATAN = -5.0, -15.0
LON_BARAT, LON_TIMUR = 110.0, 130.0
ANGIN_SAH = 120.0          # m/detik, di luar ini pasti nilai pengisi
HARMONIK = 3               # resep yang sama dengan klimatologi MJO


def _harmonik(doy: int) -> np.ndarray:
    w = 2 * math.pi * doy / 365.25
    v = [1.0]
    for k in range(1, HARMONIK + 1):
        v += [math.cos(k * w), math.sin(k * w)]
    return np.array(v)


def ambil_tahun(tahun: int) -> dict[str, float]:
    """{tanggal: AUSMI} untuk satu tahun reanalisis."""
    import netCDF4 as nc
    d = nc.Dataset(PSL.format(tahun=tahun))
    try:
        lev = np.asarray(d.variables["level"][:], dtype=float)
        il = int(np.where(lev == 850)[0][0])
        lat = np.asarray(d.variables["lat"][:], dtype=float)
        lon = np.asarray(d.variables["lon"][:], dtype=float)
        jl = np.where((lat <= LAT_UTARA) & (lat >= LAT_SELATAN))[0]
        kl = np.where((lon >= LON_BARAT) & (lon <= LON_TIMUR))[0]
        t = d.variables["time"]
        tgl = nc.num2date(t[:], t.units, only_use_cftime_datetimes=False)
        blok = np.ma.filled(
            d.variables["uwnd"][:, il, jl[0]:jl[-1] + 1, kl[0]:kl[-1] + 1].astype("float32"),
            np.nan)
    finally:
        d.close()
    blok[np.abs(blok) > ANGIN_SAH] = np.nan
    # Rerata kotak TANPA pembobotan cos(lat). Pitanya cuma 10 derajat dan
    # seluruhnya di lintang rendah, jadi bobotnya nyaris rata, dan definisi
    # bakunya pun rerata sederhana.
    nilai = np.nanmean(blok, axis=(1, 2))
    out = {}
    for i, x in enumerate(tgl):
        v = float(nilai[i])
        if not math.isnan(v):
            out[x.strftime("%Y-%m-%d")] = round(v, 4)
    return out


def main(awal: int = 1991, akhir: int = 2020) -> None:
    print(f"klimatologi AUSMI {awal} sampai {akhir}, "
          f"kotak 5 sampai 15 LS, {LON_BARAT:.0f} sampai {LON_TIMUR:.0f} BT")
    semua: dict[str, float] = {}
    for th in range(awal, akhir + 1):
        try:
            satu = ambil_tahun(th)
        except Exception as e:
            print(f"  ! {th} gagal ({e})")
            continue
        semua.update(satu)
        print(f"  {th}  {len(satu)} hari  rerata {np.mean(list(satu.values())):+.2f} m/s")

    if len(semua) < 3650:
        sys.exit(f"cuma {len(semua)} hari terkumpul, terlalu sedikit untuk 30 tahun normal")

    hari = sorted(semua)
    y = np.array([semua[h] for h in hari])
    doy = np.array([(dt.date.fromisoformat(h) - dt.date(int(h[:4]), 1, 1)).days
                    for h in hari])
    H = np.array([_harmonik(int(x)) for x in doy])
    koef, *_ = np.linalg.lstsq(H, y, rcond=None)
    sisa = y - H @ koef

    # Simpangan baku sisa PER MUSIM, bukan satu angka untuk setahun. Sebaran
    # AUSMI jauh lebih lebar waktu monsunnya aktif daripada waktu kemarau,
    # jadi satu angka akan membuat anomali musim hujan terlihat biasa saja dan
    # anomali musim kemarau terlihat luar biasa.
    sd_bulan = []
    bln = np.array([int(h[5:7]) for h in hari])
    for m in range(1, 13):
        s = sisa[bln == m]
        sd_bulan.append(round(float(np.std(s)), 4) if len(s) > 30 else None)

    siklus = [round(float(_harmonik(d) @ koef), 4) for d in range(366)]
    basis = {
        "indeks": "AUSMI",
        "acuan": "Kajikawa, Wang, Yang 2010, Int. J. Climatol.",
        "definisi": "rerata u850 di 5 LS sampai 15 LS, 110 BT sampai 130 BT",
        "kotak": {"latN": LAT_UTARA, "latS": LAT_SELATAN,
                  "lonW": LON_BARAT, "lonE": LON_TIMUR},
        "sumber_klim": "NCEP/NCAR Reanalysis daily, NOAA PSL",
        "periode_klim": f"{awal}-{akhir}",
        "hari_klim": len(semua),
        "harmonik": HARMONIK,
        "koef": [round(float(x), 6) for x in koef],
        # Siklus musiman sudah dihitung penuh 366 hari supaya pemakainya tidak
        # perlu mengulang aljabar harmoniknya. Koefisiennya tetap disimpan
        # untuk jejak.
        "siklus_doy": siklus,
        "sd_bulan": sd_bulan,
        "sd_total": round(float(np.std(sisa)), 4),
    }
    KELUAR.write_text(json.dumps(basis, separators=(",", ":")), encoding="utf-8")
    print(f"\nditulis {KELUAR.name}, {len(semua)} hari dipakai")
    print(f"  siklus musiman, puncak {max(siklus):+.2f} m/s di doy {siklus.index(max(siklus))}, "
          f"lembah {min(siklus):+.2f} m/s di doy {siklus.index(min(siklus))}")
    print(f"  simpangan baku sisa {basis['sd_total']:.2f} m/s")
    print(f"  per bulan {basis['sd_bulan']}")


if __name__ == "__main__":
    a = int(sys.argv[1]) if len(sys.argv) > 1 else 1991
    b = int(sys.argv[2]) if len(sys.argv) > 2 else 2020
    main(a, b)
