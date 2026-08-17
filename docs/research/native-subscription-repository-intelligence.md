# Research ledger: native subscription agents and repository intelligence

Last reviewed / Poslední revize: 2026-08-16. Community sources describe
experience only; they are never authority for authentication or security.
Komunitní zdroje popisují pouze zkušenost a nejsou autoritou pro autentizaci
ani bezpečnostní rozhodnutí.

| Mechanism / mechanismus | Evidence | Decision / rozhodnutí |
|---|---|---|
| Codex subscription login | [OpenAI: Using Codex with your ChatGPT plan](https://help.openai.com/en/articles/11369540-using-codex-with-your-chatgpt-plan), [Codex CLI sign-in](https://help.openai.com/en/articles/11381614-api-codex-cli-and-sign-in-with-chatgpt) | Use native local sign-in and keep its local credential store per Unix UID. Never copy or pool it. |
| Claude subscription login | [Anthropic: Set up Claude Code](https://docs.anthropic.com/en/docs/claude-code/getting-started) | Use native Claude App Pro/Max login and its per-user credential store; expiration is recoverable. |
| Curated engineering skills | [`mattpocock/skills`](https://github.com/mattpocock/skills) at `068b6e0c62393147daf03530149cdce209c93da8`, bundled MIT license | Provider-neutral local adaptations are pinned; no automatic upstream updates. Setup, wizard and generic Git workflows are excluded. |
| Untrusted repository input | [Agentic workflow injection study](https://arxiv.org/abs/2605.07135), [GitInject](https://arxiv.org/abs/2606.09935), [LBNL guidance](https://cborg.lbl.gov/security_ai_agentic/) | Analysis checkout is read-only, repository instructions/hooks/MCP are inert data, outputs are schema/citation validated, and prompts are not a security boundary. |
| Human review and evidence | [Hacker News Codex CLI experience](https://news.ycombinator.com/item?id=45650188), [Reddit Claude CLI observability experience](https://www.reddit.com/r/ClaudeAI/comments/1r90pol/claude_codes_cli_feels_like_a_black_box_i_built_a/) | Community reports motivate explicit role outputs, audit, deterministic checks and a human approval gate; they do not define security policy. |
| Subscription limits | [Reddit Claude/Codex comparison](https://www.reddit.com/r/ClaudeCode/comments/1n2h4sb/cc_to_codex_1_week_later/), [mattpocock skill-flow discussion](https://github.com/mattpocock/skills/issues/23) | Treat quota and session expiry as expected `RATE_LIMITED`/`AUTH_REQUIRED`; do not promise unattended SLA or silently switch accounts/providers. |
| daily.dev community search | [daily.dev search](https://app.daily.dev/search?q=AI%20coding%20agents%20prompt%20injection) | Discovery-only input. No security rule is accepted without primary documentation or reproducible evidence. |

Karpathy-derived packages were not copied: the reviewed candidate had unclear
licensing/provenance. AgenticDev independently states the useful principles:
explicit assumptions, the smallest useful diff, predefined verification, and
no unrelated edits.
