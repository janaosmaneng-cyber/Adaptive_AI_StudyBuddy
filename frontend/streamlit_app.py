"""AdaptiveAI StudyBuddy - the Streamlit front end (Phase 2, step 3).

Run (from this folder):  streamlit run streamlit_app.py
It talks to the FastAPI backend (Kaggle + ngrok) and keeps all student progress
locally in SQLite through student_data.StudentStore.
"""
import html
import inspect
import os
import random

import altair as alt
import pandas as pd
import streamlit as st

from api_client import ApiError, Backend
from student_data import QUALITY, StudentStore
from student_data import srs

st.set_page_config(page_title="StudyBuddy AI", page_icon="🦄", layout="wide")

# --------------------------------------------------------------------------- constants
PALETTE = ["#ff6b9d", "#7c4dff", "#00b8e6", "#ffb300", "#26d07c", "#ff7a45", "#c04bff", "#00bfa5"]
STATUS = {  # status -> (emoji, friendly name, colour)
    "new": ("🌱", "Not started", "#00b8e6"),
    "weak": ("🔥", "Needs love", "#ff4f6d"),
    "learning": ("📈", "Getting there", "#ffa000"),
    "strong": ("🏆", "Mastered", "#1fbf75"),
}
NAV_HOME, NAV_CHAT, NAV_QUIZ, NAV_CARDS, NAV_PROGRESS = (
    "🏠 Home", "💬 Ask the Owl", "🎯 Quiz Time", "🃏 Flashcards", "📊 My Progress",
)
PAGES = [NAV_HOME, NAV_CHAT, NAV_QUIZ, NAV_CARDS, NAV_PROGRESS]

# st.button / st.altair_chart changed their "full width" argument across versions.
BTN_WIDE = {"width": "stretch"} if "width" in inspect.signature(st.button).parameters else {"use_container_width": True}
CHART_WIDE = {"width": "stretch"} if "width" in inspect.signature(st.altair_chart).parameters else {"use_container_width": True}

esc = html.escape


def md(markup):
    """Render HTML without Markdown turning indented lines into code blocks."""
    st.markdown("\n".join(line.strip() for line in markup.splitlines()), unsafe_allow_html=True)


def nl2br(text):
    return esc(text or "").replace("\n", "<br>")


# --------------------------------------------------------------------------- styling
CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Baloo+2:wght@600;700;800&family=Nunito:wght@400;600;700;800&display=swap');
html, body, [class*="css"], .stApp { font-family: 'Nunito', 'Segoe UI', sans-serif; }
h1, h2, h3, .brand, .hero-title { font-family: 'Baloo 2', 'Nunito', sans-serif !important; }

.stApp {
  background:
    radial-gradient(circle at 8% 12%, rgba(255,107,157,.22), transparent 38%),
    radial-gradient(circle at 92% 8%, rgba(0,184,230,.20), transparent 36%),
    radial-gradient(circle at 80% 92%, rgba(124,77,255,.20), transparent 40%),
    radial-gradient(circle at 12% 88%, rgba(255,179,0,.20), transparent 38%),
    #fff7fd;
}
/* glitter: two layers of tiny coloured stars that twinkle in turns */
.stApp::before, .stApp::after {
  content: ""; position: fixed; inset: 0; pointer-events: none; z-index: 0;
}
.stApp::before {
  background-image:
    radial-gradient(3px 3px at 6% 20%, #ffd23f, transparent), radial-gradient(2px 2px at 18% 70%, #ff6b9d, transparent),
    radial-gradient(3px 3px at 30% 40%, #7c4dff, transparent), radial-gradient(2px 2px at 44% 85%, #00b8e6, transparent),
    radial-gradient(3px 3px at 58% 15%, #ff6b9d, transparent), radial-gradient(2px 2px at 71% 55%, #ffd23f, transparent),
    radial-gradient(3px 3px at 84% 30%, #26d07c, transparent), radial-gradient(2px 2px at 95% 78%, #7c4dff, transparent);
  animation: twinkleA 3.2s ease-in-out infinite alternate;
}
.stApp::after {
  background-image:
    radial-gradient(2px 2px at 12% 45%, #00b8e6, transparent), radial-gradient(3px 3px at 25% 10%, #ffd23f, transparent),
    radial-gradient(2px 2px at 38% 62%, #ff6b9d, transparent), radial-gradient(3px 3px at 52% 92%, #7c4dff, transparent),
    radial-gradient(2px 2px at 66% 35%, #26d07c, transparent), radial-gradient(3px 3px at 78% 8%, #ff7a45, transparent),
    radial-gradient(2px 2px at 90% 60%, #ffd23f, transparent), radial-gradient(3px 3px at 98% 25%, #ff6b9d, transparent);
  animation: twinkleB 3.2s ease-in-out infinite alternate;
}
@keyframes twinkleA { from { opacity: .15; transform: scale(.9);} to { opacity: 1; transform: scale(1.15);} }
@keyframes twinkleB { from { opacity: 1; transform: scale(1.1);} to { opacity: .15; transform: scale(.9);} }

/* floating study emojis */
.floaty { position: fixed; inset: 0; pointer-events: none; z-index: 0; overflow: hidden; }
.floaty span { position: absolute; bottom: -60px; font-size: 28px; opacity: .0; animation: floatUp linear infinite; }
@keyframes floatUp {
  0% { transform: translateY(0) rotate(0deg); opacity: 0; }
  10% { opacity: .35; } 90% { opacity: .35; }
  100% { transform: translateY(-115vh) rotate(25deg); opacity: 0; }
}
.block-container { position: relative; z-index: 1; padding-top: 2rem; }

/* hero */
.hero { border-radius: 28px; padding: 1.6rem 2rem; margin-bottom: 1.2rem; color: white;
  background: linear-gradient(120deg, #ff6b9d, #7c4dff 45%, #00b8e6 80%, #26d07c);
  background-size: 300% 300%; animation: shimmer 9s ease infinite;
  box-shadow: 0 14px 40px rgba(124,77,255,.35); position: relative; overflow: hidden; }
.hero::after { content: "✨"; position: absolute; right: 24px; top: 8px; font-size: 64px; opacity: .35; animation: spin 12s linear infinite; }
.hero-title { font-size: 2.3rem; font-weight: 800; line-height: 1.1; margin: 0; text-shadow: 0 2px 10px rgba(0,0,0,.18); }
.hero-sub { font-size: 1.05rem; opacity: .95; margin-top: .35rem; }
@keyframes shimmer { 0%{background-position:0% 50%} 50%{background-position:100% 50%} 100%{background-position:0% 50%} }
@keyframes spin { to { transform: rotate(360deg); } }

/* cards */
.card { border-radius: 22px; padding: 1rem 1.2rem; margin-bottom: .8rem; border: 3px solid transparent;
  background: linear-gradient(#ffffff, #ffffff) padding-box, linear-gradient(135deg, var(--c1,#ff6b9d), var(--c2,#7c4dff)) border-box;
  box-shadow: 0 8px 26px rgba(124,77,255,.14); transition: transform .18s ease, box-shadow .18s ease; }
.card:hover { transform: translateY(-4px) rotate(-.4deg); box-shadow: 0 14px 34px rgba(124,77,255,.28); }
.card h4 { margin: 0 0 .25rem 0; font-family: 'Baloo 2', sans-serif; color: #2d1b4e; }
.muted { color: #7a6a9a; font-size: .88rem; }
.pill { display: inline-block; padding: .12rem .7rem; border-radius: 999px; font-size: .8rem; font-weight: 800; color: white;
  background: var(--pc, #7c4dff); margin-right: .35rem; }
.pill.soft { background: #f0e6ff; color: #5b34c9; }

/* flashcard */
.flash { border-radius: 30px; padding: 2.4rem 2rem; text-align: center; min-height: 190px; display: flex; flex-direction: column;
  justify-content: center; align-items: center; color: white; font-size: 1.45rem; font-weight: 800;
  background: linear-gradient(135deg, #7c4dff, #ff6b9d); box-shadow: 0 16px 40px rgba(124,77,255,.35); animation: pop .35s ease; }
.flash.back { background: linear-gradient(135deg, #00b8e6, #26d07c); font-size: 1.15rem; font-weight: 700; }
.flash small { font-size: .85rem; opacity: .85; font-weight: 700; margin-bottom: .6rem; letter-spacing: .08em; }
@keyframes pop { from { transform: scale(.94) rotateX(25deg); opacity: .2; } to { transform: scale(1) rotateX(0); opacity: 1; } }

/* mastery bars */
.bar { height: 16px; border-radius: 999px; background: #efe6ff; overflow: hidden; margin-top: .35rem; }
.bar > div { height: 100%; border-radius: 999px; background: var(--bc); background-image: linear-gradient(90deg, rgba(255,255,255,.35), transparent);
  animation: grow .9s ease; }
@keyframes grow { from { width: 0 !important; } }

/* score ring */
.score { width: 150px; height: 150px; border-radius: 50%; margin: 0 auto 1rem auto; display: flex; align-items: center; justify-content: center;
  font-family: 'Baloo 2', sans-serif; font-size: 2.3rem; font-weight: 800; color: #2d1b4e;
  background: radial-gradient(#fff 58%, transparent 60%), conic-gradient(var(--sc) calc(var(--pct) * 1%), #efe6ff 0);
  box-shadow: 0 10px 30px rgba(124,77,255,.25); }

/* widgets */
.stButton > button, [data-testid="stBaseButton-secondary"], [data-testid="stBaseButton-primary"] {
  border-radius: 999px; font-weight: 800; border: 0; padding: .55rem 1.3rem; transition: transform .15s ease, box-shadow .15s ease; }
.stButton > button[kind="primary"], [data-testid="stBaseButton-primary"] {
  background: linear-gradient(120deg, #ff4f9a, #7c4dff); color: white; box-shadow: 0 6px 18px rgba(255,79,154,.4); }
.stButton > button[kind="secondary"], [data-testid="stBaseButton-secondary"] {
  background: white; color: #5b34c9; box-shadow: 0 4px 14px rgba(124,77,255,.2); border: 2px solid #e4d4ff; }
.stButton > button:hover, [data-testid^="stBaseButton"]:hover { transform: translateY(-2px) scale(1.03); box-shadow: 0 10px 24px rgba(124,77,255,.35); }
[data-testid="stSidebar"] { background: linear-gradient(180deg, #f6e9ff, #e6f7ff 60%, #e9ffef); border-right: 3px solid #fff; }
[data-testid="stSidebar"] .stRadio label { font-weight: 800; font-size: 1.02rem; }
.brand { font-size: 1.9rem; font-weight: 800; background: linear-gradient(90deg, #ff4f9a, #7c4dff, #00b8e6); -webkit-background-clip: text;
  background-clip: text; -webkit-text-fill-color: transparent; background-size: 200%; animation: shimmer 6s ease infinite; }
.tagline { color: #7a6a9a; font-weight: 700; margin-bottom: .6rem; }
.level { border-radius: 16px; padding: .5rem .8rem; background: linear-gradient(120deg, #fff4c2, #ffe0f0); font-weight: 800; color: #6a3d00; text-align: center; }
[data-testid="stMetric"] { background: white; border-radius: 20px; padding: .8rem 1rem; box-shadow: 0 6px 20px rgba(124,77,255,.15); border: 2px solid #f0e6ff; }
[data-testid="stChatMessage"] { background: rgba(255,255,255,.88); border-radius: 22px; box-shadow: 0 4px 16px rgba(124,77,255,.12); }
.stTabs [data-baseweb="tab"] { font-weight: 800; border-radius: 14px 14px 0 0; }
[data-testid="stFileUploader"] section { border: 3px dashed #c9a8ff; border-radius: 22px; background: rgba(255,255,255,.7); }
.stProgress > div > div > div > div { background: linear-gradient(90deg, #ff6b9d, #7c4dff, #00b8e6); }
</style>
"""

FLOATIES = "".join(
    f'<span style="left:{left}%;animation-duration:{dur}s;animation-delay:{delay}s">{emoji}</span>'
    for left, dur, delay, emoji in [
        (4, 17, 0, "📚"), (13, 22, 4, "✏️"), (22, 19, 9, "🧠"), (31, 24, 2, "⭐"), (40, 18, 12, "🔬"),
        (49, 23, 6, "💡"), (58, 20, 1, "🎓"), (67, 26, 8, "📝"), (76, 18, 14, "🧪"), (85, 22, 3, "🦉"), (93, 25, 10, "🌈"),
    ]
)


def inject_theme():
    st.markdown(CSS, unsafe_allow_html=True)
    st.markdown(f'<div class="floaty">{FLOATIES}</div>', unsafe_allow_html=True)


def hero(title, subtitle, emoji=""):
    md(f'<div class="hero"><div class="hero-title">{emoji} {esc(title)}</div><div class="hero-sub">{esc(subtitle)}</div></div>')


def color_pair(i):
    return PALETTE[i % len(PALETTE)], PALETTE[(i + 3) % len(PALETTE)]


def mastery_bar(label, mastery, status, extra=""):
    emoji, name, color = STATUS[status]
    width = 0 if status == "new" else round(mastery * 100)
    shown = "not started yet" if status == "new" else f"{width}%"
    md(f"""
    <div class="card" style="--c1:{color};--c2:{color}">
      <div style="display:flex;justify-content:space-between;gap:1rem;align-items:center">
        <h4>{emoji} {esc(label)}</h4>
        <span class="pill" style="--pc:{color}">{name} · {shown}</span>
      </div>
      <div class="bar"><div style="width:{width}%;--bc:{color}"></div></div>
      <div class="muted" style="margin-top:.3rem">{esc(extra)}</div>
    </div>""")


def pages_text(pages):
    if not pages or pages[0] is None:
        return ""
    return f"p. {pages[0]}" if pages[0] == pages[1] else f"pp. {pages[0]}-{pages[1]}"


# --------------------------------------------------------------------------- state / helpers
@st.cache_resource
def get_student(path):
    return StudentStore(path)


def show_error(err, hint=True):
    if isinstance(err, ApiError):
        st.error(f"😵 {err}")
        if hint and err.status == 401:
            st.info("🔑 The API key doesn't match. Use the same key you set as `API_KEY` on Kaggle.")
        if hint and err.status == 404:
            st.info("🧭 The server doesn't know this topic (it forgets PDFs when it restarts). Re-upload the PDF on the Home page.")
        if hint and err.status == 400:
            st.info("📄 Upload a PDF on the Home page first.")
    else:
        st.error(f"😵 {err}")


def sidebar(student):
    with st.sidebar:
        md('<div class="brand">🦄 StudyBuddy</div><div class="tagline">your adaptive AI tutor ✨</div>')

        if "_goto" in st.session_state:
            st.session_state["nav"] = st.session_state.pop("_goto")
        if "_set_doc" in st.session_state:
            st.session_state["active_doc"] = st.session_state.pop("_set_doc")
        st.radio("Go to", PAGES, key="nav", label_visibility="collapsed")

        docs = []
        for topic in student.topic_stats():
            if topic["doc"] and topic["doc"] not in docs:
                docs.append(topic["doc"])
        if docs:
            if st.session_state.get("active_doc") not in docs:
                st.session_state["active_doc"] = docs[-1]
            st.selectbox("📘 Studying", docs, key="active_doc")

        history = student.quiz_history()
        total_correct = sum(q["correct"] for q in history)
        md(f'<div class="level">⭐ Level {1 + total_correct // 10} · {total_correct} right answers</div>')

        with st.expander("🔌 Connection", expanded=not st.session_state.get("backend_url")):
            st.text_input("Backend URL (ngrok)", key="backend_url", placeholder="https://xxxx.ngrok-free.app")
            st.text_input("API key", key="api_key", type="password")
            if st.button("Test connection", **BTN_WIDE):
                try:
                    info = backend().health()
                    st.success(f"🟢 Connected · {info.get('model', '?')} ({info.get('quantization', '?')})")
                except ApiError as err:
                    show_error(err, hint=False)
        with st.expander("🗂️ Student file"):
            st.text_input("SQLite file", key="db_path", help="One file = one student. Change it to switch students.")
        active = st.session_state.get("active_doc")
    return active


def backend():
    return Backend(st.session_state.get("backend_url", ""), st.session_state.get("api_key", ""))


def go(page):
    st.session_state["_goto"] = page


# --------------------------------------------------------------------------- HOME
def page_home(student, active_doc):
    hero("Welcome, super learner!", "Upload your lecture PDF and I'll turn it into chats, quizzes and flashcards that adapt to YOU.", "🦄")

    if "last_ingest" in st.session_state:
        info = st.session_state.pop("last_ingest")
        st.success(f"🎉 **{info['document']}** is ready! {info['pages']} pages, {len(info['topics'])} topics found.")

    left, right = st.columns([3, 2], gap="large")
    with left:
        st.subheader("📥 1. Drop your PDF")
        uploaded = st.file_uploader("Text-based PDF (scanned images need OCR first)", type=["pdf"], label_visibility="collapsed")
        if st.button("🚀 Upload & build my study map", type="primary", disabled=uploaded is None, **BTN_WIDE):
            with st.status("📖 Reading your PDF and finding topics… (this can take a minute)", expanded=True) as status:
                try:
                    result = backend().ingest(uploaded.name, uploaded.getvalue())
                    student.sync_topics(result["topics"])
                    status.update(label="Study map ready! 🗺️", state="complete")
                except ApiError as err:
                    status.update(label="Upload failed", state="error")
                    show_error(err, hint=False)
                    if err.status == 409:
                        st.info("That PDF is already on the server. Use **Sync topics** on the right instead.")
                    result = None
            if result:
                st.session_state["last_ingest"] = result
                st.session_state["_set_doc"] = result["document"]
                st.balloons()
                st.rerun()

    with right:
        st.subheader("🔧 Server tools")
        st.caption("Server restarted, or PDF already uploaded? Sync topics. Want a clean slate? Reset the server index.")
        if st.button("🔄 Sync topics from server", **BTN_WIDE):
            try:
                topics = backend().topics()["topics"]
                student.sync_topics(topics)
                if topics:
                    st.session_state["_set_doc"] = topics[-1]["doc"]
                    st.toast(f"Synced {len(topics)} topics ✅")
                    st.rerun()
                else:
                    st.warning("The server has no PDFs yet. Upload one!")
            except ApiError as err:
                show_error(err, hint=False)
        if st.button("🧹 Reset server index", **BTN_WIDE):
            try:
                backend().reset()
                st.toast("Server index cleared 🧼 (your progress is kept)")
            except ApiError as err:
                show_error(err, hint=False)

    stats = student.topic_stats(doc=active_doc)
    if stats:
        st.subheader(f"🗺️ Your study map · {active_doc}")
        columns = st.columns(3)
        for i, topic in enumerate(stats):
            c1, c2 = color_pair(i)
            emoji = STATUS[topic["status"]][0]
            with columns[i % 3]:
                md(f"""
                <div class="card" style="--c1:{c1};--c2:{c2}">
                  <h4>{emoji} {esc(topic['label'] or f'Topic {i + 1}')}</h4>
                  <span class="pill" style="--pc:{c1}">{pages_text(topic['pages'])}</span>
                  <span class="pill soft">{STATUS[topic['status']][1]}</span>
                </div>""")
        cta1, cta2, cta3 = st.columns(3)
        cta1.button("💬 Ask a question", on_click=go, args=(NAV_CHAT,), **BTN_WIDE)
        cta2.button("🎯 Take a quiz", on_click=go, args=(NAV_QUIZ,), type="primary", **BTN_WIDE)
        cta3.button("🃏 Make flashcards", on_click=go, args=(NAV_CARDS,), **BTN_WIDE)
    else:
        md("""<div class="card"><h4>🌟 How it works</h4>
        <div class="muted">1️⃣ Upload a PDF · 2️⃣ Chat with page citations · 3️⃣ Take quizzes that focus on what you miss ·
        4️⃣ Review flashcards at the perfect time · 5️⃣ Watch your mastery grow 📈</div></div>""")


# --------------------------------------------------------------------------- CHAT
def ask_owl(question, k, max_tokens):
    st.session_state.setdefault("chat", [])
    st.session_state["chat"].append({"role": "user", "content": question})
    try:
        reply = backend().chat(question, k=k, max_new_tokens=max_tokens)
        st.session_state["chat"].append({"role": "assistant", "content": reply["answer"], "sources": reply.get("sources", [])})
    except ApiError as err:
        st.session_state["chat"].append({"role": "error", "content": str(err), "status": err.status})


def render_sources(sources):
    pages = sorted({s["page"] for s in sources})
    chips = "".join(f'<span class="pill" style="--pc:{PALETTE[i % len(PALETTE)]}">📄 p. {p}</span>' for i, p in enumerate(pages))
    md(f'<div style="margin-top:.4rem">{chips}</div>')
    with st.expander(f"📚 See the {len(sources)} passages I used"):
        for src in sources:
            st.markdown(f"**p. {src['page']}** · {src['document']} · relevance {src['score']}")
            st.caption(src["snippet"].replace("\n", " ") + "…")


def page_chat(student, active_doc):
    hero("Ask the Owl", "Ask anything about your PDF. Every answer comes with page citations.", "🦉")
    st.session_state.setdefault("chat", [])

    with st.expander("⚙️ Answer settings"):
        k = st.slider("Passages to read", 1, 10, 4)
        max_tokens = st.slider("Max answer length (tokens)", 100, 1000, 400, step=50)

    starters = [t["label"] for t in student.topic_stats(doc=active_doc) if t["label"]][:3]
    if starters and not st.session_state["chat"]:
        st.caption("✨ Try one of these:")
        cols = st.columns(len(starters))
        for col, label in zip(cols, starters):
            col.button(f"Explain: {label}", key=f"starter_{label}", **BTN_WIDE,
                       on_click=lambda q=f"Explain {label} in simple words.": st.session_state.update(pending_q=q))

    for message in st.session_state["chat"]:
        if message["role"] == "error":
            show_error(ApiError(message.get("status", 0), message["content"]))
            continue
        with st.chat_message(message["role"], avatar="🧑‍🎓" if message["role"] == "user" else "🦉"):
            st.markdown(message["content"])
            if message.get("sources"):
                render_sources(message["sources"])

    typed = st.chat_input("Ask me about your lecture… 💭")
    question = typed or st.session_state.pop("pending_q", None)
    if question:
        with st.chat_message("user", avatar="🧑‍🎓"):
            st.markdown(question)
        with st.chat_message("assistant", avatar="🦉"):
            with st.spinner("🦉 Flipping through your pages…"):
                ask_owl(question, k, max_tokens)
        st.rerun()

    if st.session_state["chat"]:
        st.button("🧽 Clear chat", on_click=lambda: st.session_state.update(chat=[]))


# --------------------------------------------------------------------------- QUIZ
def build_quiz(student, plan, kind):
    questions, problems = [], []
    with st.status("🧪 Cooking up your questions…", expanded=True) as status:
        for item in plan:
            st.write(f"✨ {item['label']} · {item['n']} question(s) · {item['difficulty']}")
            try:
                reply = backend().quiz(item["n"], item["topic_id"], item["difficulty"], item["avoid_questions"])
                questions.extend(reply["questions"])
                if reply.get("note"):
                    problems.append(f"{item['label']}: {reply['note']}")
            except ApiError as err:
                problems.append(f"{item['label']}: {err}")
                if err.status in (401, 404):
                    break
        if not questions:
            status.update(label="Couldn't build the quiz", state="error")
            for problem in problems:
                st.error(f"😵 {problem}")
            return
        status.update(label="Quiz ready! 🎉", state="complete")
    random.shuffle(questions)
    quiz_id = student.start_quiz(kind=kind, plan=plan)
    st.session_state["quiz"] = {
        "id": quiz_id, "questions": questions, "idx": 0, "checked": {}, "phase": "run",
        "problems": problems, "plan": [{"label": p["label"], "n": p["n"], "difficulty": p["difficulty"]} for p in plan],
    }
    st.rerun()


def quiz_start(student, active_doc):
    stats = student.topic_stats(doc=active_doc)
    if not stats:
        st.warning("📄 No topics yet. Upload a PDF on the Home page first!")
        st.button("Go to Home 🏠", on_click=go, args=(NAV_HOME,))
        return

    mode = st.radio("Quiz style", ["🧠 Adaptive (recommended)", "🎨 Pick a topic"], horizontal=True, label_visibility="collapsed")
    total = st.slider("How many questions?", 3, 10, 5)

    if mode.startswith("🧠"):
        plan = student.plan_adaptive_quiz(total=total, doc=active_doc)
        has_history = any(t["answered"] for t in stats)
        st.subheader("🎯 Your next quiz is built around this" if has_history else "🎯 Your first quiz")
        st.caption("Weak topics get the most questions and gentler difficulty. Strong topics get harder ones." if has_history
                   else "Nothing answered yet, so I'll start with a friendly mix. After this, quizzes target what you miss!")
        columns = st.columns(len(plan))
        for i, (col, item) in enumerate(zip(columns, plan)):
            c1, c2 = color_pair(i)
            emoji, name, _ = STATUS[item["status"]]
            with col:
                md(f"""
                <div class="card" style="--c1:{c1};--c2:{c2}">
                  <h4>{emoji} {esc(item['label'])}</h4>
                  <span class="pill" style="--pc:{c1}">{item['n']} question{'s' if item['n'] != 1 else ''}</span>
                  <span class="pill soft">{esc(item['difficulty'])}</span>
                  <div class="muted" style="margin-top:.4rem">{name}</div>
                </div>""")
        if st.button("🚀 Start quiz!", type="primary", **BTN_WIDE):
            build_quiz(student, plan, "adaptive")
    else:
        by_label = {f"{t['label'] or t['topic_id']} ({pages_text(t['pages'])})": t for t in stats}
        choice = st.selectbox("Topic", list(by_label))
        topic = by_label[choice]
        difficulty = st.select_slider("Difficulty", ["easy", "medium", "hard"], value="medium")
        plan = [{"topic_id": topic["topic_id"], "label": topic["label"], "n": total, "difficulty": difficulty,
                 "mastery": topic["mastery"], "status": topic["status"],
                 "avoid_questions": student.recent_questions(topic["topic_id"])}]
        if st.button("🚀 Start quiz!", type="primary", **BTN_WIDE):
            build_quiz(student, plan, "manual")


def quiz_run(student):
    quiz = st.session_state["quiz"]
    idx, questions = quiz["idx"], quiz["questions"]
    question = questions[idx]
    checked = quiz["checked"]

    for problem in quiz.get("problems", []):
        st.warning(f"⚠️ {problem}")
    st.progress(idx / len(questions), text=f"Question {idx + 1} of {len(questions)}")

    topic = question.get("topic") or "General"
    page = f" · 📄 p. {question['source_page']}" if question.get("source_page") else ""
    md(f"""<div class="card"><span class="pill">{esc(topic)}</span><span class="pill soft">{esc(question.get('difficulty', ''))}</span>
    <span class="muted">{page}</span><h4 style="margin-top:.6rem;font-size:1.25rem">{esc(question['question'])}</h4></div>""")

    done = idx in checked
    chosen = st.radio(
        "Your answer", list(range(len(question["options"]))), index=None, key=f"q_{quiz['id']}_{idx}", disabled=done,
        format_func=lambda i: f"{'ABCD'[i]}.  {question['options'][i]}", label_visibility="collapsed",
    )

    if not done:
        if st.button("✅ Check my answer", type="primary", disabled=chosen is None):
            checked[idx] = student.record_answer(quiz["id"], question, chosen)
            st.rerun()
    else:
        right = question["answer_index"]
        if checked[idx]:
            st.success("🎉 Yes! You got it!")
        else:
            st.error(f"💪 Not this time. The answer is **{'ABCD'[right]}. {question['options'][right]}**")
        if question.get("explanation"):
            st.info(f"💡 {question['explanation']}")
        last = idx + 1 == len(questions)
        if st.button("🏁 Finish quiz" if last else "Next question ➡️", type="primary"):
            if last:
                quiz["phase"] = "done"
                quiz["summary"] = student.quiz_summary(quiz["id"])
                quiz["new_cards"] = student.cards_from_mistakes(quiz["id"])
            else:
                quiz["idx"] += 1
            st.rerun()

    st.button("✖️ Quit quiz", on_click=lambda: st.session_state.pop("quiz", None))


def quiz_done(student, active_doc):
    quiz = st.session_state["quiz"]
    summary = quiz["summary"]
    score = summary["score"] or 0
    color = "#1fbf75" if score >= 80 else "#ffa000" if score >= 50 else "#ff4f6d"
    if not quiz.get("celebrated") and score >= 80:
        st.balloons()
    quiz["celebrated"] = True

    verdict = ("🏆 Amazing work!" if score >= 80 else "🌟 Nice progress!" if score >= 50 else "💪 Every miss is a lesson!")
    hero(verdict, f"You got {summary['correct']} of {summary['total']} right.", "🎉")
    md(f'<div class="score" style="--pct:{score};--sc:{color}">{round(score)}%</div>')

    st.subheader("🧩 How each topic went")
    for i, topic in enumerate(summary["by_topic"]):
        pct = round(100 * topic["correct"] / topic["total"])
        mastery_bar(topic["label"], topic["correct"] / topic["total"], "strong" if pct >= 75 else "learning" if pct >= 45 else "weak",
                    f"{topic['correct']}/{topic['total']} correct this quiz")

    if quiz.get("new_cards"):
        st.success(f"🃏 I turned {quiz['new_cards']} missed question(s) into flashcards for spaced review.")

    wrong = [a for a in range(len(quiz["questions"])) if quiz["checked"].get(a) is False]
    if wrong:
        with st.expander(f"🔍 Review {len(wrong)} missed question(s)"):
            for a in wrong:
                q = quiz["questions"][a]
                st.markdown(f"**{q['question']}**  \n✅ {q['options'][q['answer_index']]}" + (f"  \n💡 {q['explanation']}" if q.get("explanation") else ""))

    st.subheader("🔮 Quiz 2 will look like this")
    plan = student.plan_adaptive_quiz(total=5, doc=active_doc)
    cols = st.columns(len(plan)) if plan else []
    for i, (col, item) in enumerate(zip(cols, plan)):
        emoji, name, _ = STATUS[item["status"]]
        col.metric(f"{emoji} {item['label']}", f"{item['n']} q", item["difficulty"], delta_color="off")

    a, b, c = st.columns(3)
    a.button("🎯 Next adaptive quiz", type="primary", on_click=lambda: st.session_state.pop("quiz", None), **BTN_WIDE)
    b.button("🃏 Review flashcards", on_click=lambda: (st.session_state.pop("quiz", None), go(NAV_CARDS)), **BTN_WIDE)
    c.button("📊 See progress", on_click=lambda: (st.session_state.pop("quiz", None), go(NAV_PROGRESS)), **BTN_WIDE)


def page_quiz(student, active_doc):
    hero("Quiz Time", "Questions that adapt to what you know. Missed topics come back first!", "🎯")
    quiz = st.session_state.get("quiz")
    if not quiz:
        quiz_start(student, active_doc)
    elif quiz["phase"] == "run":
        quiz_run(student)
    else:
        quiz_done(student, active_doc)


# --------------------------------------------------------------------------- FLASHCARDS
def rate_card(student, card_id, rating):
    result = student.review_card(card_id, rating)
    st.session_state["fc_show"] = False
    st.session_state["fc_last"] = f"Next review in {result['interval_days']} day(s) 📅"


def cards_review(student, active_doc):
    counts = student.card_counts()
    m1, m2, m3 = st.columns(3)
    m1.metric("📬 Due today", counts["due"])
    m2.metric("🃏 Total cards", counts["total"])
    m3.metric("🌱 Never reviewed", counts["new"])

    due = student.due_cards(limit=50)
    if not due:
        md('<div class="card"><h4>🎉 All caught up!</h4><div class="muted">No cards due. Generate new ones in the next tab, or take a quiz: missed questions become cards automatically.</div></div>')
        return
    card = due[0]
    if st.session_state.get("fc_last"):
        st.caption(st.session_state.pop("fc_last"))
    st.progress(1 / len(due), text=f"{len(due)} card(s) waiting")
    page = f" · p. {card['source_page']}" if card.get("source_page") else ""

    if not st.session_state.get("fc_show"):
        md(f'<div class="flash"><small>❓ QUESTION{esc(page)}</small>{nl2br(card["front"])}</div>')
        st.button("👀 Show answer", type="primary", on_click=lambda: st.session_state.update(fc_show=True), **BTN_WIDE)
    else:
        md(f'<div class="flash back"><small>💡 ANSWER{esc(page)}</small>{nl2br(card["back"])}</div>')
        st.caption("How well did you remember?  ('Again' brings it back tomorrow.)")
        state = srs.CardState(card["ease"], card["interval_days"], card["repetitions"], card["lapses"])
        labels = {"again": "😵 Again", "hard": "😅 Hard", "good": "😊 Good", "easy": "🤩 Easy"}
        for col, rating in zip(st.columns(4), QUALITY):
            days = srs.next_state(state, QUALITY[rating]).interval_days
            col.button(f"{labels[rating]}\n{days}d", key=f"rate_{rating}_{card['id']}", on_click=rate_card,
                       args=(student, card["id"], rating), type="primary" if rating == "good" else "secondary", **BTN_WIDE)


def cards_generate(student, active_doc):
    stats = student.topic_stats(doc=active_doc)
    if not stats:
        st.warning("📄 Upload a PDF on the Home page first!")
        return
    options = {"🌈 Whole document": None}
    options.update({f"{t['label'] or t['topic_id']} ({pages_text(t['pages'])})": t["topic_id"] for t in stats})
    choice = st.selectbox("Make cards about…", list(options))
    n = st.slider("How many cards?", 3, 15, 8)
    if st.button("✨ Generate flashcards", type="primary", **BTN_WIDE):
        with st.spinner("🪄 Sprinkling some memory magic…"):
            try:
                reply = backend().flashcards(n, options[choice], st.session_state.get("fc_fronts", []))
            except ApiError as err:
                show_error(err)
                return
        added = student.add_cards(reply["flashcards"])
        st.session_state.setdefault("fc_fronts", []).extend(c["front"] for c in reply["flashcards"])
        st.success(f"🎉 Added {added} new card(s) to your deck." + ("" if added == len(reply["flashcards"]) else " (Duplicates were skipped.)"))
        if reply.get("note"):
            st.warning(reply["note"])
        for i, card in enumerate(reply["flashcards"]):
            c1, c2 = color_pair(i)
            md(f'<div class="card" style="--c1:{c1};--c2:{c2}"><h4>❓ {esc(card["front"])}</h4><div class="muted">💡 {nl2br(card["back"])}</div></div>')


def page_cards(student, active_doc):
    hero("Flashcards", "Spaced repetition shows each card right before you'd forget it.", "🃏")
    review, generate = st.tabs(["🧠 Review", "✨ Make new cards"])
    with review:
        cards_review(student, active_doc)
    with generate:
        cards_generate(student, active_doc)


# --------------------------------------------------------------------------- PROGRESS
def page_progress(student, active_doc):
    hero("My Progress", "Watch your mastery grow, one quiz at a time.", "📊")
    stats = student.topic_stats(doc=active_doc)
    history = student.quiz_history()
    if not stats:
        st.warning("📄 Nothing to show yet. Upload a PDF and take a quiz!")
        return

    answered = sum(t["answered"] for t in stats)
    correct = sum(t["correct"] for t in stats)
    counts = student.card_counts()
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("🎯 Quizzes taken", len(history))
    m2.metric("✅ Accuracy", f"{round(100 * correct / answered)}%" if answered else "—")
    m3.metric("🏆 Topics mastered", f"{sum(t['status'] == 'strong' for t in stats)}/{len(stats)}")
    m4.metric("📬 Cards due", f"{counts['due']}/{counts['total']}")

    st.subheader("🧠 Mastery by topic")
    order = {"weak": 0, "learning": 1, "new": 2, "strong": 3}
    for topic in sorted(stats, key=lambda t: order[t["status"]]):
        extra = (f"{topic['correct']}/{topic['answered']} answers correct · " if topic["answered"] else "") + \
                f"{topic['cards_due']} card(s) due · {pages_text(topic['pages'])}"
        mastery_bar(topic["label"] or topic["topic_id"], topic["mastery"], topic["status"], extra)

    timeline = [row for row in student.mastery_timeline() if row["topic_id"] in {t["topic_id"] for t in stats}]
    if timeline:
        st.subheader("📈 Mastery after each quiz")
        frame = pd.DataFrame(timeline)
        frame["Mastery"] = frame["mastery"] * 100
        frame["Topic"] = frame["label"].replace("", "Unassigned")
        frame["Quiz"] = frame["quiz_number"]
        chart = (
            alt.Chart(frame).mark_line(point=alt.OverlayMarkDef(size=110, filled=True), strokeWidth=4, interpolate="monotone")
            .encode(
                x=alt.X("Quiz:O", title="Quiz #", axis=alt.Axis(labelAngle=0)),
                y=alt.Y("Mastery:Q", scale=alt.Scale(domain=[0, 100]), title="Mastery %"),
                color=alt.Color("Topic:N", scale=alt.Scale(range=PALETTE), legend=alt.Legend(orient="bottom", columns=2)),
                tooltip=["Topic", "Quiz", alt.Tooltip("Mastery:Q", format=".0f")],
            ).properties(height=340)
        )
        st.altair_chart(chart, **CHART_WIDE)

    if history:
        st.subheader("🏅 Score per quiz")
        scores = pd.DataFrame({"Quiz": [f"#{i + 1}" for i in range(len(history))], "Score": [q["score"] for q in history]})
        bars = alt.Chart(scores).mark_bar(cornerRadiusTopLeft=10, cornerRadiusTopRight=10, size=46).encode(
            x=alt.X("Quiz:N", sort=None, axis=alt.Axis(labelAngle=0)), y=alt.Y("Score:Q", scale=alt.Scale(domain=[0, 100]), title="Score %"),
            color=alt.Color("Score:Q", scale=alt.Scale(domain=[0, 50, 100], range=["#ff4f6d", "#ffb300", "#26d07c"]), legend=None),
            tooltip=["Quiz", "Score"],
        ).properties(height=260)
        st.altair_chart(bars, **CHART_WIDE)

    with st.expander("⚠️ Danger zone"):
        sure = st.checkbox("Yes, delete all my answers, quizzes and flashcards")
        if st.button("🗑️ Reset my progress", disabled=not sure):
            student.reset_progress()
            st.session_state.pop("quiz", None)
            st.toast("Fresh start! 🌱")
            st.rerun()


# --------------------------------------------------------------------------- main
def main():
    st.session_state.setdefault("backend_url", os.getenv("ADAPTIVE_BACKEND_URL", ""))
    st.session_state.setdefault("api_key", os.getenv("ADAPTIVE_API_KEY", ""))
    st.session_state.setdefault("db_path", os.getenv("ADAPTIVE_DB", "student.db"))
    st.session_state.setdefault("nav", NAV_HOME)

    inject_theme()
    student = get_student(st.session_state["db_path"] or "student.db")
    active_doc = sidebar(student)
    student = get_student(st.session_state["db_path"] or "student.db")  # picks up a changed file name

    page = st.session_state["nav"]
    {NAV_HOME: page_home, NAV_CHAT: page_chat, NAV_QUIZ: page_quiz, NAV_CARDS: page_cards, NAV_PROGRESS: page_progress}[page](student, active_doc)


main()
