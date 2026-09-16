from __future__ import annotations

import csv
import json
import random
import re
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://peraturan.bpk.go.id"

SEED_URLS = [
    "https://peraturan.bpk.go.id/Search?keywords=&tentang=pangan&nomor=&jenis=230",
    "https://peraturan.bpk.go.id/Search?keywords=&tentang=obat&nomor=&jenis=230"
]

OUTPUT_DIR = Path("dataset_bpk_bpom")
PDF_DIR = OUTPUT_DIR / "pdf"
METADATA_CSV = OUTPUT_DIR / "metadata.csv"
METADATA_JSON = OUTPUT_DIR / "metadata.json"

MIN_YEAR = 2020

ONLY_STATUS_BERLAKU = True

INCLUDE_KEYWORDS = [
    # pangan
    "pangan",
    "pangan olahan",
    "keamanan pangan",
    "registrasi pangan",
    "label pangan",
    "bahan tambahan pangan",
    "cemaran pangan",
    # obat
    "obat",
    "sediaan farmasi",
    "bahan obat",
    "obat tradisional",
    "farmasi",
    "penandaan obat",
    "registrasi obat",
]

EXCLUDE_KEYWORDS = [
    "kosmetik",
    "jabatan fungsional",
    "kepegawaian",
]

# Rate limit.
MIN_DELAY = 3.0
MAX_DELAY = 6.0

# Timeout per request.
TIMEOUT = 30

# Retry maksimal untuk 429/5xx/network error.
MAX_RETRIES = 3

# Ukuran chunk download PDF.
DOWNLOAD_CHUNK_SIZE = 1024 * 256

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/140.0 Safari/537.36 "
    "RAG-BPOM-Student-Project/1.0"
)


# MODEL DATA
@dataclass
class Regulation:
    detail_url: str
    pdf_url: str
    title: str
    number: str
    year: int | None
    status: str
    effective_date: str
    source_info: str
    category: str
    filename: str
    local_path: str = ""
    abstract: str = ""


# HTTP SESSION
session = requests.Session()
session.headers.update(
    {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.8",
        "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
        "Connection": "keep-alive",
    }
)

last_request_time = 0.0
robots = RobotFileParser()
robots.set_url(urljoin(BASE_URL, "/robots.txt"))


def load_robots() -> None:
    """Ambil robots.txt; jika gagal, jangan langsung gagal total."""
    try:
        print("[INFO] Membaca robots.txt ...")
        robots.read()
        print("[INFO] robots.txt berhasil dibaca.")
    except Exception as exc:
        print(f"[WARN] robots.txt tidak bisa dibaca: {exc}")
        print("[WARN] Lanjut dengan rate-limit ketat.")


def wait_rate_limit() -> None:
    """Jeda minimum antar request + jitter."""
    global last_request_time

    target_delay = random.uniform(MIN_DELAY, MAX_DELAY)
    elapsed = time.monotonic() - last_request_time

    if elapsed < target_delay:
        time.sleep(target_delay - elapsed)

    last_request_time = time.monotonic()


def polite_allowed(url: str) -> bool:
    """Cek robots.txt jika berhasil dibaca."""
    try:
        return robots.can_fetch(USER_AGENT, url)
    except Exception:
        return True


def request_with_retry(url: str, *, stream: bool = False) -> requests.Response:
    """GET dengan rate-limit, retry ringan, dan backoff."""
    if not polite_allowed(url):
        raise RuntimeError(f"URL diblokir oleh robots.txt: {url}")

    delay = 2.0

    for attempt in range(1, MAX_RETRIES + 1):
        wait_rate_limit()

        try:
            response = session.get(
                url,
                timeout=TIMEOUT,
                stream=stream,
                allow_redirects=True,
            )

            if response.status_code == 200:
                return response

            if response.status_code in (429, 500, 502, 503, 504):
                retry_after = response.headers.get("Retry-After")
                if retry_after:
                    try:
                        sleep_s = float(retry_after)
                    except ValueError:
                        sleep_s = delay
                else:
                    sleep_s = delay + random.uniform(0, 2)

                print(
                    f"[WARN] HTTP {response.status_code} untuk {url}. "
                    f"Tunggu {sleep_s:.1f} detik sebelum retry."
                )
                time.sleep(sleep_s)
                delay *= 2
                continue

            response.raise_for_status()

        except requests.RequestException as exc:
            if attempt == MAX_RETRIES:
                raise

            sleep_s = delay + random.uniform(0, 2)
            print(
                f"[WARN] Request gagal (attempt {attempt}/{MAX_RETRIES}): {exc}. "
                f"Tunggu {sleep_s:.1f} detik."
            )
            time.sleep(sleep_s)
            delay *= 2

    raise RuntimeError(f"Gagal mengakses {url}")


# HELPER PARSING
def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def get_lines(soup: BeautifulSoup) -> list[str]:
    raw = soup.get_text("\n")
    lines = []
    for line in raw.splitlines():
        line = clean_text(line)
        if line:
            lines.append(line)
    return lines


def get_value_after_label(lines: list[str], label: str) -> str:
    for i, line in enumerate(lines):
        if line.lower() == label.lower() and i + 1 < len(lines):
            return lines[i + 1]
    return ""


def parse_year(lines: list[str], title: str = "", url: str = "") -> int | None:
    """Ambil tahun dari metadata halaman; fallback ke judul dan URL."""
    candidates = [
        get_value_after_label(lines, "Tahun"),
        title,
        url,
    ]

    for value in candidates:
        match = re.search(r"\b(20\d{2})\b", value or "")
        if match:
            return int(match.group(1))

    return None


def parse_detail_page(url: str) -> Regulation | None:
    response = request_with_retry(url)
    soup = BeautifulSoup(response.text, "html.parser")
    lines = get_lines(soup)

    # Judul utama biasanya ada di H1.
    h1 = soup.find("h1")
    title = clean_text(h1.get_text(" ", strip=True)) if h1 else ""

    if not title:
        title = next(
            (
                line
                for line in lines
                if line.lower().startswith("peraturan badan pengawas obat dan makanan")
            ),
            "",
        )

    year = parse_year(lines, title=title, url=url)
    status = get_value_after_label(lines, "Status")
    effective_date = get_value_after_label(lines, "Tanggal Berlaku")
    source_info = get_value_after_label(lines, "Sumber")

    # Nomor peraturan
    number = ""
    nomor_value = get_value_after_label(lines, "Nomor")
    if nomor_value:
        number = re.sub(r"\D+", "", nomor_value)

    # Ambil abstrak dengan mencari area "ABSTRAK PERATURAN".
    abstract = ""
    try:
        start = next(
            i for i, line in enumerate(lines)
            if line.upper() == "ABSTRAK PERATURAN"
        )
        tail = lines[start + 1 : start + 20]
        abstract = " ".join(tail)
    except StopIteration:
        pass

    full_context = f"{title} {abstract} {' '.join(lines[:120])}".lower()

    # Pastikan halaman memang Peraturan BPOM.
    if "badan pengawas obat dan makanan" not in full_context and "peraturan bpom" not in full_context:
        return None

    # Filter status
    if ONLY_STATUS_BERLAKU and status.lower() != "berlaku":
        print(f"[SKIP] Status bukan Berlaku: {title}")
        return None

    # Filter tahun
    if year is None or year < MIN_YEAR:
        print(f"[SKIP] Tahun terlalu lama: {title} ({year})")
        return None

    # Filter topik.
    has_include = any(keyword in full_context for keyword in INCLUDE_KEYWORDS)
    has_exclude = any(keyword in full_context for keyword in EXCLUDE_KEYWORDS)

    if not has_include or has_exclude:
        print(f"[SKIP] Di luar scope utama: {title}")
        return None

    # Cari URL download PDF
    pdf_url = ""
    for anchor in soup.find_all("a", href=True):
        href = urljoin(url, anchor["href"])
        text = clean_text(anchor.get_text(" ", strip=True)).lower()

        if "/download/" in href.lower() and (".pdf" in href.lower() or "download" in text):
            pdf_url = href
            break

    if not pdf_url:
        print(f"[WARN] PDF tidak ditemukan: {url}")
        return None

    # Kategori sederhana untuk metadata
    category = "Pangan"
    if any(k in full_context for k in [
        "obat",
        "sediaan farmasi",
        "bahan obat",
        "farmasi",
        "penandaan obat",
        "registrasi obat",
    ]):
        category = "Obat"
    if "pangan" in full_context and (
        "pangan olahan" in full_context
        or "keamanan pangan" in full_context
        or "registrasi pangan" in full_context
    ):
        category = "Pangan"

    # Buat nama file sendiri, tidak menggunakan nama file dari URL BPK
    short_title = title

    # Buang prefix yang tidak perlu
    short_title = re.sub(
        r"(?i)^peraturan badan pengawas obat dan makanan\s+nomor\s+\d+\s+tahun\s+\d+\s*",
        "",
        short_title,
    )

    # Ambil maksimal beberapa kata pertama agar nama tidak terlalu panjang
    words = short_title.split()
    short_title = "_".join(words[:7])

    # Bersihkan karakter yang tidak aman untuk Windows
    short_title = re.sub(r'[<>:"/\\|?*]', "", short_title)
    short_title = re.sub(r"\s+", "_", short_title)

    # Batasi panjang filename
    short_title = short_title[:80].rstrip("_")

    filename = (
        f"PerBPOM_{int(number):02d}_{year}_{short_title}.pdf"
        if number.isdigit() and year
        else f"PerBPOM_{number}_{year or 'unknown'}.pdf"
    )
    
    return Regulation(
        detail_url=url,
        pdf_url=pdf_url,
        title=title,
        number=number,
        year=year,
        status=status,
        effective_date=effective_date,
        source_info=source_info,
        category=category,
        filename=filename,
        abstract=abstract,
    )


def normalize_search_url(url: str, page_number: int | None = None) -> str:
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)

    if page_number is not None:
        qs["page"] = [str(page_number)]

    query = urlencode(qs, doseq=True)

    return urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            query,
            parsed.fragment,
        )
    )


def current_page_number(url: str) -> int:
    qs = parse_qs(urlparse(url).query)
    try:
        return int(qs.get("page", ["1"])[0])
    except (ValueError, TypeError):
        return 1


def extract_detail_links(soup: BeautifulSoup, page_url: str) -> list[str]:
    results = []
    seen = set()

    for anchor in soup.find_all("a", href=True):
        href = urljoin(page_url, anchor["href"])
        parsed = urlparse(href)

        if parsed.netloc != urlparse(BASE_URL).netloc:
            continue

        if not parsed.path.startswith("/Details/"):
            continue

        clean = urlunparse(
            (parsed.scheme, parsed.netloc, parsed.path, "", "", "")
        )

        if clean not in seen:
            seen.add(clean)
            results.append(clean)

    return results


def find_next_search_url(soup: BeautifulSoup, current_url: str) -> str | None:
    current_page = current_page_number(current_url)
    candidate = None

    current_parsed = urlparse(current_url)
    current_base_query = parse_qs(current_parsed.query)
    current_base_query.pop("page", None)

    for anchor in soup.find_all("a", href=True):
        href = urljoin(current_url, anchor["href"])
        parsed = urlparse(href)

        if parsed.netloc != current_parsed.netloc:
            continue

        if parsed.path.lower() != current_parsed.path.lower():
            continue

        qs = parse_qs(parsed.query)

        if "page" not in qs:
            continue

        try:
            page = int(qs["page"][0])
        except (ValueError, TypeError):
            continue

        base = parse_qs(parsed.query)
        base.pop("page", None)

        if base != current_base_query:
            continue

        if page <= current_page:
            continue

        if candidate is None or page < current_page_number(candidate):
            candidate = href

    return candidate


# SCRAPE SEARCH RESULT PAGES
def crawl_seed(seed_url: str) -> list[str]:
    """Crawl semua halaman pagination dari satu search URL."""
    detail_urls = []
    visited_pages = set()
    current_url = seed_url

    while current_url and current_url not in visited_pages:
        visited_pages.add(current_url)
        print(f"\n[PAGE] {current_url}")

        response = request_with_retry(current_url)
        soup = BeautifulSoup(response.text, "html.parser")

        page_links = extract_detail_links(soup, current_url)
        print(f"[INFO] Ditemukan {len(page_links)} detail links.")

        detail_urls.extend(page_links)

        next_url = find_next_search_url(soup, current_url)

        if not next_url:
            print("[INFO] Tidak ada halaman berikutnya.")
            break

        current_url = next_url

    return detail_urls


def download_pdf(item: Regulation) -> None:
    PDF_DIR.mkdir(parents=True, exist_ok=True)

    target = PDF_DIR / item.filename

    if target.exists() and target.stat().st_size > 0:
        item.local_path = str(target)
        print(f"[SKIP PDF] Sudah ada: {target.name}")
        return

    print(f"[PDF] {item.filename}")

    response = request_with_retry(item.pdf_url, stream=True)

    content_type = response.headers.get("Content-Type", "").lower()

    if "pdf" not in content_type and not item.pdf_url.lower().endswith(".pdf"):
        print(
            f"[WARN] Content-Type tidak terlihat sebagai PDF: {content_type}"
        )

    with target.open("wb") as f:
        for chunk in response.iter_content(chunk_size=DOWNLOAD_CHUNK_SIZE):
            if chunk:
                f.write(chunk)

    item.local_path = str(target)
    print(f"[OK PDF] {target}")


# SIMPAN METADATA
def save_metadata(items: list[Regulation]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    rows = [asdict(item) for item in items]

    with METADATA_JSON.open("w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)

    fieldnames = [
        "detail_url",
        "pdf_url",
        "title",
        "number",
        "year",
        "status",
        "effective_date",
        "source_info",
        "category",
        "filename",
        "local_path",
        "abstract",
    ]

    with METADATA_CSV.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\n[OK] Metadata JSON: {METADATA_JSON}")
    print(f"[OK] Metadata CSV : {METADATA_CSV}")


def main() -> None:
    if not SEED_URLS:
        raise SystemExit(
            "SEED_URLS masih kosong.\n"
            "Buka peraturan.bpk.go.id, lakukan pencarian untuk topik "
            "'pangan olahan' / 'obat' / 'sediaan farmasi', lalu copy URL "
            "hasil pencariannya ke SEED_URLS."
        )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    PDF_DIR.mkdir(parents=True, exist_ok=True)

    load_robots()

    all_detail_urls = []
    for seed_url in SEED_URLS:
        if "peraturan.bpk.go.id" not in urlparse(seed_url).netloc:
            print(f"[WARN] Seed URL dilewati karena bukan domain BPK: {seed_url}")
            continue

        all_detail_urls.extend(crawl_seed(seed_url))

    unique_detail_urls = list(dict.fromkeys(all_detail_urls))
    print(
        f"\n[INFO] Total detail URL unik yang ditemukan: "
        f"{len(unique_detail_urls)}"
    )

    selected: list[Regulation] = []

    for idx, detail_url in enumerate(unique_detail_urls, start=1):
        print(f"\n[DETAIL {idx}/{len(unique_detail_urls)}] {detail_url}")

        try:
            item = parse_detail_page(detail_url)
        except Exception as exc:
            print(f"[ERROR] Gagal parse {detail_url}: {exc}")
            continue

        if item is None:
            continue

        duplicate = next(
            (
                x
                for x in selected
                if x.number == item.number
                and x.year == item.year
                and item.number
            ),
            None,
        )

        if duplicate:
            print(f"[SKIP] Duplikasi: {item.title}")
            continue

        selected.append(item)

    print(f"\n[INFO] Regulasi terpilih: {len(selected)}")

    for idx, item in enumerate(selected, start=1):
        print(f"\n[DOWNLOAD {idx}/{len(selected)}]")
        try:
            download_pdf(item)
        except Exception as exc:
            print(f"[ERROR] Download gagal: {item.pdf_url}")
            print(f"        {exc}")

    save_metadata(selected)

    print("\n=== SELESAI ===")
    print(f"Folder dataset : {OUTPUT_DIR.resolve()}")
    print(f"Jumlah regulasi: {len(selected)}")
    print("Catatan: periksa kembali metadata dan status regulasi sebelum")
    print("memasukkannya ke pipeline embedding/vector database.")


if __name__ == "__main__":
    main()
