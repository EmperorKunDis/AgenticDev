-- Seed: jeden projekt, jedna fáze, jeden úkol, jedna stanice.
-- Cíl: hned po startu máš co pustit skrz pipeline.
\c agenticdev

INSERT INTO client (name, ico) VALUES ('AgenticDev interní', NULL);

INSERT INTO project (client_id, code, repo_url, data_class, model_allowlist)
SELECT id, 'sandbox', 'ssh://git@vps:2222/agenticdev/sandbox.git', 'internal',
       ARRAY['claude-sonnet-5','local/qwen2.5-coder:32b']
FROM client WHERE name = 'AgenticDev interní';

INSERT INTO phase (project_id, kind, order_idx, active)
SELECT id, 'implementation', 3, true FROM project WHERE code = 'sandbox';

INSERT INTO task (phase_id, kind, title, spec_ref, dod, write_scope, risk, state, priority)
SELECT p.id, 'feature',
       'Smoke test: přidej funkci slugify + testy',
       'prd/sandbox/10-requirements.md#REQ-001',
       '["funkce slugify zvládá českou diakritiku","unit testy pokrývají prázdný vstup a diakritiku","README zmiňuje použití"]'::jsonb,
       ARRAY['src/**','tests/**'],
       'low', 'ready', 1
FROM phase p JOIN project pr ON pr.id = p.project_id WHERE pr.code = 'sandbox';

INSERT INTO principal (kind, display_name, email)
VALUES ('human', 'Martin Švanda', 'martin@praut.cz');

INSERT INTO project_member (project_id, principal_id)
SELECT p.id, pr.id FROM project p CROSS JOIN principal pr
WHERE p.code='sandbox' AND pr.email='martin@praut.cz';

INSERT INTO harness_version (semver, image_digest)
VALUES ('0.1.0', 'sha256:0000000000000000000000000000000000000000000000000000000000000000');

INSERT INTO director_version (director_id, semver, channel, requires_harness, uri, sha256)
VALUES ('feature-director', '0.1.0', 'stable', '^0.1',
        'file:///directors/feature-director', 'PENDING');

INSERT INTO agent_profile (role, semver, prompt_ref, model_allowlist) VALUES
  ('architect',   '0.1.0', 'workers/architect.md',   ARRAY['claude-sonnet-5']),
  ('implementer', '0.1.0', 'workers/implementer.md', ARRAY['claude-sonnet-5']),
  ('tester',      '0.1.0', 'workers/tester.md',      ARRAY['claude-sonnet-5']),
  ('reviewer',    '0.1.0', 'workers/reviewer.md',    ARRAY['claude-sonnet-5']);
