#!/usr/bin/env python3
"""Ambil jadwal kelas dari dokumen Google Docs fakultas dan simpan sebagai jadwal.json.

Pakai:  python scripts/sync_jadwal.py            (ambil dari internet)
        python scripts/sync_jadwal.py --file x.html   (tes dengan file lokal)
Aman: jika parsing gagal atau kolom kelas tidak ditemukan, jadwal.json lama TIDAK ditimpa.
"""
import argparse, datetime as dt, json, re, sys
from pathlib import Path

from bs4 import BeautifulSoup

URL = ("https://docs.google.com/document/d/e/"
       "2PACX-1vRKAk68agqoX2OTSK2-XvxVEWf4ZDDq7W8zm8vvzhGb1W1DGjLsUGjI6eFQYaHl3dbLtyU3D9PezHBA/pub")
KELAS = "2023 C"
OUT = Path(__file__).resolve().parent.parent / "jadwal.json"

HARI = {"SENIN": 0, "SELASA": 1, "RABU": 2, "KAMIS": 3, "JUMAT": 4, "SABTU": 5, "MINGGU": 6}
HARI_ID = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]
BULAN = {b: i + 1 for i, b in enumerate(
    "JANUARI FEBRUARI MARET APRIL MEI JUNI JULI AGUSTUS SEPTEMBER OKTOBER NOVEMBER DESEMBER".split())}
DAY_RE = re.compile(r"^(SENIN|SELASA|RABU|KAMIS|JUMAT|SABTU|MINGGU)\s*,?\s*(\d{1,2})\s+([A-Z]+)\s+\d{4}\s*(.*)$")
TIME_RE = re.compile(r"^(\d{2})\.(\d{2})-(\d{2})\.(\d{2})$")


def fetch(url):
    import requests
    r = requests.get(url, timeout=60, headers={"User-Agent": "Mozilla/5.0 jadwal-sync"})
    r.raise_for_status()
    return r.text


def grid(table):
    """Ratakan tabel ke grid (baris, kolom) dengan memperhitungkan rowspan/colspan."""
    rows = table.find_all("tr")
    g = {}
    for r, tr in enumerate(rows):
        c = 0
        for td in tr.find_all(["td", "th"]):
            while (r, c) in g:
                c += 1
            rs, cs = int(td.get("rowspan", 1)), int(td.get("colspan", 1))
            txt = re.sub(r"\s+", " ", td.get_text(" ", strip=True)).strip()
            for i in range(rs):
                for j in range(cs):
                    g[(r + i, c + j)] = txt
            c += cs
    return len(rows), g


def infer_date(weekday, day, month, today):
    """Judul hari di dokumen sering salah tahun, jadi tahun dicari dari kecocokan nama hari."""
    best = None
    for y in (today.year - 1, today.year, today.year + 1):
        try:
            d = dt.date(y, month, day)
        except ValueError:
            continue
        if d.weekday() == weekday and abs((d - today).days) <= 200:
            if best is None or abs((d - today).days) < abs((best - today).days):
                best = d
    return best


def parse_entry(text):
    status = ""
    m = re.match(r"^KULIAH (DITUNDA|GANTI)\s*(.*)$", text, re.I)
    if m:
        status, text = m.group(1).lower(), m.group(2)
    judul, dosen = text, ""
    up = text.upper()
    if " (" in text and text.endswith(")") and not up.startswith("UJIAN"):
        judul, rest = text.split(" (", 1)
        dosen = rest[:-1]
    if up.startswith("UJIAN"):
        jenis = "ujian"
    elif re.search(r"PRACTICAL TEST|REMEDIAL", up):
        jenis = "tes"
    elif up.startswith("KKD"):
        jenis = "kkd"
    elif up.startswith("SGD"):
        jenis = "sgd"
    elif up.startswith("LABORATORY"):
        jenis = "praktikum"
    elif re.match(r"^(SUBMIT|MEET|PRESENT)", up):
        jenis = "tugas"
    else:
        jenis = "kuliah"
    return {"judul": judul.strip(), "dosen": dosen.strip(), "status": status, "jenis": jenis}


def hhmm(h, m):
    return f"{h}:{m}"


def parse(html, kelas=KELAS, today=None):
    today = today or dt.date.today()
    soup = BeautifulSoup(html, "html.parser")
    items, warnings = [], []
    for el in soup.body.descendants:
        n = getattr(el, "name", None)
        if n == "table":
            items.append(("T", el))
        elif n in ("p", "h1", "h2", "h3") and el.find_parent("table") is None:
            t = re.sub(r"\s+", " ", el.get_text(" ", strip=True)).upper()
            if DAY_RE.match(t) and len(t) < 80:
                items.append(("D", t))

    days, seen, title, ruang, col_found = {}, set(), None, "", False
    for typ, v in items:
        if typ == "D":
            title = v
            continue
        if title is None:
            continue
        m = DAY_RE.match(title)
        wd, dd, bulan, note = HARI[m.group(1)], int(m.group(2)), BULAN.get(m.group(3)), m.group(4).strip("() ")
        nrows, g = grid(v)
        ncol = max(c for _, c in g) + 1
        idx = next((c for c in range(ncol) if g.get((0, c), "").upper().startswith(kelas.upper())), None)
        if idx is None:
            continue
        col_found = True
        if not ruang:
            head = g[(0, idx)]
            r = re.search(r"R\.KELAS (.+?) LT\.(\d+) (\w+)$", head.upper())
            if r:
                nama = r[1].title() if r[1].startswith("AULA") else f"Ruang Kelas {r[1]}"
                ruang = f"{nama}, Lt. {r[2]}, Gedung {r[3]}"
            else:
                ruang = head[len(kelas):].strip().title()
        date = infer_date(wd, dd, bulan, today) if bulan else None
        if date is None:
            warnings.append(f"Tanggal tidak cocok dengan nama hari, dilewati: {title}")
            continue
        if date in seen:
            continue
        seen.add(date)
        forum, sesi, prev = [], [], None
        for r in range(1, nrows):
            label, text = g.get((r, 0), ""), g.get((r, idx), "")
            if not text:
                prev = None
                continue
            if label.lower().startswith("diskusi"):
                parts = re.split(r"\s+(?=\d\.\s)", text)
                forum = [re.sub(r"^\d\.\s*", "", p).strip() for p in parts if p.strip()]
                continue
            t = TIME_RE.match(label)
            if not t:
                continue
            mulai, selesai = hhmm(t[1], t[2]), hhmm(t[3], t[4])
            if prev and prev["_raw"] == text and prev["selesai"] == mulai:
                prev["selesai"] = selesai
                continue
            e = parse_entry(text)
            e.update({"mulai": mulai, "selesai": selesai, "_raw": text})
            sesi.append(e)
            prev = e
        for e in sesi:
            e.pop("_raw", None)
        days[date] = {"tanggal": date.isoformat(), "hari": HARI_ID[wd], "catatan": note.title() if note else "",
                      "forum": forum, "sesi": sesi}
    if not col_found:
        raise RuntimeError(f"Kolom kelas '{kelas}' tidak ditemukan di tabel mana pun.")
    hari = [days[d] for d in sorted(days)]
    return {"meta": {"kelas": kelas, "ruang": ruang, "sumber": URL, "peringatan": warnings[:20]}, "hari": hari}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file")
    ap.add_argument("--today", help="YYYY-MM-DD (untuk tes)")
    a = ap.parse_args()
    today = dt.date.fromisoformat(a.today) if a.today else dt.date.today()
    try:
        html = Path(a.file).read_text(encoding="utf-8") if a.file else fetch(URL)
        data = parse(html, today=today)
        if not any(d["sesi"] or d["forum"] for d in data["hari"]):
            raise RuntimeError("Hasil parsing kosong; jadwal lama dipertahankan.")
    except Exception as e:  # jangan timpa data lama
        print(f"GAGAL: {e}", file=sys.stderr)
        sys.exit(1)
    old = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else None
    if old and old.get("hari") == data["hari"] and old["meta"].get("ruang") == data["meta"]["ruang"] and old["meta"].get("kelas") == data["meta"]["kelas"]:
        print("Tidak ada perubahan.")
        return
    data["meta"]["diperbarui"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Tersimpan: {len(data['hari'])} hari -> {OUT}")


if __name__ == "__main__":
    main()
