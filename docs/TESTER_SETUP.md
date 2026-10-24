# Ask BPL test version: setup and testing guide

**Read this first.** This is a **test version**. It can answer questions from only the few BPL policies that have been loaded into it (BPL has 88 policies; the check tool in step 6 tells you how many are loaded right now). BPL has **not yet confirmed that any of them is the current approved version**, so every answer is labelled as coming from a test index. Nothing here is policy advice. Do not use it to make real decisions.

This guide has two parts:

- **Part A is for testers.** You will be given a link or shown a screen. You do not install anything.
- **Part B is for the person who runs the test version** (the build team, or a helper sitting with a tester). It is a step-by-step setup with a built-in check at the end.

---

## Before anyone outside the build team tests

Five questions are still open with BPL (Selvon). Until they are answered, **keep testing to the build team and Selvon**. The build team keeps the exact wording in its "Questions for Selvon" list.

| Open BPL question | Why it matters | Requirement |
|---|---|---|
| Is it acceptable that testers' questions are sent to outside services? | Every question typed goes to **OpenAI** (to match it to policy text), **Anthropic** (to write the answer) and **Pinecone** (to store policy text). | SAF-5, SAF-9, NFR-4 |
| Should questions be saved, and for how long? | The test page signs everyone in as an identified demo user, so the question text **is saved** in the database with the answer. (Questions the system blocks for personal details are not saved.) | SAF-5 |
| May testers see the loaded policies while BPL has not confirmed them? | They are labelled "Test index", but BPL has not agreed to that. | ING-1, SAF-6 |
| How will testers get in: on their own computer, or through a link the team runs? | Today each person would need developer tools. See "Why testers should not set this up themselves" below. | INT-1, NFR-3 |
| Who tests, and how is feedback collected? | Everyone signs in as the **same demo user**, so feedback cannot be traced to a person and nobody can test whether answers differ by job role. | (team plan, not a PRD item) |

---

## Part A: for testers

**What you will be given:** a link (or a screen shared by the build team), and a short note from them saying which questions to try.

**What to do**

1. Open the page. Type a question about a BPL policy in everyday words, the way you would ask a colleague.
2. Read the answer. It should say which policy it came from and show a **Test index** tag. Open the citation to check the answer against the policy text.
3. If the page says it cannot answer, that can be correct. The system is designed to refuse when the policy does not say. Tell the build team if you think it *should* have been able to answer.
4. Send your feedback to the person who gave you the link. For each problem, note: what you asked, what you expected, what you got.

**Please do not type personal information**, including:

- Real names of colleagues, patrons or children, or details of a real case.
- Anything you would not want an outside company to receive. Questions are sent to outside AI services (see above).
- Passwords, keys or access codes.

**What the answers are, and are not**

- They are drawn only from the loaded policy text, with the source shown. If you see an answer with no source, report it.
- They are **not** confirmed current, **not** legal advice and **not** a substitute for asking HR, your manager or the policy owner.
- The page does **not** change answers by your job role yet. Everyone tests as the same user.
- "Librarian verified" or legal views do not exist in this version. That is deliberate: it needs a BPL review process that has not been defined.

---

## Why testers should not set this up themselves

Running the test version needs Python, Node.js, Docker, a database and **paid keys for three outside services**. Every tester who did this would need those keys, and a key handed to many people is a real risk: anyone holding one can spend money on it, and spend alerts have not been set up yet (NFR-8).

So: **the build team runs one copy and testers use it.** If a hosted copy is not ready, a helper runs it and the tester uses it on the helper's screen.

---

## Part B: for the person running the test version

You will need: Git, **Python 3.10 or newer** (3.11 is what the project uses), **Node.js (current LTS)**, **Docker Desktop**, and the three keys from the build team. **Never paste a key into chat, email or a document.** If one is exposed, tell the build team so it can be replaced.

### Step 1. Get the code

Open a terminal in the folder where the project lives. All the commands below are run from the **project folder** unless it says otherwise.

### Step 2. Create the settings file (`.env`)

1. Copy `.env.example` (in the project folder) to a new file named `.env` **inside `packages/orchestrator`**.
   *This is the most common mistake.* The program reads `.env` from the folder you run it in, which is `packages/orchestrator`. A `.env` left in the project's top folder is not found and the keys will look missing.
2. Open `.env` in a text editor and fill in:
   - `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `PINECONE_API_KEY` (from the build team), and `PINECONE_INDEX_NAME` if it differs from `askbpl-pilot`.
   - `JWT_SECRET_KEY`: the program refuses to start without it. Make one by running `python3 -c "import secrets; print(secrets.token_urlsafe(48))"` and pasting the result after the `=`.
3. Type values with **no spaces and no quote marks** around them.
4. Leave `ALLOW_TEST_INDEX=true`. This is what lets the unconfirmed test policies answer, with the label.

The file `.env` is ignored by Git, so it is not uploaded. Keep it that way: **do not add it to Git and do not send it to anyone.**

### Step 3. Start the database

Open Docker Desktop and wait until it says it is running. Then, in the project folder:

```
docker compose -f infra/docker-compose.yml up -d
```

### Step 4. Install and prepare

```
cd packages/orchestrator
python3 -m venv .venv
source .venv/bin/activate          # on Windows: .venv\Scripts\activate
pip install -e ".[dev]"
alembic upgrade head
askbpl-seed
```

`alembic upgrade head` builds the database tables. `askbpl-seed` adds the contact routing rules and the shared **demo tester** account that the test page uses.

### Step 5. Load the test policies

You also need an index in Pinecone, created once by the build team (1536 dimensions, cosine; details in `docs/PINECONE_CORPUS_INGEST.md`). Then:

```
askbpl-ingest-batch
```

This reads the policy PDFs in `sample_corpus/pilot`, applies the team's per-document decisions from the source inventory, and stores the text in the database and Pinecone. It **uses paid OpenAI and Pinecone usage** (small). One scanned policy is held back on purpose, because its text has not been checked by a person.

### Step 6. Run the check

```
askbpl-doctor
```

It tells you, in plain words, what is ready and what is not. Every line marked **[FIX]** says what to do. Fix the first one, run it again, and repeat until none is left. Then run:

```
askbpl-doctor --live
```

That also asks OpenAI, Anthropic and Pinecone whether the keys work. It costs a fraction of a cent. Run it only when you mean to.

| Tag | Meaning |
|---|---|
| **[OK]** | This part is in place. |
| **[FIX]** | Testing will not work until this is fixed. |
| **[CHECK]** | Not broken, but look at it. |
| **[NOTE]** | Something to know. Not a problem. |
| **[SKIP]** | Not checked (for example, a key is not set). |

The check **never prints a key**, never changes anything, and does not contact any outside service unless you add `--live`. It cannot tell you whether answers are right, whether the policies are current, or whether BPL has approved the use of outside services. A clean result means only that the parts are connected.

### Step 7. Start the server and the page

In one terminal (still in `packages/orchestrator`, with the virtual environment on):

```
uvicorn ask_bpl_orchestrator.main:app --host 127.0.0.1 --port 8000
```

In a second terminal:

```
cd packages/web-demo
cp .env.example .env.local        # on Windows: copy .env.example .env.local
npm install
npm run dev
```

Make sure `.env.local` contains `VITE_API_BASE_URL=http://localhost:8000` and **does not** contain `VITE_MOCK_ASK=true` (that switches on pretend answers). Open the address `npm run dev` prints (usually `http://localhost:5173`).

Finally, in a third terminal, check the running system:

```
cd packages/orchestrator && source .venv/bin/activate
askbpl-doctor --url http://localhost:8000
```

Then ask one question you know the answer to, and open its citation. Only then invite a tester.

---

## Cost, keys and sharing: what to watch

- **Spend alerts are not set up yet** (NFR-8). Before real testing, the build team should set a spending limit and an alert in each of the OpenAI, Anthropic and Pinecone dashboards.
- Use `--host 127.0.0.1` as above. That keeps the server reachable only from your own computer. Do not open it to a network, and do not host it publicly, until BPL has answered the open questions.
- The demo account is created with a **default access code** (`DEMO2026`) unless you set `PILOT_DEMO_ACCESS_CODE` before running `askbpl-seed`. If a server is ever reachable by others, set your own code first.
- The test page signs everyone in automatically as the same demo user. Anyone who can reach the page can use it and spend on the keys behind it.
- Questions and answers are saved in the database on the machine running it (except questions blocked for personal details, whose text is not stored). Treat that machine, and the database, as holding staff questions.

## If something goes wrong

| What you see | What it means | What to do |
|---|---|---|
| `[FIX] ... is not set` for a key | The program cannot find it. | Check the `.env` is in `packages/orchestrator`, with no quote marks or spaces. |
| `Cannot reach the database` | The database is not running. | Open Docker Desktop, rerun step 3, wait a minute. |
| `The database tables are not up to date` | The code is newer than the database. | Run `alembic upgrade head`. |
| `No policy documents can be used` | Nothing is loaded, or test mode is off. | Run step 5; check `ALLOW_TEST_INDEX=true`. |
| `PRETEND mode` | The page shows canned answers. | Remove `VITE_MOCK_ASK` from `.env.local` and restart the page. |
| `The service refused the key` (with `--live`) | The key is mistyped, expired or switched off. | Ask the build team for a replacement. Do not post the old one anywhere. |
| Every question is refused | Often a loading problem, sometimes correct. | Run `askbpl-doctor --live`; if it is clean, tell the build team which question. |

## What this version does not do yet

Not built, or waiting on BPL: real sign-in by person and role; a hosted review environment; approved acronym definitions; BPL-approved contact details and crisis wording; a confirmed list of current policies; a decision on retention and outside processing. See the progress report for the full list.
