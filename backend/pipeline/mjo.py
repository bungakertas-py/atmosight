"""Indeks MJO dan medan anomalinya.

Resepnya RMM Wheeler dan Hendon 2004, tujuh langkah, TAPI EOF-nya dilatih
pada bujur yang memang kita sajikan saja, 62,5 sampai 180,0 BT. Itu keputusan
pemilik. Akibatnya nomor fase tidak otomatis berarti tempat yang sama dengan
BoM, jadi urutan dan tanda EOF SUDAH DISELARASKAN ke geografi fase baku waktu
basisnya dibuat, lihat kunci "selaras" di mjo_basis.json.

Tiga medan, OLR, U850, U200, dirata ratakan 15 LS sampai 15 LU.

ASAL DATANYA SENGAJA BEDA UNTUK TIAP MEDAN.
  OLR   dari CPC blended OLR 1 derajat lewat OPeNDAP NOAA PSL. Rekamannya
        1991 sampai sekarang, jadi klimatologinya sahih. GFS punya ULWRF
        sendiri tapi TIDAK DIPAKAI untuk indeks, sebab klimatologi kita
        dilatih pada CPC dan mencampur dua model meninggalkan selisih
        biasnya di dalam anomali.
  angin dari analisis GFS yang memang sudah diunduh pipeline ini.

JEBAKAN YANG SUDAH MEMAKAN WAKTU, jangan diulang.
  1. Nilai pengisi berkas PSL itu -9,97e36. Sesudah dirata ratakan melintang
     bersama sel yang sah, sisanya bisa mendarat di 1e28 dan LOLOS dari
     ambang 1e30. Saring pakai RENTANG FISIK, bukan ambang besar.
  2. np.asarray pada MaskedArray MEMBUANG maskernya dan memulangkan data
     mentah yang di posisi termasker berisi NOL. Seluruh berkas jadi nol dan
     indeksnya jatuh ke 12,5 persen, persis setara menebak acak. Pakai
     np.ma.filled(x, np.nan).

Modul ini GAGAL LEMBUT. Apa pun yang salah, dia mengembalikan None dan
pipeline lanjut tanpa MJO. Fitur ini pelengkap, bukan alasan seluruh
kiriman hari itu batal.
"""
from __future__ import annotations

import datetime as dt
import json
import math
from pathlib import Path

import numpy as np

DIR = Path(__file__).resolve().parent
BASIS = DIR / "mjo_basis.json"
# Riwayat DISIMPAN TERKOMPRESI dan IKUT DI-COMMIT. Runner GitHub Actions itu
# sekali pakai, jadi kalau riwayatnya cuma di disk runner dia hilang tiap jalan
# dan indeksnya tidak akan pernah terbentuk. Cache Actions sempat
# dipertimbangkan, tapi cache boleh dibuang kapan saja oleh GitHub, dan
# kehilangan riwayat berarti MJO menghilang 120 hari sampai backfill dijalankan
# tangan. Dikompresi supaya commit hariannya kecil, sekitar 100 KB bukan 460.
RIWAYAT = DIR.parent / "data" / "state" / "mjo_riwayat.json.gz"

OLR_URL = ("https://psl.noaa.gov/thredds/dodsC/Datasets/"
           "cpc_blended_olr-1deg/olr.day.mean.nc")
LAT_BATAS = 15.1          # 15 LS sampai 15 LU, resep RMM
OLR_SAH = (50.0, 400.0)   # rentang fisik W/m2
ANGIN_SAH = 120.0         # m/detik, di luar ini pasti nilai pengisi
RIWAYAT_HARI = 400        # 120 untuk rata rata + sisanya untuk Hovmoller
HOV_HARI = 95             # panjang diagram Hovmoller


def _muat_basis() -> dict | None:
    try:
        return json.loads(BASIS.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"  ! mjo: basis tak terbaca ({e})")
        return None


def _muat_riwayat() -> dict:
    import gzip
    try:
        return json.loads(gzip.decompress(RIWAYAT.read_bytes()).decode("utf-8"))
    except Exception:
        return {"hari": [], "olr": [], "u850": [], "u200": []}


def _simpan_riwayat(r: dict) -> None:
    import gzip
    RIWAYAT.parent.mkdir(parents=True, exist_ok=True)
    # mtime=0 supaya berkasnya BIT PER BIT SAMA kalau isinya sama. Tanpa itu
    # gzip menanam cap waktu dan git melihat perubahan tiap hari walau datanya
    # tidak berubah, lalu repo gemuk tanpa alasan.
    RIWAYAT.write_bytes(gzip.compress(
        json.dumps(r, separators=(",", ":")).encode("utf-8"), mtime=0))


def _rapikan(r: dict) -> dict:
    """Urut menurut tanggal, buang kembar, potong ke RIWAYAT_HARI terakhir."""
    pasang = {}
    for i, h in enumerate(r["hari"]):
        pasang[h] = (r["olr"][i], r["u850"][i], r["u200"][i])
    kunci = sorted(pasang)[-RIWAYAT_HARI:]
    return {"hari": kunci,
            "olr": [pasang[h][0] for h in kunci],
            "u850": [pasang[h][1] for h in kunci],
            "u200": [pasang[h][2] for h in kunci]}


def ambil_olr(kisi: list[float], hari_mulai: str, hari_akhir: str) -> dict:
    """OLR harian CPC, rata rata meridional 15 LS sampai 15 LU, lalu
    diinterpolasi ke kisi bujur basis. Mengembalikan {tanggal: [nilai]}."""
    import netCDF4 as nc
    d = nc.Dataset(OLR_URL)
    lat = d.variables["lat"][:]
    lon = np.asarray(d.variables["lon"][:], dtype=float)
    t = d.variables["time"]
    tgl = nc.num2date(t[:], t.units, only_use_cftime_datetimes=False)
    tgl = np.array([x.strftime("%Y-%m-%d") for x in tgl])
    pilih = np.where((tgl >= hari_mulai) & (tgl <= hari_akhir))[0]
    if not len(pilih):
        d.close()
        return {}
    jl = np.where((lat <= LAT_BATAS) & (lat >= -LAT_BATAS))[0]
    blok = np.ma.filled(
        d.variables["olr"][pilih[0]:pilih[-1] + 1, jl[0]:jl[-1] + 1, :].astype("float32"),
        np.nan)
    d.close()
    blok[(blok < OLR_SAH[0]) | (blok > OLR_SAH[1])] = np.nan
    garis = np.nanmean(blok, axis=1)                    # (waktu, bujur)
    out = {}
    for n, i in enumerate(range(pilih[0], pilih[-1] + 1)):
        baris = garis[n]
        if np.isnan(baris).all():
            continue
        sah = ~np.isnan(baris)
        out[tgl[i]] = [round(float(v), 3)
                       for v in np.interp(kisi, lon[sah], baris[sah])]
    return out


def angin_dari_profil(output_dir: Path, kisi: list[float]) -> tuple[list, list] | None:
    """U850 dan U200 rata rata 15 LS sampai 15 LU, dibaca dari keluaran profil
    yang SUDAH ditulis pipeline, yaitu profile_meta.json plus profile.bin.gz.

    Sengaja membaca berkas, bukan menerima larik dari profiles.py. Dengan
    begitu modul ini tidak memaksa profiles.py mengubah apa yang dia pulangkan,
    dan dia tetap bisa dijalankan sendiri waktu backfill.

    Yang diambil LANGKAH WAKTU PERTAMA, yaitu analisis. Prakiraan jam jam
    berikutnya tidak boleh masuk riwayat, riwayat itu catatan keadaan yang
    sudah terjadi."""
    import gzip
    try:
        meta = json.loads((output_dir / "profile_meta.json").read_text(encoding="utf-8"))
        mentah = gzip.decompress((output_dir / "profile.bin.gz").read_bytes())
    except Exception as e:
        print(f"  ! mjo: profil tak terbaca ({e})")
        return None
    try:
        nx, ny = int(meta["nx"]), int(meta["ny"])
        lev = list(meta["levels"])
        i8, i2 = lev.index(850), lev.index(200)
        v = [x for x in meta["vars"] if x["var"] == "u"][0]
    except Exception as e:
        print(f"  ! mjo: profil tak punya u 850/200 ({e})")
        return None
    dt_np = np.uint8 if v["dtype"] == "uint8" else np.int16
    arr = np.frombuffer(mentah, dtype=dt_np, count=v["byteLength"] // np.dtype(dt_np).itemsize,
                        offset=v["byteOffset"]).astype(np.float64)
    arr = arr * float(v.get("scale", 1.0)) + float(v.get("offset", 0.0))
    bidang = nx * ny
    nlev = len(lev)
    lon = meta["bounds"][0] + np.arange(nx) * float(meta["dx"])
    lat = meta["bounds"][3] - np.arange(ny) * float(meta["dy"])
    jl = np.where((lat <= LAT_BATAS) & (lat >= -LAT_BATAS))[0]
    if not len(jl):
        return None
    keluar = []
    for il in (i8, i2):
        a0 = (0 * nlev + il) * bidang          # langkah waktu 0 = analisis
        bid = arr[a0:a0 + bidang].reshape(ny, nx)[jl, :]
        bid = np.where(np.abs(bid) > ANGIN_SAH, np.nan, bid)
        garis = np.nanmean(bid, axis=0)
        sah = ~np.isnan(garis)
        if sah.sum() < 4:
            return None
        keluar.append([round(float(x), 3) for x in np.interp(kisi, lon[sah], garis[sah])])
    return keluar[0], keluar[1]


def _harmonik(tanggal: str) -> np.ndarray:
    d = dt.date.fromisoformat(tanggal)
    doy = (d - dt.date(d.year, 1, 1)).days
    w = 2 * math.pi * doy / 365.25
    v = [1.0]
    for k in (1, 2, 3):
        v += [math.cos(k * w), math.sin(k * w)]
    return np.array(v)


def hitung_indeks(basis: dict, riwayat: dict) -> dict | None:
    """Anomali, buang rata rata 120 hari, normalisasi, proyeksi ke dua EOF."""
    hari = riwayat["hari"]
    if len(hari) < 121:
        print(f"  ! mjo: riwayat baru {len(hari)} hari, butuh 121")
        return None
    medan = basis["medan"]
    X = {k: np.array(riwayat[k], dtype=float) for k in medan}
    Hm = np.array([_harmonik(h) for h in hari])
    anom = {}
    for k in medan:
        anom[k] = X[k] - Hm @ np.array(basis["koef"][k], dtype=float)
    # rata rata 120 hari SEBELUM hari yang dihitung, untuk tiap hari ke-120 ke atas
    n = len(hari)
    jejak = []
    EOF = np.array(basis["eof"], dtype=float)
    ps = np.array(basis["sigma_pc"], dtype=float)
    tukar = bool(basis["selaras"]["tukar"])
    tanda = np.array(basis["selaras"]["tanda"], dtype=float)
    # Hovmoller WAJIB memakai anomali tahap akhir, yaitu yang rata rata 120
    # harinya sudah dibuang, bukan yang baru dibuang musimnya. Kalau tidak,
    # peta dan diagramnya memakai dua definisi anomali yang berbeda padahal
    # legendanya sama, dan sinyal ENSO akan bocor ke diagram.
    awal_hov = max(120, n - HOV_HARI)
    hov = {k: [] for k in medan}
    for i in range(120, n):
        vek = []
        for k in medan:
            a = anom[k][i] - anom[k][i - 120:i].mean(axis=0)
            vek.append(a / basis["sigma_medan"][k])
        if i >= awal_hov:
            for k, a in zip(medan, vek):
                hov[k].append(a * basis["sigma_medan"][k])   # balik ke satuan asli
        pc = np.concatenate(vek) @ EOF.T / ps
        if tukar:
            pc = pc[::-1]
        pc = pc * tanda
        amp = float(np.hypot(pc[0], pc[1]))
        sudut = math.degrees(math.atan2(pc[1], pc[0])) % 360
        jejak.append({"tanggal": hari[i],
                      "rmm1": round(float(pc[0]), 4),
                      "rmm2": round(float(pc[1]), 4),
                      "fase": int(((int(sudut // 45) + 4) % 8) + 1),
                      "amplitudo": round(amp, 4)})
    if not jejak:
        return None
    return {"indeks": jejak[-1], "jejak": jejak[-60:],
            "hovmoller_anom": hov, "hovmoller_hari": hari[awal_hov:]}


def bangun(output_dir: Path, kisi_amplop=None, run_time: str = "") -> dict | None:
    """Pintu masuk dari run.py. Memulangkan isi mjo.json, atau None."""
    basis = _muat_basis()
    if not basis:
        return None
    kisi = [float(x) for x in basis["lon"]]
    riwayat = _rapikan(_muat_riwayat())

    hari_ini = dt.date.today().isoformat()
    mulai = (dt.date.today() - dt.timedelta(days=RIWAYAT_HARI)).isoformat()
    try:
        olr_baru = ambil_olr(kisi, mulai, hari_ini)
    except Exception as e:
        print(f"  ! mjo: OLR tak terambil ({e})")
        olr_baru = {}
    angin = angin_dari_profil(output_dir, kisi)

    # SATU BARIS DITAMBAH PER JALAN, dan hanya kalau KETIGA medannya ada.
    # OLR CPC tertinggal beberapa hari, jadi tanggal yang anginnya sudah ada
    # tapi OLR-nya belum tidak bisa dipasang, begitu pula sebaliknya. Baris
    # setengah TIDAK DIISI TEBAKAN, dia dilewati saja. Deret berlubang lebih
    # jujur daripada deret yang ditambal karangan, dan lubangnya akan
    # tertutup sendiri waktu backfill dijalankan.
    # Tanggal yang dipasang adalah tanggal OLR TERBARU yang tersedia, bukan
    # hari ini, sebab itu yang benar benar punya ketiga medannya.
    sudah = set(riwayat["hari"])
    if angin and olr_baru:
        tgl = max(olr_baru)
        if tgl not in sudah:
            riwayat["hari"].append(tgl)
            riwayat["olr"].append(olr_baru[tgl])
            riwayat["u850"].append(angin[0])
            riwayat["u200"].append(angin[1])
    riwayat = _rapikan(riwayat)
    _simpan_riwayat(riwayat)
    print(f"  mjo: riwayat {len(riwayat['hari'])} hari, terakhir "
          f"{riwayat['hari'][-1] if riwayat['hari'] else '-'}")

    hasil = hitung_indeks(basis, riwayat)
    if not hasil:
        return None
    hov = hasil["hovmoller_anom"]
    doc = {
        "run_time": run_time,
        "generated_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sumber": "OLR CPC blended + angin analisis GFS, dimasak GitHub Actions",
        "metode": basis["metode"],
        "domain": {"lon_barat": kisi[0], "lon_timur": kisi[-1],
                   "lat_selatan": -15.0, "lat_utara": 15.0},
        "validasi": basis.get("validasi", {}),
        "indeks": hasil["indeks"],
        "jejak": hasil["jejak"],
        "hovmoller": {
            "lon": kisi,
            "waktu": hasil["hovmoller_hari"],
            "batas_analisis": hasil["hovmoller_hari"][-1],
            "olr": [[round(float(v), 2) for v in b] for b in hov["olr"]],
            "u850": [[round(float(v), 2) for v in b] for b in hov["u850"]],
            "u200": [[round(float(v), 2) for v in b] for b in hov["u200"]],
        },
    }
    if kisi_amplop:
        doc["amplop"] = kisi_amplop
    return doc
