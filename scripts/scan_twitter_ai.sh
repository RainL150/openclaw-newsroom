#!/bin/bash
# Twitter/X AI News Scanner
# Scans official accounts, reporters/leakers, and trending AI topics
# Requires: bird CLI — https://bird.fast
# Install: npm install -g @steipete/bird  OR  brew install steipete/tap/bird

set -e

# Auto-detect bird binary (supports npm global, Homebrew Intel/ARM, custom PATH)
BIRD="$(command -v bird 2>/dev/null || true)"
if [ -z "$BIRD" ]; then
  echo "Warning: bird CLI not found in PATH. Twitter bird scan skipped."
  echo "Install: npm install -g @steipete/bird  OR  brew install steipete/tap/bird"
  exit 0
fi

# Auto-detect timeout command (macOS ARM: gtimeout from coreutils; Linux: timeout)
TIMEOUT_CMD="$(command -v gtimeout 2>/dev/null || command -v timeout 2>/dev/null || true)"
run_timeout() {
  local _dur="$1"; shift
  if [ -n "$TIMEOUT_CMD" ]; then "$TIMEOUT_CMD" "$_dur" "$@"; else "$@"; fi
}

# Auth helper: run setup_bird_auth.sh and re-source .env
SETUP_SCRIPT="$SCRIPT_DIR/setup_bird_auth.sh"
_try_refresh_auth() {
  if [ ! -f "$SETUP_SCRIPT" ]; then
    echo "  setup_bird_auth.sh not found — cannot refresh." >&2
    return 1
  fi
  echo "  Running setup_bird_auth.sh to refresh tokens..." >&2
  if bash "$SETUP_SCRIPT" >&2; then
    set -a
    [ -f "$SCRIPT_DIR/../.env" ] && source "$SCRIPT_DIR/../.env"
    set +a
    return 0
  fi
  return 1
}

# Auth check: prefer AUTH_TOKEN/CT0 env vars (no keychain prompts).
if [ -z "$AUTH_TOKEN" ] || [ -z "$CT0" ]; then
  if [ -t 0 ]; then
    # Interactive terminal — ask user once
    echo "" >&2
    echo "Twitter: AUTH_TOKEN/CT0 未配置。" >&2
    printf "  现在运行 setup_bird_auth.sh 自动获取? [y/N] " >&2
    read -r _ans </dev/tty
    if [[ "$_ans" =~ ^[Yy]$ ]]; then
      _try_refresh_auth || { echo "  配置失败 — 跳过 Twitter。" >&2; exit 0; }
    else
      echo "  跳过 Twitter 扫描。" >&2
      exit 0
    fi
  else
    echo "Warning: AUTH_TOKEN/CT0 not set — Twitter scan skipped." >&2
    echo "  Run once: bash scripts/setup_bird_auth.sh" >&2
    exit 0
  fi
fi

BIRD_EXTRA=""

# Auth probe: detect expired/invalid tokens before full scan (saves time on 38 calls)
_PROBE=$(run_timeout 8s $BIRD search "from:OpenAI" -n 1 --plain 2>&1 || true)
if echo "$_PROBE" | grep -qiE "unauthorized|401|auth|login required|invalid|expired|forbidden"; then
  echo "  Twitter token 已失效 — 尝试自动刷新..." >&2
  if _try_refresh_auth; then
    echo "  Token 已刷新，继续扫描。" >&2
  else
    echo "  刷新失败 — 跳过 Twitter 扫描。" >&2
    exit 0
  fi
fi
unset _PROBE

echo "Scanning X/Twitter for AI news..."

# Tier 1: Official AI company accounts (announcements)
OFFICIAL_ACCOUNTS=(
  "OpenAI"
  "AnthropicAI"
  "GoogleAI"
  "Google"
  "HuggingFace"
  "MetaAI"
  "AIatMeta"
  "MistralAI"
  "DeepMind"
  "GoogleDeepMind"
  "xAI"
  "NVIDIAAIDev"
  "Apple"
  "MicrosoftAI"
)

# Tier 2: Reporters, leakers, and fast-signal accounts (break news first)
# Customize: add reporters who cover your beat
REPORTER_ACCOUNTS=(
  "btibor91"
  "testingcatalog"
  "kylewiggers"
  "dseetharaman"
  "rachelmetz"
  "CadeMetz"
  "inafried"
  "_philschmid"
  "rohanpaul_ai"
  "benthompson"
  "natolambert"
  "lennysan"
  "Suhail"
)

# Tier 3: CEO/thought leader accounts (context, not breaking)
CEO_ACCOUNTS=(
  "sama"
  "darioamodei"
  "ylecun"
  "karpathy"
  "AndrewYNg"
  "fchollet"
  "goodfellow_ian"
  "demishassabis"
  "elonmusk"
  "satyanadella"
)

echo "Scanning official accounts..."
for acct in "${OFFICIAL_ACCOUNTS[@]}"; do
  run_timeout 8s $BIRD $BIRD_EXTRA search "from:$acct" -n 3 --plain 2>/dev/null | head -20 || true
done

echo ""
echo "Scanning reporters & leakers..."
for acct in "${REPORTER_ACCOUNTS[@]}"; do
  run_timeout 8s $BIRD $BIRD_EXTRA search "from:$acct" -n 3 --plain 2>/dev/null | head -20 || true
done

echo ""
echo "Breaking AI news search..."
run_timeout 10s $BIRD $BIRD_EXTRA search just launched OR now available OR rolling out OR just released AI model -filter:replies -filter:retweets -n 8 --plain 2>/dev/null | head -40 || true

echo ""
echo "Product launches & announcements..."
run_timeout 10s $BIRD $BIRD_EXTRA search introducing OR announcing AI OR LLM OR model -filter:replies -filter:retweets -n 8 --plain 2>/dev/null | head -40 || true

echo ""
echo "CEO signals (context only)..."
for acct in "${CEO_ACCOUNTS[@]}"; do
  run_timeout 8s $BIRD $BIRD_EXTRA search "from:$acct" -n 2 --plain 2>/dev/null | head -15 || true
done
