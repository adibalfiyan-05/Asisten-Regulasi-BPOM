"""
app.py - Asisten Regulasi BPOM
UI redesign: modern government-tech dashboard.
Jalankan dengan: streamlit run app.py
"""

import os
import sys
import html
import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from rag import generate_answer
from vector_store import count

st.set_page_config(
    page_title="Asisten Regulasi BPOM",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ============================================================
# DESIGN SYSTEM
# ============================================================

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

:root { --navy:#0b1736; --navy2:#122653; --blue:#2563eb; --text:#17233b;
        --muted:#758096; --line:#e5eaf2; --page:#f7f9fc; --white:#fff; }
* { font-family:'Inter',sans-serif; }
.stApp { background:var(--page); }
#MainMenu, footer { visibility:hidden; }
.block-container { max-width:1500px; padding:30px 42px 55px; }
[data-testid="stHeader"] { background:transparent; }

/* SIDEBAR */
[data-testid="stSidebar"] { background:linear-gradient(180deg,#091532 0%,#10234b 100%); border:0; }
[data-testid="stSidebar"] > div:first-child { padding:25px 19px; }
[data-testid="stSidebar"] * { color:#e8eefc; }
.brand { display:flex; align-items:center; gap:12px; margin:2px 8px 29px; }
.brand-mark { width:43px;height:43px;border-radius:13px;display:flex;align-items:center;justify-content:center;
 background:linear-gradient(145deg,#3987ff,#1956c9);font-size:21px;font-weight:800;box-shadow:0 10px 25px #06122d; }
.brand-title { font-size:15px;font-weight:800;line-height:1.1; }
.brand-sub { font-size:9px;color:#8da2cb!important;margin-top:4px; }
.side-label { margin:0 8px 8px;color:#6f84ab!important;font-size:9px;font-weight:800;letter-spacing:1.1px;text-transform:uppercase; }
.nav { padding:11px 12px;margin:3px 0;border-radius:10px;color:#aebbd4!important;font-size:11px;font-weight:650; }
.nav.active { color:#fff!important;background:rgba(64,128,245,.17);box-shadow:inset 3px 0 #4b91ff; }
.sys { margin:22px 4px 20px;padding:14px;border:1px solid rgba(255,255,255,.07);border-radius:14px;background:rgba(255,255,255,.045); }
.sys-head { display:flex;justify-content:space-between;font-size:10px;font-weight:700; }
.dot { display:inline-block;width:7px;height:7px;border-radius:50%;background:#35d58a;box-shadow:0 0 0 4px rgba(53,213,138,.1);margin-right:7px; }
.sys-num { margin-top:8px;font-size:25px;font-weight:800;letter-spacing:-1px; }
.sys-cap { color:#8095bc!important;font-size:9px; }
.side-line { height:1px;background:rgba(255,255,255,.08);margin:20px 4px; }
[data-testid="stSidebar"] .stSelectbox label,[data-testid="stSidebar"] .stSlider label { color:#aebdd8!important;font-size:10px!important;font-weight:600!important; }
[data-testid="stSidebar"] [data-baseweb="select"] > div { background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.09);border-radius:10px; }
.disclaimer { color:#7f91b4!important;font-size:9px;line-height:1.65;margin:4px 5px; }
.side-footer { color:#62769e!important;font-size:9px;line-height:1.5;margin:27px 7px 0;padding-top:14px;border-top:1px solid rgba(255,255,255,.07); }

/* HERO */
.hero { position:relative;overflow:hidden;min-height:245px;border-radius:24px;padding:35px 41px;display:flex;align-items:center;
 background:radial-gradient(circle at 82% 25%,rgba(87,163,255,.32),transparent 27%),radial-gradient(circle at 94% 90%,rgba(26,94,218,.3),transparent 31%),linear-gradient(112deg,#10295c,#173e7b 55%,#0f316b);box-shadow:0 18px 42px rgba(18,43,86,.13); }
.hero:after { content:"";position:absolute;width:320px;height:320px;border:1px solid rgba(255,255,255,.1);border-radius:50%;right:55px;top:-165px;box-shadow:0 0 0 46px rgba(255,255,255,.018),0 0 0 94px rgba(255,255,255,.012); }
.hero-content { position:relative;z-index:2;max-width:760px; }
.eyebrow { color:#b8d3ff!important;font-size:11px;font-weight:650;letter-spacing:.2px; }
.hero h1 { color:#fff!important;font-size:35px;line-height:1.1;font-weight:800;letter-spacing:-1.4px;margin:8px 0 12px; }
.hero h1 span { color:#82b7ff; }
.hero p { color:#d2e0f8!important;font-size:12px;line-height:1.7;max-width:620px;margin:0; }
.badge { display:inline-block;margin-top:16px;padding:6px 10px;border-radius:999px;background:rgba(255,255,255,.09);border:1px solid rgba(255,255,255,.1);color:#e5efff!important;font-size:9px;font-weight:650; }

/* SEARCH */
.section-title { color:#1b2943;font-size:14px;font-weight:800;margin:27px 0 5px; }
.section-sub { color:#818b9e;font-size:10px;margin-bottom:9px; }
div[data-testid="stTextInput"] > div { background:#fff;border:1px solid #dfe5ee;border-radius:15px;min-height:53px;box-shadow:0 7px 24px rgba(23,35,59,.055); }
div[data-testid="stTextInput"] > div:focus-within { border-color:#7aa8f8;box-shadow:0 0 0 4px rgba(37,99,235,.08); }
div[data-testid="stTextInput"] input { color:#1a2740;font-size:12px;font-weight:500; }
div[data-testid="stTextInput"] input::placeholder { color:#a1a9b8; }
div[data-testid="stTextInput"] label { display:none; }
.stButton > button { border-radius:11px;min-height:40px;border:1px solid #e2e7ef;background:#fff;color:#2a3750;font-size:10px;font-weight:650;transition:.18s; }
.stButton > button:hover { border-color:#b9cdf1;color:#1f5fc8;transform:translateY(-1px); }
.stButton > button[kind="primary"] { background:linear-gradient(135deg,#2b6de9,#1957c8);border:0;color:#fff;min-height:53px;font-size:11px;font-weight:700;box-shadow:0 9px 22px rgba(37,99,235,.2); }
.stButton > button[kind="primary"]:hover { color:#fff;box-shadow:0 12px 26px rgba(37,99,235,.28); }

/* QUICK */
.quick-head { display:flex;justify-content:space-between;align-items:baseline;margin-top:27px;margin-bottom:10px; }
.quick-title { font-size:14px;font-weight:800;color:#1b2943; }
.quick-sub { color:#8a93a3;font-size:9px; }
.qcard { min-height:105px;border-radius:15px;padding:14px;border:1px solid transparent; }
.qblue{background:#eef5ff;border-color:#dceaff}.qgreen{background:#effbf4;border-color:#dff3e7}.qpurple{background:#f5f1ff;border-color:#e9ddff}
.qicon { width:28px;height:28px;border-radius:9px;display:flex;align-items:center;justify-content:center;font-size:13px;margin-bottom:9px;background:#fff; }
.qquestion { color:#27344d;font-size:10px;line-height:1.55;font-weight:650; }

/* RESULTS */
.result-title { margin:31px 0 11px;font-size:14px;color:#1a2943;font-weight:800; }
.answer-card,.source-panel { background:#fff;border:1px solid var(--line);border-radius:18px;box-shadow:0 8px 26px rgba(26,42,68,.045); }
.answer-head { padding:19px 22px 15px;border-bottom:1px solid #edf0f5;display:flex;align-items:center;gap:9px; }
.answer-icon { width:30px;height:30px;border-radius:9px;background:#e9f2ff;color:#2468df;display:flex;align-items:center;justify-content:center;font-size:14px; }
.answer-head span { font-size:12px;font-weight:800;color:#24334e; }
.answer-body { padding:20px 22px; }
.answer-body p,.answer-body li { color:#4b5669;font-size:11px;line-height:1.8; }
.answer-body h1,.answer-body h2,.answer-body h3 { color:#26354e;font-size:13px; }
.note { margin-top:16px;padding:11px 13px;border-radius:11px;background:#f5f8fd;border-left:3px solid #5b8eea;color:#657188;font-size:9px;line-height:1.65; }
.source-panel { padding:18px; }
.source-head { color:#25334d;font-size:12px;font-weight:800;margin-bottom:12px; }
.count { padding:3px 7px;border-radius:999px;background:#eef5ff;color:#3470d4;font-size:8px;margin-left:5px; }
.source-item { border:1px solid #edf0f5;border-radius:12px;padding:11px;margin-bottom:8px;background:#fbfcfe; }
.source-item:last-child{margin-bottom:0}.source-title{color:#2b3850;font-size:10px;font-weight:750;line-height:1.4}.source-index{display:inline-flex;width:21px;height:21px;align-items:center;justify-content:center;border-radius:7px;background:#edf4ff;color:#2867cf;font-size:8px;font-weight:800;margin-right:7px}.source-meta{color:#818b9d;font-size:8.5px;line-height:1.6;margin-top:6px}.source-snippet{color:#667184;font-size:8.5px;line-height:1.6;margin-top:7px;padding-top:7px;border-top:1px solid #edf0f4}.source-link{display:inline-block;margin-top:7px;color:#2867cf!important;font-size:8.5px;font-weight:700;text-decoration:none}.empty{padding:30px;text-align:center;color:#8791a1;font-size:10px;border:1px dashed #dce2ec;border-radius:14px;}
[data-testid="stAlert"]{border-radius:12px;font-size:10px}
@media(max-width:900px){.block-container{padding:20px}.hero h1{font-size:28px}.hero{padding:28px}.hero:after{right:-110px}}
</style>
""", unsafe_allow_html=True)

# ============================================================
# SIDEBAR
# ============================================================

total_chunks = count()

with st.sidebar:
    st.markdown(f"""
    <div class="brand"><div class="brand-mark">⚖</div><div>
        <div class="brand-title">BPOM REGULASI</div><div class="brand-sub">AI Regulatory Assistant</div>
    </div></div>
    <div class="side-label">Menu</div>
    <div class="nav active">⌂ &nbsp; Beranda</div>
    <div class="nav">◷ &nbsp; Riwayat Pertanyaan</div>
    <div class="nav">ⓘ &nbsp; Tentang Aplikasi</div>
    <div class="sys"><div class="sys-head"><span><span class="dot"></span>Sistem Aktif</span><span>●</span></div>
      <div class="sys-num">{total_chunks}</div><div class="sys-cap">chunk regulasi ter-index</div></div>
    <div class="side-label">Filter Data</div>
    """, unsafe_allow_html=True)

    topic_filter = st.selectbox(
        "Topik Dokumen",
        ["Semua Topik", "Pangan", "Obat", "Registrasi", "Label / Otentikasi"],
    )
    top_k_val = st.slider("Jumlah Chunk Diambil (top-k)", 3, 12, 8)

    st.markdown("""
    <div class="side-line"></div>
    <div class="disclaimer"><strong>Catatan Penafian</strong><br>
    Sistem ini merupakan asisten informasi berbasis dokumen resmi. Jawaban bukan pengganti keputusan hukum, medis, atau keputusan resmi BPOM.</div>
    <div class="side-footer">Asisten Regulasi BPOM<br>Pangan &amp; Obat · RAG System</div>
    """, unsafe_allow_html=True)

# ============================================================
# HERO
# ============================================================

st.markdown("""
<section class="hero"><div class="hero-content">
<div class="eyebrow">SELAMAT DATANG DI</div>
<h1>Asisten Regulasi <span>BPOM</span></h1>
<p>Temukan informasi regulasi pangan dan obat secara lebih cepat melalui pencarian berbasis dokumen resmi dan teknologi Retrieval-Augmented Generation (RAG).</p>
<div class="badge">✦ &nbsp; Informasi berbasis dokumen regulasi</div>
</div></section>
""", unsafe_allow_html=True)

# ============================================================
# SEARCH
# ============================================================

st.markdown('<div class="section-title">Cari Informasi Regulasi</div><div class="section-sub">Ketik pertanyaan Anda secara natural. Sistem akan mencari dokumen yang paling relevan.</div>', unsafe_allow_html=True)

default_q = st.session_state.get("query_input", "")
search_col, button_col = st.columns([5.8, 1.15], gap="small")
with search_col:
    user_query = st.text_input(
        "Masukkan pertanyaan Anda terkait regulasi BPOM:",
        value=default_q,
        placeholder="Contoh: Apa saja informasi yang wajib dicantumkan pada label pangan?",
        label_visibility="collapsed",
    )
with button_col:
    search_clicked = st.button("⌕  Cari & Jawab", type="primary", use_container_width=True)

# ============================================================
# QUICK QUESTIONS
# ============================================================

st.markdown('<div class="quick-head"><div class="quick-title">Pertanyaan Cepat</div><div class="quick-sub">Pilih salah satu untuk mencoba</div></div>', unsafe_allow_html=True)

questions = [
    ("qblue", "⌕", "Apa syarat dan kewajiban dalam Standar Cara Distribusi Obat yang Baik?"),
    ("qgreen", "▤", "Bagaimana tata laksana pengajuan persetujuan obat pengembangan baru?"),
    ("qpurple", "✓", "Apa ketentuan perizinan berusaha berbasis risiko untuk subsektor obat dan makanan?"),
]
cols = st.columns(3, gap="small")
for i, (cls, icon, question) in enumerate(questions, start=1):
    with cols[i - 1]:
        st.markdown(f'<div class="qcard {cls}"><div class="qicon">{icon}</div><div class="qquestion">{question}</div></div>', unsafe_allow_html=True)
        if st.button("Gunakan pertanyaan ini", key=f"quick_{i}", use_container_width=True):
            st.session_state["query_input"] = question
            st.rerun()

# ============================================================
# SEARCH RESULT
# ============================================================

if search_clicked:
    if not user_query.strip():
        st.warning("Silakan masukkan pertanyaan terlebih dahulu.")
    else:
        with st.spinner("Mencari dokumen relevan dan menyusun jawaban..."):
            selected_topic = None if topic_filter == "Semua Topik" else topic_filter
            response = generate_answer(user_query, top_k=top_k_val, topic_filter=selected_topic)

        st.markdown('<div class="result-title">Hasil Pencarian</div>', unsafe_allow_html=True)
        result_col, source_col = st.columns([1.25, .85], gap="large")

        with result_col:
            st.markdown('<div class="answer-card"><div class="answer-head"><div class="answer-icon">✦</div><span>Jawaban Asisten</span></div><div class="answer-body">', unsafe_allow_html=True)
            st.markdown(response["answer"])
            st.markdown('<div class="note"><strong>Informasi penting:</strong> Jawaban disusun berdasarkan dokumen yang berhasil ditemukan oleh sistem. Selalu periksa sumber regulasi resmi untuk keputusan yang bersifat formal.</div></div></div>', unsafe_allow_html=True)

        with source_col:
            sources = response.get("sources", [])
            st.markdown(f'<div class="source-panel"><div class="source-head">📚 Sumber Referensi <span class="count">{len(sources)} sumber</span></div>', unsafe_allow_html=True)
            if not sources:
                st.markdown('<div class="empty">⌕<br><br>Tidak ada dokumen sumber yang digunakan.</div>', unsafe_allow_html=True)
            else:
                for idx, src in enumerate(sources, start=1):
                    title = html.escape(str(src.get("title", "Dokumen Regulasi")))
                    filename = html.escape(str(src.get("filename", "-")))
                    page_start = html.escape(str(src.get("page_start", "-")))
                    page_end = html.escape(str(src.get("page_end", "-")))
                    pasal = html.escape(str(src.get("pasal"))) if src.get("pasal") else ""
                    snippet = html.escape(str(src.get("snippet", "")))
                    url = src.get("source_url")
                    pasal_html = f'<br><strong>Pasal/Bab:</strong> {pasal}' if pasal else ""
                    link_html = f'<a class="source-link" href="{html.escape(str(url), quote=True)}" target="_blank">↗ Buka Dokumen Resmi</a>' if url else ""
                    st.markdown(f'''<div class="source-item"><div><span class="source-index">{idx}</span><span class="source-title">{title}</span></div>
                    <div class="source-meta"><strong>File:</strong> {filename}<br><strong>Halaman:</strong> {page_start} - {page_end}{pasal_html}</div>
                    <div class="source-snippet"><strong>Konteks:</strong> "{snippet}"</div>{link_html}</div>''', unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)
