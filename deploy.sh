#!/usr/bin/env bash
set -euo pipefail

# ── Config ──────────────────────────────────────────────
REMOTE_USER="dzaczek"
REMOTE_HOST="10.10.100.22"
REMOTE_DIR="/home/dzaczek/mminihunter"
SSH_TARGET="${REMOTE_USER}@${REMOTE_HOST}"

echo "=== Mac Mini Hunter - Deploy to ${SSH_TARGET} ==="

# ── 1. Create remote directory ──────────────────────────
echo "[1/5] Preparing remote directory..."
ssh "${SSH_TARGET}" "mkdir -p ${REMOTE_DIR}"

# ── 2. Sync project files (exclude unnecessary stuff) ──
echo "[2/5] Syncing project files..."
rsync -avz --delete \
    --exclude '.git' \
    --exclude '.env' \
    --exclude 'target/' \
    --exclude 'dashboard/target/' \
    --exclude '__pycache__' \
    --exclude '*.pyc' \
    --exclude 'test_*.py' \
    --exclude 'tests/' \
    --exclude '.env.example' \
    --exclude 'deploy.sh' \
    --exclude 'pgdata/' \
    ./ "${SSH_TARGET}:${REMOTE_DIR}/"

# ── 3. Copy .env if it doesn't exist on remote ─────────
echo "[3/5] Checking .env on remote..."
ssh "${SSH_TARGET}" "
    if [ ! -f ${REMOTE_DIR}/.env ]; then
        echo '  .env not found - copying example...'
        cp ${REMOTE_DIR}/.env.example ${REMOTE_DIR}/.env 2>/dev/null || true
        echo '  ⚠ IMPORTANT: Edit ${REMOTE_DIR}/.env on the server with real values!'
        echo '    Required: POSTGRES_PASSWORD, DASH_PASS, CLOUDFLARE_TUNNEL_TOKEN'
    else
        echo '  .env exists - skipping'
    fi
"

# ── 4. Export local DB and import on remote ─────────────
echo "[4/5] Migrating database..."
if command -v pg_dump &>/dev/null; then
    # Try to get local DB URL from .env
    if [ -f .env ]; then
        LOCAL_DB_URL=$(grep -E '^DATABASE_URL=' .env | cut -d= -f2- || true)
    fi
    LOCAL_DB_URL="${LOCAL_DB_URL:-postgresql://tracker:change_me_in_production@localhost:5432/mac_tracker}"

    echo "  Dumping local database..."
    pg_dump "${LOCAL_DB_URL}" --no-owner --no-acl --clean --if-exists > /tmp/mminihunter_dump.sql 2>/dev/null && {
        echo "  Uploading dump to remote..."
        scp /tmp/mminihunter_dump.sql "${SSH_TARGET}:/tmp/mminihunter_dump.sql"
        rm /tmp/mminihunter_dump.sql

        echo "  Starting DB container and importing..."
        ssh "${SSH_TARGET}" "
            cd ${REMOTE_DIR}
            docker compose up -d db
            echo '  Waiting for DB to be ready...'
            sleep 5
            # Get DB credentials from .env
            source .env 2>/dev/null || true
            DB_USER=\${POSTGRES_USER:-tracker}
            DB_NAME=\${POSTGRES_DB:-mac_tracker}
            docker compose exec -T db psql -U \${DB_USER} -d \${DB_NAME} < /tmp/mminihunter_dump.sql
            rm /tmp/mminihunter_dump.sql
            echo '  Database imported successfully!'
        "
    } || {
        echo "  ⚠ Could not dump local DB (not running?). Skipping DB migration."
        echo "    The DB will be initialized from init-db.sql on first run."
    }
else
    echo "  ⚠ pg_dump not found. Skipping DB migration."
    echo "    The DB will be initialized from init-db.sql on first run."
fi

# ── 5. Build and start containers on remote ─────────────
echo "[5/5] Building and starting containers..."
ssh "${SSH_TARGET}" "
    cd ${REMOTE_DIR}
    docker compose build
    docker compose up -d
    echo ''
    echo '=== Deployment complete ==='
    docker compose ps
"

echo ""
echo "Done! Next steps:"
echo "  1. SSH to server: ssh ${SSH_TARGET}"
echo "  2. Edit .env:     nano ${REMOTE_DIR}/.env"
echo "     - Set DASH_PASS (dashboard login password)"
echo "     - Set CLOUDFLARE_TUNNEL_TOKEN"
echo "     - Set POSTGRES_PASSWORD (strong password)"
echo "  3. Restart:       cd ${REMOTE_DIR} && docker compose up -d"
echo ""
echo "Cloudflare Tunnel setup:"
echo "  1. Go to https://one.dash.cloudflare.com"
echo "  2. Zero Trust -> Networks -> Tunnels -> Create"
echo "  3. Copy the tunnel token to .env as CLOUDFLARE_TUNNEL_TOKEN"
echo "  4. Add public hostname pointing to: http://dashboard:8080"
