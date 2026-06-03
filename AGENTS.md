# Testing Instructions for AI Agents — Ask BPL

Consistent testing approach for this monorepo. Applies to all code changes in `packages/orchestrator` (Python/FastAPI) and `packages/web-demo` (React/Vite).

---

## General Rules (apply to every stack)

- **Always write a failing test before changing behavior.** Red → green → refactor.
- **Test behavior, not implementation.** Assert on outputs, rendered UI, or HTTP responses — never on internal variables, private methods, or call counts unless the call itself is the contract.
- **One assertion concept per test.** The test name must describe what's being verified.
- **Use Arrange / Act / Assert structure.** Separate setup, execution, and assertions with blank lines.
- **Do not delete or skip tests to make a build pass.** If a test is wrong, fix it or explain why in the PR.
- **Do not mock the thing under test.** Mock collaborators (network, DB, time, randomness) — never the function you're testing.
- **Run the tests before reporting work as done.** Do not claim "tests pass" without running them.
- **Match the existing test style.** Read 2–3 nearby test files before writing a new one. Follow their naming, structure, and helper patterns.
- **No commented-out tests, no `.only`, no `.skip` left in committed code.**

---

## Ask BPL monorepo

| Package | Stack | Test location | Run |
|---------|-------|---------------|-----|
| `packages/orchestrator` | FastAPI, pytest, pytest-asyncio | `tests/test_*.py` | `cd packages/orchestrator && pytest` |
| `packages/web-demo` | React 19, Vitest, Testing Library | `src/**/*.test.{ts,tsx}` | `cd packages/web-demo && npm run test` |

CI runs both jobs (see `.github/workflows/ci.yml`). After changes, run the relevant suite(s) and report the command plus exit status.

**Orchestrator integration tests** (`test_api_integration.py`, etc.) require Postgres with migrations and seed — same as CI:

```bash
docker compose -f infra/docker-compose.yml up -d
cd packages/orchestrator && alembic upgrade head && askbpl-seed && pytest
```

Smoke tests like `test_api_smoke.py` hit `/healthz` and do not need a database.

---

## React — `packages/web-demo` (Vitest + React Testing Library)

### Conventions

- Test files: `Component.test.tsx` or `module.test.ts` next to source under `src/`.
- Use `describe` / `it` from `vitest` (see `Modal.test.tsx`, `types.test.ts`).
- Setup: `src/test/setup.ts` loads `@testing-library/jest-dom/vitest`.
- **Query by accessible role or text first.** Order of preference:
  1. `getByRole('button', { name: /submit/i })`
  2. `getByLabelText`, `getByPlaceholderText`
  3. `getByText`
  4. `getByTestId` — **last resort only**, when nothing else works.
- **Never query by class name, CSS selector, or DOM structure.**
- Use `@testing-library/user-event` (not `fireEvent`) for interactions — install if adding new interaction tests.
- Wrap `userEvent` calls in `await` — it is async.

### Required pattern

```tsx
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { LoginForm } from './LoginForm'

describe('LoginForm', () => {
  it('submits the form with entered credentials', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()

    render(<LoginForm onSubmit={onSubmit} />)

    await user.type(screen.getByLabelText(/email/i), 'a@b.com')
    await user.type(screen.getByLabelText(/password/i), 'secret')
    await user.click(screen.getByRole('button', { name: /log in/i }))

    expect(onSubmit).toHaveBeenCalledWith({ email: 'a@b.com', password: 'secret' })
  })
})
```

### Async UI

- Use `findBy*` queries for elements that appear after async work.
- Use `waitFor` only when there is no element-appearance to await.
- Do not use arbitrary `setTimeout` or `sleep` in tests.

### Mocking modules

- Use `vi.mock('module-path')` at the top of the file.
- Mock fetch/axios at the network boundary, not inside components.

### Run

```bash
cd packages/web-demo
npm run test              # single run (CI)
npm run test:watch        # watch mode
npm run test -- src/path/to/Component.test.tsx
```

---

## Python — `packages/orchestrator` (pytest)

### Conventions

- Test files: `tests/test_*.py`.
- Test functions: `def test_<behavior>():`.
- Config: `[tool.pytest.ini_options]` in `pyproject.toml` (`asyncio_mode = "auto"`, `testpaths = ["tests"]`).
- Use fixtures (`@pytest.fixture`) for shared setup — do not duplicate setup across tests.
- Use `pytest.mark.parametrize` for tests that differ only by input/output.
- Use `tmp_path` for file I/O — never write to the real filesystem.
- Use `monkeypatch` for env vars; use `unittest.mock.patch` / `AsyncMock` for external services (OpenAI, Pinecone, etc.) — see `test_api_integration.py`.
- API tests use `fastapi.testclient.TestClient` with `from ask_bpl_orchestrator.main import app`.

### Required patterns

```python
import pytest
from fastapi.testclient import TestClient

from ask_bpl_orchestrator.main import app

client = TestClient(app)


def test_healthz_ok_and_request_id_header() -> None:
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers.get("X-Request-ID")


def test_example_raises() -> None:
    with pytest.raises(ValueError):
        raise ValueError("expected")


@pytest.mark.parametrize("rating,status", [
    ("helpful", 401),
])
def test_feedback_requires_bearer_token(rating: str, status: int) -> None:
    response = client.post("/feedback/", json={"request_id": "00000000-0000-0000-0000-000000000001", "rating": rating})

    assert response.status_code == status
```

### Database

- Unit tests mock the DB layer or avoid DB entirely.
- Integration tests use the CI Postgres URL pattern (`DATABASE_URL`, migrations, `askbpl-seed`) — never dev or prod databases.

### Run

```bash
cd packages/orchestrator
pytest                    # all tests
pytest -v                 # verbose
pytest tests/test_x.py    # one file
pytest -k "healthz"       # tests matching name
pytest --cov=ask_bpl_orchestrator  # with coverage
pytest -x                 # stop on first failure
```

---

## When you write or change code

1. Identify which behaviors changed.
2. Write or update tests for each changed behavior.
3. Run the full test suite for the package you touched — not just one file when feasible.
4. If a previously passing test now fails, explain whether the test or the code is wrong before making it pass.
5. Report the test command you ran and its exit status in your final summary.

---

## When tests fail

- Read the error message before changing anything.
- Reproduce the failure locally with the narrowest possible test invocation.
- Do not "fix" a test by loosening an assertion (`toBeTruthy` instead of `toBe(5)`) unless the original assertion was wrong.
- Do not add `try/except` or `try/catch` around the assertion to make it pass.
- If a test is flaky, find the source of nondeterminism (time, ordering, async race) — do not add retries.
