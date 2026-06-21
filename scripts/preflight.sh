#!/bin/bash
# Pre-flight check: run before starting or committing
# Usage: bash scripts/preflight.sh [python-path]
#   python-path: defaults to the py311 conda env
set -e

PYTHON="${1:-/opt/anaconda3/envs/py311/bin/python}"
BACKEND_DIR="$(cd "$(dirname "$0")/../backend" && pwd)"
echo "=== Pre-flight checks for $BACKEND_DIR ==="

# 1. Python syntax check (compile all .py files)
echo "--- Syntax check ---"
failed=0
while IFS= read -r -d '' f; do
    if ! $PYTHON -m py_compile "$f" 2>/dev/null; then
        echo "❌ SYNTAX ERROR: $f"
        failed=1
    fi
done < <(find "$BACKEND_DIR/app" -name '*.py' -print0)
if [ $failed -eq 0 ]; then
    echo "✅ All .py files compile"
fi

# 2. Import check (test all modules can be imported)
echo "--- Import check ---"
cd "$BACKEND_DIR"
$PYTHON -c "
import sys; sys.path.insert(0, '.')
modules = [
    'app.core.config','app.core.database','app.core.redis','app.core.security',
    'app.models.models','app.schemas.schemas','app.api.deps',
    'app.api.v1.auth','app.api.v1.users','app.api.v1.clubs',
    'app.api.v1.venues','app.api.v1.bookings','app.api.v1.posts',
    'app.api.v1.tournaments','app.main',
]
failed = 0
for mod in modules:
    try:
        __import__(mod)
    except Exception as e:
        print(f'❌ {mod}: {e}')
        failed += 1
if failed:
    print(f'{failed} module(s) failed')
    sys.exit(1)
print('✅ All modules import OK')
" || { echo "❌ Import check failed — fix before starting"; exit 1; }

echo ""
echo "✅ All pre-flight checks passed"
