"""Ukur selisih AUSMI satu model lawan versi reanalisis, lalu simpan ke basis.

    python ausmi_bias.py [--model NAMA] [--riwayat JALUR] [--tulis]

BIASNYA PER MODEL. Angka yang keluar dari sini selisih sistematis antara
SATU model dan reanalisis, jadi dia milik model itu saja. Memakainya untuk
model lain menggeser acuan model lain sejauh kesalahan model ini. Hasilnya
disimpan di basis di bawah "bias" dan dinamai dengan nama modelnya, bukan
ditimpa ke satu kunci bersama.

  --model    nama model, bawaannya gfs. Dipakai sebagai nama kunci.
  --riwayat  berkas riwayat model itu. Tanpa ini dia memakai riwayat bawaan
             ausmi.py, yang milik GFS.

Contoh untuk ECMWF:

    python ausmi_bias.py --model ecmwf \
        --riwayat ../data/state/ausmi_riwayat_ecmwf.json.gz --tulis

Kenapa ini ada. Nilai harian AUSMI datang dari analisis GFS, klimatologinya
dari reanalisis NCEP/NCAR. Dua model berbeda, kisi berbeda, 1 derajat lawan
2,5 derajat. Selisih sistematis di antara keduanya akan muncul UTUH di dalam
anomali dan terbaca seolah olah keadaan atmosfernya yang menyimpang.

Di MJO masalah yang sama ada tapi tidak bisa diukur semurah ini, sebab di
sana medannya satu garis bujur penuh. Di sini keluarannya satu angka per
hari, jadi selisihnya tinggal dirata ratakan.

ACUANNYA TETAP NCEP/NCAR, DIPUTUSKAN PEMILIK 21 OKTOBER 2026. Sempat
ditimbang pindah ke ERA5, sebab ERA5T lewat ARCO Google Cloud terbuka tanpa
akun dan cuma tertinggal enam hari, sedangkan NCEP/NCAR di PSL waktu itu
baru sampai 17 Maret 2026, yaitu tujuh bulan. Tidak jadi, dan itu keputusan
yang disengaja.

Akibatnya harus diketahui orang yang membaca ini nanti. Model yang baru
lahir TIDAK BISA diukur biasnya sampai reanalisis menyusul ke bulan bulan
dia hidup. Untuk ECMWF yang mulai 20 Oktober 2026, dari lag yang terukur
sekarang itu kira kira pertengahan 2027. Sampai saat itu dia jalan dengan
`bias_terukur` null, dan itu memang keadaan yang benar, bukan pekerjaan
yang tertinggal. Jangan diakali dengan meminjam bias model lain.

Yang dibandingkan cuma hari yang DUA DUANYA punya. Riwayat GFS kita isinya
hasil backfill, reanalisis PSL basi berbulan, jadi irisannya ada di awal
tahun berjalan dan di tahun tahun sebelumnya.

Tanpa --tulis dia cuma melapor, tidak menyentuh berkas apa pun.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np

import ausmi
from ausmi_basis_build import ambil_tahun


def main(tulis: bool = False, model: str = "gfs",
         riwayat_jalur: Path | None = None) -> None:
    basis = ausmi._muat_basis()
    if not basis:
        sys.exit("ausmi_basis.json belum ada, jalankan ausmi_basis_build.py dulu")
    riwayat = ausmi._rapikan(ausmi._muat_riwayat(riwayat_jalur))
    if len(riwayat["hari"]) < 30:
        sys.exit(f"riwayat {model} baru {len(riwayat['hari'])} hari, "
                 "jalankan ausmi_backfill.py dulu")

    gfs = dict(zip(riwayat["hari"], riwayat["u850"]))

    # HARI SEMAIAN DIBUANG, dan ini penjaga yang paling penting di berkas ini.
    #
    # Riwayat model baru disemai dari model lain supaya MJO tidak mati empat
    # bulan menunggu 121 hari terkumpul. Hari hari semaian itu nilainya milik
    # model penyemai, cuma berkasnya saja yang milik model baru. Mengukur bias
    # dari sana memulangkan bias model penyemai dengan label model baru, dan
    # angkanya kelihatan sangat meyakinkan sebab memang hasil hitungan betulan
    # dari deret betulan.
    #
    # Terbukti 21 Oktober 2026. Diukur untuk ECMWF, keluar -0,323 dari 193
    # hari dengan korelasi 0,9891, sama persis sampai digit terakhir dengan
    # bias_gfs yang sudah ada di basis. Kalau ditulis, ECMWF akan berjalan
    # bertahun tahun memakai koreksi GFS sambil mengaku sudah diukur sendiri.
    semai = riwayat.get("semai_sampai")
    if semai:
        sebelum = len(gfs)
        gfs = {h: v for h, v in gfs.items() if h > semai}
        print(f"riwayat {model}: {sebelum} hari, {sebelum - len(gfs)} di "
              f"antaranya semaian dari {riwayat.get('semai_dari', 'model lain')} "
              f"sampai {semai} dan DIBUANG")
    if not gfs:
        sys.exit(f"riwayat {model} isinya semaian semua, belum ada satu hari pun "
                 f"yang benar benar diukur dari {model}. Biarkan dia jalan dulu.")

    tahun = sorted({int(h[:4]) for h in gfs})
    print(f"riwayat {model} {len(gfs)} hari hasil ukur sendiri, tahun {tahun}")

    rea: dict[str, float] = {}
    for th in tahun:
        try:
            rea.update(ambil_tahun(th))
        except Exception as e:
            print(f"  ! reanalisis {th} tak terambil ({e})")

    sama = sorted(set(gfs) & set(rea))
    print(f"irisan {len(sama)} hari"
          + (f", {sama[0]} sampai {sama[-1]}" if sama else ""))
    if len(sama) < 20:
        sys.exit("irisan terlalu pendek untuk menyimpulkan bias. "
                 "Perpanjang backfill supaya menembus bulan bulan yang "
                 "masih tercakup reanalisis.")

    g = np.array([gfs[h] for h in sama])
    r = np.array([rea[h] for h in sama])
    d = g - r
    bias = float(np.mean(d))
    print(f"\n  {model:10s} rerata {g.mean():+.3f}  sd {g.std():.3f}")
    print(f"  reanalisis rerata {r.mean():+.3f}  sd {r.std():.3f}")
    print(f"  selisih    rerata {bias:+.3f}  sd {d.std():.3f}  "
          f"maks |{np.abs(d).max():.3f}|")
    print(f"  korelasi   {float(np.corrcoef(g, r)[0, 1]):.4f}")

    # Ambang penilaian. Simpangan baku sisa klimatologi sekitar 2,8 m/detik,
    # jadi bias di bawah 0,2 itu di bawah sepersepuluh derau musiman dan
    # mengoreksinya cuma menambah angka tanpa menambah arti.
    if abs(bias) < 0.2:
        print("\n  Bias KECIL, di bawah 0,2 m/detik. Tidak perlu dikoreksi, "
              "tapi tetap dicatat supaya keputusan ini ada jejaknya.")
    else:
        print(f"\n  Bias NYATA {bias:+.3f} m/detik. Dipakai menggeser "
              "klimatologi, bukan menggeser nilai hariannya.")

    if not tulis:
        print("\n(tanpa --tulis, basis tidak disentuh)")
        return
    # Disimpan DI BAWAH NAMA MODELNYA, bukan ditimpa ke kunci bersama, kalau
    # tidak model yang diukur belakangan menghapus angka model sebelumnya dan
    # dua duanya jalan memakai bias yang terakhir kebetulan ditulis.
    per = basis.setdefault("bias", {})
    per[model] = {"bias": round(bias, 4),
                  "hari": len(sama),
                  "sd": round(float(d.std()), 4),
                  "korelasi": round(float(np.corrcoef(g, r)[0, 1]), 4),
                  "diukur": dt.date.today().isoformat()}
    if model == "gfs":
        # Kunci lama tetap diisi supaya basis yang sudah terbit tidak berubah
        # artinya buat pembaca lama. Pembaca baru memakai basis["bias"].
        basis["bias_gfs"] = round(bias, 4)
        basis["bias_hari"] = len(sama)
        basis["bias_sd"] = round(float(d.std()), 4)
        basis["bias_korelasi"] = round(float(np.corrcoef(g, r)[0, 1]), 4)
    ausmi.BASIS.write_text(json.dumps(basis, separators=(",", ":")), encoding="utf-8")
    print(f"\nditulis ke {ausmi.BASIS.name}, bias[{model}] = {per[model]['bias']:+.4f}")


def _arg(nama: str) -> str | None:
    """Nilai sesudah `nama` di argv, atau None."""
    if nama in sys.argv:
        i = sys.argv.index(nama)
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return None


if __name__ == "__main__":
    jalur = _arg("--riwayat")
    main("--tulis" in sys.argv,
         model=_arg("--model") or "gfs",
         riwayat_jalur=Path(jalur) if jalur else None)
