-- Nastavení měnitelné z admin panelu.
-- Migrace, ne přepis: tenhle soubor se u existující instalace nespustí
-- (init skripty Postgresu běží jen nad prázdnou databází), proto tabulku
-- zakládá i control-plane při startu. Tady je pro čisté instalace.

CREATE TABLE IF NOT EXISTS setting (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by TEXT
);

COMMENT ON TABLE setting IS
  'Konfigurace čtená za běhu. Věci vyžadující restart zůstávají v .env.';
