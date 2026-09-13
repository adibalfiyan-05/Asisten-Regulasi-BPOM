"""
embedding.py
Wrapper embedding model. Default: sentence-transformers model multilingual
yang mendukung Bahasa Indonesia, jalan lokal (gratis, tanpa API key) --
cocok untuk tugas kuliah dengan budget terbatas.

Model default: 'paraphrase-multilingual-MiniLM-L12-v2'
- Ukuran kecil (~470MB), cukup cepat di CPU.
- Mendukung 50+ bahasa termasuk Indonesia.
- Kalau butuh kualitas lebih tinggi & device kuat, bisa ganti ke
  'intfloat/multilingual-e5-base' (tinggal ubah MODEL_NAME).

CATATAN OFFLINE FALLBACK:
Saat model pertama kali dipakai, sentence-transformers perlu mengunduh
bobot model dari HuggingFace (butuh internet, sekali saja -- setelah itu
otomatis pakai cache lokal). Kalau tidak ada koneksi internet sama sekali
(mis. environment kampus yang firewall-nya ketat), modul ini otomatis
JATUH KE fallback embedding berbasis hashing (scikit-learn HashingVectorizer)
supaya pipeline TETAP BISA di-demo end-to-end, dengan peringatan di console.
Fallback ini bukan semantic embedding sungguhan (hanya bag-of-words hashing),
jadi kualitas retrieval-nya lebih rendah -- pastikan koneksi internet ada
minimal sekali saat run pertama supaya model asli ke-download & ke-cache.
"""

from functools import lru_cache

MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"
FALLBACK_DIM = 384

_fallback_warned = False


@lru_cache(maxsize=1)
def _load_model():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(MODEL_NAME)


@lru_cache(maxsize=1)
def _load_fallback_vectorizer():
    from sklearn.feature_extraction.text import HashingVectorizer
    return HashingVectorizer(
        n_features=FALLBACK_DIM,
        alternate_sign=False,
        norm="l2",
        ngram_range=(1, 2),
        analyzer="word",
    )


def _embed_fallback(texts: list[str]) -> list[list[float]]:
    global _fallback_warned
    if not _fallback_warned:
        print("[PERINGATAN] Tidak bisa memuat model sentence-transformers "
              "(kemungkinan tidak ada koneksi internet untuk unduh model dari "
              "HuggingFace). Menggunakan FALLBACK hashing embedding -- ini "
              "cukup untuk menguji pipeline, TAPI kualitas retrieval lebih "
              "rendah dibanding embedding semantik asli. Jalankan ulang saat "
              "ada internet supaya model asli ter-cache secara permanen.")
        _fallback_warned = True
    vectorizer = _load_fallback_vectorizer()
    vectors = vectorizer.transform(texts)
    return vectors.toarray().tolist()


def embed_texts(texts: list[str], batch_size: int = 32) -> list[list[float]]:
    """Ubah list teks menjadi list vector embedding."""
    if not texts:
        return []
    try:
        model = _load_model()
        embeddings = model.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=False,
            normalize_embeddings=True,  # supaya cosine similarity setara dot product
        )
        return embeddings.tolist()
    except Exception:
        return _embed_fallback(texts)


def embed_query(query: str) -> list[float]:
    """Ubah satu pertanyaan pengguna menjadi vector (untuk retrieval)."""
    return embed_texts([query])[0]
