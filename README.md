# Support Copilot

An **agentic, RAG-powered customer support system**. It answers customer questions from a knowledge base, looks up real order/refund data through a self-built MCP server, decides when a tool action (refund, cancellation, escalation, etc.) is required, and pauses for **human approval** before doing anything consequential — all orchestrated as an explicit **LangGraph** state machine with durable, resumable state.

It is built to demonstrate production-grade agentic AI engineering: hybrid RAG, two-track retrieval, self-grounding verification, long-term customer memory, human-in-the-loop approvals, a hand-rolled MCP server, background job processing, and full observability — not just "call an LLM and print the answer."

---

## 1. What it actually does (product view)

Think of it as a **Zendesk/Intercom-style support desk with an AI agent sitting in the seat**:

- A **customer** (role `user`) chats with the agent. The agent can answer policy questions (from an uploaded knowledge base), check real order status/refund history (via MCP tools), remember things about that customer across sessions, and — when warranted — take action (refund, cancel order, apply store credit, send email, escalate).
- An **operator/admin** (role `admin`) uploads knowledge base documents, reviews and approves/rejects pending agent-proposed actions, manages tickets, manages users, and watches SLA/metrics.
- Tickets submitted outside the chat (`/tickets/intake`) get **auto-triaged** by an LLM on a schedule (intent, urgency, team) and **SLA-breach monitored**, so the system is proactive, not just reactive.

The core engineering thesis: an agent should **read broadly but act narrowly** — it can pull in any context it needs, but it can only cause side effects through a fixed, declared tool registry, and every consequential tool requires a human to click "approve."

---

## 2. System architecture

```
┌────────────────────────── Frontend (React 19 + Vite + Tailwind) ───────────────────────────┐
│  ChatPage · ApprovalsPage · KnowledgePage · TicketsPage · CustomerPage · MetricsPage · Users │
└───────────────────────────────────────┬───────────────────────────────────────────────────────┘
                                         │ axios (JWT bearer, streaming fetch for /chat)
                                         ▼
┌──────────────────────────────────── FastAPI (api, :8000) ────────────────────────────────────┐
│ JWT auth + RBAC · slowapi rate limiting · CORS                                               │
│ /auth/login /auth/refresh · /chat · /approve · /approvals · /documents(+upload) · /tickets   │
│ /memories/{id} · /admin/users                                                                 │
│                                                                                                 │
│   ┌─────────────────────── LangGraph agent (compiled, checkpointed) ─────────────────────┐   │
│   │ load_memory → route →(retrieve|skip)→ draft → grounding_check → extract_semantic     │   │
│   │   → decide_action →(interrupt for approval | auto-exec)→ execute_action → write_memory│   │
│   └──────────────────────────────────────────────────────────────────────────────────────┘   │
└───────┬───────────────────────────────┬──────────────────────────────────┬───────────────────┘
        │                               │                                  │
        ▼                               ▼                                  ▼
┌───────────────────┐      ┌─────────────────────────┐         ┌────────────────────────────┐
│ Postgres+pgvector  │      │ Redis (arq job queue)   │         │ External APIs               │
│ documents/chunks   │      │ ingest_document         │         │ LLM: OpenAI-compatible      │
│ memories (vector)  │◄────►│ auto_triage (cron)      │         │ (Groq / Ollama / OpenAI)     │
│ orders/refunds/... │      │ check_sla (cron)        │         │ Embeddings: local            │
│ users/tickets/      │      └───────────┬─────────────┘         │ sentence-transformers        │
│ approvals/checkpts │                  │                       │ Langfuse (optional traces)   │
└────────────────────┘                  ▼                       └────────────────────────────┘
                              ┌─────────────────────┐
                              │ arq Worker container │
                              └─────────────────────┘
```

**Services (`docker-compose.yml`)**: `db` (pgvector/pgvector:pg16), `redis` (redis:7), `api` (FastAPI), `worker` (arq, separate Dockerfile/container so it scales independently from the API), `frontend` (Nginx-served Vite build), `langfuse` + `langfuse-db` (optional observability stack).

---

## 3. The agent: LangGraph state machine (the centerpiece)

Defined in [backend/app/graph.py](backend/app/graph.py). State is a `TypedDict` (`ChatState`) carrying `message`, `customer_id`, `memories`, `context`, `draft`, `grounded`, `escalate`, `action`, `action_payload`, `human_approved`, `action_result`, etc. — passed between nodes and **checkpointed to Postgres** after every node (`AsyncPostgresSaver`), so a conversation thread can crash, restart, or sit paused for approval indefinitely without losing state.

**Flow:**

```
START
  └─ load_memory        fetch this customer's long-term memories (vector search)
       └─ route          LLM (temp=0) classifies: 'retrieve' or 'skip'
            ├─ retrieve  (only if not a greeting)
            │   ├─ track 1: hybrid_search() over the KB (vector + keyword, RRF fused)
            │   └─ track 2: regex-detect "ORD-123" → MCP get_order / get_refund_status
            └─ draft     LLM writes an answer grounded in context + memories
                 └─ grounding_check   LLM (temp=0) verifies the draft is actually
                 │                    supported by the retrieved context (not just
                 │                    "a relevant chunk existed")
                 └─ extract_semantic  LLM extracts ONE durable fact about the
                 │                    customer, if any ("prefers email", "premium")
                 └─ decide_action     LLM (temp=0) decides: no action / read-only
                      │               tool (auto-exec) / consequential tool
                      ├─ interrupt()  if consequential → graph PAUSES here,
                      │               state checkpointed, HTTP 202 returned
                      │               to frontend, row written to `approvals`
                      └─ execute_action   runs the tool function from TOOL_REGISTRY
                           └─ write_memory   episodic memory: "asked X, we did Y"
                                └─ END
```

**Why each design choice:**

| Choice | Reasoning |
|---|---|
| LLM-based router, not keyword matching | Understands intent ("see ya" vs "what's your refund window") instead of brittle string matching; defaults to `retrieve` on ambiguity (fail-safe, not fail-open). |
| Two-track retrieval (KB *and* MCP) | A vector store answers "what's your return policy"; it can never answer "what's the status of ORD-123" correctly because that's live transactional data, not a textual chunk. Both are retrieval, just from different sources, merged before drafting. |
| Explicit `grounding_check` step | Similarity score says "a relevant chunk was found." It does **not** say "the LLM's answer didn't hallucinate beyond that chunk." Those are different failure modes — a second LLM call (temp=0, strict yes/no) closes that gap and flips `escalate=True` when unsupported. |
| `decide_action` returns structured 3-line text (`ACTION:`/`PAYLOAD:`/`REASON:`), hand-parsed | Works with any OpenAI-compatible model, including small local ones (Llama 3.1 8B via Groq/Ollama) that may not reliably emit valid function-calling JSON. Simpler, more robust across providers than relying on native tool-calling. |
| `interrupt()` (LangGraph primitive) | Physically suspends graph execution and snapshots full state to the Postgres checkpointer — not a polling loop, not an in-memory flag that dies on restart. `POST /approve` resumes with `Command(resume={"approved": bool})` from the exact suspension point. |
| Tool registry (`TOOL_REGISTRY` dict) | Single source of truth read by the graph, the action-planner prompt (`_build_action_list()` builds the prompt dynamically from the registry — no hardcoded tool list to drift out of sync), and the execution step. Adding a tool = one dict entry. |
| Semantic vs. episodic memory split | Episodic = "what happened" (write every turn). Semantic = "durable fact about this customer" (write only when the LLM judges something is actually worth keeping forever) — avoids flooding memory with noise. |

---

## 4. Hybrid retrieval (RAG core)

[backend/app/retrieval.py](backend/app/retrieval.py)

- **Vector search**: pgvector cosine distance (`embedding <=> query_vec`) over `chunks.embedding` (384-dim, HNSW-indexed).
- **Keyword search**: Postgres full-text search (`tsv @@ plainto_tsquery(...)`, GIN-indexed, generated `tsvector` column).
- **Fusion**: **Reciprocal Rank Fusion** (`score = Σ 1/(60 + rank)` across both result lists), *not* a weighted average of raw scores.
  - **Why RRF over averaging**: cosine similarity and `ts_rank` live on incompatible scales — there's no principled way to average them. RRF only uses *rank position*, so scale never matters. `RRF_K=60` is the standard literature constant that dampens the influence of low-ranked hits.
- **Why hybrid at all**: vector search catches *meaning* ("refund" ≈ "money back"); keyword search catches *exact tokens* (order IDs, SKUs, version numbers) that embeddings often blur together. Each compensates for the other's blind spot.
- `best_vector_score` is surfaced back through the graph state as a confidence signal (a weak top match implies "this probably isn't in the KB," feeding the `confidence_threshold` config knob).

**Embeddings** ([backend/app/embeddings.py](backend/app/embeddings.py)): local `sentence-transformers` model `BAAI/bge-small-en-v1.5` (384-dim), CPU, no API key, no per-call cost. BGE models retrieve better when the **query** gets a special instruction prefix ("Represent this sentence for searching relevant passages: ") while **passages** are embedded without it — an intentional asymmetry from the BGE paper, implemented as separate `embed_query` / `embed_passages` functions.

**Chunking** ([backend/app/chunking.py](backend/app/chunking.py)): paragraph-aware, not fixed-character. Packs whole paragraphs up to a 900-char budget with 150-char overlap carried into the next chunk, and force-splits any single paragraph that alone exceeds the budget. Rationale: cutting mid-sentence destroys the semantic unit that retrieval depends on; chunking strategy is one of the highest-leverage RAG tuning knobs, often more impactful than the embedding model choice.

**Eval harness** ([backend/eval/retrieval_eval.py](backend/eval/retrieval_eval.py)): a small labeled question set computes **hit-rate** and **MRR** against `hybrid_search`, plus a separate **prompt-injection eval** that fires known jailbreak strings ("ignore your rules," "you are DAN," "pretend you have no restrictions") at the `draft` system prompt and asserts the response never echoes the injected instruction — turning the "we defend against prompt injection" claim into a runnable, graded test instead of just a comment.

---

## 5. Cost-conscious LLM/embedding split (a deliberate architectural decision)

- **LLM calls** (routing, drafting, grounding check, semantic extraction, action planning, ticket triage) go through a single **OpenAI-compatible client** ([backend/app/llm.py](backend/app/llm.py)) — three env vars (`OPENAI_BASE_URL`, `OPENAI_API_KEY`, `LLM_MODEL`) swap between **Groq** (free tier, `llama-3.1-8b-instant`), **Ollama** (fully local), or real **OpenAI**, with zero code changes. This is low-volume (one to six calls per chat turn) and quality-critical, so it's worth paying an API for.
- **Embeddings** run locally via `sentence-transformers` — high-volume (every chunk on ingest, every query, every memory write/read) and comparatively quality-tolerant, so paying per-call API cost for them doesn't make sense. This LLM-API / embeddings-local split is the single most interview-worthy cost decision in the stack.

---

## 6. MCP integration (Model Context Protocol)

The project **builds its own MCP server** rather than only consuming a third-party one — a deliberately chosen, more advanced demonstration than most "agent" projects attempt.

- **Server** ([backend/app/mcp_server.py](backend/app/mcp_server.py), `FastMCP`, stdio transport): exposes
  - **Tools**: `get_order`, `get_customer`, `list_customer_orders`, `get_refund_status`, `search_orders_by_status`
  - **Resources**: `order://{order_id}`, `customer://{customer_id}` (human-readable reads)
  - **Prompts**: `support_context`, `refund_assessment` (reusable templates an operator/agent can invoke)
- **Client** ([backend/app/mcp_client.py](backend/app/mcp_client.py)): thin async wrappers (`fetch_order_context`, `fetch_customer_context`, `check_refund_status`) called from the graph's `retrieve` node.
- **Why MCP instead of calling Postgres directly from the graph**: it decouples the agent from the data layer — swap Postgres for a different order-management backend and the agent code doesn't change, because it only ever speaks the MCP tool contract. It also demonstrates understanding of the *protocol* (tools + resources + prompts as distinct primitives), not just wiring up one API call.
- **Windows quirk worth knowing**: all MCP imports are lazy (deferred inside functions) because importing `mcp`/`FastMCP` at module load time can trigger a `pywintypes` import failure under uvicorn's reload/subprocess model on Windows. Same import, just deferred.

---

## 7. Tools & the human-in-the-loop approval loop

[backend/app/tools.py](backend/app/tools.py) — every tool is `async`, **idempotent** (critical: the approval flow can retry on network failure without double-charging/double-refunding), and tagged `needs_approval` in `TOOL_REGISTRY`:

| Tool | Approval? | Idempotency mechanism |
|---|---|---|
| `issue_refund` | ✅ required | checks `refunds.order_id` (UNIQUE) before insert → `already_refunded` |
| `cancel_order` | ✅ required | checks for existing `CANCELLED:{order_id}` ticket |
| `update_order_status` | ✅ required | validates against a strict status enum |
| `apply_store_credit` | ✅ required | intentionally stackable (not idempotent — credits can apply multiple times) |
| `send_email` | ✅ required | logged to `emails_sent` for audit |
| `escalate_ticket` | ✅ required | creates a `tickets` row |
| `track_shipment` | ❌ read-only | — |
| `add_internal_note` | ❌ read-only | — |

**Approval flow end-to-end:**
1. `decide_action` calls `interrupt({action, payload, reason, draft, ...})` → graph suspends, checkpoint persisted.
2. `POST /chat` sees `result["__interrupt__"]`, inserts a row into `approvals` (status `pending`) and a linked `tickets` row, returns `{"status": "pending_approval", ...}` to the frontend instead of an answer.
3. Admin reviews in the **Approvals** page, calls `POST /approve {approved, thread_id}`.
4. Backend updates the `approvals` row, then resumes the *exact same graph thread* via `graph.ainvoke(Command(resume={"approved": body.approved}), config={"configurable": {"thread_id": ...}})`.
5. `execute_action` runs the tool only if `human_approved=True`; either way the thread proceeds to `write_memory` and completes.

This is the core "agentic but safe" pattern: the agent can *propose* any consequential action, but a human gate sits between proposal and execution, and that gate is a first-class part of the state graph (not an external if/else bolted on).

---

## 8. Authentication & RBAC

[backend/app/auth.py](backend/app/auth.py) · [backend/app/main.py](backend/app/main.py)

- **Passwords**: bcrypt via `passlib`.
- **Access token**: JWT, HS256, 8-hour expiry, claims `sub` (username), `role`, `customer_id`. Stateless — no DB hit per request to check identity, just signature verification.
- **Refresh token**: JWT, 7-day expiry, `type: "refresh"` claim (so it can never be replayed as an access token), consumed and **rotated** on every `/auth/refresh` call (old token effectively invalidated by issuing a new pair) — if a stolen refresh token gets used, the legitimate user's next refresh attempt with the old token fails, signalling compromise.
- **RBAC**: two roles, `admin` and `user`, embedded directly in the JWT. `require_admin` / `require_any` are FastAPI dependencies gating each route. A `user` is auto-linked to a `customers` row on first login (`create_customer_for_user`, `ON CONFLICT DO UPDATE`, idempotent).
- **Admin seeding**: a fixed admin user is created on startup from `ADMIN_USERNAME`/`ADMIN_PASSWORD` env vars (idempotent — skips if already present).
- **Rate limiting**: `slowapi`, e.g. `/auth/login` capped at 5/min, `/chat` at 20/min, `/tickets/intake` at 30/min.

**Known, deliberately-flagged production gaps** (good interview material — shows awareness, not just code):
- Tokens currently live in browser `sessionStorage` → vulnerable to XSS. Production fix: httpOnly, Secure, SameSite cookies.
- JWTs are stateless, so there is **no revocation before expiry**. Production fix: a Redis-backed token blocklist checked on each request, or refresh tokens persisted in DB so they can be invalidated on logout.

---

## 9. Long-term memory (per-customer)

[backend/app/memory.py](backend/app/memory.py) — distinct from the **LangGraph checkpointer**, which is short-term/per-thread state. This is long-term, cross-session, per-`customer_id`, stored in the `memories` table with its own 384-dim embedding column and HNSW index.

- **Episodic**: "what happened" — written after every interaction (`write_episode` node), e.g. *"Customer asked about refund for ORD-123. Agent processed refund of ₹2999."*
- **Semantic**: durable facts — written only when the LLM judges something is worth keeping forever, e.g. *"Customer is a repeat returner."* (`extract_semantic_memory` node)
- **Retrieval**: vector similarity against the *current message*, not recency — so a 3-month-old memory about "ORD-123" resurfaces exactly when the customer brings up ORD-123 again, even past dozens of newer, unrelated memories.

This three-tier separation (checkpointer / episodic / semantic) — each with different write frequency, retention, and retrieval strategy — is more deliberate than the common "dump everything into one vector store" pattern.

---

## 10. Background jobs (arq worker)

[backend/app/worker.py](backend/app/worker.py) — a separate container (`Dockerfile.worker`) running an `arq` worker against the same Redis/Postgres, so ingestion/triage load never blocks the request-serving API process and the two scale independently.

| Job | Trigger | Purpose |
|---|---|---|
| `ingest_document` | Enqueued on `/documents` or `/documents/upload` | chunk → embed → insert `chunks` rows → flip `documents.status` to `ready`/`failed` |
| `auto_triage` | Cron, every 5 min | LLM-classifies up to 20 unclassified `tickets` (intent/urgency/team), routes to a queue, flips status to `open` |
| `check_sla` | Cron, every 15 min | flags `tickets.sla_breached = true` once open longer than 1h (high) / 4h (medium) / 24h (low) |

Running triage and SLA checks on a schedule rather than in the request path is what makes the system **proactive** — tickets get classified and breaches get surfaced even with no operator online, instead of relying on someone to load a page.

---

## 11. Document ingestion pipeline

```
Admin uploads PDF/DOCX/TXT  (POST /documents/upload, admin-only, ≤20MB/file)
  → extract_text()        PyMuPDF for PDF, python-docx for DOCX (tables included), raw decode for .txt
  → INSERT INTO documents (status='pending')
  → enqueue_job("ingest_document", doc_id)   — returns immediately, doesn't block the request
  → [arq worker] chunk_text() → aembed_passages() → INSERT INTO chunks (per chunk, with embedding)
  → UPDATE documents SET status='ready', chunk_count=N
```
Scanned/image-only PDFs raise a clear `ValueError` ("no extractable text — may be scanned, paste text manually") rather than silently ingesting nothing.

---

## 12. Observability (Langfuse)

[backend/app/tracing.py](backend/app/tracing.py) — every `/chat` call emits a trace (`agent-run`) with input/output/metadata (`route_decision`, `best_vector_score`, `context_chunks`, `memory_count`, `duration_ms`, model name) plus nested spans for `retrieval`, `grounding-check`, `action-decision`, and `action-execution`. Approval decisions get their own `approval-decision` trace. Entirely optional and non-fatal — if `LANGFUSE_PUBLIC_KEY`/`SECRET_KEY` aren't set, tracing silently no-ops; if Langfuse itself errors, the chat response is unaffected (tracing failures are caught and logged, never raised).

---

## 13. Data model

[db/init.sql](db/init.sql) — Postgres 16 + the `pgvector` extension.

| Table | Role |
|---|---|
| `users` | auth + RBAC, links to `customers` |
| `customers` | end-user profile |
| `documents` / `chunks` | KB source docs and their embedded chunks (`VECTOR(384)`, generated `tsvector`) |
| `memories` | per-customer episodic/semantic memories (`VECTOR(384)`) |
| `orders` / `refunds` / `store_credits` | transactional data the agent reads/writes via tools & MCP |
| `tickets` | support tickets (chat escalations + direct intake), carries `intent`/`urgency`/`assigned_to`/`sla_breached` |
| `approvals` | pending/approved/rejected agent-proposed actions, `payload` as `JSONB` |
| `internal_notes` / `emails_sent` | audit trail for agent-side annotations and outbound comms |

**Indexes**: HNSW (`vector_cosine_ops`) on both vector columns for fast approximate similarity search; GIN on the chunks' `tsv` for full-text; B-tree on `approvals.status`/`thread_id` for queue lookups. LangGraph's own checkpoint tables are created separately by `AsyncPostgresSaver.setup()`.

---

## 14. Tech stack

**Backend**: FastAPI · Uvicorn · LangGraph (`>=1.2`) + `langgraph-checkpoint-postgres` · psycopg3 (async, pooled) + pgvector · sentence-transformers · OpenAI SDK (provider-agnostic) · arq + Redis · python-jose + passlib[bcrypt] · PyMuPDF + python-docx · slowapi · pydantic-settings

**Frontend**: React 19 · React Router 7 · Vite 8 · Tailwind CSS 4 · Axios · lucide-react · oxlint

**Infra**: PostgreSQL 16 + pgvector · Redis 7 · Docker / Docker Compose · Langfuse 2 (optional) · GitHub Actions CI

---

## 15. Frontend

[frontend/src/App.jsx](frontend/src/App.jsx) — single `BrowserRouter`, a left sidebar nav filtered by role (`admin`-only items hidden for `user`), route guards (`RequireAuth`, `RequireAdmin`) that redirect to `/login` or `/`.

| Route | Page | Access |
|---|---|---|
| `/login` | LoginPage | public |
| `/` | ChatPage | any authenticated user |
| `/approvals` | ApprovalsPage | admin |
| `/kb` | KnowledgePage | admin |
| `/customer` | CustomerPage ("Customer 360") | admin |
| `/metrics` | MetricsPage | admin |
| `/tickets` | TicketsPage | admin |
| `/users` | UsersPage | admin |

The chat UI streams the `/chat` response (`StreamingResponse`, word-by-word with a small artificial delay server-side) for a typing-effect UX, and surfaces `pending_approval` responses as an inline approval prompt rather than a dead end.

---

## 16. Deployment & CI

- **Images**: `backend/Dockerfile` (API, `uvicorn app.main:app`), `backend/Dockerfile.worker` (same codebase, `arq app.worker.WorkerSettings` entrypoint — one codebase, two run modes), `frontend/Dockerfile` (Vite build → Nginx).
- **docker-compose.yml** wires `db`/`redis` healthchecks as hard dependencies (`condition: service_healthy`) before `api`/`worker` start, and the `api` container has its own `/health` healthcheck.
- **CI** ([.github/workflows/ci.yml](.github/workflows/ci.yml)): three jobs — backend (`py_compile` syntax check + import smoke test), frontend (`npm ci && npm run build` — catches import errors, missing components, Tailwind config breaks), and a Docker job (gated on the first two passing) that builds all three images with `gha` layer caching but never pushes. Deliberately a build/lint gate, not a full test suite — there's no pytest/unit-test job currently, which is a known, callable-out limitation.

---

## 17. Design decisions & tradeoffs (interview cheat sheet)

| Decision | Why | Tradeoff accepted |
|---|---|---|
| OpenAI-compatible client instead of a vendor SDK | One code path works with Groq, Ollama, OpenAI, Together — swap via 3 env vars | Loses access to provider-specific features (e.g. native structured outputs); the system leans on hand-parsed structured text instead |
| Embeddings local, LLM remote | Embeddings are high-volume + cost-tolerant; LLM calls are low-volume + quality-critical | First request pays a one-time ~130MB model download; CPU-bound encode, must be off the event loop (`asyncio.to_thread`) |
| Hybrid (vector+keyword) retrieval via RRF | Neither retrieval mode alone covers both semantic and exact-token queries | Two DB round trips per query instead of one; more code than a pure vector store |
| Self-built MCP server vs. calling Postgres directly | Decouples agent from data layer; demonstrates protocol fluency | More moving parts (a second "service boundary") for what could've been one DB call |
| `interrupt()`-based human approval | Approval state lives *inside* the durable graph state, survives crashes/restarts | Slightly more complex mental model than a simple polling table; requires a checkpointer |
| Structured-text action parsing instead of function-calling | Works even on small local models that don't reliably emit tool-call JSON | Hand-rolled parser is more fragile than native function calling; mitigated by strict prompt format + `temperature=0` |
| Paragraph-aware chunking (900/150) | Avoids mid-sentence cuts that wreck retrieval | No structural awareness (markdown headers, code blocks) yet — flagged as the next upgrade |
| JWT in `sessionStorage`, no revocation list | Simplicity for a project of this scope | XSS exposure + can't force-logout before expiry; explicitly documented production upgrades (httpOnly cookies, Redis blocklist) |
| Separate API and worker containers | Ingestion/triage load never blocks request latency; each scales independently | More infra to run locally (Redis + 2 app containers instead of 1) |

---

## 18. Known limitations / what's explicitly *not* done yet

- No automated test suite in CI beyond syntax/import checks and a frontend build — `eval/retrieval_eval.py` is a manual/local hit-rate + injection-defense script, not wired into CI.
- No token revocation/blocklist; refresh tokens aren't persisted server-side, so rotation detection is best-effort.
- Chunking has no structure awareness (would benefit code/markdown-heavy KBs).
- `apply_store_credit` is intentionally not idempotent (stacking is a feature, but means retries can double-apply if not handled carefully upstream).
- Several tool implementations (`track_shipment`, `update_order_status`) simulate the downstream call instead of hitting a real courier/OMS API — clearly marked in code as integration points.

---

## 19. Running it locally

```bash
cp .env.example .env        # fill in OPENAI_API_KEY (Groq free tier) or point at local Ollama
docker compose up -d        # db, redis, api, worker, frontend, langfuse
```
- API: http://localhost:8000 (docs at `/docs`)
- Frontend: http://localhost:5173
- Langfuse (optional tracing UI): http://localhost:3000
- Default admin login: `ADMIN_USERNAME` / `ADMIN_PASSWORD` from `.env` (defaults `admin` / `admin123` — change in production)

Retrieval/injection eval (manual, against a running DB):
```bash
cd backend && python -m eval.retrieval_eval
```

---

## 20. One-paragraph elevator pitch

*"It's an agentic customer-support copilot: a LangGraph state machine that routes each message, retrieves answers via hybrid vector+keyword search over a knowledge base, cross-references real order data through a self-built MCP server, drafts a grounded reply and verifies its own grounding before answering, decides whether a tool action is warranted, and — for anything consequential like a refund — pauses the entire graph and checkpoints it to Postgres until a human approves. It remembers customers across sessions with separate episodic and semantic memory, runs ticket triage and SLA monitoring on a background worker, and traces every step to Langfuse. The interesting engineering is less 'call an LLM' and more the surrounding scaffolding: grounding verification, idempotent tools, human-in-the-loop as a first-class graph node, and a deliberate local-embeddings/remote-LLM cost split."*
