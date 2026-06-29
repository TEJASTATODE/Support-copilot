-- Runs automatically the FIRST time the pgdata volume is created.
-- To re-run: docker compose down -v && docker compose up -d

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS documents (
    id          SERIAL PRIMARY KEY,
    title       TEXT NOT NULL,
    source      TEXT,
    content     TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'pending',
    chunk_count INT  NOT NULL DEFAULT 0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS chunks (
    id          SERIAL PRIMARY KEY,
    document_id INT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index INT NOT NULL,
    content     TEXT NOT NULL,
    embedding   VECTOR(384),
    tsv         TSVECTOR GENERATED ALWAYS AS (to_tsvector('english', content)) STORED
);

CREATE TABLE IF NOT EXISTS customers (
    id          SERIAL PRIMARY KEY,
    external_id TEXT UNIQUE,
    name        TEXT,
    email       TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS tickets (
    id            SERIAL PRIMARY KEY,
    customer_id   INT REFERENCES customers(id) ON DELETE SET NULL,
    thread_id     TEXT,
    subject       TEXT,
    body          TEXT,
    intent        TEXT,
    urgency       TEXT,
    status        TEXT NOT NULL DEFAULT 'new',
    assigned_to   TEXT,
    sla_breached  BOOLEAN DEFAULT false,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at   TIMESTAMPTZ
);


CREATE TABLE IF NOT EXISTS memories (
    id          SERIAL PRIMARY KEY,
    customer_id INT NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    kind        TEXT NOT NULL,
    content     TEXT NOT NULL,
    embedding   VECTOR(384),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS orders (
    id          SERIAL PRIMARY KEY,
    order_id    TEXT NOT NULL UNIQUE,
    customer_id INT REFERENCES customers(id) ON DELETE SET NULL,
    product     TEXT NOT NULL,
    amount      NUMERIC(10,2) NOT NULL,
    status      TEXT NOT NULL DEFAULT 'processing',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS refunds (
    id         SERIAL PRIMARY KEY,
    order_id   TEXT NOT NULL UNIQUE,
    amount     NUMERIC(10,2) NOT NULL,
    reason     TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS store_credits (
    id          SERIAL PRIMARY KEY,
    customer_id INT NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    amount      NUMERIC(10,2) NOT NULL,
    reason      TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS internal_notes (
    id          SERIAL PRIMARY KEY,
    ticket_id   INT REFERENCES tickets(id) ON DELETE CASCADE,
    customer_id INT REFERENCES customers(id) ON DELETE CASCADE,
    note        TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS emails_sent (
    id          SERIAL PRIMARY KEY,
    customer_id INT REFERENCES customers(id) ON DELETE CASCADE,
    subject     TEXT NOT NULL,
    body        TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS approvals (
    id          SERIAL PRIMARY KEY,
    thread_id   TEXT NOT NULL,
    customer_id INT,
    action      TEXT NOT NULL,
    payload     JSONB NOT NULL DEFAULT '{}',
    status      TEXT NOT NULL DEFAULT 'pending',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at TIMESTAMPTZ
);

-- indexes
CREATE INDEX IF NOT EXISTS chunks_embedding_hnsw   ON chunks   USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS chunks_tsv_gin          ON chunks   USING gin  (tsv);
CREATE INDEX IF NOT EXISTS memories_embedding_hnsw ON memories USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS memories_customer_idx   ON memories (customer_id);
CREATE INDEX IF NOT EXISTS approvals_status_idx    ON approvals (status);
CREATE INDEX IF NOT EXISTS approvals_thread_idx    ON approvals (thread_id);

-- seed data
INSERT INTO orders (order_id, customer_id, product, amount, status)
VALUES
    ('ORD-123', NULL, 'Wireless Headphones', 2999.00, 'shipped'),
    ('ORD-456', NULL, 'Phone Case',           499.00, 'delivered'),
    ('ORD-789', NULL, 'Laptop Stand',        1299.00, 'processing'),
    ('ORD-999', NULL, 'Bluetooth Speaker',   1999.00, 'delivered')
ON CONFLICT (order_id) DO NOTHING;

CREATE TABLE IF NOT EXISTS users (
    id              SERIAL PRIMARY KEY,
    username        TEXT NOT NULL UNIQUE,
    hashed_password TEXT NOT NULL,
    role            TEXT NOT NULL DEFAULT 'user',
    is_active       BOOLEAN NOT NULL DEFAULT true,
    customer_id     INT REFERENCES customers(id) ON DELETE SET NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);