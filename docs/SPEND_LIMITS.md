# Ask BPL: spend limits and alerts (NFR-8)

**Decision owner: BPL** (team note 2026-11-01: BPL sets the amounts). The figures below are the build team's suggestions.

**For:** whoever holds the OpenAI, Anthropic and Pinecone accounts behind Ask BPL's keys. About 10 minutes. Nothing
here changes the code. Menu paths were checked against each provider's documentation on 2026-11-01; dashboards change,
so if a label differs, look for "Billing" or "Limits".

## How much Ask BPL actually costs (estimate)

| Item | Estimate | Basis |
|---|---|---|
| One answered question (Claude, `claude-sonnet-4-6`) | about $0.015 | ~3,500 input and ~300 output tokens at $3 / $15 per million (assumed sizes; refusals and gated questions cost less) |
| One full evaluation, both sets, `--repeat 3` (228 questions) | about $3.40 | the above x 228 |
| All recorded evaluation traffic since 2026-10-01 (3,609 questions) | about $54 | the above x 3,609 |
| Embedding the whole corpus once (OpenAI) | under $0.01 | 181 passages x ~500 tokens at $0.02 per million |

These are estimates, not invoices. The provider dashboards show the real figures.

## 1. Anthropic (answers): the main cost

1. Sign in to the **Claude Console** and open **Billing** (`platform.claude.com/settings/billing`).
2. In **Spend limits**, click **Set limit** (or **Adjust limit**).
3. Suggested: **$75 per month** while the team is evaluating; **$25 per month** after the code freeze if only BPL IT is
   trying it.
4. What happens at the limit: requests fail with "You have reached your specified API usage limits" until the next
   month or until the limit is raised. Ask BPL then shows its "temporarily unavailable" error, not a wrong answer.
5. Watch actual spend on the **Usage** page (`platform.claude.com/usage`). The documentation does not describe email
   alerts for Anthropic spend, so check this page weekly while testing continues.

## 2. OpenAI (embeddings): small cost, but set a hard cap

1. Sign in at `platform.openai.com`, then **Settings → Organization → Limits** (`platform.openai.com/settings/organization/limits`).
2. Add an **email alert** at **$5**.
3. Set a **hard spend limit** at **$10 per month** (it stops API traffic at the limit). Ask BPL's normal use is far
   below this; reaching it would mean something is wrong (a loop, a leaked key).
4. If the key sits in its own OpenAI project, limits can also be set on that project.

## 3. Pinecone (vector search)

1. In the Pinecone console, check which plan the organization is on.
2. **Starter (free):** no monthly minimum and no charges; usage is capped by the plan's limits instead. Nothing to set.
3. **Paid plan** (Finance is arranging one for a tester's team): open the organization's billing settings and set any
   spending alert offered. Pinecone's documentation does not describe one, so confirm in the console or with Pinecone
   support.

## 4. When the team hands over

- Lower the Anthropic limit to what BPL IT expects to use, or to $0 if nobody will use it for a while.
- Revoke the team's keys and issue BPL-owned keys (SAF-4); never paste a key into a document or chat.

## 5. Record it

Record the limits BPL sets (amounts only, never keys) in `docs/HANDOVER.md` section 8; NFR-8 is done once they are set.
