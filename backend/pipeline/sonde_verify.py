"""Verifikasi model lawan pengamatan RADIOSONDE.

Saudara `metar_verify.py`, dan sengaja sebentuk dengannya: toleransi per
parameter, persen "tepat", MAE, lalu rata rata datar. Bedanya tiga.

1. METAR mengukur PERMUKAAN. Sounding mengukur SELURUH KOLOM, sampai 11 hPa.
   Jadi di sini ada sumbu tambahan, yaitu level tekanan, dan hasilnya punya
   kunci `level` yang tidak dipunyai kartu METAR.

2. TEKANAN TIDAK DIVERIFIKASI, DAN TIDAK DIGANTI APA APA. Di METAR tekanan
   itu yang diukur. Di sounding tekanan itu SUMBUNYA, jadi memverifikasinya
   sama dengan membuktikan 500 sama dengan 500.

   Penggantinya yang lazim tinggi geopotensial, dan itu sempat dipasang di
   sini lalu DIBUANG lagi. Alasannya kedua pipeline kita cuma mengunduh t,
   r, u, dan v di level tekanan, lihat `profiles.py` fetch_profile dan
   `ecmwf.py` PROFIL_VAR. Tinggi geopotensial berarti menambah satu medan
   unduhan di dua pipeline demi satu parameter, dan itu memaksa. Keputusan
   pemilik 27 Oktober 2026: kalau tidak bisa, tidak usah dipaksa.

   Jadi yang diverifikasi EMPAT parameter, semuanya dari medan yang memang
   sudah diunduh untuk Skew-T. Nol unduhan tambahan.

3. LEAD-NYA TIDAK BOLEH NOL. Ini yang paling penting dan paling mudah salah.
   Sounding cuma ada di 00Z dan 12Z, dan run model juga. Kalau dicocokkan
   seperti metar_verify yang mengambil bingkai paling dekat yang sudah lewat,
   yang ketemu selalu f000, yaitu ANALISIS. Padahal analisis itu sudah
   menyerap sounding yang sama lewat asimilasi, jadi mengadu keduanya itu
   melingkar dan hasilnya pasti terlihat bagus tanpa sebab. Yang dipakai di
   sini lead sekitar 24 jam, lihat LEAD_TARGET.

Datanya dari University of Wyoming, keluaran CSV. Dia menampung pesan TEMP
yang dikirim BMKG lewat GTS, jadi yang punya datanya BMKG. Tidak ada CORS,
jadi ini memang harus dijalankan di sisi server, bukan di browser.
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import math
import urllib.error
import urllib.parse
import urllib.request

# Delapan stasiun yang betul betul meluncurkan. Diverifikasi 27 Oktober 2026
# dengan menarik riwayat setahun tiap stasiun, ketersediaan 94 sampai 99,7
# persen. Daftar kandidat yang lebih panjang (Padang, Pontianak, Manado,
# Ambon, Biak, Jayapura, Merauke) sudah dicoba dan KOSONG, jangan ditambahkan
# lagi tanpa mengeceknya ulang.
STASIUN = [
    {"kode": "96035", "nama": "Medan",     "lat":   3.56, "lon":  98.68},
    {"kode": "96509", "nama": "Tarakan",   "lat":   3.33, "lon": 117.56},
    {"kode": "96749", "nama": "Jakarta",   "lat":  -6.11, "lon": 106.65},
    {"kode": "96935", "nama": "Surabaya",  "lat":  -7.36, "lon": 112.76},
    {"kode": "97180", "nama": "Makassar",  "lat":  -5.06, "lon": 119.55},
    {"kode": "97230", "nama": "Denpasar",  "lat":  -8.75, "lon": 115.16},
    {"kode": "97372", "nama": "Kupang",    "lat": -10.16, "lon": 123.66},
    {"kode": "97502", "nama": "Sorong",    "lat":  -0.93, "lon": 131.11},
]

# 1000 hPa SENGAJA TIDAK IKUT. Di Jakarta dia duduk di 113 m, praktis
# permukaan, dan permukaan sudah diukur METAR dengan 21 stasiun tiap jam
# lawan 8 stasiun dua kali sehari di sini. Lebih buruk untuk keterangan yang
# sama. Lebih jahat lagi, kalau tekanan permukaan turun di bawah 1000 hPa
# level itu hilang atau diekstrapolasi ke bawah tanah tanpa galat apa pun.
# Kupang hari ini sudah di 1002 hPa, jadi dia selangkah dari lubang itu.
#
# KENAPA ENAM INI. Tekanan di sounding itu SUMBU PENCOCOK, bukan yang
# diverifikasi: dia yang memilih di ketinggian mana empat parameter lain
# diadu. Jadi yang boleh dipilih cuma level yang ADA DI SEMUA model.
#
#   GFS    22 level, 1000 sampai 50
#   ECMWF  14 level, 1000 sampai 10
#   iris   13 level: 1000 925 850 700 600 500 400 300 250 200 150 100 50
#
# Enam di bawah semuanya di dalam irisan itu, sebarannya dari bawah awan
# sampai ketinggian jelajah. Sisa irisannya (925, 600, 400, 150, 100, 50)
# bisa ditambahkan kapan saja, tapi level bersebelahan tidak saling bebas
# jadi menambahnya menambah angka tanpa menambah banyak keterangan.
#
# WRF belum punya profil sama sekali per 27 Oktober 2026. Enam level inilah
# yang harus dia terbitkan supaya bisa masuk tabel yang sama.
LEVEL_VERIF = [850, 700, 500, 300, 250, 200]

# Toleransi "dianggap tepat". Beda dari metar_verify di dua tempat.
# Angin 10 kt, bukan 5. Di permukaan angin 5 sampai 10 kt sehingga 5 kt masuk
# akal, tapi di 250 hPa anginnya 50 sampai 100 kt dan toleransi 5 kt membuat
# hampir semua ramalan dinyatakan salah padahal bagus.
# Tekanan TIDAK ADA penggantinya, alasannya di docstring nomor 2.
TOL = {
    "Suhu":       ("C",   2.0),
    "Kelembapan": ("%",  10.0),
    "Angin":      ("kt", 10.0),
    "Arah angin": ("der", 45.0),
}

# Arah angin tidak terdefinisi waktu anginnya tenang: pada 1 m/detik, arah 20
# dan 200 sama sama benar dan alatnya pun melaporkan apa saja. metar_verify
# memakai 3 knot, di sini 2,5 m/detik (sekitar 4,9 knot) sebab di udara atas
# angin selemah itu memang jarang dan pasangannya cuma menambah derau.
ANGIN_MIN = 2.5

# Lead yang diincar, jam. Lihat alasan nomor 3 di docstring.
LEAD_TARGET = 24
LEAD_TOLERANSI = 6     # terima 18 sampai 30 jam

MIN_PASANGAN = 40      # di bawah ini "segera", sama dengan metar_verify

_EMBER = "https://weather.uwyo.edu/wsgi/sounding"


def _beda_arah(a: float, b: float) -> float:
    """Selisih sudut melingkar. 350 lawan 10 itu 20, bukan 340."""
    d = abs(a - b) % 360
    return d if d <= 180 else 360 - d


def url_sounding(kode: str, waktu: dt.datetime) -> str:
    q = urllib.parse.urlencode({
        "datetime": waktu.strftime("%Y-%m-%d %H:00:00"),
        "id": kode, "src": "FM35", "type": "TEXT:CSV",
    })
    return f"{_EMBER}?{q}"


def ambil_csv(kode: str, waktu: dt.datetime, timeout: int = 45) -> str | None:
    """Teks CSV satu sounding, atau None kalau tidak ada. 404 dan balasan
    kosong BUKAN galat, stasiun yang tidak meluncurkan hari itu hal biasa."""
    try:
        with urllib.request.urlopen(url_sounding(kode, waktu), timeout=timeout) as r:
            teks = r.read().decode("utf-8", "replace")
    except (urllib.error.HTTPError, urllib.error.URLError, OSError):
        return None
    # Yang berisi data selalu dimulai baris header CSV. Kalau servernya
    # memulangkan halaman HTML "no data", panjangnya pendek dan tanpa koma.
    return teks if teks.lstrip().startswith("time,") else None


def urai_csv(teks: str) -> list[dict] | None:
    """CSV Wyoming -> daftar level, urut dari permukaan ke atas.

    Tiap level: {p, z, t, rh, ws, wd}. Baris yang salah satu kolom pokoknya
    kosong DIBUANG, sebab balon kadang kehilangan satu sensor di tengah
    jalan dan barisnya tetap ditulis dengan kolom kosong.

    `z` ikut diurai walau TIDAK diverifikasi. Dia datang dari baris yang sama
    sehingga gratis, dan tinggi yang wajib naik waktu tekanan turun itu satu
    satunya uji kerusakan berkas yang murah dan pasti. Lihat _uji()."""
    baris = []
    for row in csv.DictReader(io.StringIO(teks)):
        try:
            p = float(row["pressure_hPa"])
            z = float(row["geopotential height_m"])
            t = float(row["temperature_C"])
            td = float(row["dew point temperature_C"])
            rh = float(row["relative humidity_%"])
            wd = float(row["wind direction_degree"])
            ws = float(row["wind speed_m/s"])
        except (TypeError, ValueError, KeyError):
            continue
        # TITIK EMBUN DI ATAS SUHU ITU MUSTAHIL, dan di data Wyoming itu
        # betul betul muncul. Medan 27 Okt 00Z, 489 hPa: suhu -49,5 sedangkan
        # titik embun -31,5, dan RH-nya ditulis 652 persen. Sebabnya sensor
        # suhu melonjak sesaat (-40,1 lalu -41,1 lalu -49,5 lalu -42,3) dan
        # RH tetap dihitung dari angka lonjakan itu. Sebelas level dari 121
        # kena di satu berkas itu saja.
        #
        # Yang dibuang SELURUH levelnya, bukan cuma kolom kelembapannya,
        # sebab yang rusak justru suhunya dan itu ikut diverifikasi.
        # Interpolasi akan melompati lubangnya, dan itu jauh lebih baik
        # daripada memakai angka yang kita tahu salah.
        if td > t + 0.2 or not (0 <= rh <= 102):
            continue
        baris.append({"p": p, "z": z, "t": t, "rh": rh, "ws": ws, "wd": wd})
    if len(baris) < 5:
        return None
    baris.sort(key=lambda b: -b["p"])
    return baris


def pada_level(baris: list[dict], target: float) -> dict | None:
    """Nilai amatan pada satu level tekanan, hasil interpolasi.

    DALAM LOGARITMA TEKANAN, bukan tekanan lurus. Jarak antar level sounding
    tidak tetap, rapat di bawah dan renggang di atas, dan ketinggian itu
    kira kira lurus terhadap log tekanan. Interpolasi lurus terhadap tekanan
    membuat tinggi geopotensial meleset puluhan meter di lapisan atas,
    padahal toleransinya cuma 30 m.

    Arah angin diinterpolasi lewat komponen u dan v, BUKAN lewat derajatnya.
    Rata rata 350 dan 10 derajat itu 0, bukan 180."""
    atas = bawah = None
    for b in baris:
        if b["p"] >= target:
            bawah = b                      # tekanan lebih besar = lebih rendah
        elif atas is None:
            atas = b
            break
    if bawah is None or atas is None:
        return None                        # target di luar jangkauan balon
    lp, lb, la = math.log(target), math.log(bawah["p"]), math.log(atas["p"])
    if la == lb:
        return None
    f = (lp - lb) / (la - lb)
    lin = lambda k: bawah[k] + f * (atas[k] - bawah[k])
    ub = -bawah["ws"] * math.sin(math.radians(bawah["wd"]))
    vb = -bawah["ws"] * math.cos(math.radians(bawah["wd"]))
    ua = -atas["ws"] * math.sin(math.radians(atas["wd"]))
    va = -atas["ws"] * math.cos(math.radians(atas["wd"]))
    u, v = ub + f * (ua - ub), vb + f * (va - vb)
    return {
        "p": target, "z": lin("z"), "t": lin("t"), "rh": lin("rh"),
        "ws": math.hypot(u, v),
        "wd": (math.degrees(math.atan2(-u, -v)) + 360) % 360,
    }


def rangkum(galat: dict[str, list[float]], per_level: dict[str, dict[str, list[float]]],
            n_stasiun: int, hari: int) -> dict | None:
    """Daftar galat -> blok akurasi, bentuknya sama dengan config.AKURASI
    ditambah kunci `level`."""
    total = sum(len(v) for v in galat.values())
    if total < MIN_PASANGAN:
        return None

    def hitung(err: list[float], tol: float, sat: str) -> dict:
        return {"tepat": round(100 * sum(1 for e in err if e <= tol) / len(err), 1),
                "mae": round(sum(err) / len(err), 2), "sat": sat, "tol": tol}

    param = {k: hitung(galat[k], tol, sat) for k, (sat, tol) in TOL.items() if galat[k]}
    if not param:
        return None
    level = {}
    for lv, g in per_level.items():
        isi = {k: hitung(g[k], TOL[k][1], TOL[k][0]) for k in TOL if g.get(k)}
        if isi:
            level[lv] = {"nilai": round(sum(p["tepat"] for p in isi.values()) / len(isi), 1),
                         "parameter": isi}
    return {
        "nilai": round(sum(p["tepat"] for p in param.values()) / len(param), 1),
        "label": "",
        "sumber": f"Radiosonde {n_stasiun} stasiun",
        "periode": f"{hari} hari terakhir",
        "pasangan": total,
        "auto": True,
        "parameter": param,
        "level": level,
        "catatan": ("Diadu dengan pengamatan balon cuaca BMKG pada ramalan "
                    f"sekitar {LEAD_TARGET} jam, bukan pada analisis, sebab "
                    "analisis sudah memakai pengamatan yang sama. Rata-rata "
                    "dari parameter yang ada."),
    }


# ---------------------------------------------------------------- swauji
# Dijalankan tangan: python sonde_verify.py --uji
# Tidak menyentuh jaringan. Contohnya SENGAJA dipatok di sini, termasuk baris
# rusak dari Medan 27 Okt 00Z yang asli, supaya saringan itu tidak pernah
# diam diam dilepas orang lagi.
_CONTOH = """time,longitude,latitude,pressure_hPa,geopotential height_m,temperature_C,\
dew point temperature_C,ice point temperature_C,relative humidity_%,humidity wrt ice_%,\
mixing ratio_g/kg,wind direction_degree,wind speed_m/s
2026-10-26 23:30:00, 98.68, 3.56, 1009.0,   24, 25.0, 22.0, 22.0, 83, 83,17.0,200, 3.0
2026-10-26 23:30:00, 98.68, 3.56,  850.0, 1520, 18.0, 16.0, 16.0, 88, 88,13.5, 350, 5.0
2026-10-26 23:38:00, 98.68, 3.56,  700.0, 3160, 10.0,  5.0,  5.0, 72, 72, 8.0, 10, 7.0
2026-10-26 23:50:00, 98.68, 3.56,  547.0, 5074,-25.8,-18.3,-16.4,193,249,1.65,240, 4.1
2026-10-26 23:52:00, 98.68, 3.56,  500.0, 5740,-41.1,-28.9,-26.1,335,500,0.71,245, 4.1
2026-10-26 23:55:00, 98.68, 3.56,  489.0, 5892,-49.5,-31.5,-28.5,652,1056,0.56,255,4.6
2026-10-26 23:58:00, 98.68, 3.56,  450.0, 6400,-30.0,-35.0,-32.0, 65, 90,0.40,250, 8.0
2026-10-27 00:10:00, 98.68, 3.56,  300.0, 9700,-32.0,-45.0,-41.0, 30, 45,0.10,255, 9.0
2026-10-27 00:20:00, 98.68, 3.56,  200.0,12450,-54.0,-60.0,-56.0, 55, 95,0.05, 25, 7.0
2026-10-27 00:30:00, 98.68, 3.56,  100.0,16600,-78.0,-87.0,-83.0, 24, 50,0.00,175, 8.0
"""


def _uji() -> None:
    b = urai_csv(_CONTOH)
    assert b is not None and len(b) == 7, len(b or [])          # 3 baris rusak dibuang
    assert all(x["rh"] <= 102 for x in b), "RH mustahil lolos saringan"
    assert [x["p"] for x in b] == sorted((x["p"] for x in b), reverse=True), "urutan"
    assert [x["z"] for x in b] == sorted(x["z"] for x in b), "tinggi tidak monoton"

    tepat = pada_level(b, 850.0)
    asli = [x for x in b if x["p"] == 850.0][0]
    for k in ("z", "t", "rh"):
        assert abs(tepat[k] - asli[k]) < 1e-9, (k, tepat[k], asli[k])

    assert pada_level(b, 50.0) is None, "level di luar jangkauan balon harus None"

    assert _beda_arah(350, 10) == 20 and _beda_arah(10, 350) == 20
    assert _beda_arah(0, 180) == 180

    # Arah angin WAJIB diinterpolasi lewat u dan v. Antara 350 dan 10 derajat
    # jawabannya sekitar 0, bukan 180. Ini pernah salah di tempat lain.
    lintas = [{"p": 900, "z": 1000, "t": 10, "rh": 50, "ws": 10, "wd": 350},
              {"p": 800, "z": 2000, "t": 5, "rh": 50, "ws": 10, "wd": 10}]
    assert _beda_arah(pada_level(lintas, 849.0)["wd"], 0) < 2

    # Interpolasi tinggi WAJIB dalam log tekanan. Di tengah 900 dan 800 hPa,
    # titik tengah LOG ada di 848,5 hPa, bukan 850.
    tgh = pada_level(lintas, 848.528)
    assert abs(tgh["z"] - 1500) < 1.0, tgh["z"]

    _uji_riwayat()
    print("sonde_verify: swauji lolos")


def _uji_riwayat() -> None:
    """Uji simpanan lead 24 jam TANPA jaringan, ambil_csv diganti contoh."""
    import numpy as np
    import tempfile, json, pathlib

    levels = [850, 700, 500, 300, 250, 200]
    kisi = {"west": 95.0, "east": 140.0, "north": 8.0, "south": -11.0,
            "nx": 46, "ny": 20}
    # medan datar: tiap level satu nilai, jadi hasil sampling bisa ditebak
    bikin = lambda v: np.full((len(levels), kisi["ny"], kisi["nx"]), v, dtype="float32")
    arr = {"t": bikin(18.0), "r": bikin(88.0), "u": bikin(3.0), "v": bikin(-4.0)}
    run = dt.datetime(2026, 10, 26, 0, tzinfo=dt.timezone.utc)
    waktu = ["2026-10-26T00:00:00Z",   # lead  0, harus DILEWATI
             "2026-10-26T12:00:00Z",   # lead 12, di luar jendela
             "2026-10-27T00:00:00Z",   # lead 24, INI yang dicatat
             "2026-10-27T06:00:00Z"]   # bukan jam sounding
    per = [arr] * len(waktu)

    riwayat = {}
    n = simpan_ramalan(riwayat, per, waktu, kisi, levels, run)
    assert n == 1, n
    e = riwayat["ramalan"]["2026-10-27T00:00:00Z"]
    assert e["lead"] == 24 and len(e["titik"]) == len(STASIUN)
    # u=3 v=-4 berarti laju 5 m/detik = 9,72 knot. Arahnya 323,1 derajat,
    # BUKAN 143,1. Arah angin itu ASAL, bukan tujuan: udaranya bergerak ke
    # tenggara (143), jadi dilaporkan datang dari barat laut (323). Rumusnya
    # sama persis dengan metar_verify.py:142, jangan "diperbaiki".
    t, r, ws, wd = e["titik"]["96749"]["850"]
    assert abs(t - 18) < 1e-6 and abs(r - 88) < 1e-6
    assert abs(ws - 5 * KT) < 0.02, ws
    assert abs(wd - 323.1) < 0.2, wd

    # pasangkan, dengan ambil_csv palsu
    asli = globals()["ambil_csv"]
    globals()["ambil_csv"] = lambda kode, waktu, timeout=45: _CONTOH
    try:
        kini = dt.datetime(2026, 10, 27, 6, tzinfo=dt.timezone.utc)
        baru = pasangkan(riwayat, kini)
    finally:
        globals()["ambil_csv"] = asli
    assert baru > 0, "tidak ada pasangan terbentuk"
    assert not riwayat["ramalan"], "bingkai harus dihapus sesudah ditarik"
    assert len(riwayat["galat"]) == baru
    g0 = riwayat["galat"][0]
    assert {"vt", "lead", "kode", "lv", "Suhu", "Kelembapan", "Angin"} <= set(g0)

    # BELUM waktunya: bingkai yang valid_time-nya masih di depan jangan ditarik
    r2 = {}
    simpan_ramalan(r2, per, waktu, kisi, levels, run)
    globals()["ambil_csv"] = lambda *a, **k: (_ for _ in ()).throw(AssertionError("ditarik terlalu dini"))
    try:
        assert pasangkan(r2, dt.datetime(2026, 10, 26, 23, tzinfo=dt.timezone.utc)) == 0
    finally:
        globals()["ambil_csv"] = asli
    assert "2026-10-27T00:00:00Z" in r2["ramalan"], "bingkai belum waktunya jangan dibuang"

    # galat di luar jendela 7 hari WAJIB terbuang
    r3 = {"ramalan": {}, "galat": [{"vt": "2026-10-01T00:00:00Z", "lead": 24,
                                    "kode": "96749", "lv": "850", "Suhu": 1.0}]}
    pasangkan(r3, dt.datetime(2026, 10, 27, 6, tzinfo=dt.timezone.utc))
    assert r3["galat"] == [], "galat basi tidak terbuang"



# ------------------------------------------------------- simpanan lead 24 jam
#
# KENAPA PERLU SIMPANAN. Ramalan hari ini baru bisa diadu BESOK. Kalau
# dicocokkan seperti metar_verify yang mengambil bingkai terdekat yang sudah
# lewat, yang ketemu selalu f000 sebab sounding dan run sama sama di 00Z dan
# 12Z. Itu analisis, dan analisis sudah menyerap sounding yang sama.
#
# Jadi tiap run menyimpan nilai modelnya untuk bingkai yang jatuh di jam
# sounding dengan lead sekitar 24 jam, lalu run berikutnya yang mengadunya
# begitu balonnya sudah naik. Polanya meniru riwayat semaian AUSMI.
#
# Berkasnya duduk di folder keluaran, jadi dia ikut tersinggah antar-run
# GitAction DAN ikut terbit. Kecil: satu bingkai 8 stasiun 6 level cuma
# sekitar 2 kB, dan galat tujuh hari sekitar 40 kB.
NAMA_RIWAYAT = "sonde_riwayat.json"
JENDELA_HARI = 7
KT = 1.943844          # m/detik -> knot
MAKS_COBA = 4          # sesudah ini bingkai yang tak pernah dapat sounding dibuang
MAKS_PER_RUN = 3       # batas bingkai yang ditarik sekali jalan, jangan menggedor


def _jam(s: str) -> dt.datetime:
    return dt.datetime.strptime(s, "%Y-%m-%dT%H:00:00Z").replace(tzinfo=dt.timezone.utc)


def simpan_ramalan(riwayat: dict, per_waktu: list[dict], waktu: list[str],
                   kisi: dict, levels: list[int], run: dt.datetime) -> int:
    """Catat nilai model di tiap stasiun untuk bingkai yang jatuh TEPAT di jam
    sounding (00Z atau 12Z) dengan lead 18 sampai 30 jam. Kembalikan jumlah
    bingkai yang dicatat, biasanya 1 atau 2."""
    from metar_verify import _sampler
    samp = _sampler({**kisi, "width": kisi["nx"], "height": kisi["ny"]})
    idx = {lv: i for i, lv in enumerate(levels)}
    n = 0
    for i, w in enumerate(waktu):
        vt = _jam(w)
        if vt.hour not in (0, 12):
            continue
        lead = (vt - run).total_seconds() / 3600
        if not (LEAD_TARGET - LEAD_TOLERANSI <= lead <= LEAD_TARGET + LEAD_TOLERANSI):
            continue
        arr, isi = per_waktu[i], {}
        for st in STASIUN:
            per_lv = {}
            for lv in LEVEL_VERIF:
                k = idx.get(lv)
                if k is None:
                    continue
                t = samp(arr["t"][k], st["lat"], st["lon"])
                r = samp(arr["r"][k], st["lat"], st["lon"])
                u = samp(arr["u"][k], st["lat"], st["lon"])
                v = samp(arr["v"][k], st["lat"], st["lon"])
                if None in (t, r, u, v):
                    continue
                per_lv[str(lv)] = [round(t, 2), round(r, 1),
                                   round(math.hypot(u, v) * KT, 2),
                                   round((math.degrees(math.atan2(-u, -v)) + 360) % 360, 1)]
            if per_lv:
                isi[st["kode"]] = per_lv
        if isi:
            riwayat.setdefault("ramalan", {})[w] = {
                "run": run.strftime("%Y-%m-%dT%H:00:00Z"),
                "lead": round(lead), "coba": 0, "titik": isi,
            }
            n += 1
    return n


def pasangkan(riwayat: dict, now: dt.datetime) -> int:
    """Tarik sounding untuk bingkai yang waktunya sudah lewat, hitung galat,
    simpan ke riwayat["galat"]. Kembalikan jumlah pasangan baru.

    Bingkai yang sudah ditarik DIHAPUS dari `ramalan`, jadi tiap bingkai cuma
    sekali menelan jaringan. Yang tak pernah dapat sounding dibuang sesudah
    MAKS_COBA, supaya tidak jadi beban abadi."""
    ramalan = riwayat.setdefault("ramalan", {})
    galat = riwayat.setdefault("galat", [])
    baru = 0
    # Latensi Wyoming sekitar 3 jam. Ditunggu 4 supaya tidak menarik sia sia.
    siap = sorted(w for w in ramalan if _jam(w) <= now - dt.timedelta(hours=4))
    for w in siap[:MAKS_PER_RUN]:
        entri = ramalan[w]
        vt = _jam(w)
        dapat = 0
        for st in STASIUN:
            ramal = entri["titik"].get(st["kode"])
            if not ramal:
                continue
            teks = ambil_csv(st["kode"], vt)
            if teks is None:
                continue
            baris = urai_csv(teks)
            if baris is None:
                continue
            dapat += 1
            for lv_s, (mt, mr, mws, mwd) in ramal.items():
                obs = pada_level(baris, float(lv_s))
                if obs is None:
                    continue
                g = {"vt": w, "lead": entri["lead"], "kode": st["kode"], "lv": lv_s,
                     "Suhu": abs(mt - obs["t"]),
                     "Kelembapan": abs(mr - obs["rh"]),
                     "Angin": abs(mws - obs["ws"] * KT)}
                # Arah angin cuma dihitung kalau anginnya memang berarah.
                if obs["ws"] >= ANGIN_MIN:
                    g["Arah angin"] = _beda_arah(mwd, obs["wd"])
                galat.append(g)
                baru += 1
        if dapat:
            del ramalan[w]
        else:
            entri["coba"] += 1
            if entri["coba"] >= MAKS_COBA:
                del ramalan[w]
    # buang galat yang lewat jendela
    batas = (now - dt.timedelta(days=JENDELA_HARI)).strftime("%Y-%m-%dT%H:00:00Z")
    riwayat["galat"] = [g for g in galat if g["vt"] >= batas]
    return baru


def jalankan(out_dir, per_waktu: list[dict], waktu: list[str], kisi: dict,
             levels: list[int], run: dt.datetime,
             now: dt.datetime | None = None) -> dict | None:
    """Satu panggilan untuk pipeline: muat riwayat, catat ramalan run ini,
    adu yang sudah waktunya, tulis riwayat, kembalikan blok akurasi."""
    import json
    from pathlib import Path
    now = now or dt.datetime.now(dt.timezone.utc)
    jalur = Path(out_dir) / NAMA_RIWAYAT
    try:
        riwayat = json.loads(jalur.read_text())
    except Exception:
        riwayat = {}

    n = simpan_ramalan(riwayat, per_waktu, waktu, kisi, levels, run)
    try:
        baru = pasangkan(riwayat, now)
    except Exception as e:
        print("  ! sounding tak terjangkau:", str(e)[:90])
        baru = 0
    jalur.write_text(json.dumps(riwayat, separators=(",", ":")))

    g = riwayat.get("galat", [])
    print(f"  sonde: {n} bingkai dicatat, {baru} pasangan baru, "
          f"{len(g)} galat dalam {JENDELA_HARI} hari")
    if not g:
        return None
    semua = {k: [x[k] for x in g if k in x] for k in TOL}
    per_lv: dict[str, dict] = {}
    for x in g:
        d = per_lv.setdefault(x["lv"], {k: [] for k in TOL})
        for k in TOL:
            if k in x:
                d[k].append(x[k])
    kode = {x["kode"] for x in g}
    return rangkum(semua, per_lv, len(kode), JENDELA_HARI)

if __name__ == "__main__":
    import sys
    if "--uji" in sys.argv:
        _uji()
    else:
        print(__doc__)
