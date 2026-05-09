-- Схема БД для сессий чата и лидов (SQLite-совместимый синтаксис).
-- Для PostgreSQL: замените AUTOINCREMENT на SERIAL/BIGSERIAL или GENERATED AS IDENTITY,
-- тип DATETIME на TIMESTAMPTZ, при необходимости добавьте расширение uuid-ossp.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS chat_sessions (
    id              TEXT PRIMARY KEY,           -- UUID с клиента или сервера
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
    user_agent      TEXT,
    client_ip_hash  TEXT,                       -- опционально: хэш IP для метрик без хранения сырого IP
    metadata_json   TEXT                        -- JSON: referrer, UTM и т.д.
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      TEXT NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    role            TEXT NOT NULL CHECK (role IN ('system', 'user', 'assistant', 'tool')),
    content         TEXT NOT NULL,
    token_count     INTEGER,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    meta_json       TEXT                        -- JSON: model id, latency_ms, retrieval chunks ids
);

CREATE INDEX IF NOT EXISTS idx_chat_messages_session_created
    ON chat_messages(session_id, created_at);

CREATE TABLE IF NOT EXISTS leads (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id           TEXT REFERENCES chat_sessions(id) ON DELETE SET NULL,
    display_name         TEXT,
    phone                TEXT NOT NULL,
    preferred_contact_at TEXT,                   -- свободный текст: «будни 10–18», «завтра после 15»
    topic                TEXT,                   -- интерес к тренингу / тема
    notes                TEXT,
    raw_dialog_summary   TEXT,
    status               TEXT NOT NULL DEFAULT 'new'
        CHECK (status IN ('new', 'notified', 'failed', 'processed')),
    created_at           TEXT NOT NULL DEFAULT (datetime('now')),
    telegram_message_id  TEXT,                   -- ответ Telegram API при успехе
    email_sent_at        TEXT,                   -- когда ушла копия на почту (NULL если не слали)
    email_error          TEXT,
    error_detail         TEXT                    -- ошибка доставки TG/SMTP и т.д.
);

CREATE INDEX IF NOT EXISTS idx_leads_session ON leads(session_id);
CREATE INDEX IF NOT EXISTS idx_leads_status_created ON leads(status, created_at);
