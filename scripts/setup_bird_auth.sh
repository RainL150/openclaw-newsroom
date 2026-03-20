#!/bin/bash
# setup_bird_auth.sh — One-time Twitter/X auth setup
#
# Reads Chrome cookies directly (via macOS keychain + openssl) and writes
# AUTH_TOKEN / CT0 to .env so bird never needs keychain access again.
#
# Run once from a terminal when you see repeated keychain prompts:
#   bash scripts/setup_bird_auth.sh
#
# Requirements: macOS, Chrome with x.com logged in, python3, openssl (built-in)

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${NEWSROOM_ENV_FILE:-$SCRIPT_DIR/../.env}"

echo "=== Twitter/X One-Time Auth Setup ==="
echo ""
echo "This reads your Chrome cookies to extract Twitter auth tokens."
echo "You will see ONE macOS keychain password prompt — that's the last one."
echo ""

# ── Step 1: Get Chrome Safe Storage key (one keychain prompt) ──────────────
CHROME_KEY=$(security find-generic-password -w -a "Chrome" -s "Chrome Safe Storage" 2>/dev/null || true)
if [ -z "$CHROME_KEY" ]; then
    echo "Error: Could not read Chrome Safe Storage key from keychain."
    echo "Make sure Chrome is installed and you have logged into x.com at least once."
    exit 1
fi

echo "Got Chrome Safe Storage key. Decrypting cookies..."

# ── Step 2: Decrypt Chrome's SQLite cookies DB and extract tokens ──────────
RESULT=$(python3 - "$CHROME_KEY" <<'PYEOF'
import sys, os, sqlite3, shutil, tempfile, hashlib, subprocess, json

chrome_key = sys.argv[1].encode('utf-8')

# Chrome on macOS encrypts cookies with AES-128-CBC
# Key = PBKDF2(password=chrome_key, salt=b'saltysalt', iterations=1003, dklen=16)
aes_key = hashlib.pbkdf2_hmac('sha1', chrome_key, b'saltysalt', 1003, dklen=16)
key_hex = aes_key.hex()
iv_hex = '20' * 16  # 16 space characters (Chrome's fixed IV)

def decrypt_cookie(encrypted):
    if not encrypted:
        return ""
    if len(encrypted) < 3 or encrypted[:3] != b'v10':
        # Not encrypted (older format) — value is stored as plaintext
        return encrypted.decode('utf-8', errors='ignore')
    payload = encrypted[3:]
    proc = subprocess.run(
        ['openssl', 'enc', '-d', '-aes-128-cbc', '-nosalt',
         '-K', key_hex, '-iv', iv_hex],
        input=payload, capture_output=True
    )
    if proc.returncode != 0:
        return ""
    raw = proc.stdout
    if not raw:
        return ""
    # Remove PKCS7 padding
    pad = raw[-1]
    if 1 <= pad <= 16:
        raw = raw[:-pad]
    return raw.decode('utf-8', errors='ignore')

# Try Default profile first, then all profiles
profiles = ['Default', 'Profile 1', 'Profile 2', 'Profile 3']
cookies_db = None
for profile in profiles:
    p = os.path.expanduser(
        f"~/Library/Application Support/Google/Chrome/{profile}/Cookies"
    )
    if os.path.exists(p):
        cookies_db = p
        break

if not cookies_db:
    print(json.dumps({"error": "Chrome cookies DB not found"}))
    sys.exit(0)

# Copy DB — Chrome may have it locked
tmp = tempfile.mktemp(suffix='.db')
shutil.copy2(cookies_db, tmp)
auth_token = ct0 = ""
try:
    conn = sqlite3.connect(tmp)
    for name, value, encrypted_value in conn.execute(
        "SELECT name, value, encrypted_value FROM cookies "
        "WHERE host_key LIKE '%.twitter.com' OR host_key LIKE '%.x.com' "
        "ORDER BY last_access_utc DESC"
    ):
        if name == 'auth_token' and not auth_token:
            auth_token = value if value else decrypt_cookie(encrypted_value)
        elif name == 'ct0' and not ct0:
            ct0 = value if value else decrypt_cookie(encrypted_value)
        if auth_token and ct0:
            break
    conn.close()
finally:
    os.unlink(tmp)

print(json.dumps({"auth_token": auth_token, "ct0": ct0}))
PYEOF
)

AUTH_TOKEN=$(python3 -c "import sys,json; d=json.loads(sys.argv[1]); print(d.get('auth_token',''))" "$RESULT")
CT0=$(python3 -c "import sys,json; d=json.loads(sys.argv[1]); print(d.get('ct0',''))" "$RESULT")

if [ -z "$AUTH_TOKEN" ] || [ -z "$CT0" ]; then
    echo ""
    echo "Error: Could not extract auth_token/ct0 from Chrome cookies."
    echo "Please make sure:"
    echo "  1. Chrome is installed"
    echo "  2. You are logged into x.com in Chrome"
    echo "  3. Chrome is not open (close it and retry, or try while it's open)"
    exit 1
fi

# ── Step 3: Write to .env (upsert — replace existing lines) ────────────────
touch "$ENV_FILE"
TMP_ENV=$(mktemp)
# Remove existing AUTH_TOKEN/CT0 lines, append new values
grep -v '^AUTH_TOKEN=' "$ENV_FILE" | grep -v '^CT0=' > "$TMP_ENV" 2>/dev/null || true
echo "AUTH_TOKEN=$AUTH_TOKEN" >> "$TMP_ENV"
echo "CT0=$CT0" >> "$TMP_ENV"
mv "$TMP_ENV" "$ENV_FILE"

echo ""
echo "Done! Saved to $ENV_FILE"
echo "AUTH_TOKEN and CT0 are now set — bird will never prompt keychain again."
echo ""
echo "Note: If you log out of x.com in Chrome, run this script again to refresh."
