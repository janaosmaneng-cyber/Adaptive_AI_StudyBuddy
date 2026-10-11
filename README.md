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
.
├── app.py                  FastAPI app (registers all routers)
├── config.py               Settings (model names, limits, API key)
├── auth.py                 Bearer-token check
├── schemas.py              Request/response models
├── requirements.txt        Backend packages (Kaggle)
├── routers/
│   ├── health.py           GET  /health      (public)
│   ├── generate.py         POST /generate
│   ├── documents.py        POST /ingest, POST /reset
│   ├── topics.py           GET  /topics
│   ├── chat.py             POST /chat
│   ├── quiz.py             POST /quiz
│   └── flashcards.py       POST /flashcards
├── services/
│   ├── model_service.py    Loads the LLM
│   ├── vector_store.py     Embeddings + FAISS index (in RAM)
│   ├── pdf_service.py      PDF text extraction + chunking
│   ├── topic_service.py    Splits each PDF into topics
│   └── json_utils.py       Safe parsing of model JSON output
├── streamlit_app.py        The frontend
├── api_client.py           Frontend → backend calls (adds the ngrok header)
├── requirements-frontend.txt
├── .streamlit/config.toml  Theme + 50 MB upload limit
├── student_data/           Student progress layer (SQLite): mastery, spaced repetition
├── tests/test_student_data.py   33 unit tests for the student layer
└── student.db              Created automatically (one file = one student)
```

---

## Quick start (every session)

Start the **backend first**. The frontend needs the ngrok URL that the backend prints.

1. **Backend:** run the Kaggle notebook (Part 1 below) and copy the printed URL.
2. **Frontend:** run Streamlit on your computer (Part 2 below) and paste the URL and API key.
3. Upload a text-based PDF and start studying.

---

## Part 1 — Backend on Kaggle

### One-time setup

1. **Dataset:** go to kaggle.com/datasets → **New Dataset** and upload `ddd.zip` (the project code). Keep it **Private**.
   Do **not** include `.venv`, `.venv-ui`, `__pycache__`, `student.db`, or model files. The notebook installs packages, and the model downloads itself.
2. **ngrok token:** log in at dashboard.ngrok.com and copy your authtoken from **Your Authtoken**.
3. **Notebook:** create a notebook (or import `AdaptiveAI_Kaggle_Backend.ipynb`), then in its settings:
   - **Accelerator:** GPU T4 x2
   - **Internet:** On
   - **Add Input:** attach your dataset
4. **Secrets:** in the notebook menu **Add-ons → Secrets**, add two secrets and tick both so they attach to the notebook:
   - `NGROK_TOKEN` = your ngrok authtoken
   - `API_KEY` = a long private password you choose

### Run it (every session)

Run the notebook cells **in order, one at a time**:

| Cell | What it does | Expected result |
|---|---|---|
| 1 | Chooses the model (`LLM_NAME`) | nothing printed |
| 2 | Finds and unpacks the project | `Project dir: ...` |
| 3 | Installs packages | Dependency warnings about gradio, pydantic, starlette etc. are harmless |
| 4 | Reads your secrets | nothing printed |
| 5 | Downloads and loads the model | `GPUs: 2` (first run takes several minutes) |
| 6 | Starts the server and the ngrok tunnel | `PUBLIC URL: https://xxxx.ngrok-free.app` |
| 7 | Self-test | `status: ok`, then `400 No PDF material indexed yet` (this means your key works) |

Copy the **PUBLIC URL** from cell 6 and **leave the notebook running**. If you stop or restart it, the URL dies.

### Choosing a model

Set `LLM_NAME` in notebook cell 1 (the notebook sets it through the `LLM_NAME` environment variable, which `config.py` reads):

| Model | Notes |
|---|---|
| `Qwen/Qwen2.5-7B-Instruct` | Faster, good quality |
| `Qwen/Qwen2.5-14B-Instruct` | **Recommended** for T4 x2 (4-bit, about 9 GB) |
| `Qwen/Qwen2.5-32B-Instruct` | Strongest, slow on T4s |

> **Important:** the default in `config.py` is `Qwen/Qwen2.5-0.5B-Instruct`, a very small model meant for quick local tests. Its answers and quizzes are weak. For real use, set a bigger `LLM_NAME` as above.

### Backend settings (environment variables)

| Variable | Default | Meaning |
|---|---|---|
| `API_KEY` | see warning below | Bearer token for all protected endpoints |
| `LLM_NAME` | `Qwen/Qwen2.5-0.5B-Instruct` | Language model |
| `EMB_NAME` | `BAAI/bge-m3` | Embedding model |
| `QUANT` | `4bit` | Quantization (`4bit` needs a CUDA GPU with bitsandbytes) |
| `MAX_PDF_MB` | `30` | Upload size limit |
| `MAX_TOPICS_PER_DOC` | `8` | Topics per PDF |

> **Security warning:** if `API_KEY` is not set, `config.py` falls back to a key written in the file. Always set your own `API_KEY` secret, change or remove the fallback in `config.py`, and never share a notebook or zip that contains real keys. Anyone with your ngrok URL and key can use your GPU.

---

## Part 2 — Frontend on your computer (Windows)

### One-time setup

Use Python 3.10 or 3.11. In PowerShell, from the project folder (the one containing `streamlit_app.py`):

```powershell
python -m venv .venv-ui
.venv-ui\Scripts\activate
pip install -r requirements-frontend.txt
```

### Run it (every session)

```powershell
.venv-ui\Scripts\activate
$env:ADAPTIVE_BACKEND_URL="https://xxxx.ngrok-free.app"
$env:ADAPTIVE_API_KEY="your-key"
streamlit run streamlit_app.py
```

The browser opens at `http://localhost:8501`.

The two environment variables are optional. You can also skip them and type the values in the sidebar under **🔌 Connection**:

- **Backend URL (ngrok):** the URL from Kaggle cell 6
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

## Using the app

1. **Upload a PDF** in the sidebar. It must be a text-based PDF (selectable text). Scanned images are not supported (no OCR). The backend splits it into chunks, builds the search index, and asks the model to title each topic, so ingest takes a while.
2. **🏠 Home:** overview and quick actions.
3. **💬 Ask the Owl:** ask questions about the PDF. Open "See the passages I used" to check the sources.
4. **🎯 Quiz Time:** the quiz covers up to 3 topics, prioritising weak and unseen ones. Wrong answers can become flashcards automatically.
5. **🃏 Flashcards:** review due cards (Again / Hard / Good / Easy), or make new cards for a topic.
6. **📊 My Progress:** mastery per topic, quiz history, and a mastery timeline.

**Starting over:** use **🧹 Reset server index** in the sidebar to clear all uploaded PDFs from the server. Your progress is kept. To delete progress too, use **🗑️ Reset my progress** on the progress page.

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

```powershell
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
| `401 Unauthorized` on upload or reset | API key in the sidebar differs from the Kaggle `API_KEY` | Retype it exactly. In Kaggle, run `print(repr(API_KEY))` to spot hidden spaces. After editing a secret, rerun cell 4 onward |
| `409 ... already indexed` | That filename is already in the index | Click **🧹 Reset server index**, or restart the backend |
| "Can't reach the backend" | Notebook stopped, or the URL changed | Check Kaggle is running and paste the **current** URL |
| "Server took too long" | Model busy (a 14B model on T4 can take 20 to 60 s per answer) | Wait and retry, or switch to the 7B model |
| `422 No readable text found` | The PDF is scanned images | Use a text-based PDF |
| `400 Could not read PDF` | Corrupt or encrypted PDF | Try another file |
| `413 ... too large` | File over `MAX_PDF_MB` (default 30 MB) | Use a smaller PDF or raise `MAX_PDF_MB` |
| `CUDA out of memory` in the Kaggle log | Model too large | Use the 7B model and rerun from cell 5 |
| `ddd.zip not found` | Kaggle unpacked the dataset automatically | The notebook's cell 2 handles both cases; check the dataset is attached under **Input** |
| `did not return JSON` | Wrong or stale URL | Rerun cell 6 and paste the new URL |

---

## Limits to know about

- **The index lives in RAM.** Uploaded PDFs are lost when the Kaggle notebook restarts. Upload them again. Student progress is safe in `student.db`.
- **A new ngrok URL each run.** Free ngrok URLs change every time you start the tunnel.
- **Kaggle sessions end.** They stop after idle time or when your weekly GPU quota runs out. Stop the session when you are done to save quota.
- **No OCR.** Only PDFs with selectable text work.
- **Answer quality depends on the model.** Quizzes should be checked against the source PDF. Results from the 0.5B default model are not reliable.
- **Model downloads need Internet** the first time. Kaggle's Internet setting must be on.
