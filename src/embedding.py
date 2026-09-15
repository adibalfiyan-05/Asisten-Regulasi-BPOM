"""
embedding.py
Wrapper embedding model menggunakan 'intfloat/multilingual-e5-base'.
Model ini sangat efektif untuk pemahaman teks formal/hukum Bahasa Indonesia.
"""

from functools import lru_cache

MODEL_NAME = "intfloat/multilingual-e5-base"
FALLBACK_DIM = 768

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
        print("[PERINGATAN] Tidak bisa memuat model sentence-transformers. "
              "Menggunakan FALLBACK hashing embedding...")
        _fallback_warned = True
    vectorizer = _load_fallback_vectorizer()
    vectors = vectorizer.transform(texts)
    return vectors.toarray().tolist()


def embed_texts(texts: list[str], batch_size: int = 32) -> list[list[float]]:
    """Ubah list teks (passage/chunk) menjadi list vector embedding."""
    if not texts:
        return []
    try:
        model = _load_model()
        # Model E5 membutuhkan prefix 'passage: ' pada tiap dokumen
        prefixed_texts = [f"passage: {t}" for t in texts]
        embeddings = model.encode(
            prefixed_texts,
            batch_size=batch_size,
            show_progress_bar=False,
            normalize_embeddings=True,
        )
        return embeddings.tolist()
    except Exception:
        return _embed_fallback(texts)


def embed_query(query: str) -> list[float]:
    """Ubah pertanyaan pengguna menjadi vector. Model E5 membutuhkan prefix 'query: '."""
    try:
        model = _load_model()
        prefixed_query = f"query: {query}"
        embedding = model.encode(
            [prefixed_query],
            show_progress_bar=False,
            normalize_embeddings=True,
        )[0]
        return embedding.tolist()
    except Exception:
        return _embed_fallback([query])[0]