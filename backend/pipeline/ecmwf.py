# -*- coding: utf-8 -*-
"""ECMWF IFS 9 km, sumber data keempat Atmosight.

   KENAPA ADA. ECMWF membuka langganan 9 km jadi gratis pada 20 Oktober 2026.
   Sebelum itu open data mereka cuma 0,25 derajat, sama kasarnya dengan GFS,
   jadi tidak ada alasan memakainya. Sekarang kisinya 2,5 kali lebih halus di
   tiap sumbu, yaitu 6,2 kali lebih banyak sel di domain kita, 1181 x 661
   lawan 473 x 265.

   DELAPAN LAYER, dan itu bukan pilihan melainkan batas. Daftar parameter
   permukaan di open data 0p1 sudah diperiksa pesan per pesan, 45 macam, dan
   TIGA hal yang dipakai Atmosight memang tidak ada di sana.

   1. CIN TIDAK ADA. Yang ada cuma `mucape` tanpa pasangannya, dan tidak ada
      nama lain yang mendekati, bukan `cin`, bukan `mucin`. Jadi tombol CIN
      otomatis redup di model ini, sebab `applyLevelUI` di app.js meredupkan
      tombol yang layernya tidak ada di katalog. Itu perilaku yang sudah ada,
      bukan tambahan, dan memang yang diminta.
   2. TIGA LAYER ANOMALI, `olr_anom`, `u850_anom`, `u200_anom`, tidak dibuat
      di sini. Bahan mentahnya ada, `ttr` untuk OLR dan `u` di 850 dan 200
      hPa. Yang tidak ada KLIMATOLOGI DUA DIMENSI-nya. `mjo_basis.json` di
      folder ini memang berisi dasar 1991-2020, tapi cuma SATU dimensi, rata
      rata 15 LS sampai 15 LU per bujur, dan itu untuk indeks RMM. Dari situ
      tidak bisa dibuat peta. Membuat anomali dengan dasar seadanya berarti
      menerbitkan peta yang salah dengan percaya diri, jadi tidak dibuat.
   SKEW-T IKUT DIBUAT, dengan 14 level, dan pemilik sudah tahu batasnya.
   GFS memberi 22 level, ECMWF 14, yang hilang 950, 900, 800, 750, 650, 550,
   450, 350, dan 70. Delapan dari sembilan itu di lapisan bawah, tempat LCL,
   LFC, dan apungan parcel dihitung, jadi soundingnya memang lebih kasar di
   bawah. Itu diterima, sebab gunanya model kedua memang untuk DIBANDINGKAN,
   dan sounding yang lebih kasar tetap kabar selama orang tahu asalnya.
   Frontend membaca jumlah level dari `profile_meta.json`, bukan dari angka
   mati, jadi tidak ada yang perlu diubah di sana.

   CARA MENGAMBILNYA. Tiap langkah punya dua GRIB2 raksasa, permukaan 78 MB
   dan level tekanan 370 MB. Yang diunduh BUKAN berkas itu, tapi pesan pesan
   di dalamnya, lewat berkas .index di sebelahnya yang berisi offset dan
   panjang tiap pesan. Satu indeks dibaca sekali lalu dipakai untuk semua
   parameter di langkah itu.

   AKURASINYA DIHITUNG, bukan ditulis tangan. Dipakai `metar_verify` yang
   sama dengan Private Model. Lihat `akurasi_metar()` untuk alasan kenapa
   yang diverifikasi RUN LAIN, bukan run yang ditampilkan.

   LISENSINYA CC BY 4.0, dan penyebutannya WAJIB. Ada LICENCE.txt di folder
   datanya yang menunjuk ke apps.ecmwf.int/datasets/licences/general.
   Syaratnya baris hak cipta ECMWF, kalimat "based on data and products of
   the European Centre for Medium-Range Weather Forecasts (ECMWF)", dan
   keterangan bahwa datanya diolah ulang. Itu urusan KET_SUMBER di app.js.
"""
from __future__ import annotations

import concurrent.futures as cf
import datetime as dt
import gzip
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np
import xarray as xr

from config import PROFILE_STRIDE, REGION
from process import (MS_TO_KNOTS, _SCALAR_SCALES, _encode_vector_png,
                     _export_velocity_json, _render_scalar_preview,
                     _render_speed_preview)

EMBER = "https://data.ecmwf.int/forecasts"
LABEL = "ECMWF - 9 km"
DERAJAT = 0.1

# Sejajar dengan GFS supaya dua modelnya bisa diadu langkah per langkah.
# ECMWF sendiri menyediakan sampai 144 jam, jadi memanjangkannya cuma soal
# mengubah angka ini lewat env.
LANGKAH_MAKS = int(os.environ.get("LANGKAH_MAKS") or 72)
LANGKAH = list(range(0, LANGKAH_MAKS + 1, 3))

# Pratinjau DITULIS PADA KISI ASLINYA. GFS memperbesar 4x sebab kisinya kasar
# dan tanpa itu petanya kotak kotak. Di sini kisinya sudah 6,2 kali lebih
# rapat, jadi memperbesar cuma menggemukkan berkas. Diukur pada bingkai yang
# sama, 1x = 229 KB, 2x = 1557 KB, sedangkan GFS 785 KB. Jadi 1x lebih ringan
# daripada GFS sekaligus lebih halus, dan peramban tetap melembutkannya waktu
# gambarnya diregangkan.
PERBESAR = 1

# KISI PARTIKEL ANGIN SENGAJA DIKASARKAN KE 0,3 DERAJAT. Ini SATU SATUNYA
# tempat di model ini yang sengaja lebih kasar daripada GFS, dan ada
# sebabnya. `_export_velocity_json` menulis seluruh medan sebagai angka di
# dalam JSON, dan di GFS saja satu bingkai sudah 4,6 MB. Pada kisi 9 km penuh
# itu jadi 28 MB per bingkai, 700 MB satu run, cuma demi animasi partikel.
#
# Diukur, 0,2 derajat memberi 7,3 MB per bingkai, LEBIH BERAT daripada GFS,
# sedangkan 0,3 derajat memberi 3,2 MB, lebih ringan. Hostingan kita pernah
# terukur 29 KB per detik, dan pada kecepatan itu 7,3 MB berarti empat menit
# untuk satu bingkai. Beda kerapatan 0,25 lawan 0,3 derajat tidak akan
# terlihat orang pada animasi partikel. Heatmap kecepatannya TETAP 9 km
# penuh, yang dikasarkan cuma partikelnya.
VELO_DERAJAT = 0.3

# Sama dengan wind_surface GFS, supaya pembacaan frontend tidak berubah.
UNSCALE = [-40.0, 40.0]

# KISI PANEL TITIK 0,2 DERAJAT, bukan 9 km penuh, dan ini soal ukuran berkas.
# `point_cells.bin` bersusun per sel dan TIDAK BOLEH di-gzip, sebab Range di
# dalam aliran gzip tidak ada artinya. Pada 9 km penuh dia jadi 273 MB, dan
# ditambah 166 MB gambar satu model ini saja sudah 440 MB sedangkan cadangan
# GitHub Pages punya batas lunak 1 GB. Pada 0,2 derajat jadi sekitar 68 MB,
# dan itu MASIH LEBIH RAPAT daripada GFS yang 0,25 derajat. Untuk meteogram
# di satu titik, beda 11 km dan 22 km tidak mengubah apa pun yang dibaca
# orang. Peta tetap 9 km penuh, yang dikasarkan cuma deret titiknya.
#
# Kisi ini juga yang dipakai isobar, siklon, ITCZ, dan monsun, sebab keempat
# modul itu menerima `series` yang sama.
TITIK_DERAJAT = 0.2

# Riwayat MJO dan AUSMI DIPISAH DARI GFS. Dua deret itu panjangnya ratusan
# hari dan dipakai menghitung anomali serta onset. Kalau dua model menulis ke
# berkas yang sama, satu deret berisi dua model berselang seling dan tidak
# ada lagi yang bisa memisahkannya.
STATE = Path(__file__).resolve().parents[1] / "data" / "state"

OUTPUT = Path(__file__).resolve().parents[1] / "data" / "output" / "ecmwf_9km"

# Parameter permukaan yang diunduh tiap langkah, pakai nama ECMWF.
PARAM = ["2t", "2d", "10u", "10v", "tprate", "msl", "tcc", "mucape"]
# Yang dipakai memverifikasi lawan METAR, lebih sedikit.
# `metar_verify` cuma mengambil pengamatan 30 jam terakhir, jadi tidak ada
# gunanya mengadu ramalan yang lebih tua dari itu, pasangannya sudah hilang.
JENDELA_METAR = 30

PARAM_VERIF = ["2t", "2d", "10u", "10v", "msl"]

# Level tekanan yang ADA di open data 0p1, urut permukaan ke atas, sama
# arahnya dengan PROFILE_LEVELS milik GFS. 70 hPa tidak ada di sini, jadi
# layer stratosfer 70 hPa memang tidak bisa dibuat dari ECMWF.
PROFIL_LEVEL = [1000, 925, 850, 700, 600, 500, 400, 300, 250, 200, 150, 100, 50, 10]
PROFIL_VAR = ["t", "r", "u", "v"]
# Kisi profil ~1 derajat, sama dengan GFS. Di GFS stride 4 pada 0,25 derajat,
# di sini 10 pada 0,1 derajat, jadi kisi keluarannya berukuran sama.
PROFIL_STRIDE = int(round(PROFILE_STRIDE * 0.25 / DERAJAT))

SATUAN = {"temp_surface": "°C", "humidity_surface": "%", "cloud_surface": "%",
          "pressure_surface": "hPa", "storm_potential": "J/kg",
          "rain_surface": "mm/jam", "rain_accum_surface": "mm/hari",
          "wind_surface": "m/s"}


# ------------------------------------------------------------------ jaringan

def _ambil(url: str, rentang: tuple[int, int] | None = None, timeout: int = 180,
           coba: int = 4) -> bytes:
    """Unduh, DENGAN PENGULANGAN. Satu run penuh itu sekitar 1.600 permintaan
    dan 3 GB, jadi satu kedipan jaringan hampir pasti terjadi di suatu tempat.
    Tanpa pengulangan, satu TimeoutError di langkah ke-19 membuang semua
    kerja sebelumnya. Sudah kejadian sekali waktu menguji.

    Jedanya naik 3, 6, 12 detik. Yang diulang cuma galat jaringan. 404 dan
    kawan kawan dilempar apa adanya, sebab mengulang berkas yang memang
    tidak ada cuma memperlambat."""
    req = urllib.request.Request(url)
    if rentang:
        req.add_header("Range", "bytes=%d-%d" % (rentang[0], rentang[0] + rentang[1] - 1))
    for k in range(coba):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                b = r.read()
            if rentang and len(b) != rentang[1]:
                raise OSError("potongan pendek, %d dari %d bita" % (len(b), rentang[1]))
            return b
        except urllib.error.HTTPError:
            raise
        except Exception as e:
            if k == coba - 1:
                raise
            jeda = 3 * 2 ** k
            print("      ulang %d/%d sesudah %d detik, %s"
                  % (k + 1, coba - 1, jeda, str(e)[:60]))
            time.sleep(jeda)
    raise OSError("tidak tercapai")


def _akar(run: dt.datetime) -> str:
    return "%s/%s/%02dz/ifs/0p1/oper" % (EMBER, run.strftime("%Y%m%d"), run.hour)


def _ada(run: dt.datetime) -> bool:
    try:
        urllib.request.urlopen(urllib.request.Request(_akar(run) + "/", method="HEAD"),
                               timeout=30)
        return True
    except Exception:
        return False


def run_terbaru(mundur_jam: int = 96, umur_minimal: int = 0) -> dt.datetime:
    """Run paling baru yang folder 0p1-nya BETUL BETUL ADA.

    Didaftar ke servernya, bukan ditebak dari jam dinding. Latensinya dua jam
    dan belum semua run membawa 0p1, jadi menebak berarti separuh unduhan jadi
    404. Jebakan yang sama pernah kena di Himawari.

    `umur_minimal` dipakai mencari run untuk verifikasi, yang sengaja harus
    sudah cukup tua supaya jam jam awalnya sudah lewat."""
    kini = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None, minute=0, second=0,
                                                    microsecond=0)
    kini -= dt.timedelta(hours=umur_minimal)
    kini = kini.replace(hour=kini.hour - kini.hour % 6)
    for k in range(mundur_jam // 6 + 1):
        w = kini - dt.timedelta(hours=6 * k)
        if _ada(w):
            return w
    raise RuntimeError("tidak ada run 0p1 dalam %d jam terakhir" % mundur_jam)


def indeks(run: dt.datetime, langkah: int) -> dict | None:
    """Tabel offset tiap parameter di satu langkah. Dibaca SEKALI per langkah."""
    url = "%s/%s0000-%dh-oper-fc-sfc.index" % (_akar(run), run.strftime("%Y%m%d%H"), langkah)
    try:
        baris = _ambil(url).decode().splitlines()
    except urllib.error.HTTPError:
        return None
    tabel: dict[str, tuple[int, int]] = {}
    for l in baris:
        if not l.strip():
            continue
        d = json.loads(l)
        tabel.setdefault(d["param"], (int(d["_offset"]), int(d["_length"])))
    return tabel


def petik(run: dt.datetime, langkah: int, tabel: dict, param: str,
          folder: Path) -> Path | None:
    """Unduh SATU pesan GRIB lewat offset di tabel indeks."""
    if param not in tabel:
        return None
    url = "%s/%s0000-%dh-oper-fc-sfc.grib2" % (_akar(run), run.strftime("%Y%m%d%H"), langkah)
    tujuan = folder / ("%s_%dh.grib2" % (param, langkah))
    tujuan.write_bytes(_ambil(url, tabel[param]))
    return tujuan


# -------------------------------------------------------------------- bacaan

def baca(grib: Path) -> tuple[np.ndarray, dict]:
    """Baca satu pesan lalu potong ke domain Atmosight.

    JEBAKAN ANTIMERIDIAN. cfgrib memulangkan bujur -180 sampai 179,9, jadi
    BUJUR 180 TIDAK ADA sebagai angka. Tepi timur domain kita tepat di 180,
    dan kolom itu tersimpan sebagai -180 di ujung lain berkas. Memotong 62
    sampai 180 apa adanya menghasilkan 1180 kolom, bukan 1181, dan kolom
    paling timur hilang TANPA GALAT. Jadi kolom -180 diambil terpisah lalu
    disambungkan di ujung kanan. Sesudah ini jumlah kolomnya cocok dengan
    GFS. Saudara dekat jebakan antimeridian di Oceansight."""
    ds = xr.open_dataset(grib, engine="cfgrib", backend_kwargs={"indexpath": ""})
    da = ds[list(ds.data_vars)[0]]
    lat = da.latitude.values
    turun = lat[0] > lat[-1]
    da = da.sel(latitude=slice(REGION["top_lat"] + 1e-3, REGION["bottom_lat"] - 1e-3)
                if turun else
                slice(REGION["bottom_lat"] - 1e-3, REGION["top_lat"] + 1e-3))
    if da.latitude.values[0] < da.latitude.values[-1]:
        da = da.isel(latitude=slice(None, None, -1))      # utara di baris atas

    barat = da.sel(longitude=slice(REGION["left_lon"] - 1e-3,
                                   REGION["right_lon"] - DERAJAT / 2.0))
    nilai = np.asarray(barat.values, dtype="float32")
    if abs(REGION["right_lon"] - 180.0) < 1e-6:
        tepi = da.sel(longitude=-180.0, method="nearest")
        nilai = np.concatenate([nilai, np.asarray(tepi.values, "float32")[:, None]], axis=1)
    # DIBULATKAN. Koordinat GRIB datang dengan derau pecahan, bujur 62 jadi
    # 61,99999999999466, dan angka itu masuk ke catalog.json apa adanya.
    kisi = dict(west=round(float(barat.longitude.values[0]), 4),
                east=round(float(REGION["right_lon"]), 4),
                north=round(float(da.latitude.values[0]), 4),
                south=round(float(da.latitude.values[-1]), 4),
                width=nilai.shape[1], height=nilai.shape[0])
    return nilai, kisi


def rh_dari(t_k: np.ndarray, td_k: np.ndarray) -> np.ndarray:
    """Kelembapan nisbi persen dari suhu dan titik embun, rumus Magnus.

    ECMWF TIDAK MENGIRIM RH permukaan, yang ada titik embun 2 meter. Ini bukan
    hampiran kasar, Magnus itu rumus baku dan `metar_verify._rh` memakai rumus
    yang sama untuk mengubah titik embun METAR jadi RH. Jadi model dan
    pengamatan dihitung dengan cara yang sama persis dan adunya adil."""
    a, b = 17.625, 243.04
    t, td = t_k - 273.15, td_k - 273.15
    rh = 100.0 * np.exp(a * td / (b + td) - a * t / (b + t))
    return np.clip(rh, 0.0, 100.0).astype("float32")


def _kasarkan(arr: np.ndarray, kisi: dict, derajat: float) -> tuple[np.ndarray, dict]:
    """Ambil tiap sel ke-n supaya kisinya jadi `derajat`. Dipakai partikel angin."""
    n = max(1, int(round(derajat / DERAJAT)))
    kecil = arr[::n, ::n]
    k = dict(kisi, width=kecil.shape[1], height=kecil.shape[0],
             east=round(kisi["west"] + (kecil.shape[1] - 1) * DERAJAT * n, 4),
             south=round(kisi["north"] - (kecil.shape[0] - 1) * DERAJAT * n, 4))
    return kecil, k


def _tepi(kisi: dict) -> list:
    """Kotak TEPI SEL, bukan pusat sel. Bedanya setengah sel.

    Leaflet menarik tepi gambar ke kotak yang diberikan, jadi kalau yang
    diberikan pusat sel seluruh medan tergeser setengah sel."""
    h = DERAJAT / 2.0
    return [round(kisi["west"] - h, 4), round(kisi["south"] - h, 4),
            round(kisi["east"] + h, 4), round(kisi["north"] + h, 4)]


# ------------------------------------------------------------------- akurasi

def akurasi_metar(kerja: Path) -> dict | None:
    """Adu ramalan lawan pengamatan METAR, bentuknya sama dengan akurasi GFS.

    YANG DIVERIFIKASI BUKAN RUN YANG DITAMPILKAN, dan itu disengaja. Run yang
    ditampilkan selalu yang terbaru, dan karena latensinya cuma dua jam, jam
    jam ramalannya hampir semuanya BELUM TERJADI. Yang bisa diadu paling cuma
    satu dua langkah, dan angka akurasi dari dua langkah itu derau.

    Jadi dipakai run yang umurnya sekitar 27 jam. Seluruh langkah 0 sampai 27
    jam sudah lewat, jadi ada sepuluh waktu yang betul betul bisa diadu. Batas
    27 jam juga bukan sembarang, `metar_verify` cuma mengambil pengamatan 30
    jam terakhir, jadi run yang lebih tua pasangannya mulai hilang.

    Gagal-lunak. Kalau METAR tidak terjangkau atau pasangannya kurang, pulang
    None dan lencana akurasi di situs menulis "segera"."""
    import metar_verify

    sekarang = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    # Dicari run PALING TUA yang masih punya 0p1 DAN masih di dalam jendela
    # pengamatan, sebab makin tua run-nya makin banyak jam ramalan yang sudah
    # terjadi dan bisa diadu. Bukan yang paling baru.
    #
    # JANGAN DIPATOK UMUR TERTENTU. Versi pertama memaksa run berumur 27 jam
    # dan hasilnya nol pasangan, sebab layanan 0p1 baru dibuka 20 Oktober
    # 2026 sehingga belum ada run setua itu yang punya 0p1. Sekarang yang
    # tersedia dipungut apa adanya, dan verifikasinya mengecil sendiri waktu
    # arsipnya masih pendek lalu melebar sendiri sesudah layanannya berumur.
    awal = sekarang - dt.timedelta(hours=JENDELA_METAR)
    awal = awal.replace(minute=0, second=0, microsecond=0)
    awal = awal.replace(hour=awal.hour - awal.hour % 6)
    calon = []
    w = awal
    while w <= sekarang:
        calon.append(w)
        w += dt.timedelta(hours=6)
    run = next((c for c in calon if _ada(c)), None)
    if run is None:
        print("  verifikasi dilewati, tidak ada run 0p1 di %d jam terakhir"
              % JENDELA_METAR)
        return None
    # Langkah yang sudah terjadi DAN masih punya pengamatan pasangannya.
    langkah = [s for s in LANGKAH
               if run + dt.timedelta(hours=s) <= sekarang
               and run + dt.timedelta(hours=s) >= awal]
    print("\n  verifikasi METAR, run %s %02dz, %d langkah yang sudah terjadi"
          % (run.strftime("%Y-%m-%d"), run.hour, len(langkah)))

    medan: dict[str, list] = {k: [] for k in ("t2m", "rh2m", "mslp", "u10", "v10")}
    waktu, kisi = [], None
    for s in langkah:
        tabel = indeks(run, s)
        if not tabel or not all(p in tabel for p in PARAM_VERIF):
            continue
        ambil = {}
        for p in PARAM_VERIF:
            g = petik(run, s, tabel, p, kerja)
            ambil[p], kisi = baca(g)
            g.unlink()
        medan["t2m"].append(ambil["2t"] - 273.15)
        medan["rh2m"].append(rh_dari(ambil["2t"], ambil["2d"]))
        medan["mslp"].append(ambil["msl"] / 100.0)
        medan["u10"].append(ambil["10u"])
        medan["v10"].append(ambil["10v"])
        waktu.append(run + dt.timedelta(hours=s))
    if not waktu:
        print("  verifikasi dilewati, tidak ada langkah yang terbaca")
        return None

    ak = metar_verify.verify(kisi, {k: np.stack(v) for k, v in medan.items()},
                             waktu, sekarang)
    if ak:
        ak["periode"] = "%d jam, run %s %02dZ" % (langkah[-1] - langkah[0],
                                                  run.strftime("%d %b"), run.hour)
        ak["catatan"] = ("Diadu dengan pengamatan METAR bandara Indonesia pada jam "
                         "jam awal ramalan yang sudah terjadi. Dihitung ulang "
                         "otomatis tiap kali pipeline jalan. Rata rata dari "
                         "parameter yang ada.")
        print("  akurasi METAR %.1f persen dari %d pasangan"
              % (ak["nilai"], ak["pasangan"]))
    else:
        print("  akurasi belum cukup, lencana akan menulis segera")
    return ak


# -------------------------------------------------------------------- profil

def indeks_pl(run: dt.datetime, langkah: int) -> dict | None:
    """Tabel offset level tekanan, kuncinya (param, level).

    BEDA DENGAN `indeks` yang kuncinya param saja. Di berkas permukaan satu
    param cuma punya satu pesan, di berkas level tekanan dia punya empat
    belas, satu per level, dan pesan pesannya TERSEBAR bukan berurutan. Jadi
    tidak bisa digabung jadi satu permintaan Range, harus satu per satu."""
    url = "%s/%s0000-%dh-oper-fc-pl.index" % (_akar(run), run.strftime("%Y%m%d%H"), langkah)
    try:
        baris = _ambil(url).decode().splitlines()
    except urllib.error.HTTPError:
        return None
    tabel: dict[tuple[str, int], tuple[int, int]] = {}
    for l in baris:
        if not l.strip():
            continue
        d = json.loads(l)
        tabel[(d["param"], int(d["levelist"]))] = (int(d["_offset"]), int(d["_length"]))
    return tabel


def profil_satu(run: dt.datetime, langkah: int, kerja: Path) -> tuple[dict, dict] | None:
    """Profil t, r, u, v di seluruh level untuk satu langkah.

    Pulang ({t,r,u,v} bentuk (nlev, ny, nx), grid), sudah dikasarkan ke ~1
    derajat dan berorientasi baris 0 di utara, sama dengan `fetch_profile`
    milik GFS. Satuan t dalam Celsius, r persen, u dan v m/detik."""
    tabel = indeks_pl(run, langkah)
    if tabel is None:
        return None
    url = "%s/%s0000-%dh-oper-fc-pl.grib2" % (_akar(run), run.strftime("%Y%m%d%H"), langkah)
    mau = [(v, l) for v in PROFIL_VAR for l in PROFIL_LEVEL]
    if any(k not in tabel for k in mau):
        return None

    # DIUNDUH BERBARENGAN, didekode berurutan. Yang memakan waktu di sini
    # BUKAN lebar pita tapi jumlah permintaan, 56 potongan per langkah yang
    # satu satu pulang pergi ke Eropa. Terukur 222 detik per langkah kalau
    # berurutan, yaitu 92 menit untuk satu run, padahal isinya cuma 101 MB.
    # Enam utas memotong itu tanpa membebani servernya.
    #
    # Yang dibuat berbarengan CUMA unduhannya. cfgrib dan eccodes di
    # belakangnya memakai keadaan global, jadi pendekodeannya tetap satu
    # per satu.
    with cf.ThreadPoolExecutor(max_workers=6) as kolam:
        isi = list(kolam.map(lambda k: _ambil(url, tabel[k]), mau))

    s = PROFIL_STRIDE
    arr: dict[str, list] = {v: [] for v in PROFIL_VAR}
    kisi = None
    for (var, lev), b in zip(mau, isi):
        g = kerja / ("pl_%s_%d_%dh.grib2" % (var, lev, langkah))
        g.write_bytes(b)
        nilai, kisi = baca(g)
        g.unlink()
        arr[var].append(nilai[::s, ::s])
    g = {"west": kisi["west"],
         "east": round(kisi["west"] + (len(range(0, kisi["width"], s)) - 1) * DERAJAT * s, 4),
         "north": kisi["north"],
         "south": round(kisi["north"] - (len(range(0, kisi["height"], s)) - 1) * DERAJAT * s, 4),
         "nx": len(range(0, kisi["width"], s)), "ny": len(range(0, kisi["height"], s))}
    keluar = {v: np.stack(arr[v]).astype("float32") for v in PROFIL_VAR}
    keluar["t"] = keluar["t"] - 273.15                      # K -> Celsius
    # RH DIJEPIT KE 0..100. ECMWF menghitung kelembapan nisbi terhadap ES di
    # level dingin, jadi nilainya sah sah saja melewati 100, dan terukur
    # sampai 130,2 persen dan turun sampai -0,9. Angka di atas 100 membuat
    # titik embun hitungan Skew-T jadi LEBIH TINGGI daripada suhunya, dan di
    # grafik kurva Td akan menyeberangi kurva T. Itu mustahil dibaca orang
    # sebagai apa pun selain kerusakan.
    keluar["r"] = np.clip(keluar["r"], 0.0, 100.0)
    return keluar, g


def bangun_profil(run: dt.datetime, langkah: list[int], kerja: Path,
                  out_dir: Path) -> int:
    """profile_cells.bin plus profile_meta.json, bentuknya sama dengan GFS.

    MAHAL, dan itu memang sifatnya. Pesan level tekanan tidak bisa dipotong
    menurut wilayah, jadi tiap level diunduh sedunia lalu dibuang sebagian
    besar. Satu langkah itu 101 MB untuk empat variabel kali empat belas
    level, 56 permintaan Range. Yang dipakai cuma domain kita.

    Keberadaan `profile_meta.json` yang MENYALAKAN tombol Skew-T di situs,
    jadi kalau bagian ini gagal, sisanya tetap terbit dan Skew-T-nya saja
    yang tidak muncul."""
    from profiles import write_profile_data

    waktu, per_waktu, kisi = [], [], None
    for s in langkah:
        hasil = profil_satu(run, s, kerja)
        if hasil is None:
            print("    profil %3dh tidak lengkap, dilewati" % s)
            continue
        arr, kisi = hasil
        per_waktu.append(arr)
        waktu.append((run + dt.timedelta(hours=s)).strftime("%Y-%m-%dT%H:00:00Z"))
        print("    profil %3dh  %d level, kisi %d x %d"
              % (s, len(PROFIL_LEVEL), kisi["nx"], kisi["ny"]))
    if not waktu:
        print("  profil gagal seluruhnya, Skew-T tidak akan muncul")
        return 0
    return write_profile_data(waktu, per_waktu, kisi, out_dir=out_dir,
                              levels=PROFIL_LEVEL)


# -------------------------------------------------------------------- utama

def tulis_point_cells(deret: dict, out_dir: Path) -> int:
    """point_cells.bin, susunan [y][x][var][waktu], plus kunci `cells` di meta.

    HARUS DITULIS SENDIRI. `write_point_data` milik process.py cuma
    menghasilkan `point_data.bin.gz` bersusun [waktu][y][x] plus metanya.
    Berkas per sel yang dipakai panel titik sekarang dibuat di sisi server
    cirrus, bukan di pipeline ini, jadi untuk ECMWF tidak ada yang membuatnya
    kalau tidak dibuat di sini.

    KENAPA PER SEL. Pada susunan lama satu titik tersebar di seluruh berkas,
    jadi satu satunya cara mengambilnya mengunduh semuanya. Diukur di GFS, 22
    MB untuk sesuatu yang isinya 400 bita. Dengan susunan ini satu titik duduk
    bersebelahan dan frontend cukup meminta satu potongan Range.

    TIDAK DI-GZIP, dan itu bukan kelalaian. Bita ke-n hasil mampat tidak
    berhubungan dengan bita ke-n isi aslinya, jadi Range di dalam aliran gzip
    tidak ada artinya.

    Urutan variabelnya mengikuti _POINT_ENC di process.py dan HARUS sama
    dengan urutan di `vars` metanya, sebab frontend membaca `cellOffset` dari
    situ."""
    from process import _NP_DTYPE, _POINT_ENC

    meta_p = out_dir / "point_meta.json"
    if not meta_p.exists():
        return 0
    meta = json.loads(meta_p.read_text())
    ny, nx, nt = meta["ny"], meta["nx"], len(meta["times"])

    per_sel, geser = [], 0
    for v in meta["vars"]:
        enc = _POINT_ENC[v["var"]]
        tumpuk = np.stack([np.nan_to_num(a) for a in deret[v["var"]]]).astype("float32")
        simpan = np.round((tumpuk - enc["offset"]) / enc["scale"]).astype(
            _NP_DTYPE[enc["dtype"]])
        # (t,ny,nx) -> (ny,nx,t), lalu dibaca sebagai bita mentah.
        sel = np.ascontiguousarray(simpan.transpose(1, 2, 0)).view(np.uint8).reshape(ny, nx, -1)
        per_sel.append(sel)
        v["cellOffset"] = geser
        v["cellLength"] = int(sel.shape[2])
        geser += int(sel.shape[2])
    gabung = np.concatenate(per_sel, axis=2)
    (out_dir / "point_cells.bin").write_bytes(gabung.tobytes(order="C"))
    meta["cells"] = {"file": "point_cells.bin", "order": "yxvt", "stride": geser,
                     "bytes": int(ny) * int(nx) * geser}
    meta_p.write_text(json.dumps(meta))
    return (out_dir / "point_cells.bin").stat().st_size


def _semai_riwayat(nama: str) -> Path:
    """Jalur riwayat ECMWF, DISALIN SEKALI dari punya GFS kalau belum ada.

    Kenapa disemai dan tidak dimulai dari nol. MJO butuh paling sedikit 121
    hari sebelum indeksnya bisa dihitung, jadi deret yang benar benar kosong
    berarti panel MJO mati sekitar empat bulan. Yang disalin itu deret
    ANALISIS harian, dan analisis GFS dan ECMWF untuk hari yang sama di kotak
    yang sama nyaris berimpit, jadi sambungannya satu hari saja dan tidak
    kelihatan pada deret 400 hari.

    Sesudah semaian pertama dua deret itu berjalan sendiri sendiri dan
    riwayat GFS TIDAK PERNAH DITULISI lagi dari sini."""
    punya_kita = STATE / ("%s_riwayat_ecmwf.json.gz" % nama)
    # YANG DIPERIKSA ISINYA, bukan sekadar ada berkasnya. Jalan pertama yang
    # gagal di tengah meninggalkan berkas riwayat KOSONG, dan penjaga yang
    # cuma melihat keberadaan berkas akan menganggapnya sudah tersemai lalu
    # melewatinya selamanya. Sudah kejadian waktu menguji, berkasnya 47 bita
    # berisi deret nol hari dan MJO tidak akan pernah hidup.
    kosong = True
    if punya_kita.exists():
        try:
            isi = json.loads(gzip.decompress(punya_kita.read_bytes()).decode("utf-8"))
            kosong = not isi.get("hari")
        except Exception:
            kosong = True
    if kosong:
        punya_gfs = STATE / ("%s_riwayat.json.gz" % nama)
        if punya_gfs.exists():
            punya_kita.parent.mkdir(parents=True, exist_ok=True)
            punya_kita.write_bytes(punya_gfs.read_bytes())
            print("  riwayat %s disemai dari GFS, %.0f KB"
                  % (nama, punya_kita.stat().st_size / 1024))
    return punya_kita


def produk_turunan(deret: dict, waktu: list, kisi: dict, run: dt.datetime,
                   out_dir: Path) -> None:
    """Panel titik, label kota, isobar, siklon, ITCZ, monsun, MJO, AUSMI.

    TIDAK ADA SATU PUN YANG DITULIS ULANG DI SINI. Enam modul pertama sudah
    ada di pipeline GFS dan semuanya menerima bentuk yang sama, `(series,
    times, grid)`, jadi cukup disusunkan deretnya lalu dipanggil apa adanya.
    MJO dan AUSMI tidak butuh deret sama sekali, dua duanya membaca
    `profile.bin.gz` dari folder keluaran yang sudah ditulis sebelum ini.

    DUA KOLOM HILANG dibanding GFS, `cin` dan `ltg`, sebab open data ECMWF
    memang tidak menyediakannya. `write_point_data` melewati variabel yang
    tidak ada tanpa galat, jadi panelnya tetap jalan dengan delapan kolom.

    TIAP BAGIAN DIBUNGKUS SENDIRI SENDIRI. Satu produk pelengkap yang gagal
    tidak boleh menjatuhkan kiriman yang sudah jadi, dan itu aturan yang
    sama dengan run.py di GFS."""
    from process import write_city_data, write_point_data
    from isobars import build_isobars
    from cyclones import detect_and_track
    from itcz import detect_itcz
    from monsoon import build_monsoon, build_monsoon_velocity
    import ausmi
    import mjo

    jam = run.strftime("%Y-%m-%dT%H:00:00Z")
    kini = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def coba(nama, kerja):
        try:
            kerja()
        except Exception as e:
            print("  ! %s dilewati, %s" % (nama, str(e)[:90]))

    def titik():
        sz = write_point_data(deret, waktu, kisi, out_dir)
        cz = write_city_data(deret, waktu, kisi, out_dir)
        tulis_point_cells(deret, out_dir)
        sel = out_dir / "point_cells.bin"
        print("  panel titik  : point_cells.bin %.0f MB, point_data.bin.gz %.0f MB, "
              "city_data.json %.0f KB"
              % ((sel.stat().st_size / 1048576) if sel.exists() else 0,
                 sz / 1048576, cz / 1024))
    coba("panel titik", titik)

    def isobar():
        iso = build_isobars(deret, waktu, kisi)
        iso["run_time"] = jam
        (out_dir / "isobars.json").write_text(json.dumps(iso))
        print("  isobar       : %d garis, %d waktu"
              % (sum(len(f.get("iso", [])) for f in iso["frames"]), len(iso["frames"])))
    coba("isobar", isobar)

    def siklon():
        cyc = detect_and_track(deret, waktu, kisi)
        cyc["run_time"], cyc["generated_at"] = jam, kini
        (out_dir / "cyclones.json").write_text(json.dumps(cyc))
        print("  siklon       : %d jalur" % len(cyc["tracks"]))
    coba("siklon", siklon)

    def zona():
        itz = detect_itcz(deret, waktu, kisi)
        itz["run_time"], itz["generated_at"] = jam, kini
        (out_dir / "itcz.json").write_text(json.dumps(itz))
        print("  ITCZ         : %d segmen, %d waktu"
              % (sum(len(f) for f in itz["frames"]), len(itz["frames"])))
    coba("ITCZ", zona)

    def monsun():
        mon = build_monsoon(deret, waktu, kisi)
        mon["run_time"] = jam
        (out_dir / "monsoon.json").write_text(json.dumps(mon))
        mv = build_monsoon_velocity(deret, kisi, run)
        if mv:
            (out_dir / "monsoon_velocity.json").write_text(
                json.dumps(mv, separators=(",", ":")))
        bv = build_monsoon_velocity(deret, kisi, run, lon_min=107.5, lon_max=117.5,
                                    lat_min=-2.5, lat_max=7.5, stride=2)
        if bv:
            (out_dir / "monsoon_velocity_bv.json").write_text(
                json.dumps(bv, separators=(",", ":")))
        f = (mon.get("phase") or {})
        print("  monsun       : %s (%s)" % (f.get("label", "-"), f.get("season", "-")))
    coba("monsun", monsun)

    # MJO satu satunya bagian yang menyentuh server pihak ketiga waktu jalan,
    # dia menarik OLR dari NOAA PSL. Kalau PSL mati, sisanya tetap terbit.
    def indeks_mjo():
        m = mjo.bangun(out_dir, run_time=jam,
                       riwayat_jalur=_semai_riwayat("mjo"),
                       label_angin="ECMWF")
        if m:
            (out_dir / "mjo.json").write_text(json.dumps(m, separators=(",", ":")))
            ix = m["indeks"]
            print("  MJO          : fase %s amplitudo %.2f" % (ix["fase"], ix["amplitudo"]))
    coba("MJO", indeks_mjo)

    def indeks_ausmi():
        a = ausmi.bangun(out_dir, run_time=jam,
                         riwayat_jalur=_semai_riwayat("ausmi"))
        if a:
            (out_dir / "ausmi.json").write_text(json.dumps(a, separators=(",", ":")))
            k = a["kini"]
            print("  AUSMI        : %+.2f m/s %s (anomali %+.2f)"
                  % (k["nilai"], k["arah"], k["anomali"]))
    coba("AUSMI", indeks_ausmi)


def jalan(out_dir: Path = OUTPUT, verifikasi: bool = True,
          profil: bool = True) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    kerja = out_dir / "_unduh"
    kerja.mkdir(exist_ok=True)

    run = run_terbaru()
    cap = "%s_%02d" % (run.strftime("%Y%m%d"), run.hour)
    print("run 0p1   : %s %02dz" % (run.strftime("%Y-%m-%d"), run.hour))
    print("langkah   : %d, 0 sampai %d jam tiap 3 jam\n" % (len(LANGKAH), LANGKAH[-1]))

    layer: dict[str, list] = {k: [] for k in (
        "temp_surface", "humidity_surface", "cloud_surface", "pressure_surface",
        "storm_potential", "rain_surface", "wind_surface")}
    harian: dict[str, np.ndarray] = {}
    hitung: dict[str, int] = {}
    # Deret untuk panel titik, label kota, isobar, siklon, ITCZ, dan monsun.
    # Nama kuncinya WAJIB sama dengan _POINT_ENC di process.py, kalau tidak
    # variabelnya dilewati diam diam tanpa galat.
    deret: dict[str, list] = {k: [] for k in
                              ("u", "v", "rain", "temp", "humidity", "cloud",
                               "pressure", "cape")}
    waktu_deret: list[str] = []
    kisi_titik = None
    kisi, unduh = None, 0

    for s in LANGKAH:
        tabel = indeks(run, s)
        if tabel is None:
            print("    %3dh indeks tidak ada, dilewati" % s)
            continue
        ambil = {}
        for p in PARAM:
            g = petik(run, s, tabel, p, kerja)
            if g is None:
                continue
            unduh += g.stat().st_size
            ambil[p], kisi = baca(g)
            g.unlink()
        if not all(p in ambil for p in PARAM):
            print("    %3dh parameternya tidak lengkap, dilewati" % s)
            continue

        berlaku = run + dt.timedelta(hours=s)
        vt = berlaku.strftime("%Y-%m-%dT%H:00:00Z")

        def skalar(kunci: str, nilai: np.ndarray) -> None:
            b = "%s_%s_f%03d" % (kunci, cap, s)
            _render_scalar_preview(nilai, _SCALAR_SCALES[kunci],
                                   out_dir / (b + "_preview.webp"), scale_up=PERBESAR)
            layer[kunci].append({
                "valid_time": vt, "forecast_step_hours": s,
                "preview_image": b + "_preview.webp",
                "value_max": round(float(np.nanmax(nilai)), 2),
            })

        skalar("temp_surface", ambil["2t"] - 273.15)
        skalar("humidity_surface", rh_dari(ambil["2t"], ambil["2d"]))
        skalar("cloud_surface", ambil["tcc"] * 100.0)
        skalar("pressure_surface", ambil["msl"] / 100.0)
        skalar("storm_potential", ambil["mucape"])
        hujan = ambil["tprate"] * 3600.0
        skalar("rain_surface", hujan)

        # Angin, tiga berkas seperti GFS. Partikelnya dikasarkan, heatmap
        # kecepatannya tidak.
        u, v = ambil["10u"], ambil["10v"]
        b = "wind_surface_%s_f%03d" % (cap, s)
        _encode_vector_png(u, v, UNSCALE, out_dir / (b + ".png"))
        _render_speed_preview(u, v, out_dir / (b + "_preview.webp"), scale=PERBESAR)
        uk, kk = _kasarkan(u, kisi, VELO_DERAJAT)
        vk, _ = _kasarkan(v, kisi, VELO_DERAJAT)
        _export_velocity_json(uk, vk, kk, run, s, out_dir / (b + "_velocity.json"))
        layer["wind_surface"].append({
            "valid_time": vt, "forecast_step_hours": s,
            "data_image": b + ".png", "preview_image": b + "_preview.webp",
            "velocity_json": b + "_velocity.json", "unscale": UNSCALE,
            "speed_knots_max": round(float(np.nanmax(np.hypot(u, v)) * MS_TO_KNOTS), 1),
        })

        # Akumulasi harian dikumpulkan sambil jalan, tiap langkah menyumbang
        # tiga jam. Harinya baru ditulis kalau GENAP delapan langkah, aturan
        # yang sama dengan run_rain_daily di GFS. Hari yang tidak penuh
        # dibuang daripada menampilkan 18 jam hujan berlabel satu hari.
        hari = berlaku.strftime("%Y-%m-%d")
        harian[hari] = harian.get(hari, 0.0) + hujan * 3.0
        hitung[hari] = hitung.get(hari, 0) + 1

        kecil = {}
        for nama, nilai in (("u", u), ("v", v), ("rain", hujan),
                            ("temp", ambil["2t"] - 273.15),
                            ("humidity", rh_dari(ambil["2t"], ambil["2d"])),
                            ("cloud", ambil["tcc"] * 100.0),
                            ("pressure", ambil["msl"] / 100.0),
                            ("cape", ambil["mucape"])):
            kecil[nama], kisi_titik = _kasarkan(nilai, kisi, TITIK_DERAJAT)
            deret[nama].append(kecil[nama])
        waktu_deret.append(vt)

        print("    %3dh  suhu %4.1f  hujan %5.1f  angin %4.1f kt  cape %4.0f"
              % (s, np.nanmax(ambil["2t"] - 273.15), np.nanmax(hujan),
                 np.nanmax(np.hypot(u, v)) * MS_TO_KNOTS, np.nanmax(ambil["mucape"])))

    if not layer["rain_surface"]:
        raise RuntimeError("tidak satu pun langkah berhasil")

    layer["rain_accum_surface"] = []
    for hari in sorted(harian):
        if hitung[hari] < 8:
            continue
        b = "rain_accum_surface_%s_%s" % (cap, hari.replace("-", ""))
        _render_scalar_preview(harian[hari], _SCALAR_SCALES["rain_accum_surface"],
                               out_dir / (b + "_preview.webp"), scale_up=PERBESAR)
        layer["rain_accum_surface"].append({
            "valid_time": hari + "T00:00:00Z", "period_hours": 24,
            "preview_image": b + "_preview.webp",
            "value_max": round(float(np.nanmax(harian[hari])), 2),
        })
        print("    harian %s  maks %.0f mm" % (hari, np.nanmax(harian[hari])))

    if profil:
        print()
        bangun_profil(run, LANGKAH, kerja, out_dir)

    # SESUDAH profil, bukan sebelum. MJO dan AUSMI membaca profile.bin.gz
    # dari folder keluaran, jadi urutannya mengikat.
    print("\nProduk turunan:")
    produk_turunan(deret, waktu_deret, kisi_titik, run, out_dir)

    akurasi = akurasi_metar(kerja) if verifikasi else None

    katalog = {
        "generated_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "model": "ECMWF",
        "model_label": LABEL,
        "run_time": run.strftime("%Y-%m-%dT%H:00:00Z"),
        "region": {
            "bounds": [kisi["west"], kisi["south"], kisi["east"], kisi["north"]],
            "image_bounds": _tepi(kisi),
        },
        "layers": {
            k: {"kind": "vector" if k == "wind_surface" else "scalar",
                "level": "surface", "units": SATUAN[k], "model": "ECMWF",
                "frames": v}
            for k, v in layer.items() if v
        },
    }
    if akurasi:
        katalog["akurasi"] = akurasi
    (out_dir / "catalog.json").write_text(json.dumps(katalog, indent=2))

    besar = sum(f.stat().st_size for f in out_dir.iterdir() if f.is_file())
    (out_dir / "ringkas.md").write_text("\n".join([
        "### ECMWF 9 km, %d layer" % len(katalog["layers"]), "",
        "| yang diukur | hasil |", "|---|---|",
        "| run | %s |" % katalog["run_time"],
        "| layer | %s |" % ", ".join(sorted(katalog["layers"])),
        "| bingkai | %d per layer, sampai %d jam |" % (len(layer["rain_surface"]),
                                                       LANGKAH[-1]),
        "| kisi | %d x %d sel, %.1f sampai %.1f BT, %.1f sampai %.1f LU |"
        % (kisi["width"], kisi["height"], kisi["west"], kisi["east"],
           kisi["south"], kisi["north"]),
        "| diunduh | %.0f MB GRIB |" % (unduh / 1048576),
        "| dihasilkan | %.0f MB |" % (besar / 1048576),
        "| akurasi METAR | %s |" % ("%.1f persen dari %d pasangan"
                                    % (akurasi["nilai"], akurasi["pasangan"])
                                    if akurasi else "belum cukup"),
        "", "CIN dan tiga layer anomali tidak ada di open data ECMWF, jadi "
            "tombolnya otomatis redup. Alasannya di docstring ecmwf.py.",
    ]) + "\n")
    try:
        kerja.rmdir()
    except OSError:
        pass

    print("\nkisi      : %d x %d, %.1f BT sampai %.1f BT, %.1f sampai %.1f LU"
          % (kisi["width"], kisi["height"], kisi["west"], kisi["east"],
             kisi["south"], kisi["north"]))
    print("layer     : %s" % ", ".join(sorted(katalog["layers"])))
    print("diunduh   : %.0f MB GRIB" % (unduh / 1048576))
    print("dihasilkan: %.0f MB" % (besar / 1048576))
    return katalog


if __name__ == "__main__":
    jalan()
