"""
cleaning.py
Fungsi-fungsi pembersihan teks hasil ekstraksi PDF.

Tujuan: menghapus noise (nomor halaman berulang, header/footer berulang,
karakter kontrol/bermasalah) TANPA menghilangkan isi regulasi (pasal, ayat,
angka, dsb).
"""

import re
import unicodedata
from collections import Counter


def normalize_unicode(text: str) -> str:
    """Normalisasi unicode (mis. ligatures, smart quotes) ke bentuk standar."""
    text = unicodedata.normalize("NFKC", text)
    return text


def remove_control_chars(text: str) -> str:
    """Hapus karakter kontrol yang tidak bermakna (kecuali newline & tab)."""
    return "".join(
        ch for ch in text
        if ch in ("\n", "\t") or unicodedata.category(ch)[0] != "C"
    )


def collapse_whitespace(text: str) -> str:
    """Rapikan spasi/baris kosong berlebih, tapi pertahankan struktur paragraf."""
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    return text.strip()


def detect_repeating_lines(pages_text: list[str], min_ratio: float = 0.6) -> set[str]:
    """
    Deteksi baris yang berulang di banyak halaman (kandidat header/footer,
    misalnya 'BADAN PENGAWAS OBAT DAN MAKANAN' atau nomor halaman berjalan).
    Baris yang muncul di >= min_ratio dari total halaman dianggap noise.
    """
    if not pages_text:
        return set()
    line_page_count = Counter()
    for page in pages_text:
        lines = {ln.strip() for ln in page.split("\n") if ln.strip()}
        for ln in lines:
            # Hanya pertimbangkan baris pendek sebagai kandidat header/footer
            if len(ln) <= 90:
                line_page_count[ln] += 1
    threshold = max(2, int(len(pages_text) * min_ratio))
    return {ln for ln, cnt in line_page_count.items() if cnt >= threshold}


def is_pure_page_number(line: str) -> bool:
    """Deteksi baris yang isinya cuma nomor halaman, mis. '12', '- 12 -', 'Halaman 12'."""
    stripped = line.strip()
    if not stripped:
        return False
    patterns = [
        r"^\d{1,4}$",
        r"^-\s*\d{1,4}\s*-$",
        r"^(hal(aman)?|page)\.?\s*\d{1,4}(\s*/\s*\d{1,4})?$",
        r"^\d{1,4}\s*/\s*\d{1,4}$",
    ]
    return any(re.match(p, stripped, flags=re.IGNORECASE) for p in patterns)


def clean_page_text(raw_text: str, repeating_lines: set[str] | None = None) -> str:
    """
    Bersihkan teks satu halaman:
    - normalisasi unicode
    - hapus karakter kontrol
    - buang baris nomor halaman murni
    - buang baris header/footer yang berulang di seluruh dokumen
    - rapikan whitespace
    """
    text = normalize_unicode(raw_text)
    text = remove_control_chars(text)

    repeating_lines = repeating_lines or set()
    cleaned_lines = []
    for line in text.split("\n"):
        stripped = line.strip()
        if is_pure_page_number(stripped):
            continue
        if stripped in repeating_lines:
            continue
        cleaned_lines.append(line)

    text = "\n".join(cleaned_lines)
    text = collapse_whitespace(text)
    return text


def clean_document_pages(pages_text: list[str]) -> list[str]:
    """Bersihkan seluruh halaman dokumen sekaligus (dengan deteksi header/footer)."""
    repeating = detect_repeating_lines(pages_text)
    return [clean_page_text(p, repeating) for p in pages_text]
