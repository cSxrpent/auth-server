#!/usr/bin/env bash
set -euo pipefail

echo "=== RXZBOT START ==="

if [ "${RUN_MIGRATION:-false}" = "true" ]; then
  echo "[1/3] Initializing database..."
  python init_database.py

  echo "[2/3] Running GitHub → DB migration..."
  python run_migration.py

  echo "✅ Migration finished"
else
  echo "⏭️ Migration skipped"
fi

echo "[3/3] Starting server..."
exec gunicorn server:app --workers 3 --bind 0.0.0.0:${PORT:-5000}
