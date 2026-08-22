"""Konfigurasi model kedua: WRF Citarum (ITB).

Sumbernya server terbuka http://167.205.106.70/aws/citarum/ . Datanya ARSIP
2018-2020, bukan realtime, jadi jendela waktunya digulirkan sendiri di sini
meniru cara GFS bergulir (1 hari ke belakang + 3 hari ke depan).

Catatan penting soal server itu ada di memory `wrf-citarum-itb-server`.
Ringkasnya, tiga hal yang gampang menjebak.
1. Bulan dan tanggal pakai nol di depan, JAM TIDAK. `/2018/10/12/9/1.tif`.
2. Jam di path itu WIB, bukan UTC.
3. Folder ada untuk semua tanggal tapi isinya sering salinan hari yang sama.
   Karena itu tanggal yang boleh dipakai DIDAFTAR di RENTANG_DATA, hasil
   pemeriksaan hash satu per satu, bukan ditebak.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BACKEND_DIR / "data" / "output" / "wrf"
RAW_DIR = BACKEND_DIR / "data" / "raw" / "wrf"

BASE_URL = "http://167.205.106.70/aws/citarum"

# Zona waktu jam di path.
TZ_JAM = 7  # WIB

# ---------------------------------------------------------------- grid
# Angka diambil dari header velocity JSON (pusat sel) dan tiepoint GeoTIFF
# (tepi sel). Keduanya sudah diadu dan konsisten.
NX, NY = 153, 54
GRID = {
    "width": NX, "height": NY,
    "west": 105.102, "east": 114.752,
    "north": -5.55103, "south": -8.88899231,
}
# Tepi sel, untuk menempatkan gambar overlay (bukan pusat sel).
IMAGE_BOUNDS = [105.0697945, -8.920360565, 114.78421, -5.519435885]

# Bingkai dikunci ke domain WRF sendiri. Sama mekanismenya dengan GFS, yaitu
# minZoom dipatok pada tampilan awal dan pan dibatasi kotak ini, jadi daerah
# di luar domain tak pernah kelihatan dan peta tak bisa ditarik keluar.
# Sengaja memakai tepi sel, bukan pusat sel, supaya tak ada celah di pinggir.
FRAME_BOUNDS = list(IMAGE_BOUNDS)

# Kotak inti tampilan awal, meniru VIEW_CORE punya GFS. Frontend melebarkan
# sumbu yang perlu sampai rasionya sama dengan layar, lalu MENJEPITnya ke
# FRAME_BOUNDS supaya daerah di luar domain tak pernah kelihatan.
#
# LEBAR dan TINGGI persis yang disetujui user (5,2 x 2,7 derajat), cuma
# PUSATNYA digeser 1,05 derajat ke barat. Alasannya, ke-13 pos hujan berkumpul
# di 107,04 sampai 107,97 BT, dan panel Parameter di kiri layar menutupi kira
# kira 0,85 derajat pertama. Dengan tepi kiri di 107,2 seluruh jaringan pos
# hilang di balik panel, padahal pos itu yang jadi dasar angka akurasi.
# Menggeser pusat TIDAK mengubah tingkat zoom, jadi permintaan zoom tetap utuh.
VIEW_CORE = [106.15, -8.55, 111.35, -5.85]

# ---------------------------------------------------------------- parameter
# folder di server -> (kunci layer frontend, satuan, kind)
PARAMS = {
    "Temperatur":      ("temp_surface",     "°C",    "scalar"),
    "CH":              ("rain_surface",     "mm/jam", "scalar"),
    "Kelembaban":      ("humidity_surface", "%",     "scalar"),
    "Tekanan":         ("pressure_surface", "hPa",   "scalar"),
    "Kecepatan_Angin": ("wind_surface",     "m/s",   "vector"),
}
# Layer turunan, dihitung bukan diunduh.
LAYER_AKUMULASI = "rain_accum_surface"   # jumlah CH per tanggal WIB

# Arah angin. Formatnya sudah leaflet-velocity (u dan v), gridnya SAMA PERSIS
# dengan GeoTIFF, dan |u,v| terbukti identik dengan Kecepatan_Angin.
FOLDER_ANGIN = "Arah_Angin"
# Berkas arah angin yang isinya NaN semua ukurannya SELALU tepat segini.
# Jadi bisa disaring lewat HEAD tanpa mengunduh isinya.
UKURAN_ANGIN_NAN = 168233

# ---------------------------------------------------------------- jendela
# Rentang tanggal yang datanya BENAR BENAR baru, hasil adu hash 766 tanggal.
# Di luar ini isinya salinan satu hari beku (15 Jun 2019 sampai 10 Nov 2020).
# Cuma rentang yang panjangnya >= HARI_JENDELA yang didaftar.
RENTANG_DATA = [
    ("2018-10-10", "2018-10-14"),   # 5 hari
    ("2018-10-30", "2018-11-05"),   # 7 hari
    ("2018-11-13", "2018-11-30"),   # 18 hari
    ("2018-12-11", "2018-12-28"),   # 18 hari
    ("2018-12-30", "2019-01-15"),   # 17 hari
    ("2019-01-17", "2019-01-25"),   # 9 hari
    ("2019-02-05", "2019-02-09"),   # 5 hari
    ("2019-02-15", "2019-02-20"),   # 6 hari
    ("2019-03-26", "2019-03-29"),   # 6 hari
    ("2019-04-25", "2019-06-14"),   # 51 hari
]

HARI_JENDELA = 4          # 1 hari lampau + 3 hari "ke depan", meniru -24j..+72j GFS
HARI_LAMPAU = 1           # hari pertama jendela dianggap masa lalu

# Hari nyata saat jendela pertama dipakai. Tiap hari nyata berlalu, jendela
# maju satu langkah. Dipakai supaya cron 04.00 WIB menghasilkan jendela yang
# berbeda tiap hari, persis seperti GFS yang selalu membawa run baru.
JANGKAR = dt.date(2026, 8, 22)


def _hari(a: str, b: str) -> list[dt.date]:
    d0, d1 = dt.date.fromisoformat(a), dt.date.fromisoformat(b)
    return [d0 + dt.timedelta(days=i) for i in range((d1 - d0).days + 1)]


def semua_jendela() -> list[list[dt.date]]:
    """Semua jendela 4 hari BERURUTAN yang mungkin, tak pernah melompati lubang."""
    out: list[list[dt.date]] = []
    for a, b in RENTANG_DATA:
        hh = _hari(a, b)
        for i in range(len(hh) - HARI_JENDELA + 1):
            out.append(hh[i:i + HARI_JENDELA])
    return out


def jendela_untuk(hari_nyata: dt.date | None = None) -> list[dt.date]:
    """Jendela yang dipakai untuk tanggal nyata tertentu. Bergulir satu langkah
    per hari, lalu memutar balik ke awal kalau daftarnya habis (110 langkah)."""
    hari_nyata = hari_nyata or dt.date.today()
    jj = semua_jendela()
    i = (hari_nyata - JANGKAR).days % len(jj)
    return jj[i]


def url_berkas(param: str, hari: dt.date, jam: int, nama: str) -> str:
    """JAM TANPA NOL DI DEPAN. Kalau dipadding jadi 404."""
    return f"{BASE_URL}/{param}/{hari:%Y/%m/%d}/{jam}/{nama}"


# ---------------------------------------------------------------- akurasi
# Dihitung SEKALI di scratchpad/wrf_test/sapu_ambang.py, lalu dipatok di sini.
# Sengaja statis, tidak ikut jendela yang sedang tampil, supaya angkanya stabil
# dan pipeline harian tak perlu mengunduh data pengamatan sama sekali.
#
# Pembandingnya 13 pos hujan di DAS Citarum. Periode verifikasi 52 hari, yaitu
# semua hari model yang datanya asli DAN ada pengamatannya. Pengamatan yang
# utuh cuma raingauge Oktober sampai Desember 2018 plus aws November 2020,
# bulan lain berkasnya kosong atau terpotong di server.
#
# SUHU TIDAK DIPAKAI. Sensor pos jelas tak berpelindung radiasi, tengah hari
# tembus 46 sampai 52 derajat. Itu bukan suhu udara, jadi mengadu WRF dengannya
# cuma mengukur cacat sensor.
#
# Angka di bawah skala HARIAN, hujan atau tidak dengan ambang 1 mm. Di skala
# per jam model ini KALAH dari tebakan sepele "selalu kering" (74,0 lawan
# 91,5 persen), jadi angka per jam TIDAK boleh dipajang sebagai akurasi.
AKURASI = {
    "nilai": 58.2,            # proporsi benar, hari hujan atau kering
    "label": "hari hujan",
    "dasar": 50.3,            # skor tebakan sepele, sebagai pembanding jujur
    "pod": 87.8,              # dari hari yang benar benar hujan, tertangkap
    "far": 45.0,              # dari hari yang diprediksi hujan, meleset
    "csi": 51.1,
    "hss": 16.8,
    "pos": 13,
    "hari": 52,
    "pasangan": 594,
    "bias_hujan": 1.43,       # total model dibagi total pengamatan
    "catatan": ("Verifikasi hujan harian lawan 13 pos hujan DAS Citarum, "
                "52 hari pada Okt-Des 2018. Model cenderung terlalu basah, "
                "totalnya 1,43 kali pengamatan."),
}

# Pos hujan yang dipakai. Disalin ke keluaran supaya bisa digambar di peta.
# lat, lon, nama. Sensor suhu mati di beberapa pos, tapi penakar hujannya jalan.
POS_HUJAN = [
    ("DAS Cisangkuy", -7.1886, 107.6056), ("DAS Citarik", -6.9955, 107.9683),
    ("Sapan", -6.9919, 107.6868), ("Cikeruh", -6.9308, 107.7860),
    ("Cikapundung", -6.6951, 107.3667), ("Bendung Curugagung", -6.8588, 107.6172),
    ("Cijengkol", -6.6217, 107.6752), ("Bendung Pundong", -6.4388, 107.5110),
    ("Cimalaya", -6.4320, 107.5145), ("Cikao", -6.5571, 107.4369),
    ("DAS Cibeet", -6.5078, 107.2174), ("Das Cikarang", -6.3398, 107.0393),
    ("Cilalawi Catchment Area", -6.6173, 107.4053),
]
