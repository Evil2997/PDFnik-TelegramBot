#!/usr/bin/env bash
# scripts/trivy_check.sh
#
# Сканирование зависимостей через Trivy с фильтрацией по году CVE:
#   CVE-2019 и старше  → все severity (LOW, MEDIUM, HIGH, CRITICAL)
#   CVE-2020           → все severity
#   CVE-2021 и новее   → только MEDIUM, HIGH, CRITICAL
#
# Использование:
#   bash scripts/trivy_check.sh              # сканировать текущую директорию
#   bash scripts/trivy_check.sh image myapp:latest  # сканировать Docker образ
#
# Зависимости:
#   trivy — https://github.com/aquasecurity/trivy
#   jq    — sudo apt install jq / brew install jq

set -euo pipefail

# ─── Конфиг ───────────────────────────────────
SCAN_TARGET="${2:-.}"          # второй аргумент или текущая директория
SCAN_MODE="${1:-fs}"           # fs (файлы) или image (Docker образ)
OLD_CVE_YEAR=2020              # включительно — все severity
EXIT_CODE=0

# ─── Цвета ────────────────────────────────────
RED="\033[0;31m"
YELLOW="\033[1;33m"
CYAN="\033[0;36m"
GREEN="\033[0;32m"
NC="\033[0m"

log()  { echo -e "${CYAN}[trivy]${NC} $*"; }
warn() { echo -e "${YELLOW}[trivy]${NC} $*"; }
fail() { echo -e "${RED}[trivy]${NC} $*"; }
ok()   { echo -e "${GREEN}[trivy]${NC} $*"; }

# ─── Проверка зависимостей ────────────────────
command -v trivy > /dev/null 2>&1 || {
  fail "trivy not found. Install: https://aquasecurity.github.io/trivy/latest/getting-started/installation/"
  exit 1
}
command -v jq > /dev/null 2>&1 || {
  fail "jq not found. Install: sudo apt install jq"
  exit 1
}

# ─── Общие аргументы trivy ────────────────────
TRIVY_COMMON_ARGS=(
  --format json          # JSON для парсинга
  --ignore-unfixed       # игнорировать CVE без доступного фикса
  --quiet                # без прогресс баров
)

if [[ "$SCAN_MODE" == "image" ]]; then
  TRIVY_CMD="trivy image"
  log "Scanning Docker image: $SCAN_TARGET"
else
  TRIVY_CMD="trivy fs"
  TRIVY_COMMON_ARGS+=(--scanners vuln)  # для fs явно указываем что сканируем
  log "Scanning filesystem: $SCAN_TARGET"
fi

# ─── Функция: запуск trivy и получение JSON ───
run_trivy() {
  local severity="$1"
  $TRIVY_CMD \
    "${TRIVY_COMMON_ARGS[@]}" \
    --severity "$severity" \
    "$SCAN_TARGET" 2>/dev/null
}

# ─── Функция: фильтр CVE по году ──────────────
# Принимает JSON от trivy, возвращает только CVE нужного года
filter_by_year() {
  local json="$1"
  local operator="$2"   # "old" = <= OLD_CVE_YEAR, "new" = > OLD_CVE_YEAR

  echo "$json" | jq --arg op "$operator" --argjson cutoff "$OLD_CVE_YEAR" '
    .Results[]? |
    .Vulnerabilities[]? |
    select(.VulnerabilityID | test("CVE-([0-9]{4})-"; "g")) |
    . as $vuln |
    (.VulnerabilityID | capture("CVE-(?<year>[0-9]{4})-") | .year | tonumber) as $year |
    if $op == "old" then
      select($year <= $cutoff)
    else
      select($year > $cutoff)
    end |
    {
      id: .VulnerabilityID,
      year: $year,
      severity: .Severity,
      pkg: .PkgName,
      installed: .InstalledVersion,
      fixed: (.FixedVersion // "no fix"),
      title: (.Title // "no title")
    }
  '
}

# ─── Функция: красивый вывод результатов ──────
print_results() {
  local label="$1"
  local results="$2"

  local count
  count=$(echo "$results" | jq -s 'length')

  if [[ "$count" -eq 0 ]]; then
    ok "$label → no vulnerabilities found"
    return
  fi

  warn "$label → found $count vulnerabilities:"
  echo ""

  # Группируем по severity для читаемости
  for severity in CRITICAL HIGH MEDIUM LOW; do
    local filtered
    filtered=$(echo "$results" | jq -s --arg s "$severity" '[.[] | select(.severity == $s)]')
    local scount
    scount=$(echo "$filtered" | jq 'length')

    [[ "$scount" -eq 0 ]] && continue

    echo -e "  ${YELLOW}[$severity]${NC} ($scount)"
    echo "$filtered" | jq -r '.[] | "    \(.id) | \(.pkg) \(.installed) → fix: \(.fixed) | \(.title)"'
    echo ""
  done
}

# ═══════════════════════════════════════════════
#  ПРОХОД 1: CVE-$OLD_CVE_YEAR и старше — ВСЕ severity
# ═══════════════════════════════════════════════
log "Pass 1: CVE-${OLD_CVE_YEAR} and older → ALL severities (LOW+)"
echo ""

JSON_ALL=$(run_trivy "CRITICAL,HIGH,MEDIUM,LOW")
OLD_RESULTS=$(filter_by_year "$JSON_ALL" "old")
OLD_COUNT=$(echo "$OLD_RESULTS" | jq -s 'length')

print_results "CVE ≤ ${OLD_CVE_YEAR}" "$OLD_RESULTS"

if [[ "$OLD_COUNT" -gt 0 ]]; then
  EXIT_CODE=1
fi

# ═══════════════════════════════════════════════
#  ПРОХОД 2: CVE после $OLD_CVE_YEAR — только MEDIUM+
# ═══════════════════════════════════════════════
log "Pass 2: CVE after ${OLD_CVE_YEAR} → MEDIUM, HIGH, CRITICAL only"
echo ""

JSON_MEDIUM=$(run_trivy "CRITICAL,HIGH,MEDIUM")
NEW_RESULTS=$(filter_by_year "$JSON_MEDIUM" "new")
NEW_COUNT=$(echo "$NEW_RESULTS" | jq -s 'length')

print_results "CVE > ${OLD_CVE_YEAR} (MEDIUM+)" "$NEW_RESULTS"

if [[ "$NEW_COUNT" -gt 0 ]]; then
  EXIT_CODE=1
fi

# ═══════════════════════════════════════════════
#  ИТОГ
# ═══════════════════════════════════════════════
echo ""
TOTAL=$((OLD_COUNT + NEW_COUNT))

if [[ "$EXIT_CODE" -eq 0 ]]; then
  ok "✅ All clear. Total vulnerabilities found: 0"
else
  fail "❌ Total vulnerabilities found: $TOTAL (old CVE: $OLD_COUNT, new CVE: $NEW_COUNT)"
fi

exit $EXIT_CODE
