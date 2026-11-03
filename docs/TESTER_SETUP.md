# Ask BPL test version: setup and testing guide

**Read this first.** This is a **test version**. It can answer questions from only the few BPL policies that have been loaded into it (BPL has 88 policies; the check tool in step 6 tells you how many are loaded right now). BPL has **not yet confirmed that any of them is the current approved version**, so every answer is labelled as coming from a test index. Nothing here is policy advice. Do not use it to make real decisions.

This guide has three parts:

- **Part A is for testers.** You will be given a link or shown a screen. You do not install anything.
- **Part B is for the person who runs the test version** (the build team, or a helper sitting with a tester). It is a step-by-step setup with a built-in check at the end.
- **Part C is for the build team, when more than one person will test.** It explains how to give each tester their own sign-in, what code has to be built for that, and how to run a round of testing with several people.

---

## Before anyone outside the build team tests

Five questions are still open with BPL (Selvon). Until they are answered, **keep testing to the build team and Selvon**. The build team keeps the exact wording in its "Questions for Selvon" list.

| Open BPL question | Why it matters | Requirement |
|---|---|---|
| Is it acceptable that testers' questions are sent to outside services? | Every question typed goes to **OpenAI** (to match it to policy text), **Anthropic** (to write the answer) and **Pinecone** (to store policy text). | SAF-5, SAF-9, NFR-4 |
| Should questions be saved, and for how long? | The test page signs everyone in as an identified demo user, so the question text **is saved** in the database with the answer. (Questions the system blocks for personal details are not saved.) | SAF-5 |
| May testers see the loaded policies while BPL has not confirmed them? | They are labelled "Not yet confirmed by BPL", but BPL has not agreed to that. | ING-1, SAF-6 |
| How will testers get in: on their own computer, or through a link the team runs? | Today each person would need developer tools. See "Why testers should not set this up themselves" below. | INT-1, NFR-3 |
| Who tests, and how is feedback collected? | Everyone signs in as the **same demo user**, so feedback cannot be traced to a person and nobody can test whether answers differ by job role. | (team plan, not a PRD item) |

---

## Part A: for testers

**What you will be given:** a link (or a screen shared by the build team), and a short note from them saying which questions to try.

**What to do**

1. Open the page. Type a question about a BPL policy in everyday words, the way you would ask a colleague.
2. Read the answer. It should say which policy it came from and show a **Not yet confirmed** tag. Open the citation to check the answer against the policy text.
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

**On Windows**, the repository's `.gitattributes` keeps the checked files (the scanned policy's validated text, the policy files) byte-for-byte. A copy cloned **before** that file existed may already have had the validated text's line endings changed. After pulling, refresh those files once (nothing in them is yours to edit; the workbook is not touched):

```
rm -rf packages/orchestrator/extraction_reviews
git checkout -- packages/orchestrator/extraction_reviews
git checkout -- 'packages/orchestrator/sample_corpus/*.yaml' 'packages/orchestrator/sample_corpus/**/*.md'
git status
```

`git status` should then show nothing changed. Do not change `core.autocrlf` for this; `.gitattributes` already covers these folders. Never open and re-save `validated_text.md`: any change, including line endings, makes the system refuse it, by design.

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

You also need an index in Pinecone, created once by the build team (1536 dimensions, cosine; details in `docs/PINECONE_CORPUS_INGEST.md`). It must be a **plain dense vector index**: no integrated embedding model and **no document schema** (text fields). Ask BPL writes vectors it has already made, and Pinecone refuses those writes to a document-schema index. Check an existing index first (reads only):

```
python -c "from pinecone import Pinecone; from ask_bpl_orchestrator.config import get_settings as g; s=g(); print(Pinecone(api_key=s.pinecone_api_key).describe_index(s.pinecone_index_name))"
```

Correct: `dimension=1536`, `metric='cosine'`, `vector_type='dense'`, `embed=None`, and a schema with only `_values` and `_sparse_values`. Then:

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
npm ci
npm run dev
```

Use `npm ci`, not `npm install`: it installs exactly the versions in `package-lock.json` and never changes
`package.json`. If npm suggests `npm audit fix --force` or offers to change versions, do not accept; tell the build
team. A changed lint package once left ESLint unable to run.

Make sure `.env.local` contains `VITE_API_BASE_URL=http://localhost:8000` and **does not** contain `VITE_MOCK_ASK=true` (that switches on pretend answers). Open the address `npm run dev` prints (usually `http://localhost:5173`).

Finally, in a third terminal, check the running system:

```
cd packages/orchestrator && source .venv/bin/activate
askbpl-doctor --url http://localhost:8000
```

Then ask one question you know the answer to, and open its citation. Only then invite a tester.

---

## Part C: several testers, each with their own sign-in

Part B gives you one running copy that everyone uses as the **same demo user**. That is fine for one person at a
time on a shared screen. With several testers it is not: every question and every thumbs-up or thumbs-down is saved
against `pilot-demo@bklynlibrary.org`, so you cannot tell who asked what, cannot follow up on a comment, and cannot
compare expert and non-expert testers.

The fix is: **still one running copy, but each tester signs in with their own email and access code.**

Do not start Part C with people outside the build team until BPL has answered the open questions at the top of this
guide. Per-person sign-in means questions are saved **against a named person**, which makes the "should questions be
saved, and for how long?" question more important, not less.

### C1. What already exists, and what is missing

Already in the code (nothing to build):

| Piece | Where | What it does |
|---|---|---|
| Tester accounts | `testers` table (`db/models.py`, class `Tester`) | One row per person: email, **hashed** access code, group (`SME` or `non_expert`), department, `active` on/off. |
| Sign-in | `POST /auth/sign-in` (`api/routes_auth.py`) | Takes `email`, `access_code`, `attribution_mode`. Returns a `token`. A wrong code gets `401 Invalid credentials`. |
| Token check | `resolve_session` in `api/deps.py` | Every question, feedback and document request accepts `Authorization: Bearer <token>` and records the session against that tester. |
| Switching someone off | `authenticate_tester` in `api/deps.py` | A tester with `active = false` cannot sign in. Their past questions are kept. |
| Holding the sign-in in the page | `web-demo/src/auth/` (`AuthProvider`, `useAuth`, `types.ts`) | Keeps the token in memory only. **Written but not used anywhere yet.** |

Missing (this is the work):

1. **A command to add, list and switch off testers.** Today the only ways in are `askbpl-seed` (the shared demo user)
   and two one-off scripts for named people (`services/seed_selvon.py`, `services/seed_laulder.py`). Those scripts use
   a fixed, shared code (`DEMO2026`) and always set the group to `SME`.
2. **A sign-in screen in the test page.** The page never calls `/auth/sign-in`. It sends no token, so the server
   quietly signs every visitor in as the demo user (`create_attributed_demo_session` in
   `services/public_session.py`).
3. **A setting to turn the shared demo sign-in off.** As long as it is on, anyone can skip the sign-in screen and
   still use the system, and spend on the keys, as the demo user.

Build them in that order (C2, C3, C4). Each is small and can be merged on its own.

**About "attributed" and "anonymous".** The sign-in request has an `attribution_mode`. With `"anonymous"` the session
is **not** linked to the tester (`tester_id` is left empty), even though they signed in with their own code. For
per-person testing, the sign-in screen must send `"attributed"`. If BPL later wants testers to be able to choose, the
screen can offer both, and the choice is then recorded on each session.

### C2. Build: the `askbpl-add-tester` command (orchestrator)

Follow `AGENTS.md`: write the failing tests first.

**Tests first** (new file `packages/orchestrator/tests/test_add_tester.py`, needs the database as in CI):

- `test_add_tester_creates_active_account_with_given_group_and_department`
- `test_add_tester_stores_only_a_hash_of_the_access_code`: the saved `access_code_hash` is not the code itself, and
  `bcrypt.verify(code, hash)` is true.
- `test_added_tester_can_sign_in_with_the_printed_code`: `POST /auth/sign-in` with `attribution_mode: "attributed"`
  returns 200.
- `test_add_tester_twice_keeps_one_row_and_replaces_the_code`: running it again for the same email does not make a
  second row; the old code stops working and the new one works.
- `test_deactivated_tester_cannot_sign_in`: after `--deactivate`, sign-in returns 401.
- `test_add_tester_rejects_an_unknown_group`

**Code:**

1. Make `seed_demo_tester` in `ask_bpl_orchestrator/seed.py` take `group` and `department` as arguments (keep the
   current values, `SME` and `"Pilot"`, as defaults so `askbpl-seed` behaves exactly as before). Today it overwrites
   the group with `SME` every time it runs.
2. Add a new module, for example `ask_bpl_orchestrator/testers_cli.py`, with a `main()` that supports:

   ```
   askbpl-add-tester --email jdoe@bklynlibrary.org --group non_expert --department "Youth Services"
   askbpl-add-tester --from-file testers.csv
   askbpl-add-tester --list
   askbpl-add-tester --deactivate jdoe@bklynlibrary.org
   ```

   - **Making the code.** Generate it with `secrets.token_urlsafe(9)` (about 12 characters). Do not accept codes on the
     command line: they end up in shell history. Print each new code **once**, next to its email, and never write it to
     a file or the database in plain text.
   - **`--from-file`**: a CSV with columns `email,group,department`. Print one line per tester:
     `jdoe@bklynlibrary.org  non_expert  Youth Services  <code>`. Keep the CSV out of Git (put it in your job folder or
     somewhere outside the project folder); it holds names, not codes.
   - **`--list`**: prints email, group, department, active, and when the code was issued. Never prints codes or hashes.
   - **`--deactivate`**: sets `active = false`. Do **not** delete the row: the questions and feedback point to it.
   - Lower-case every email before saving or looking it up (the existing code already does this).
3. Register it in `packages/orchestrator/pyproject.toml` under `[project.scripts]`, next to `askbpl-seed`:

   ```toml
   askbpl-add-tester = "ask_bpl_orchestrator.testers_cli:main"
   ```

   Then reinstall so the command exists: `pip install -e ".[dev]"`.
4. Once this works, delete `services/seed_selvon.py` and `services/seed_laulder.py`, and recreate those two people with
   the new command (they get new, private codes).

**Watch out:** `passlib` is pinned with `bcrypt<4.1` in `pyproject.toml` because newer `bcrypt` crashes it. Do not
upgrade either while doing this.

### C3. Build: a setting to turn the shared demo sign-in off (orchestrator)

**Tests first** (add to an existing API test file, or a new `tests/test_public_demo_switch.py`):

- `test_question_without_token_gets_401_when_public_demo_is_off`
- `test_question_without_token_still_works_when_public_demo_is_on` (today's behaviour, so nothing else breaks)
- `test_question_with_valid_token_works_when_public_demo_is_off`

Use `monkeypatch.setenv("PUBLIC_DEMO_ENABLED", "false")` and clear the settings cache (`get_settings.cache_clear()`)
inside the test, the same way other tests change settings.

**Code:**

1. In `ask_bpl_orchestrator/config.py`, next to `public_demo_tester_email`, add:

   ```python
   # Off = every request must carry a tester's sign-in token (Part C of docs/TESTER_SETUP.md).
   public_demo_enabled: bool = True
   ```
2. In `resolve_session` (`api/deps.py`), just before the last step that calls `create_attributed_demo_session`, return
   `401 "Please sign in"` when `get_settings().public_demo_enabled` is false. Leave the `X-Session-ID` branch above it
   alone for now; it only reuses sessions that already exist.
3. Add a line to `askbpl-doctor` (`doctor.py`) so the check says which mode is on, for example
   `[NOTE] Shared demo sign-in is OFF: testers must sign in with their own code` or
   `[CHECK] Shared demo sign-in is ON: anyone who can open the page uses it as the demo user`. Add a test for each
   message in `tests/test_doctor.py`, following the tests already there.
4. Add `PUBLIC_DEMO_ENABLED=true` (commented, with one line of explanation) to `.env.example`.

Leave it **on** by default so nothing changes for anyone until they choose to turn it off.

### C4. Build: the sign-in screen (web page)

Read `src/components/pilot/Modal.test.tsx` and one more test in `src/` first, and follow their style. Install
`@testing-library/user-event` as a dev dependency if it is not already there (`npm install -D
@testing-library/user-event`, then commit the updated `package-lock.json`).

**Tests first:**

- `src/auth/SignInForm.test.tsx`:
  - `it('sends the email and access code to sign in')`: mock `fetch`, type into the fields found with
    `getByLabelText(/email/i)` and `getByLabelText(/access code/i)`, click `getByRole('button', { name: /sign in/i })`,
    and check the request body contains `attribution_mode: "attributed"`.
  - `it('shows a message when the code is wrong')`: `fetch` answers 401; `await screen.findByRole('alert')` contains
    something like "That email and code don't match".
  - `it('does not show the access code in plain text')`: the code field has `type="password"`.
- `src/conversation/askApi.test.ts` (it already exists; add to it):
  - `it('sends the sign-in token as a bearer header when signed in')`
  - `it('sends no X-Session-ID when a token is present')`

**Code:**

1. **Mount `AuthProvider`.** Wrap the page in `<AuthProvider>` in `src/App.tsx` (or `router.tsx`) so `useAuth()`
   works everywhere. Keep the token in memory only, as `src/auth/types.ts` already says: no `localStorage`. A page
   reload signs the tester out; that is intended.
2. **New `src/auth/SignInForm.tsx`.** It needs:
   - an **Email** field and an **Access code** field (`type="password"`, `autocomplete="off"`), each with a visible
     `<label>`, and a **Sign in** button;
   - on submit, `POST ${apiBase}/auth/sign-in` with
     `{ email, access_code, attribution_mode: 'attributed', user_agent: navigator.userAgent }`;
   - on 200: call `signIn({ token, email, attribution: 'attributed' })` from `useAuth()`;
   - on 401: a message in an element with `role="alert"`; on a network error, reuse `networkErrorMessage` from
     `conversation/askApi.ts`;
   - the "Please do not type personal information" reminder from Part A, short.
3. **Show it before the chat.** In `src/AskPilotShell.tsx`, if `useAuth().session` is empty, show `SignInForm`
   inside the modal instead of the conversation. Once signed in, show the conversation and a small **Sign out** link
   that calls `signOut()`. Show the signed-in email somewhere small, so a tester on a shared computer can see whose
   session it is.
4. **Send the token.** In `src/conversation/demoSession.ts`, change `apiSessionHeaders` and
   `apiSessionHeadersReadOnly` to also take an optional token. When a token is given, send
   `Authorization: Bearer <token>` and **no** `X-Session-ID`. Pass the token in from the callers in
   `src/conversation/askApi.ts` (`postAsk` / `askQuestion`, `fetchDocumentText`, `submitFeedback`). Those are called
   from `src/conversation/useAskChat.ts`, `src/components/pilot/WireframeShell.tsx` and
   `src/components/pilot/DocumentViewer.tsx`; each should read the token from `useAuth()` and pass it in. Leave `src/avatar/AvatarShellLegacy.tsx` as it is; it is switched off by default.
5. **Expired or rejected sign-in.** Sign-ins last `SESSION_TTL_HOURS` (8 hours by default). If any API call returns
   401, call `signOut()` and show the form again with "Your sign-in has ended. Please sign in again." Do not retry.
6. **Mock mode.** When `VITE_MOCK_ASK=true`, skip the form so visual checks still work without a database.
7. **Never put a code in the page settings.** `askbpl-doctor` already warns if `VITE_PILOT_DEMO_ACCESS_CODE` is in
   `.env.local`. Do not add one.

### C5. Check the whole thing before inviting anyone

Run both test suites and note the exit status of each:

```
cd packages/orchestrator && pytest
cd packages/web-demo && npm run test && npm run lint && npm run build
```

Then try it by hand, on your own machine:

1. In `packages/orchestrator/.env`, set `PUBLIC_DEMO_ENABLED=false`. Restart `uvicorn`.
2. `askbpl-add-tester --email you@bklynlibrary.org --group SME --department "Build team"` and note the code.
3. `askbpl-doctor --url http://localhost:8000` shows no **[FIX]** lines and says the shared demo sign-in is off.
4. Open the page. You see the sign-in form, not the chat.
5. Sign in with a **wrong** code: you get the "don't match" message.
6. Sign in with the right code, ask a question, and give it a thumbs-up.
7. Check it was saved against you (step C7 shows how).
8. `askbpl-add-tester --deactivate you@bklynlibrary.org`, sign out, try again: sign-in is refused.

### C6. Running a round of testing with several people

1. **Make the list.** A CSV with `email,group,department`, one row per tester. Use `SME` for people who know the
   policies well (HR, managers, policy owners) and `non_expert` for everyone else. Put the real department, so you
   can later see whether answers work for different roles.
2. **Before anyone signs in:**
   - Set your own `PILOT_DEMO_ACCESS_CODE` in `.env` and rerun `askbpl-seed`, so the default `DEMO2026` no longer
     works anywhere.
   - Set `PUBLIC_DEMO_ENABLED=false`.
   - Set a spending limit and an alert in the OpenAI, Anthropic and Pinecone dashboards (see "Cost, keys and sharing"
     below). With several testers, spend adds up faster.
   - Decide who can reach the server. With `--host 127.0.0.1` only your own computer can; testers would use your
     screen. A copy others can open from their own computers needs a decision from BPL first (open question 4).
3. **Create the accounts:** `askbpl-add-tester --from-file testers.csv`. Copy the printed codes straight into
   individual messages.
4. **Send each tester, separately:** the link, their email, their own code, and the Part A instructions. Send the
   code on its own, not in a group email or a shared document. If a code is exposed, run `askbpl-add-tester` again
   for that email: the old code stops working.
5. **During testing:** use `askbpl-add-tester --list` to see who has an account. Switch off anyone who leaves the
   test with `--deactivate`.
6. **At the end of the round:** deactivate every tester account. Then follow whatever BPL decides about keeping or
   deleting the saved questions (open question 2).

### C7. Seeing results per tester

The build-team console's Sessions page is not wired up yet, and `GET /admin/sessions` shows a tester ID but not an
email. Until that is built, read the results straight from the database (this changes nothing):

```
docker compose -f infra/docker-compose.yml exec postgres psql -U askbpl -d askbpl
```

Then:

```sql
SELECT t.email, t."group", t.department,
       q.submitted_at, q.question_text, r.response_type,
       f.rating, f.comment
FROM questions q
JOIN testers t        ON t.tester_id = q.tester_id
LEFT JOIN responses r ON r.request_id = q.request_id
LEFT JOIN feedback f  ON f.request_id = q.request_id
ORDER BY t.email, q.submitted_at;
```

And a summary by group:

```sql
SELECT t."group", count(*) AS questions,
       count(*) FILTER (WHERE f.rating = 'helpful')     AS helpful,
       count(*) FILTER (WHERE f.rating = 'not_helpful') AS not_helpful
FROM questions q
JOIN testers t       ON t.tester_id = q.tester_id
LEFT JOIN feedback f ON f.request_id = q.request_id
GROUP BY t."group";
```

Questions from anonymous sessions and from the shared demo user have no tester (or the demo tester) and are not split
out by person. Questions blocked for personal details have no saved text. Treat what you read here as staff data: do
not copy it into chat, email or a shared document without BPL's agreement.

A good follow-up is to show the email and group on the console's Sessions and Feedback pages. That needs a change to
`routes_internal.py` and the two console pages, with tests.

### C8. Later: real BPL sign-in

Access codes are a stand-in. The plan (`TRD-AUTH-5`, noted in `seed_selvon.py`) is to replace them with BPL's own
Microsoft sign-in (Entra ID), which also gives each person's real role. When that happens, the `testers` table and the
token check stay; only how a person proves who they are changes. Do not build that until BPL asks for it.

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
| Answers from the Collection Maintenance Procedures call it a policy, or the per-passage type shows "not recorded" | The database was loaded before patch 0060 recorded document types. | Run `alembic upgrade head`, then `askbpl-apply-inventory` once (it changes no vectors). |
| `No policy documents can be used` | Nothing is loaded, or test mode is off. | Run step 5; check `ALLOW_TEST_INDEX=true`. |
| `PRETEND mode` | The page shows canned answers. | Remove `VITE_MOCK_ASK` from `.env.local` and restart the page. |
| `The service refused the key` (with `--live`) | The key is mistyped, expired or switched off. | Ask the build team for a replacement. Do not post the old one anywhere. |
| Every question is refused | Often a loading problem, sometimes correct. | Run `askbpl-doctor --live`; if it is clean, tell the build team which question. |
| `This index has a document schema, so writes must go through the documents API` | The Pinecone index was created as a document-schema index. Upgrading the client does not help. | Delete it and create a plain dense index (1536, cosine, no document schema): `docs/PINECONE_CORPUS_INGEST.md` section 2. If `.env` has `PINECONE_HOST`, update it to the new index's host. |
| `validation record rejected: validated text was changed after the review was finalized` | Usually line endings changed by Git on Windows; otherwise someone edited the file. | Refresh the files as in step 1 (Windows), then `askbpl-extraction-review verify`. Do not edit the file. |

## What this version does not do yet

Not built, or waiting on BPL: real sign-in by person and role; a hosted review environment; approved acronym definitions; BPL-approved contact details and crisis wording; a confirmed list of current policies; a decision on retention and outside processing. See the progress report for the full list.
