#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
#  Přepnutí dodavatele modelů. Spouštěj na VPS.
#     tools/set-provider.sh codex|openai|openrouter|ollama|codex-cli|anthropic
# ═══════════════════════════════════════════════════════════════
set -euo pipefail
ENV=/srv/praut/config/.env
[[ -f $ENV ]] || { echo "✗ $ENV neexistuje"; exit 1; }

set_kv() {
  if grep -q "^$1=" "$ENV"; then
    sed -i "s|^$1=.*|$1=$2|" "$ENV"
  else
    echo "$1=$2" >> "$ENV"
  fi
}

case "${1:-}" in
  codex|openai)
    set_kv MODEL_BACKEND openai
    set_kv MODEL_BASE_URL https://api.openai.com/v1
    set_kv DEFAULT_MODEL "${2:-gpt-5-codex}"
    set_kv EGRESS_ALLOWLIST "api.openai.com,registry.npmjs.org,pypi.org"
    echo "→ OpenAI / Codex přes API. Doplň MODEL_API_KEY do $ENV"
    ;;
  openrouter)
    set_kv MODEL_BACKEND openai
    set_kv MODEL_BASE_URL https://openrouter.ai/api/v1
    set_kv DEFAULT_MODEL "${2:-openai/gpt-5.5}"
    set_kv EGRESS_ALLOWLIST "openrouter.ai,registry.npmjs.org,pypi.org"
    echo "→ OpenRouter. Jeden klíč, skoro všechny modely. Doplň MODEL_API_KEY"
    ;;
  codex-cli)
    set_kv MODEL_BACKEND cli
    set_kv CLI_TEMPLATE 'codex exec --model {model} --cd {cwd} {prompt}'
    set_kv DEFAULT_MODEL "${2:-gpt-5.5}"
    echo "→ Codex CLI jako podproces. Agent má skutečné nástroje."
    echo "  Codex musí být v harness image (pod/Dockerfile)."
    ;;
  ollama)
    set_kv MODEL_BACKEND ollama
    set_kv DEFAULT_MODEL "local/${2:-qwen2.5-coder:32b}"
    set_kv EGRESS_ALLOWLIST "registry.npmjs.org,pypi.org"
    echo "→ Lokální Ollama. Zdarma, nic neodchází ven."
    ;;
  anthropic)
    set_kv MODEL_BACKEND anthropic
    set_kv MODEL_BASE_URL https://api.anthropic.com
    set_kv DEFAULT_MODEL "${2:-claude-sonnet-4-6}"
    set_kv EGRESS_ALLOWLIST "api.anthropic.com,registry.npmjs.org,pypi.org"
    echo "→ Anthropic API. Doplň MODEL_API_KEY"
    ;;
  *)
    echo "Použití: $0 {codex|openai|openrouter|codex-cli|ollama|anthropic} [model]"
    exit 1
    ;;
esac

cd /srv/praut/src/vps && docker compose --env-file "$ENV" up -d control-plane >/dev/null 2>&1 || true
echo "✓ hotovo"
