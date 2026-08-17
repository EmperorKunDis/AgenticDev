"""
Migrace schématu.

Init skripty Postgresu (`vps/sql/*.sql`) běží JEN nad prázdnou databází.
U instalace, která už jednou naběhla, se nikdy nespustí — takže cokoli,
co se ve schématu opraví, musí umět dojet i sem.

Každý krok je idempotentní a spouští se při startu control plane. Když
selže, řekne to nahlas do logu a aplikaci nezhasne: nabíhající kontejner
v restart-loopu je horší než jedna nedojetá migrace.
"""
from __future__ import annotations

from .main import db

# (jméno, SQL). Jméno se jen loguje, stav se nikde nedrží — všechny kroky
# jsou napsané tak, že opakované spuštění nic nezmění.
STEPS: list[tuple[str, str]] = [
    (
        "setting — tabulka nastavení měnitelného z panelu",
        """
        CREATE TABLE IF NOT EXISTS setting (
            key        TEXT PRIMARY KEY,
            value      TEXT NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_by TEXT
        )
        """,
    ),
    (
        "enrollment — kdo se přihlásil a čeká na účet",
        # Pody běží na VPS (ADR-0005), takže účet zakládá root příkazem
        # `agenticdev-ctl user add`. Control plane na to nemá právo ani ho
        # mít nemá, proto si jen zapíše, kdo se ohlásil, a správce to vidí.
        """
        CREATE TABLE IF NOT EXISTS enrollment (
            id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            first_name TEXT NOT NULL,
            last_name  TEXT NOT NULL,
            email      TEXT NOT NULL,
            os         TEXT,
            ip         TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            claimed_at TIMESTAMPTZ,
            claimed_by TEXT
        )
        """,
    ),
    (
        "enrollment — automatické založení izolovaného účtu",
        """
        ALTER TABLE enrollment ADD COLUMN IF NOT EXISTS login TEXT;
        ALTER TABLE enrollment ADD COLUMN IF NOT EXISTS ssh_public_key TEXT;
        ALTER TABLE enrollment ADD COLUMN IF NOT EXISTS status_token_hash TEXT;
        ALTER TABLE enrollment ADD COLUMN IF NOT EXISTS state TEXT NOT NULL DEFAULT 'pending';
        ALTER TABLE enrollment ADD COLUMN IF NOT EXISTS error TEXT;
        CREATE UNIQUE INDEX IF NOT EXISTS enrollment_active_login
          ON enrollment (login) WHERE state IN ('pending', 'provisioning', 'ready');
        """,
    ),
    (
        "provider profiles a verzovaná repository intelligence",
        """
        CREATE TABLE IF NOT EXISTS provider_profile (
          principal_id uuid NOT NULL REFERENCES principal(id) ON DELETE CASCADE,
          provider text NOT NULL CHECK (provider IN ('claude','codex')),
          auth_status text NOT NULL DEFAULT 'unknown'
            CHECK (auth_status IN ('unknown','ready','auth_required','rate_limited')),
          last_verified_at timestamptz,
          account_label text,
          PRIMARY KEY (principal_id, provider)
        );
        ALTER TABLE project ADD COLUMN IF NOT EXISTS analysis_status text
          NOT NULL DEFAULT 'awaiting_provider';
        CREATE TABLE IF NOT EXISTS repository_analysis (
          id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          project_id uuid NOT NULL REFERENCES project(id) ON DELETE CASCADE,
          commit_sha text NOT NULL CHECK (commit_sha ~ '^[0-9a-f]{40}$'),
          analyzer_version text NOT NULL,
          state text NOT NULL CHECK
            (state IN ('awaiting_provider','analyzing','questions','review','ready','failed')),
          provider text CHECK (provider IN ('claude','codex')),
          static_scan jsonb NOT NULL DEFAULT '{}'::jsonb,
          result jsonb,
          questions jsonb NOT NULL DEFAULT '[]'::jsonb,
          answers jsonb NOT NULL DEFAULT '{}'::jsonb,
          approved_at timestamptz,
          approved_by uuid REFERENCES principal(id),
          error text,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (project_id, commit_sha, analyzer_version)
        );
        CREATE INDEX IF NOT EXISTS repository_analysis_project_state
          ON repository_analysis(project_id, state, updated_at DESC);
        """,
    ),
    (
        "proof-of-possession device authentication",
        """
        ALTER TABLE workstation ADD COLUMN IF NOT EXISTS device_public_key TEXT;
        CREATE TABLE IF NOT EXISTS device_challenge (
          id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          workstation_id uuid NOT NULL REFERENCES workstation(id) ON DELETE CASCADE,
          nonce text NOT NULL UNIQUE,
          expires_at timestamptz NOT NULL,
          used_at timestamptz,
          created_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS device_challenge_expiry ON device_challenge(expires_at);
        """,
    ),
    (
        "event — append-only přes trigger místo pravidla",
        # Pravidlo na UPDATE blokovalo `INSERT ... ON CONFLICT` na event,
        # a tím KAŽDÝ zápis do auditní stopy. Instalace vydané předtím
        # mají pravidla v sobě, takže je tady odstraníme a nahradíme
        # triggerem, který stejnou věc vynutí a nerozbije idempotenci.
        """
        DO $$
        BEGIN
          DROP RULE IF EXISTS event_no_update ON event;
          DROP RULE IF EXISTS event_no_delete ON event;

          CREATE OR REPLACE FUNCTION event_append_only() RETURNS trigger AS $fn$
          BEGIN
            RAISE EXCEPTION 'event je append-only, % není povolený', TG_OP
              USING HINT = 'Auditní stopa se nepřepisuje. Zapiš opravný záznam.';
          END $fn$ LANGUAGE plpgsql;

          IF NOT EXISTS (SELECT 1 FROM pg_trigger
                          WHERE tgname = 'event_no_change'
                            AND tgrelid = 'event'::regclass) THEN
            CREATE TRIGGER event_no_change BEFORE UPDATE OR DELETE ON event
              FOR EACH ROW EXECUTE FUNCTION event_append_only();
          END IF;

          IF NOT EXISTS (SELECT 1 FROM pg_trigger
                          WHERE tgname = 'event_no_truncate'
                            AND tgrelid = 'event'::regclass) THEN
            CREATE TRIGGER event_no_truncate BEFORE TRUNCATE ON event
              FOR EACH STATEMENT EXECUTE FUNCTION event_append_only();
          END IF;
        END $$
        """,
    ),
    (
        "workstation.ssh_public_key — klíč, kterým se člověk přihlásí na VPS",
        # V režimu domain (bez Tailscale) dělá autentizaci obyčejné SSH, ne
        # tailnet. Veřejný klíč z registrace se proto musí uschovat, aby ho
        # `agenticdev-ctl keys sync` mohl zapsat do authorized_keys toho
        # člověka. Control plane to sám nedělá a nemá — je v kontejneru a
        # do /home nedosáhne, což je záměr.
        """
        ALTER TABLE workstation ADD COLUMN IF NOT EXISTS ssh_public_key TEXT
        """,
    ),
    (
        "workstation.key_installed_at — kdy se klíč dostal do authorized_keys",
        """
        ALTER TABLE workstation ADD COLUMN IF NOT EXISTS key_installed_at TIMESTAMPTZ
        """,
    ),
    (
        "workstation.login — pod jakým účtem na VPS ten člověk pracuje",
        """
        ALTER TABLE workstation ADD COLUMN IF NOT EXISTS login TEXT
        """,
    ),
    (
        "runtime boundary — membership a kill-switch epoch",
        """
        CREATE TABLE IF NOT EXISTS project_member (
          project_id UUID NOT NULL REFERENCES project(id) ON DELETE CASCADE,
          principal_id UUID NOT NULL REFERENCES principal(id) ON DELETE CASCADE,
          active BOOLEAN NOT NULL DEFAULT true,
          PRIMARY KEY (project_id, principal_id)
        );
        ALTER TABLE platform_state ADD COLUMN IF NOT EXISTS epoch BIGINT NOT NULL DEFAULT 1
        ;INSERT INTO project_member(project_id,principal_id)
          SELECT p.id,pr.id FROM project p CROSS JOIN principal pr WHERE pr.active
          ON CONFLICT (project_id,principal_id) DO NOTHING
        """,
    ),
    (
        "subscription režim a GitHub identity",
        """
        ALTER TABLE project DROP COLUMN IF EXISTS budget_czk_month;
        ALTER TABLE task DROP COLUMN IF EXISTS budget_czk;
        ALTER TABLE IF EXISTS evaluation DROP COLUMN IF EXISTS eval_cost_czk;
        ALTER TABLE agent_run DROP COLUMN IF EXISTS cost_czk;
        CREATE TABLE IF NOT EXISTS github_identity (
          id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          principal_id uuid REFERENCES principal(id) ON DELETE CASCADE,
          github_user_id text NOT NULL UNIQUE,
          github_login text NOT NULL,
          display_name text,
          avatar_url text,
          token_encrypted text NOT NULL,
          scopes text[] NOT NULL DEFAULT '{}',
          is_default boolean NOT NULL DEFAULT false,
          last_verified_at timestamptz,
          created_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE UNIQUE INDEX IF NOT EXISTS github_identity_one_default
          ON github_identity(is_default) WHERE is_default;
        """,
    ),
]


def run() -> list[str]:
    """Projede všechny kroky. Vrátí popisy těch, které selhaly."""
    failed: list[str] = []
    for name, sql in STEPS:
        try:
            with db() as c:
                c.execute(sql)
            print(f"[migrace] {name} ✓")
        except Exception as e:                        # noqa: BLE001
            failed.append(name)
            print(f"[migrace] {name} ✗ {e}")
    return failed
