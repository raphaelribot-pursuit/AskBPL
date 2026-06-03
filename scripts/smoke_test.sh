#!/usr/bin/env bash
# =============================================================
# Ask BPL — Smoke Test Script v2
# Engineer : Denward Lee Aulder
# Date     : 2026-05-27
#
# Updated field names to match live API response shape:
#   type: "answer" | "refusal_oo_corpus" (not "answered": bool)
#   routing: []  (array, not object)
# =============================================================

BASE="${BASE:-http://localhost:8000}"
EMAIL="pilot-demo@bklynlibrary.org"
CODE="DEMO2026"

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo ""
echo "======================================================="
echo "  Ask BPL Smoke Tests — $(date '+%Y-%m-%d %H:%M')"
echo "======================================================="

# -------------------------------------------------------
# AUTH
# -------------------------------------------------------
echo ""
echo -e "${BLUE}[AUTH] Signing in as demo tester...${NC}"

AUTH_HTTP=$(curl -sS -o /tmp/askbpl_auth_body.json -w "%{http_code}" --max-time 120 \
  -X POST "$BASE/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\": \"$EMAIL\", \"access_code\": \"$CODE\", \"attribution_mode\": \"anonymous\"}")
AUTH_RESPONSE=$(cat /tmp/askbpl_auth_body.json)

TOKEN=$(echo "$AUTH_RESPONSE" | jq -r '.token // .access_token // empty' 2>/dev/null)

if [ -z "$TOKEN" ]; then
  echo -e "${RED}[FAIL] Auth failed (HTTP ${AUTH_HTTP}). Response:${NC}"
  cat /tmp/askbpl_auth_body.json
  exit 1
fi
echo -e "${GREEN}[PASS] Auth OK — JWT obtained${NC}"

# -------------------------------------------------------
# TEST 1 — Gift acceptance (Selvon's demo case)
# Expect: type="answer", 2-4 sentences, citations present,
#         no legal hedging
# -------------------------------------------------------
echo ""
echo "-------------------------------------------------------"
echo -e "${BLUE}TEST 1: Gift acceptance question${NC}"
echo "  Q: Can I accept a gift from a vendor?"
echo "-------------------------------------------------------"

ASK1_HTTP=$(curl -sS -o /tmp/askbpl_ask1_body.json -w "%{http_code}" --max-time 180 \
  -X POST "$BASE/v1/ask" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"question":"Can I accept a gift from a vendor?"}')
RESP1=$(cat /tmp/askbpl_ask1_body.json)

echo ""
echo "HTTP status: $ASK1_HTTP"
echo "Full response:"
if echo "$RESP1" | jq . >/dev/null 2>&1; then
  echo "$RESP1" | jq .
else
  echo "$RESP1"
  echo -e "${YELLOW}[WARN] Body is not JSON (often HTTP 500 plain text from an unhandled server error).${NC}"
fi

TYPE1=$(echo "$RESP1" | jq -r '.type // empty')
ANSWER1=$(echo "$RESP1" | jq -r '.answer // empty')
CITATIONS1=$(echo "$RESP1" | jq -r '.citations | length')

echo ""
if [ "$TYPE1" = "answer" ]; then
  echo -e "${GREEN}[PASS] type: answer — question answered from corpus${NC}"

  SENTENCE_COUNT=$(echo "$ANSWER1" | grep -o '[.!?]' | wc -l | tr -d ' ')
  if [ "$SENTENCE_COUNT" -le 4 ]; then
    echo -e "${GREEN}[PASS] Response length: ~${SENTENCE_COUNT} sentence(s) — within 2-4 cap${NC}"
  else
    echo -e "${YELLOW}[WARN] Response length: ~${SENTENCE_COUNT} sentence(s) — may exceed cap${NC}"
  fi

  if [ "$CITATIONS1" -gt 0 ]; then
    echo -e "${GREEN}[PASS] Citations present: ${CITATIONS1} source(s)${NC}"
  else
    echo -e "${RED}[FAIL] No citations returned${NC}"
  fi

  if echo "$ANSWER1" | grep -qi "pursuant to\|in accordance with\|as stipulated"; then
    echo -e "${YELLOW}[WARN] Legal hedging phrase detected — review tone${NC}"
  else
    echo -e "${GREEN}[PASS] No legal hedging phrases detected${NC}"
  fi
else
  echo -e "${RED}[FAIL] type=${TYPE1} — system refused an answerable question${NC}"
fi

# -------------------------------------------------------
# TEST 2 — Out-of-corpus refusal
# Expect: type="refusal_oo_corpus", routing array present,
#         no Executive Director
# -------------------------------------------------------
echo ""
echo "-------------------------------------------------------"
echo -e "${BLUE}TEST 2: Out-of-corpus refusal + routing card${NC}"
echo "  Q: What is BPL's employee discipline policy?"
echo "-------------------------------------------------------"

ASK2_HTTP=$(curl -sS -o /tmp/askbpl_ask2_body.json -w "%{http_code}" --max-time 180 \
  -X POST "$BASE/v1/ask" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"question":"What is BPL'\''s employee discipline policy?"}')
RESP2=$(cat /tmp/askbpl_ask2_body.json)

echo ""
echo "HTTP status: $ASK2_HTTP"
echo "Full response:"
if echo "$RESP2" | jq . >/dev/null 2>&1; then
  echo "$RESP2" | jq .
else
  echo "$RESP2"
  echo -e "${YELLOW}[WARN] Body is not JSON (often HTTP 500 plain text from an unhandled server error).${NC}"
fi

TYPE2=$(echo "$RESP2" | jq -r '.type // empty')
ROUTING_COUNT=$(echo "$RESP2" | jq -r '.routing | length')
ROUTING_TEAMS=$(echo "$RESP2" | jq -r '.routing[].team // empty' 2>/dev/null | tr '\n' ', ')
REFUSAL_EXP=$(echo "$RESP2" | jq -r '.refusal_explanation // empty')

echo ""
if [[ "$TYPE2" == refusal* ]]; then
  echo -e "${GREEN}[PASS] type: ${TYPE2} — corpus boundary held${NC}"

  if [ "$ROUTING_COUNT" -gt 0 ]; then
    echo -e "${GREEN}[PASS] Routing card present: ${ROUTING_TEAMS}${NC}"
  else
    echo -e "${YELLOW}[WARN] No routing teams returned${NC}"
  fi

  FULL_TEXT="$ROUTING_TEAMS $REFUSAL_EXP"
  if echo "$FULL_TEXT" | grep -qi "executive director"; then
    echo -e "${RED}[FAIL] Executive Director appears in routing — must be removed${NC}"
  else
    echo -e "${GREEN}[PASS] Executive Director not present in routing${NC}"
  fi
else
  echo -e "${RED}[FAIL] type=${TYPE2} — system answered an out-of-corpus question${NC}"
fi

# -------------------------------------------------------
# TEST 3 — PII rejection
# -------------------------------------------------------
echo ""
echo "-------------------------------------------------------"
echo -e "${BLUE}TEST 3: PII rejection${NC}"
echo "  Q: Can john.doe@example.com take annual leave next week?"
echo "-------------------------------------------------------"

RESP3=$(curl -s -o /tmp/pii_body.json -w "%{http_code}" \
  -X POST "$BASE/v1/ask" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"question":"Can john.doe@example.com take annual leave next week?","conversation_history":[]}')

PII_BODY=$(cat /tmp/pii_body.json)
echo ""
echo "HTTP status: $RESP3"
echo "Response body:"
echo "$PII_BODY" | jq .

echo ""
if [ "$RESP3" = "400" ]; then
  echo -e "${GREEN}[PASS] HTTP 400 returned for PII input${NC}"
else
  echo -e "${RED}[FAIL] Expected HTTP 400, got ${RESP3}${NC}"
fi

if echo "$PII_BODY" | grep -qi "john.doe@example.com"; then
  echo -e "${RED}[FAIL] PII echoed in response${NC}"
else
  echo -e "${GREEN}[PASS] PII not echoed in response${NC}"
fi

# -------------------------------------------------------
# SUMMARY
# -------------------------------------------------------
echo ""
echo "======================================================="
echo "  Smoke tests complete."
echo "  Review any [WARN] or [FAIL] lines above."
echo "  All [PASS] = ready for Selvon testing access."
echo "======================================================="
echo ""