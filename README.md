# AdaptiveAI / StudyBuddy

An adaptive study app. You upload a lecture PDF, and the app lets you:

- **Chat** with the PDF (answers come with the page numbers they were taken from)
- Take **quizzes** that adapt to what you know (weak topics come back first)
- Review **flashcards** with spaced repetition
- Track your **mastery** per topic over time

The project has two parts that run in different places:

| Part | Where it runs | What it does |
|---|---|---|
| **Backend** (FastAPI + LLM) | **Kaggle** (GPU), exposed to the internet with **ngrok** | Reads PDFs, finds relevant passages (RAG), writes answers, quizzes and flashcards |
| **Frontend** (Streamlit) | **Your computer** | The app you use. It calls the backend and stores your progress in `student.db` |

```text
Your computer (Streamlit)  ──HTTPS──►  ngrok URL  ──►  Kaggle (FastAPI + GPU model)
        │
        └── student.db  (your answers, mastery, flashcard schedule)
```

The backend keeps **no student data**. Progress lives only in `student.db` on your computer.

---

## Features

**Study with your own PDF**
- Upload any text-based lecture PDF. The app splits it into chunks and into up to 8 topics, each with an AI-written title and page range.
- **Chat with the PDF (RAG):** questions are answered from the most relevant passages, and you can open the exact passages and page numbers used.

**Adaptive quizzes**
- Multiple-choice questions with 4 options, the correct answer, an explanation and the source page.
- The quiz is built from your history: up to 3 topics, weak topics first, then unseen ones, then mastered ones.
- Difficulty adapts per topic (easy, medium, hard) and questions you already saw are avoided.
- Output is validated and retried up to 3 times, with a note if fewer valid questions came back.

**Flashcards with spaced repetition**
- AI-generated front/back cards per topic.
- Cards are scheduled with SM-2, so each one returns right before you would forget it.
- Questions you answered wrong can be turned into flashcards automatically.

**Progress tracking**
- Mastery score and status (new, weak, learning, strong) per topic.
- Quiz history, level and right-answer count, and a mastery-over-time chart.
- Several students: one `student.db` file per student.

**Engineering**
- Strong open models (Qwen 7B/14B/32B, or Mistral-Nemo) in 4-bit on free Kaggle GPUs, served through ngrok.
- API-key protected endpoints, upload size limit, and a public `/health` check with GPU memory.

---

## Project structure

```text
AdaptiveAI/
├── .gitignore
├── README.md
│
├── backend/                       # runs on Kaggle (GPU) behind ngrok; your own notebook starts it
│   ├── app.py                     FastAPI app (registers all routers)
│   ├── config.py                  Settings (models, limits, API key)
│   ├── auth.py                    Bearer-token check
│   ├── schemas.py                 Request/response models
│   ├── requirements.txt           Backend packages
│   ├── routers/
│   │   ├── health.py              GET  /health      (public)
│   │   ├── generate.py            POST /generate
│   │   ├── documents.py           POST /ingest, POST /reset
│   │   ├── topics.py              GET  /topics
│   │   ├── chat.py                POST /chat
│   │   ├── quiz.py                POST /quiz
│   │   └── flashcards.py          POST /flashcards
│   └── services/
│       ├── model_service.py       Loads the LLM + embedding model
│       ├── vector_store.py        Chunks + FAISS index (in RAM)
│       ├── pdf_service.py         PDF text extraction
│       ├── topic_service.py       Topic splitting and titles
│       └── json_utils.py          Safe parsing of model JSON output
│
└── frontend/                      # runs on your computer
    ├── streamlit_app.py           The app
    ├── api_client.py              Calls the backend (adds key + ngrok header)
    ├── requirements-frontend.txt  Frontend packages
    ├── .streamlit/config.toml     Theme + 50 MB upload limit
    ├── student_data/              Progress layer (SQLite): mastery, spaced repetition
    ├── tests/test_student_data.py 33 unit tests
    └── student.db                 Created automatically on first run
```

The two folders never import each other. They only talk over HTTP.

---

## Quick start (every session)

Start the **backend first**. The frontend needs the ngrok URL that the backend prints.

1. **Backend:** run your Kaggle notebook (Part 1 below) and copy the printed URL.
2. **Frontend:** run Streamlit on your computer (Part 2 below) and paste the URL and API key.
3. Upload a text-based PDF and start studying.

---

## Part 1 — Backend on Kaggle

The backend is the `backend/` folder. You run it from **your own Kaggle notebook** (the notebook is not part of this project). The notebook must do these things, in order:

1. Make the backend code available (attach the `backend` folder as a Kaggle dataset, then unzip or copy it to `/kaggle/working`).
2. Install the packages from `backend/requirements.txt` (this includes `uvicorn` and `pyngrok`; keep Kaggle's own `torch`).
3. Set the environment variables **before** importing the app:
   - `API_KEY` — a long private password (from a Kaggle Secret)
   - `LLM_NAME` — the model to load (see below)
   - `QUANT` — `4bit` (needs a CUDA GPU)
4. `from app import app` — this loads the models, which takes several minutes the first time.
5. Open an ngrok tunnel to port 8000 (with your `NGROK_TOKEN` secret) and run `uvicorn.run(app, host="0.0.0.0", port=8000)` in a background thread.
6. Print the public ngrok URL.

### One-time setup

1. **Dataset:** go to kaggle.com/datasets → **New Dataset** and upload the **`backend` folder only** (zipped). Keep it **Private**. Do **not** include `.venv`, `__pycache__`, or model files. The model downloads itself.
2. **ngrok token:** log in at dashboard.ngrok.com and copy your authtoken from **Your Authtoken**.
3. **Notebook settings:** **GPU T4 x2**, **Internet: On**, and attach your dataset under **Input**.
4. **Secrets:** in **Add-ons → Secrets**, add `NGROK_TOKEN` and `API_KEY`, and tick both so they attach to the notebook.

### Check that it works

Open `<your-url>/health`. You should see `status: ok` and your model name. A request to a protected endpoint without the right key returns `401`.

Copy the **public URL** and **leave the notebook running**. If you stop or restart it, the URL dies.

### Choosing a model

Set `LLM_NAME` before the app is imported:

| Model | Notes |
|---|---|
| `Qwen/Qwen2.5-7B-Instruct` | Faster, good quality |
| `Qwen/Qwen2.5-14B-Instruct` | **Recommended** for T4 x2 (4-bit, about 9 GB) |
| `Qwen/Qwen2.5-32B-Instruct` | Strongest, slow on T4s |

> **Important:** the default in `config.py` is `Qwen/Qwen2.5-0.5B-Instruct`, a very small model meant for quick tests. Its answers and quizzes are weak. For real use, set a bigger `LLM_NAME`.

### Backend settings (environment variables)

| Variable | Default | Meaning |
|---|---|---|
| `API_KEY` | empty | Bearer token for all protected endpoints. Empty = no key required (local use only). **Always set it on Kaggle.** |
| `LLM_NAME` | `Qwen/Qwen2.5-0.5B-Instruct` | Language model |
| `EMB_NAME` | `BAAI/bge-m3` | Embedding model |
| `QUANT` | `4bit` | `4bit`, `8bit` or `fp16` (`4bit` and `8bit` need a CUDA GPU with bitsandbytes) |
| `MAX_PDF_MB` | `30` | Upload size limit |
| `MAX_TOPICS_PER_DOC` | `8` | Topics per PDF |

> **Security:** with no `API_KEY` the server needs no key, which is fine on your own computer (`127.0.0.1` only) but **never** with ngrok. Never print your key in a notebook cell, and clear a notebook's outputs before sharing it. Anyone with your ngrok URL and key can use your GPU.

---

## Part 2 — Frontend on your computer (Windows, Git Bash)

All commands below are for **Git Bash**, run from the **`frontend`** folder (the one containing `streamlit_app.py`). Use Python 3.10 or 3.11.

### One-time setup

```bash
cd /c/path/to/AdaptiveAI/frontend
python -m venv .venv-ui                 # if "python" is not found, try: py -m venv .venv-ui
source .venv-ui/Scripts/activate        # your prompt now starts with (.venv-ui)
pip install -r requirements-frontend.txt
```

### Run it (every session)

```bash
cd /c/path/to/AdaptiveAI/frontend
source .venv-ui/Scripts/activate
export ADAPTIVE_BACKEND_URL="https://xxxx.ngrok-free.app"
export ADAPTIVE_API_KEY="your-key"
streamlit run streamlit_app.py
```

Variables set with `export` only last for that Git Bash window. Open a new window and you must set them again (or use the sidebar).

The browser opens at `http://localhost:8501`.

The two environment variables are optional. You can also skip them and type the values in the sidebar under **🔌 Connection**:

- **Backend URL (ngrok):** the URL printed by your Kaggle notebook
- **API key:** exactly the same value as your Kaggle `API_KEY` secret
- Click **Test connection**. You should see 🟢 **Connected** with the model name.

> **Note:** "Test connection" uses `/health`, which is public and needs no key. A wrong API key still shows green but fails later with `401 Unauthorized` on upload. Retype the key if that happens.

Other frontend settings:

| Variable | Meaning |
|---|---|
| `ADAPTIVE_BACKEND_URL` | Default backend URL |
| `ADAPTIVE_API_KEY` | Default API key |
| `ADAPTIVE_DB` | Student database file (default `student.db`) |

To switch students, change the file name under **🗂️ Student file** in the sidebar. One file is one student.

---

### Optional: run the backend on your own computer (no ngrok)

Only useful if your computer has a suitable GPU. In a **second** Git Bash window:

```bash
cd /c/path/to/AdaptiveAI/backend
python -m venv .venv && source .venv/Scripts/activate
pip install -r requirements.txt
# No API key is needed locally. Keep --host 127.0.0.1 so only your computer can reach it.
uvicorn app:app --host 127.0.0.1 --port 8000
```

Then start Streamlit in the first window with `export ADAPTIVE_BACKEND_URL="http://127.0.0.1:8000"` and leave the API key box empty.

### Optional: put the project on GitHub (Git Bash)

```bash
cd /c/path/to/AdaptiveAI        # the project root (contains backend/ and frontend/)
git init
git add .
git commit -m "AdaptiveAI project"
git branch -M main
git remote add origin https://github.com/YOUR_USER/YOUR_REPO.git
git push -u origin main
```

The included `.gitignore` keeps `student.db`, virtual environments and caches out of the repository. Never commit real keys or tokens.

---

## Using the app

**Sidebar (left):** page menu, your level, **🔌 Connection** (backend URL, API key, Test connection) and **🗂️ Student file**.

1. **🏠 Home → "Drop your PDF":** choose a text-based PDF and click **🚀 Upload & build my study map**. Scanned images are not supported (no OCR). The backend splits the PDF into chunks, builds the search index and asks the model to title each topic, so this takes a while.
2. **🏠 Home → "Server tools"** (right side):
   - **🔄 Sync topics from server:** use it if the server already has your PDF (for example after the page reloaded).
   - **🧹 Reset server index:** clears every uploaded PDF from the server. Your progress is kept.
3. **💬 Ask the Owl:** ask questions about the PDF. Open "See the passages I used" to check the sources.
4. **🎯 Quiz Time:** the quiz covers up to 3 topics, prioritising weak and unseen ones. Wrong answers can become flashcards automatically.
5. **🃏 Flashcards:** **Review** your due cards (Again / Hard / Good / Easy), or **Make new cards** for a topic.
6. **📊 My Progress:** mastery per topic, quiz history, and a mastery timeline. **🗑️ Reset my progress** (tick the checkbox first) deletes your answers, quizzes and flashcards.

### Topics

Each PDF is split into topics: consecutive groups of about 4+ chunks, at most 8 per PDF. Topic ids look like `lecture.pdf#3` and are stable for the same PDF. If you restart the backend and upload the same PDF again, your progress still lines up.

### How adaptivity works

For each topic the app looks at your last 20 answers, with older answers counting 85% as much as the next newer one. A starting guess of 50% (worth about 2 answers) stops one lucky answer from looking like mastery.

| Mastery | Status | Next-quiz difficulty |
|---|---|---|
| no answers yet | new | medium |
| below 0.45 | weak | easy |
| 0.45 to 0.75 | learning | medium |
| 0.75 or more | strong | hard |

Flashcards use SM-2 spaced repetition. Good reviews give intervals of about 1 day, 6 days, then roughly 15 days. "Again" restarts the card.

To run the student-layer tests:

```bash
cd frontend
python -m unittest discover -s tests -v
```

---

## API reference

Interactive docs: `<your-url>/docs`. In Swagger, click **Authorize** and enter the key **without** typing `Bearer `.

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/health` | public | Model, quantization, GPU memory, indexed documents |
| POST | `/generate` | key | Plain text generation (`prompt`, `max_length`) |
| POST | `/ingest` | key | Upload a PDF (returns the topics). `409` if the same filename is already indexed |
| POST | `/reset` | key | Clear the in-memory index |
| GET | `/topics` | key | List topics: id, label, page range, chunk count |
| POST | `/chat` | key | Ask about the PDF (`question`, `k`, `max_new_tokens`). Returns the answer with sources |
| POST | `/quiz` | key | Multiple-choice questions (`n`, `topic_id`, `difficulty`, `avoid_questions`) |
| POST | `/flashcards` | key | Flashcards `{front, back, source_page, topic_id, topic}` (`n`, `topic_id`, `avoid_fronts`) |

Quiz generation retries up to three times, validates the output, and avoids duplicates. If the model still produces fewer valid questions than requested, the response includes a note.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `401 Unauthorized` on upload or reset | API key in the sidebar differs from the Kaggle `API_KEY` | Retype it exactly (watch for extra spaces). After editing a Kaggle secret, restart the notebook so the new value is loaded |
| `409 ... already indexed` | That filename is already in the index | On **🏠 Home → Server tools**, click **🧹 Reset server index**, or restart the backend |
| "Can't reach the backend" | Notebook stopped, or the URL changed | Check Kaggle is running and paste the **current** URL |
| "Server took too long" | Model busy (a 14B model on T4 can take 20 to 60 s per answer) | Wait and retry, or switch to the 7B model |
| `422 No readable text found` | The PDF is scanned images | Use a text-based PDF |
| `400 Could not read PDF` | Corrupt or encrypted PDF | Try another file |
| `413 ... too large` | File over `MAX_PDF_MB` (default 30 MB) | Use a smaller PDF or raise `MAX_PDF_MB` |
| `CUDA out of memory` in the Kaggle log | Model too large | Use the 7B model and restart the backend |
| Notebook can't find the project | The dataset is not attached | Attach your backend dataset under **Input** (right sidebar) |
| `did not return JSON` | Wrong or stale URL | Restart the tunnel in your notebook and paste the new URL |

---

## Limits to know about

- **The index lives in RAM.** Uploaded PDFs are lost when the Kaggle notebook restarts. Upload them again. Student progress is safe in `student.db`.
- **A new ngrok URL each run.** Free ngrok URLs change every time you start the tunnel.
- **Kaggle sessions end.** They stop after idle time or when your weekly GPU quota runs out. Stop the session when you are done to save quota.
- **No OCR.** Only PDFs with selectable text work.
- **Answer quality depends on the model.** Quizzes should be checked against the source PDF. Results from the 0.5B default model are not reliable.
- **Model downloads need Internet** the first time. Kaggle's Internet setting must be on.
