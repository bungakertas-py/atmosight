"""Indeks AUSMI, monsun Australia.

AUSMI itu angin zonal 850 hPa dirata ratakan di kotak 5 LS sampai 15 LS,
110 BT sampai 130 BT. Kajikawa, Wang, dan Yang 2010. Satu angka per hari,
satuannya m/detik.

    positif  baratan, monsun Australia AKTIF, dan di Indonesia itu musim hujan
    negatif  timuran, monsunnya lemah, di Indonesia musim kemarau

JEBAKAN ISTILAH, dan ini yang paling mudah salah baca. Di Indonesia "Monsun
Australia" lazim berarti angin timuran yang datang DARI Australia, yaitu
musim kemarau. AUSMI yang aktif justru sebaliknya, baratan di utara
Australia, musim hujan. Dua istilah yang bunyinya mirip menunjuk keadaan yang
hampir berlawanan. Banner monsun di frontend memakai istilah Indonesia,
indeks ini memakai istilah internasional, jadi keduanya WAJIB diberi
keterangan kalau ditayangkan berdampingan.

Bedanya dengan MJO, indeks ini MURAH. Tidak ada EOF, tidak ada rerata
bergulir 120 hari, tidak ada data di luar domain yang kita sajikan. Kotaknya
duduk jauh di dalam domain 62 sampai 180 BT, 33 LS sampai 33 LU.

SUMBERNYA.
  harian       analisis GFS, dibaca dari profile.bin.gz yang SUDAH ditulis
               pipeline ini. Tidak ada unduhan tambahan sama sekali.
  klimatologi  reanalisis NCEP/NCAR 1991-2020, dipanggang sekali ke
               ausmi_basis.json oleh ausmi_basis_build.py.

Dua sumber berbeda berarti ada selisih bias di dalam anomalinya. Itu
pelajaran dari MJO dan di sini TIDAK diabaikan, selisihnya diukur oleh
ausmi_bias.py lalu disimpan di basis sebagai "bias_gfs" dan dikurangkan di
sini. Kalau kuncinya belum ada, anomalinya tetap dihitung tanpa koreksi dan
`bias_terukur` di keluaran berisi null, supaya jelas mana yang sudah
diperiksa dan mana yang belum.

Modul ini GAGAL LEMBUT, sama dengan mjo.py. Apa pun yang salah, dia
mengembalikan None dan pipeline lanjut tanpa AUSMI.
"""
from __future__ import annotations

import datetime as dt
import gzip
import json
from pathlib import Path

import numpy as np

DIR = Path(__file__).resolve().parent
BASIS = DIR / "ausmi_basis.json"
# Riwayat IKUT DI-COMMIT, alasannya sama dengan riwayat MJO. Runner GitHub
# Actions sekali pakai, kalau riwayatnya cuma di disk runner dia hilang tiap
# jalan. Berkas ini jauh lebih kecil daripada punya MJO, satu angka per hari
# bukan satu garis bujur per hari, jadi beberapa KB saja.
RIWAYAT = DIR.parent / "data" / "state" / "ausmi_riwayat.json.gz"

LAT_UTARA, LAT_SELATAN = -5.0, -15.0
LON_BARAT, LON_TIMUR = 110.0, 130.0
ANGIN_SAH = 120.0          # m/detik, di luar ini pasti nilai pengisi
RIWAYAT_HARI = 800         # dua musim penuh, cukup untuk menunjukkan onset lalu
HALUS_HARI = 5             # jendela rerata bergerak untuk deret tayang


def _muat_basis() -> dict | None:
    try:
        return json.loads(BASIS.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"  ! ausmi: basis tak terbaca ({e})")
        return None


def _muat_riwayat() -> dict:
    try:
        return json.loads(gzip.decompress(RIWAYAT.read_bytes()).decode("utf-8"))
    except Exception:
        return {"hari": [], "u850": []}


def _simpan_riwayat(r: dict) -> None:
    RIWAYAT.parent.mkdir(parents=True, exist_ok=True)
    # mtime=0 supaya berkasnya bit per bit sama kalau isinya sama, kalau tidak
    # git melihat perubahan tiap hari walau datanya tidak berubah.
    RIWAYAT.write_bytes(gzip.compress(
        json.dumps(r, separators=(",", ":")).encode("utf-8"), mtime=0))


def _rapikan(r: dict) -> dict:
    pasang = {h: r["u850"][i] for i, h in enumerate(r["hari"])}
    kunci = sorted(pasang)[-RIWAYAT_HARI:]
    return {"hari": kunci, "u850": [pasang[h] for h in kunci]}


def kotak_indeks(meta: dict) -> tuple[np.ndarray, np.ndarray]:
    """Indeks baris dan kolom kisi profil yang jatuh di dalam kotak AUSMI."""
    nx, ny = int(meta["nx"]), int(meta["ny"])
    lon = meta["bounds"][0] + np.arange(nx) * float(meta["dx"])
    lat = meta["bounds"][3] - np.arange(ny) * float(meta["dy"])
    jl = np.where((lat <= LAT_UTARA) & (lat >= LAT_SELATAN))[0]
    kl = np.where((lon >= LON_BARAT) & (lon <= LON_TIMUR))[0]
    return jl, kl


def deret_dari_profil(output_dir: Path) -> list[tuple[str, float]] | None:
    """[(valid_time, AUSMI)] untuk SEMUA langkah waktu di profil.

    Langkah pertama itu analisis, dia yang masuk riwayat. Sisanya prakiraan,
    dipakai untuk jalur ramalan di layar saja dan TIDAK BOLEH masuk riwayat.
    Riwayat itu catatan keadaan yang sudah terjadi.

    Sengaja membaca berkas keluaran, bukan menerima larik dari profiles.py,
    supaya modul ini bisa dijalankan sendiri waktu backfill. Pola yang sama
    dengan mjo.angin_dari_profil.
    """
    try:
        meta = json.loads((output_dir / "profile_meta.json").read_text(encoding="utf-8"))
        mentah = gzip.decompress((output_dir / "profile.bin.gz").read_bytes())
    except Exception as e:
        print(f"  ! ausmi: profil tak terbaca ({e})")
        return None
    try:
        nx, ny = int(meta["nx"]), int(meta["ny"])
        lev = list(meta["levels"])
        il = lev.index(850)
        v = [x for x in meta["vars"] if x["var"] == "u"][0]
        waktu = list(meta["times"])
    except Exception as e:
        print(f"  ! ausmi: profil tak punya u 850 ({e})")
        return None

    dt_np = np.uint8 if v["dtype"] == "uint8" else np.int16
    arr = np.frombuffer(mentah, dtype=dt_np,
                        count=v["byteLength"] // np.dtype(dt_np).itemsize,
                        offset=v["byteOffset"]).astype(np.float64)
    arr = arr * float(v.get("scale", 1.0)) + float(v.get("offset", 0.0))

    jl, kl = kotak_indeks(meta)
    if not len(jl) or not len(kl):
        print("  ! ausmi: kotak AUSMI di luar domain profil")
        return None
    bidang, nlev = nx * ny, len(lev)
    out = []
    for t, wkt in enumerate(waktu):
        a0 = (t * nlev + il) * bidang
        if a0 + bidang > arr.size:
            break
        bid = arr[a0:a0 + bidang].reshape(ny, nx)[np.ix_(jl, kl)]
        bid = np.where(np.abs(bid) > ANGIN_SAH, np.nan, bid)
        if np.isnan(bid).all():
            continue
        # Rerata kotak sederhana tanpa bobot cos(lat), sama dengan definisi
        # bakunya dan sama dengan cara klimatologinya dihitung.
        out.append((wkt, round(float(np.nanmean(bid)), 3)))
    return out or None


def _doy(tanggal: str) -> int:
    d = dt.date.fromisoformat(tanggal)
    return min((d - dt.date(d.year, 1, 1)).days, 365)


def _klim(basis: dict, tanggal: str) -> float:
    return float(basis["siklus_doy"][_doy(tanggal)])


def _sd(basis: dict, tanggal: str) -> float:
    s = basis["sd_bulan"][int(tanggal[5:7]) - 1]
    return float(s if s else basis["sd_total"])


def _halus(nilai: list[float], n: int = HALUS_HARI) -> list[float]:
    """Rerata bergerak yang MENGHORMATI TEPI.

    np.convolve dengan mode 'same' mengisi tepinya dengan NOL, bukan dengan
    nilai yang ada, sehingga awal dan akhir deret tertarik ke nol dan puncak
    di dekat tepi hilang. Itu sudah pernah menipuku sekali waktu mengerjakan
    MJO dan sempat membalik kesimpulan. Di sini tiap titik dirata ratakan
    HANYA dari titik yang benar benar tersedia.
    """
    a = np.asarray(nilai, dtype=float)
    r = n // 2
    return [round(float(np.nanmean(a[max(0, i - r):min(len(a), i + r + 1)])), 3)
            for i in range(len(a))]


def _musim(tanggal: str) -> str:
    """Label musim monsun belahan selatan, Juli sampai Juni."""
    d = dt.date.fromisoformat(tanggal)
    th = d.year if d.month >= 7 else d.year - 1
    return f"{th}/{th + 1}"


def _onset(hari: list[str], nilai: list[float], musim: str) -> dict:
    """Hari pertama AUSMI berbalik jadi baratan DAN bertahan.

    ATURAN INI MILIK KITA, bukan kutipan. Kajikawa dan kawan kawan memakai
    indeks yang sudah disaring banyak skala waktu, dan kita belum punya
    riwayat sepanjang itu. Yang dipakai di sini aturan sederhana yang bisa
    diperiksa siapa saja.

        onset = hari pertama sejak 1 September dengan AUSMI > 0
                DAN rerata tujuh hari mulai hari itu juga > 0

    Syarat kedua yang penting. Tanpa dia, satu hari baratan yang lewat karena
    gangguan sesaat sudah dihitung sebagai onset, padahal monsun belum
    datang. Dengan dia, yang dihitung cuma pembalikan yang bertahan.
    """
    th = int(musim.split("/")[0])
    awal, akhir = f"{th}-09-01", f"{th + 1}-06-30"
    idx = [i for i, h in enumerate(hari) if awal <= h <= akhir]
    if not idx:
        return {"musim": musim, "tanggal": None, "catatan": "riwayat belum mencakup musim ini"}
    for i in idx:
        if nilai[i] <= 0:
            continue
        jendela = nilai[i:i + 7]
        if len(jendela) < 7:
            return {"musim": musim, "tanggal": None,
                    "catatan": "ada baratan tapi belum genap tujuh hari untuk diuji"}
        if float(np.mean(jendela)) > 0:
            return {"musim": musim, "tanggal": hari[i],
                    "catatan": "baratan pertama yang bertahan tujuh hari"}
    return {"musim": musim, "tanggal": None, "catatan": "belum onset"}


def bangun(output_dir: Path, run_time: str | None = None) -> dict | None:
    basis = _muat_basis()
    if not basis:
        return None
    deret = deret_dari_profil(output_dir)
    if not deret:
        return None

    # Langkah pertama = analisis. Tanggalnya diambil dari valid_time-nya.
    tgl_anl = deret[0][0][:10]
    nilai_anl = deret[0][1]

    riwayat = _rapikan(_muat_riwayat())
    pasang = dict(zip(riwayat["hari"], riwayat["u850"]))
    pasang[tgl_anl] = nilai_anl
    riwayat = _rapikan({"hari": list(pasang), "u850": [pasang[h] for h in pasang]})
    _simpan_riwayat(riwayat)

    hari, nilai = riwayat["hari"], riwayat["u850"]
    bias = basis.get("bias_gfs")
    klim = [round(_klim(basis, h), 3) for h in hari]
    # Bias dikurangkan dari KLIMATOLOGINYA, bukan dari nilai hariannya. Nilai
    # harian itu yang ditayangkan sebagai AUSMI dan dia harus tetap apa adanya
    # supaya bisa diadu dengan indeks orang lain. Yang digeser acuannya.
    geser = float(bias) if bias is not None else 0.0
    anom = [round(nilai[i] - klim[i] - geser, 3) for i in range(len(hari))]

    kini_tgl = hari[-1]
    kini = nilai[-1]
    kini_anom = anom[-1]
    sd = _sd(basis, kini_tgl)
    musim_kini = _musim(kini_tgl)

    out = {
        "generated": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "run_time": run_time,
        "indeks": "AUSMI",
        "acuan": basis.get("acuan"),
        "definisi": basis.get("definisi"),
        "kotak": basis.get("kotak"),
        "satuan": "m/s",
        "kini": {
            "tanggal": kini_tgl,
            "nilai": kini,
            "klim": round(klim[-1] + geser, 3),
            "anomali": kini_anom,
            "sigma": round(kini_anom / sd, 2) if sd else None,
            "arah": "baratan" if kini > 0 else "timuran",
            "aktif": bool(kini > 0),
        },
        "onset": _onset(hari, nilai, musim_kini),
        "deret": {
            "hari": hari,
            "nilai": nilai,
            "halus": _halus(nilai),
            "klim": [round(k + geser, 3) for k in klim],
        },
        "ramalan": [{"t": w, "v": v} for w, v in deret],
        "klim_info": {
            "sumber": basis.get("sumber_klim"),
            "periode": basis.get("periode_klim"),
            "hari": basis.get("hari_klim"),
            "sd_bulan_ini": round(sd, 3),
        },
        "bias_terukur": bias,
    }
    return out


if __name__ == "__main__":
    import sys
    d = Path(sys.argv[1]) if len(sys.argv) > 1 else DIR.parent / "data" / "output"
    hasil = bangun(d)
    if not hasil:
        sys.exit("ausmi gagal")
    k = hasil["kini"]
    print(f"{k['tanggal']}  AUSMI {k['nilai']:+.2f} m/s  ({k['arah']})  "
          f"klim {k['klim']:+.2f}  anomali {k['anomali']:+.2f}  "
          f"{k['sigma'] if k['sigma'] is None else format(k['sigma'], '+.2f')} sigma")
    print("onset:", json.dumps(hasil["onset"], ensure_ascii=False))
    print(f"riwayat {len(hasil['deret']['hari'])} hari, ramalan {len(hasil['ramalan'])} langkah")
