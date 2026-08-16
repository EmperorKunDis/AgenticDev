-- ═══════════════════════════════════════════════════════════════
--  AgenticDev — ledger (L2)
--  Spouští se automaticky při prvním startu Postgresu.
-- ═══════════════════════════════════════════════════════════════
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE DATABASE forgejo OWNER agenticdev;

\c agenticdev

-- ─── Číselníky ─────────────────────────────────────────────────
CREATE TYPE phase_kind  AS ENUM ('discovery','design','implementation','hardening','delivery','support');
CREATE TYPE task_state  AS ENUM ('backlog','ready','assigned','running','blocked','review','done','aborted');
CREATE TYPE data_class  AS ENUM ('public','internal','confidential','restricted');
CREATE TYPE risk_class  AS ENUM ('low','standard','elevated','high');
CREATE TYPE decision_state AS ENUM ('auto','pending_human','approved','rejected');
CREATE TYPE release_channel AS ENUM ('canary','beta','stable');

-- ─── Klienti a projekty ────────────────────────────────────────
CREATE TABLE client (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name        text NOT NULL UNIQUE,
  ico         text,
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE project (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  client_id   uuid REFERENCES client(id),
  code        text NOT NULL UNIQUE,          -- montexbau, schekonom, ...
  repo_url    text NOT NULL,
  data_class  data_class NOT NULL DEFAULT 'internal',
  -- politika: jaké modely smí projekt použít; NULL = globální default
  model_allowlist  text[],
  budget_czk_month numeric(10,2) DEFAULT 5000,
  director_overrides jsonb NOT NULL DEFAULT '{}'::jsonb,
  active      boolean NOT NULL DEFAULT true,
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE phase (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id  uuid NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  kind        phase_kind NOT NULL,
  order_idx   int NOT NULL,
  active      boolean NOT NULL DEFAULT false,
  UNIQUE (project_id, kind)
);

CREATE TABLE task (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  phase_id    uuid NOT NULL REFERENCES phase(id) ON DELETE CASCADE,
  kind        text NOT NULL,                  -- feature | bugfix | refactor
  title       text NOT NULL,
  spec_ref    text,                           -- prd/<projekt>/10-requirements.md#REQ-042
  dod         jsonb NOT NULL DEFAULT '[]'::jsonb,
  write_scope text[] NOT NULL DEFAULT '{}',
  risk        risk_class NOT NULL DEFAULT 'standard',
  budget_czk  numeric(10,2) NOT NULL DEFAULT 300,
  state       task_state NOT NULL DEFAULT 'backlog',
  priority    int NOT NULL DEFAULT 100,
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON task (state, priority);

-- ─── Lidé a stroje ─────────────────────────────────────────────
CREATE TABLE principal (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  kind         text NOT NULL CHECK (kind IN ('human','agent','service')),
  display_name text NOT NULL,
  email        text,
  active       boolean NOT NULL DEFAULT true
);

CREATE TABLE workstation (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  principal_id  uuid NOT NULL REFERENCES principal(id),
  hostname      text NOT NULL UNIQUE,
  device_key_fp text NOT NULL UNIQUE,          -- ed25519 fingerprint
  channel       release_channel NOT NULL DEFAULT 'stable',
  last_seen_at  timestamptz,
  revoked_at    timestamptz
);

CREATE TABLE project_member (
  project_id   uuid NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  principal_id uuid NOT NULL REFERENCES principal(id) ON DELETE CASCADE,
  active       boolean NOT NULL DEFAULT true,
  PRIMARY KEY (project_id, principal_id)
);

-- ─── Verze runtime (kompatibilní matice) ───────────────────────
CREATE TABLE harness_version (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  semver       text NOT NULL UNIQUE,
  image_digest text NOT NULL,
  released_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE director_version (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  director_id      text NOT NULL,              -- feature-director
  semver           text NOT NULL,
  channel          release_channel NOT NULL DEFAULT 'canary',
  requires_harness text NOT NULL,              -- ^0.1
  uri              text NOT NULL,
  sha256           text NOT NULL,
  signature        text,
  eval_pass_rate   numeric(4,3),
  eval_cost_czk    numeric(10,2),
  released_at      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (director_id, semver)
);
CREATE UNIQUE INDEX one_stable_per_director
  ON director_version (director_id) WHERE channel = 'stable';

-- ─── Přidělování práce ─────────────────────────────────────────
CREATE TABLE assignment (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  task_id          uuid NOT NULL REFERENCES task(id),
  workstation_id   uuid NOT NULL REFERENCES workstation(id),
  lease_expires_at timestamptz NOT NULL,
  heartbeat_at     timestamptz NOT NULL DEFAULT now(),
  state            text NOT NULL DEFAULT 'active',
  created_at       timestamptz NOT NULL DEFAULT now()
);
-- jeden aktivní lease na task
CREATE UNIQUE INDEX one_active_lease ON assignment (task_id) WHERE state = 'active';

CREATE TABLE work_order (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  assignment_id  uuid NOT NULL REFERENCES assignment(id),
  manifest       jsonb NOT NULL,
  manifest_hash  text NOT NULL,
  director_ver   uuid REFERENCES director_version(id),
  harness_ver    uuid REFERENCES harness_version(id),
  issued_at      timestamptz NOT NULL DEFAULT now(),
  expires_at     timestamptz NOT NULL,
  revoked_at     timestamptz
);

-- ─── Kontext a běhy ────────────────────────────────────────────
CREATE TABLE context_bundle (
  manifest_hash text PRIMARY KEY,
  spec          jsonb NOT NULL,
  size_tokens   int NOT NULL,
  built_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE agent_profile (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  role           text NOT NULL,
  semver         text NOT NULL,
  prompt_ref     text NOT NULL,
  tool_allowlist text[] NOT NULL DEFAULT '{}',
  model_allowlist text[] NOT NULL DEFAULT '{}',
  UNIQUE (role, semver)
);

CREATE TABLE agent_run (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  task_id        uuid NOT NULL REFERENCES task(id),
  work_order_id  uuid REFERENCES work_order(id),
  role           text NOT NULL,
  profile_semver text,
  state_name     text,                        -- stav directora, ve kterém běžel
  model          text NOT NULL,
  input_hash     text,
  tokens_in      int NOT NULL DEFAULT 0,
  tokens_out     int NOT NULL DEFAULT 0,
  cost_czk       numeric(10,4) NOT NULL DEFAULT 0,
  duration_ms    int,
  outcome        text,
  transcript_uri text,
  created_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON agent_run (task_id, created_at);

CREATE TABLE artifact (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  task_id    uuid NOT NULL REFERENCES task(id),
  kind       text NOT NULL,
  uri        text NOT NULL,
  sha256     text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

-- ─── Rozhodovací matice ────────────────────────────────────────
CREATE TABLE decision (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  task_id     uuid NOT NULL REFERENCES task(id),
  question    text NOT NULL,
  options     jsonb NOT NULL DEFAULT '[]'::jsonb,
  criteria    jsonb NOT NULL DEFAULT '{}'::jsonb,
  recommended text,
  chosen      text,
  rationale   text,
  state       decision_state NOT NULL DEFAULT 'pending_human',
  adr_ref     text,
  embedding   vector(768),                    -- precedenty (nomic-embed-text)
  created_at  timestamptz NOT NULL DEFAULT now(),
  decided_at  timestamptz,
  decided_by  uuid REFERENCES principal(id)
);
CREATE INDEX ON decision (state);

-- ─── Auditní stopa (append-only, hash chain) ───────────────────
CREATE TABLE event (
  seq        bigserial PRIMARY KEY,
  ts         timestamptz NOT NULL DEFAULT now(),
  actor_id   uuid,
  subject_type text NOT NULL,
  subject_id text NOT NULL,
  verb       text NOT NULL,
  payload    jsonb NOT NULL DEFAULT '{}'::jsonb,
  dedupe_key text NOT NULL,
  prev_hash  text NOT NULL,
  hash       text NOT NULL
);
-- Idempotence: retry nesmí duplikovat (invariant P6)
CREATE UNIQUE INDEX event_dedupe
  ON event (subject_type, subject_id, verb, dedupe_key);

CREATE OR REPLACE FUNCTION event_chain() RETURNS trigger AS $$
DECLARE prev text;
BEGIN
  SELECT hash INTO prev FROM event ORDER BY seq DESC LIMIT 1;
  NEW.prev_hash := COALESCE(prev, repeat('0', 64));
  NEW.hash := encode(digest(
      NEW.prev_hash || NEW.ts::text || COALESCE(NEW.actor_id::text,'-') ||
      NEW.subject_type || NEW.subject_id || NEW.verb || NEW.payload::text,
    'sha256'), 'hex');
  RETURN NEW;
END $$ LANGUAGE plpgsql;

CREATE TRIGGER event_chain_trg BEFORE INSERT ON event
  FOR EACH ROW EXECUTE FUNCTION event_chain();

-- Append-only. Vynuceno triggerem, ne pravidlem: RULE na UPDATE nebo
-- INSERT znemožní `INSERT ... ON CONFLICT` na téže tabulce, a na tom
-- stojí idempotence zápisu do ledgeru (invariant P6). Trigger navíc
-- selže nahlas — pravidlo `DO INSTEAD NOTHING` mazání tiše zahodilo,
-- takže se úprava ledgeru tvářila jako úspěšná.
CREATE OR REPLACE FUNCTION event_append_only() RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION 'event je append-only, % není povolený', TG_OP
    USING HINT = 'Auditní stopa se nepřepisuje. Zapiš opravný záznam.';
END $$ LANGUAGE plpgsql;

CREATE TRIGGER event_no_change BEFORE UPDATE OR DELETE ON event
  FOR EACH ROW EXECUTE FUNCTION event_append_only();

CREATE TRIGGER event_no_truncate BEFORE TRUNCATE ON event
  FOR EACH STATEMENT EXECUTE FUNCTION event_append_only();

-- ─── Kill switch ───────────────────────────────────────────────
CREATE TABLE platform_state (
  id              int PRIMARY KEY DEFAULT 1 CHECK (id = 1),
  issuing_enabled boolean NOT NULL DEFAULT true,
  reason          text,
  updated_at      timestamptz NOT NULL DEFAULT now()
  ,epoch          bigint NOT NULL DEFAULT 1
);
INSERT INTO platform_state (id) VALUES (1);
