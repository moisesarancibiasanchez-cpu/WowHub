#!/bin/bash
# =============================================================================
# Script de configuracion de conexiones - WowHub Multi-Agent V134.2
# =============================================================================
#
# USO: source setup_connections.sh
#
# Este archivo NO debe commitearearse con secretos.
# Los secretos van en .env (que esta en .gitignore).
#
# El .env puede tener overrides para desarrollo local.
# =============================================================================

# =============================================================================
# VARIABLES — cargar desde .env si existe
# =============================================================================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/.env"

if [[ -f "$ENV_FILE" ]]; then
    set -a  # auto-export todas las variables asignadas
    source "$ENV_FILE"
    set +a
fi

# =============================================================================
# VARIABLES GITHUB (valores por defecto — usar .env para overrides)
# =============================================================================
export GITHUB_OWNER="${GITHUB_OWNER:-moisesarancibiasanchez-cpu}"
export GITHUB_REPO="${GITHUB_REPO:-WowHub}"
export GITHUB_BRANCH="${GITHUB_BRANCH:-main}"

# =============================================================================
# VARIABLES RAILWAY
# =============================================================================
export RAILWAY_URL="${RAILWAY_URL:-https://wowhub-api-production.up.railway.app}"
export APP_NAME="${APP_NAME:-WowHub}"
export APP_ENV="${APP_ENV:-production}"

# =============================================================================
# VARIABLES WOWHUB APP
# =============================================================================
export BASE_URL="${BASE_URL:-$RAILWAY_URL}"
export PUBLIC_BASE_URL="${PUBLIC_BASE_URL:-https://wowhub.app}"
export LOG_LEVEL="${LOG_LEVEL:-INFO}"

# =============================================================================
# VARIABLES MULTI-AGENT
# =============================================================================
export MM_USE_MOCK="${MM_USE_MOCK:-1}"
export MAX_ITERATIONS="${MAX_ITERATIONS:-5}"
export LLM_TIMEOUT_SECONDS="${LLM_TIMEOUT_SECONDS:-30}"

# =============================================================================
# PATHS DEL WORKSPACE (relativos al script, para portabilidad)
# =============================================================================
MULTI_AGENT_HOME="${MULTI_AGENT_HOME:-$SCRIPT_DIR}"
WOWHUB_APP="${WOWHUB_APP:-$MULTI_AGENT_HOME/../WowHub_GIT}"
CP_DOC="${CP_DOC:-$WOWHUB_APP/docs/TEST_CASES_V134_2.md}"
CACHE_DIR="${CACHE_DIR:-$MULTI_AGENT_HOME/cache}"
RESULTS_DIR="${RESULTS_DIR:-$MULTI_AGENT_HOME}"

export MULTI_AGENT_HOME WOWHUB_APP CP_DOC CACHE_DIR RESULTS_DIR

# =============================================================================
# VERIFICACION DEL ENTORNO
# =============================================================================
if [[ "$1" == "--check" ]]; then
    echo "Verificando entorno..."
    errors=0

    # Python
    if command -v python3 &> /dev/null; then
        echo "  python3 OK"
    else
        echo "  MISSING: python3"
        ((errors++))
    fi

    # TEST_CASES_V134_2.md
    if [[ -f "$CP_DOC" ]]; then
        echo "  TEST_CASES_V134_2.md OK"
    else
        echo "  MISSING: TEST_CASES_V134_2.md (CP_DOC=$CP_DOC)"
        ((errors++))
    fi

    # WowHub_GIT
    if [[ -d "$WOWHUB_APP/.git" ]]; then
        echo "  WowHub_GIT OK"
    else
        echo "  WARN: WowHub_GIT no es un repo git (WOWHUB_APP=$WOWHUB_APP)"
    fi

    # Railway
    http_code=$(curl -s -o /dev/null -w "%{http_code}" "$RAILWAY_URL/health" 2>/dev/null)
    if [[ "$http_code" == "200" ]]; then
        echo "  Railway /health OK (HTTP $http_code)"
    else
        echo "  WARN: Railway /health devuelve HTTP $http_code"
    fi

    # GitHub token
    if [[ -n "$GITHUB_TOKEN" && "$GITHUB_TOKEN" != "" ]]; then
        echo "  GITHUB_TOKEN configurado"
    else
        echo "  MISSING: GITHUB_TOKEN (definir en .env)"
        ((errors++))
    fi

    if [[ $errors -eq 0 ]]; then
        echo "Todo OK"
    else
        echo "ERRORS: $errors"
        return 1
    fi
fi
