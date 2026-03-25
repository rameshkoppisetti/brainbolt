#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8080}"
USER_ID="${USER_ID:-u-alice}"
SESSION_ID="${SESSION_ID:-single}"

need() { command -v "$1" >/dev/null 2>&1 || { echo "missing dependency: $1" >&2; exit 1; }; }
need curl
need python3

echo "Base URL: ${BASE_URL}"
echo "User: ${USER_ID}"

tmp_next="$(mktemp)"
tmp_answer="$(mktemp)"
tmp_answer2="$(mktemp)"
trap 'rm -f "$tmp_next" "$tmp_answer" "$tmp_answer2"' EXIT

echo
echo "== GET /v1/quiz/next"
curl -fsS "${BASE_URL}/v1/quiz/next?userId=${USER_ID}&sessionId=${SESSION_ID}" | tee "$tmp_next" >/dev/null

question_id="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["questionId"])' "$tmp_next")"
state_version="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["stateVersion"])' "$tmp_next")"
choices_json="$(python3 -c 'import json,sys; print(json.dumps(json.load(open(sys.argv[1]))["choices"]))' "$tmp_next")"

answer="$(python3 -c '
import json,sys
qid=sys.argv[1]
choices=json.loads(sys.argv[2])
if qid=="q-1-1": print("4")
elif qid=="q-1-2": print("B")
else: print(choices[0] if choices else "")
' "$question_id" "$choices_json")"

idem_key="smoke-$(date +%s)"

echo "questionId=${question_id} stateVersion=${state_version} answer=${answer} idem=${idem_key}"

echo
echo "== POST /v1/quiz/answer (first submit)"
curl -fsS -X POST "${BASE_URL}/v1/quiz/answer" \
  -H 'content-type: application/json' \
  -d "{\"userId\":\"${USER_ID}\",\"sessionId\":\"${SESSION_ID}\",\"questionId\":\"${question_id}\",\"answer\":\"${answer}\",\"stateVersion\":${state_version},\"answerIdempotencyKey\":\"${idem_key}\"}" \
  | tee "$tmp_answer" >/dev/null

echo
echo "== POST /v1/quiz/answer (idempotency replay; should not double-apply)"
curl -fsS -X POST "${BASE_URL}/v1/quiz/answer" \
  -H 'content-type: application/json' \
  -d "{\"userId\":\"${USER_ID}\",\"sessionId\":\"${SESSION_ID}\",\"questionId\":\"${question_id}\",\"answer\":\"${answer}\",\"stateVersion\":${state_version},\"answerIdempotencyKey\":\"${idem_key}\"}" \
  | tee "$tmp_answer2" >/dev/null

echo
echo "== GET /v1/quiz/metrics"
curl -fsS "${BASE_URL}/v1/quiz/metrics?userId=${USER_ID}" >/dev/null
curl -fsS "${BASE_URL}/v1/quiz/metrics?userId=${USER_ID}"

echo
echo "== GET /v1/leaderboard/score"
curl -fsS "${BASE_URL}/v1/leaderboard/score?userId=${USER_ID}&n=10"

echo
echo "== GET /v1/leaderboard/streak"
curl -fsS "${BASE_URL}/v1/leaderboard/streak?userId=${USER_ID}&n=10"

echo
echo "Smoke test complete."

