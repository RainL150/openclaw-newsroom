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


BIRD_EXTRA=""

# Auth probe: bird auto-reads Chrome cookies — check it actually fetched a tweet
_PROBE=$(run_timeout 8s $BIRD search "from:OpenAI" -n 1 --plain 2>&1 || true)
# Successful fetch contains a URL line; failure messages do not
if ! echo "$_PROBE" | grep -q "x\.com/"; then
  echo "Warning: bird auth failed — Twitter scan skipped." >&2
  echo "  Make sure you are logged into x.com in Chrome and try again." >&2
  exit 0
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
