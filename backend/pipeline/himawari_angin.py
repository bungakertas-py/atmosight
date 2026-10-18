# -*- coding: utf-8 -*-
"""Angin gerak awan Himawari-9, produk L2 Winds NOAA.

   Ini angin yang DIUKUR dari perpindahan awan antar citra, bukan angin
   hasil hitungan model. Untuk Atmosight dia pasangan yang pas buat layer
   angin GFS, sebab orang bisa membandingkan angin ramalan dengan angin
   yang sungguh sungguh terjadi.

   Datanya TITIK BERSERAK, bukan kisi. Jadi dia tidak bisa menumpang
   penggambar partikel yang dipakai layer angin GFS, dan digambar jadi
   anak panah langsung ke gambarnya di sini.

   Berkasnya NetCDF-4, yaitu HDF5, jadi bagian ini perlu h5py. Pembaca
   sendiri tidak mungkin, HDF5 itu format berpohon dengan penyaringan dan
   penyimpanan berpetak, bukan blok berurut seperti HSD."""
from __future__ import annotations

import datetime as dt
import math
import re
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from . import himawari as H

LAYER = "amv_angin"
KANAL = "C14CT"          # inframerah 11,2 um, jalan siang dan malam
QI_MIN = 60.0            # penunjuk mutu NOAA, 60 itu ambang lazim
PETAK = 1.2              # satu panah tiap petak sebesar ini, derajat
PIKSEL_PER_DERAJAT = 1.0 / H.DERAJAT

# Tiga lapis tekanan, tiga warna palet. Tinggi lime, tengah toska, rendah
# biru. Sengaja bukan gradasi mulus, sebab yang penting dibedakan itu
# LAPISANNYA, bukan angka tekanannya.
LAPIS = [
    (0, 400, (0xC5, 0xFF, 0x95), "tinggi"),
    (400, 700, (0x5D, 0xEB, 0xD7), "tengah"),
    (700, 1100, (0x4F, 0xA8, 0xD8), "rendah"),
]


def cari_berkas(waktu: dt.datetime) -> str | None:
    """Nama berkas AMV tidak bisa ditebak, ada cap waktu olahnya di ekor."""
    pre = "AHI-L2-FLDK-Winds/%s/" % waktu.strftime("%Y/%m/%d/%H%M")
    url = "%s/?list-type=2&prefix=%s" % (H.EMBER, pre)
    try:
        with urllib.request.urlopen(url, timeout=90) as r:
            xml = r.read().decode("utf-8", "replace")
    except Exception as e:
        print("    daftar AMV gagal,", e)
        return None
    for k in re.findall(r"<Key>([^<]+)</Key>", xml):
        if "-%s_" % KANAL in k:
            return k
    return None


def unduh(waktu: dt.datetime, folder: Path) -> Path | None:
    kunci = cari_berkas(waktu)
    if not kunci:
        return None
    folder.mkdir(parents=True, exist_ok=True)
    tujuan = folder / kunci.split("/")[-1]
    if tujuan.exists() and tujuan.stat().st_size > 1000:
        return tujuan
    try:
        with urllib.request.urlopen("%s/%s" % (H.EMBER, kunci), timeout=600) as r:
            tujuan.write_bytes(r.read())
    except Exception as e:
        print("    unduh AMV gagal,", e)
        return None
    return tujuan


def baca(jalur: Path):
    """Memulangkan lintang, bujur, laju, arah, tekanan yang sudah disaring."""
    import h5py
    with h5py.File(str(jalur), "r") as f:
        amb = lambda k: np.asarray(f[k][:], float)
        lat, lon = amb("Latitude"), amb("Longitude")
        spd, arah = amb("Wind_Speed"), amb("Wind_Dir")
        pres, qi, flag = amb("MedianPress"), amb("QI"), amb("Flag")
    # -999 itu nilai pengisi, bukan angka. Harus dibuang DULU, kalau tidak
    # dia ikut terhitung dan panahnya menunjuk ke arah yang tidak ada.
    sah = (np.isfinite(spd) & (spd > 0) & (spd < 200)
           & (arah >= 0) & (arah <= 360) & (pres > 0)
           & (qi >= QI_MIN) & (flag == 0)
           & (lon >= H.LON0) & (lon <= H.LON1)
           & (lat >= H.LAT0) & (lat <= H.LAT1))
    return lat[sah], lon[sah], spd[sah], arah[sah], pres[sah], qi[sah]


def jarangkan(lat, lon, spd, arah, pres, qi):
    """Satu panah per petak, yang dipilih bermutu paling tinggi.

    Lima belas ribu panah di satu gambar itu bubur. Dijarangkan per petak,
    bukan diambil acak, supaya sebarannya rata dan tidak menggerombol di
    daerah yang awannya banyak."""
    kunci = (((lat - H.LAT0) / PETAK).astype(int) * 100000
             + ((lon - H.LON0) / PETAK).astype(int))
    terbaik: dict[int, int] = {}
    for i, k in enumerate(kunci):
        j = terbaik.get(k)
        if j is None or qi[i] > qi[j]:
            terbaik[k] = i
    pilih = np.fromiter(terbaik.values(), int)
    return lat[pilih], lon[pilih], spd[pilih], arah[pilih], pres[pilih]


def gambar(lat, lon, spd, arah, pres, tujuan: Path) -> int:
    lebar = int(round((H.LON1 - H.LON0) / H.DERAJAT)) + 1
    tinggi = int(round((H.LAT1 - H.LAT0) / H.DERAJAT)) + 1
    img = Image.new("RGBA", (lebar, tinggi), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for la, lo, sp, ar, pr in zip(lat, lon, spd, arah, pres):
        warna = next((w for a, b, w, _ in LAPIS if a <= pr < b), None)
        if warna is None:
            continue
        x = (lo - H.LON0) * PIKSEL_PER_DERAJAT
        y = (H.LAT1 - la) * PIKSEL_PER_DERAJAT
        # Arah angin itu ARAH DATANGNYA, jadi ekornya yang di hulu dan
        # kepalanya menunjuk ke hilir. Dibalik 180 derajat.
        th = math.radians(ar + 180.0)
        panjang = 6.0 + min(sp, 60.0) * 0.42
        dx, dy = math.sin(th) * panjang, -math.cos(th) * panjang
        x2, y2 = x + dx, y + dy
        d.line([(x, y), (x2, y2)], fill=warna + (230,), width=2)
        # mata panah
        for sisi in (0.42, -0.42):
            d.line([(x2, y2),
                    (x2 - math.sin(th + sisi) * 4.5, y2 + math.cos(th + sisi) * 4.5)],
                   fill=warna + (230,), width=2)
    img.save(tujuan, "WEBP", quality=88, method=4, alpha_quality=100)
    return len(lat)
