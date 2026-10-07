"""Ukur selisih AUSMI versi GFS lawan versi reanalisis, lalu simpan ke basis.

    python ausmi_bias.py [--tulis]

Kenapa ini ada. Nilai harian AUSMI datang dari analisis GFS, klimatologinya
dari reanalisis NCEP/NCAR. Dua model berbeda, kisi berbeda, 1 derajat lawan
2,5 derajat. Selisih sistematis di antara keduanya akan muncul UTUH di dalam
anomali dan terbaca seolah olah keadaan atmosfernya yang menyimpang.

Di MJO masalah yang sama ada tapi tidak bisa diukur semurah ini, sebab di
sana medannya satu garis bujur penuh. Di sini keluarannya satu angka per
hari, jadi selisihnya tinggal dirata ratakan.

Yang dibandingkan cuma hari yang DUA DUANYA punya. Riwayat GFS kita isinya
hasil backfill, reanalisis PSL basi berbulan, jadi irisannya ada di awal
tahun berjalan dan di tahun tahun sebelumnya.

Tanpa --tulis dia cuma melapor, tidak menyentuh berkas apa pun.
"""
from __future__ import annotations

import json
import sys

import numpy as np

import ausmi
from ausmi_basis_build import ambil_tahun


def main(tulis: bool = False) -> None:
    basis = ausmi._muat_basis()
    if not basis:
        sys.exit("ausmi_basis.json belum ada, jalankan ausmi_basis_build.py dulu")
    riwayat = ausmi._rapikan(ausmi._muat_riwayat())
    if len(riwayat["hari"]) < 30:
        sys.exit(f"riwayat GFS baru {len(riwayat['hari'])} hari, "
                 "jalankan ausmi_backfill.py dulu")

    gfs = dict(zip(riwayat["hari"], riwayat["u850"]))
    tahun = sorted({int(h[:4]) for h in gfs})
    print(f"riwayat GFS {len(gfs)} hari, tahun {tahun}")

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
    print(f"\n  GFS        rerata {g.mean():+.3f}  sd {g.std():.3f}")
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
    basis["bias_gfs"] = round(bias, 4)
    basis["bias_hari"] = len(sama)
    basis["bias_sd"] = round(float(d.std()), 4)
    basis["bias_korelasi"] = round(float(np.corrcoef(g, r)[0, 1]), 4)
    ausmi.BASIS.write_text(json.dumps(basis, separators=(",", ":")), encoding="utf-8")
    print(f"\nditulis ke {ausmi.BASIS.name}, bias_gfs = {basis['bias_gfs']:+.4f}")


if __name__ == "__main__":
    main("--tulis" in sys.argv)
