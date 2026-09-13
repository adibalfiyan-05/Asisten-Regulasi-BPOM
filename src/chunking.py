"""
chunking.py
Memecah teks dokumen (yang sudah dibersihkan, per halaman) menjadi chunk-chunk
untuk di-embed, dengan tetap mempertahankan informasi struktural dokumen
peraturan Indonesia: BAB, Pasal, Ayat, dan nomor halaman.

Strategi (sesuai dokumen rencana proyek bagian 5 langkah 4):
1. Gabungkan seluruh halaman jadi satu teks panjang, tapi tetap simpan
   pemetaan karakter -> nomor halaman.
2. Deteksi batas "Pasal N" dan "BAB ..." dengan regex -> ini adalah unit
   semantik alami dalam dokumen regulasi.
3. Jika satu Pasal terlalu panjang (> max_chars), pecah lagi menjadi
   sub-chunk berbasis ukuran karakter dengan overlap, supaya konteks tidak
   terputus tajam.
4. Jika dokumen TIDAK punya struktur Pasal/BAB (mis. FAQ, pedoman umum),
   fallback ke chunking berbasis paragraf + ukuran karakter.

Catatan: kita pakai pendekatan berbasis karakter (bukan token) karena tidak
mau menambah dependency tokenizer yang berat. 1 token GPT/Claude-like kira-kira
~4 karakter, jadi max_chars=1600 kira-kira setara ~350-450 token.
"""

import re
from dataclasses import dataclass, field

# --- Pola regex untuk struktur dokumen regulasi Indonesia ---
BAB_PATTERN = re.compile(r"^\s*BAB\s+[IVXLCDM0-9]+\b.*$", re.IGNORECASE | re.MULTILINE)
PASAL_PATTERN = re.compile(r"^\s*Pasal\s+\d+[A-Za-z]?\s*$", re.MULTILINE)


@dataclass
class PageMarker:
    char_start: int
    page_number: int


@dataclass
class Chunk:
    text: str
    page_start: int
    page_end: int
    bab: str | None = None
    pasal: str | None = None
    chunk_index: int = 0
    extra: dict = field(default_factory=dict)


def _build_full_text_with_page_map(pages: list[tuple[int, str]]) -> tuple[str, list[PageMarker]]:
    """
    Gabungkan list (page_number, text) menjadi satu string, sambil mencatat
    di karakter offset berapa setiap halaman dimulai. Ini dipakai untuk
    menentukan page_start/page_end dari sebuah chunk berdasarkan posisi
    karakternya di full_text.
    """
    full_text_parts = []
    markers = []
    offset = 0
    for page_number, text in pages:
        markers.append(PageMarker(char_start=offset, page_number=page_number))
        full_text_parts.append(text)
        offset += len(text) + 1  # +1 untuk separator newline
    full_text = "\n".join(full_text_parts)
    return full_text, markers


def _page_range_for_span(markers: list[PageMarker], start: int, end: int) -> tuple[int, int]:
    """Cari page_start & page_end untuk rentang karakter [start, end)."""
    page_start = markers[0].page_number
    page_end = markers[0].page_number
    for m in markers:
        if m.char_start <= start:
            page_start = m.page_number
        if m.char_start < end:
            page_end = m.page_number
    return page_start, page_end


def _last_bab_before(full_text: str, pos: int) -> str | None:
    match = None
    for m in BAB_PATTERN.finditer(full_text, 0, pos):
        match = m
    return match.group(0).strip() if match else None


def _split_by_size(text: str, max_chars: int, overlap: int) -> list[tuple[int, int]]:
    """
    Pecah `text` menjadi list rentang (start, end) berukuran maksimal
    max_chars dengan overlap antar potongan, mencoba memotong di batas
    kalimat/paragraf terdekat agar tidak memotong kata di tengah.
    """
    spans = []
    n = len(text)
    if n <= max_chars:
        return [(0, n)]

    start = 0
    while start < n:
        end = min(start + max_chars, n)
        if end < n:
            # coba mundur ke batas paragraf/kalimat terdekat supaya tidak
            # memotong kalimat di tengah
            window = text[start:end]
            cut = max(window.rfind("\n\n"), window.rfind(". "), window.rfind("\n"))
            if cut > max_chars * 0.5:
                end = start + cut + 1
        spans.append((start, end))
        if end >= n:
            break
        start = max(end - overlap, start + 1)
    return spans


def chunk_document(
    pages: list[tuple[int, str]],
    max_chars: int = 1600,
    overlap: int = 200,
    min_chunk_chars: int = 40,
) -> list[Chunk]:
    """
    Chunk utama. Input: list of (page_number, cleaned_text_of_that_page).
    Output: list of Chunk, masing-masing membawa page_start/page_end dan
    (jika terdeteksi) nama BAB & nomor Pasal.
    """
    pages = [(pn, t) for pn, t in pages if t and t.strip()]
    if not pages:
        return []

    full_text, markers = _build_full_text_with_page_map(pages)

    pasal_matches = list(PASAL_PATTERN.finditer(full_text))

    chunks: list[Chunk] = []

    if pasal_matches:
        # Dokumen berstruktur Pasal -> potong per Pasal (unit semantik alami)
        boundaries = [m.start() for m in pasal_matches] + [len(full_text)]
        # Teks sebelum Pasal pertama (mis. bagian "Menimbang/Mengingat") jadi
        # satu chunk pembuka tersendiri jika cukup panjang.
        if boundaries[0] > min_chunk_chars:
            intro = full_text[0:boundaries[0]].strip()
            if len(intro) >= min_chunk_chars:
                chunks.extend(
                    _finalize_segment(intro, 0, boundaries[0], full_text, markers, max_chars, overlap)
                )

        for i, m in enumerate(pasal_matches):
            seg_start = m.start()
            seg_end = boundaries[i + 1]
            segment = full_text[seg_start:seg_end].strip()
            if len(segment) < min_chunk_chars:
                continue
            pasal_label = m.group(0).strip()
            chunks.extend(
                _finalize_segment(
                    segment, seg_start, seg_end, full_text, markers, max_chars, overlap,
                    pasal_label=pasal_label,
                )
            )
    else:
        # Fallback: tidak ada struktur Pasal terdeteksi -> chunk per ukuran,
        # coba potong di batas paragraf.
        paragraphs = [p for p in re.split(r"\n\s*\n", full_text) if p.strip()]
        cursor = 0
        buffer = ""
        buffer_start = 0
        for para in paragraphs:
            para_pos = full_text.find(para, cursor)
            if para_pos == -1:
                para_pos = cursor
            cursor = para_pos + len(para)

            if not buffer:
                buffer_start = para_pos
            if len(buffer) + len(para) + 2 <= max_chars:
                buffer = f"{buffer}\n\n{para}" if buffer else para
            else:
                if buffer.strip():
                    chunks.extend(
                        _finalize_segment(
                            buffer, buffer_start, buffer_start + len(buffer),
                            full_text, markers, max_chars, overlap,
                        )
                    )
                buffer = para
                buffer_start = para_pos
        if buffer.strip():
            chunks.extend(
                _finalize_segment(
                    buffer, buffer_start, buffer_start + len(buffer),
                    full_text, markers, max_chars, overlap,
                )
            )

    for idx, c in enumerate(chunks):
        c.chunk_index = idx
    return chunks


def _finalize_segment(
    segment_text: str,
    seg_start: int,
    seg_end: int,
    full_text: str,
    markers: list[PageMarker],
    max_chars: int,
    overlap: int,
    pasal_label: str | None = None,
) -> list[Chunk]:
    """Jika segmen (biasanya 1 Pasal) masih terlalu panjang, pecah lagi per ukuran."""
    bab = _last_bab_before(full_text, seg_start)
    sub_spans = _split_by_size(segment_text, max_chars, overlap)
    out = []
    for s, e in sub_spans:
        abs_start = seg_start + s
        abs_end = seg_start + e
        page_start, page_end = _page_range_for_span(markers, abs_start, abs_end)
        out.append(
            Chunk(
                text=segment_text[s:e].strip(),
                page_start=page_start,
                page_end=page_end,
                bab=bab,
                pasal=pasal_label,
            )
        )
    return out
