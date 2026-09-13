"""
pdf_extract.py
Ekstraksi teks PDF per halaman menggunakan PyMuPDF (fitz), sesuai rekomendasi
dokumen rencana proyek (bagian 5, langkah 2).

Kenapa per-halaman? Supaya setiap chunk nantinya bisa membawa informasi
nomor halaman -> dibutuhkan untuk citation ("Sumber: Dokumen X, hlm. Y").
"""

from dataclasses import dataclass

import fitz  # PyMuPDF


@dataclass
class PageContent:
    page_number: int  # 1-indexed, sesuai nomor halaman fisik
    text: str


def extract_pages(pdf_path: str) -> list[PageContent]:
    """
    Ekstrak teks dari setiap halaman PDF.
    Mengembalikan list PageContent (page_number 1-indexed, text mentah).
    """
    pages = []
    with fitz.open(pdf_path) as doc:
        for i, page in enumerate(doc):
            text = page.get_text("text")
            pages.append(PageContent(page_number=i + 1, text=text))
    return pages


def get_pdf_basic_info(pdf_path: str) -> dict:
    """Info dasar PDF: jumlah halaman & apakah ada text layer (bukan hasil scan)."""
    with fitz.open(pdf_path) as doc:
        n_pages = len(doc)
        sample_text_len = 0
        for page in doc:
            sample_text_len += len(page.get_text("text").strip())
            if sample_text_len > 20:
                break
        has_text_layer = sample_text_len > 20
    return {"n_pages": n_pages, "has_text_layer": has_text_layer}
