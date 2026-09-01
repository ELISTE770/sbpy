#!/usr/bin/env bash
# מתקין את SBpy בסביבה מבודדת ומוסיף פקודת `sbpy`.
#   ./install.sh              התקנה רגילה
#   ./install.sh --dev        התקנה editable
#   ./install.sh --uninstall
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_ROOT="${XDG_DATA_HOME:-$HOME/.local/share}/sbpy"
ENV_DIR="$INSTALL_ROOT/env"
BIN_DIR="${HOME}/.local/bin"
VENV_PY="$ENV_DIR/bin/python"

green() { printf '\033[32m  %s\033[0m\n' "$1"; }
cyan()  { printf '\033[36m  %s\033[0m\n' "$1"; }
warn()  { printf '\033[33m  %s\033[0m\n' "$1"; }
fail()  { printf '\033[31m  %s\033[0m\n' "$1"; exit 1; }

DEV=0
NO_GEMINI=0
for arg in "$@"; do
  case "$arg" in
    --dev) DEV=1 ;;
    --no-gemini) NO_GEMINI=1 ;;
    --uninstall)
      rm -f "$BIN_DIR/sbpy"
      rm -rf "$INSTALL_ROOT"
      green "SBpy הוסר."
      exit 0
      ;;
    *) fail "ארגומנט לא מוכר: $arg" ;;
  esac
done

echo
echo "  SBpy installer"

PYTHON="${PYTHON:-}"
if [ -z "$PYTHON" ]; then
  for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then PYTHON="$candidate"; break; fi
  done
fi
[ -n "$PYTHON" ] || fail "לא נמצא פייתון."

VERSION="$("$PYTHON" -c 'import sys;print(".".join(map(str,sys.version_info[:3])))')"
green "פייתון $VERSION"
"$PYTHON" -c 'import sys;sys.exit(0 if sys.version_info>=(3,10) else 1)' \
  || fail "SBpy דורש Python 3.10 ומעלה (נמצא $VERSION)."

if [ -x "$VENV_PY" ]; then
  green "סביבה קיימת: $ENV_DIR"
else
  cyan "יוצר סביבה מבודדת ב-$ENV_DIR ..."
  mkdir -p "$INSTALL_ROOT"
  "$PYTHON" -m venv "$ENV_DIR"
  green "נוצרה."
fi

cyan "מתקין את SBpy..."
"$VENV_PY" -m pip install --quiet --upgrade pip
SPEC="."; [ "$NO_GEMINI" -eq 1 ] || SPEC=".[gemini]"
if [ "$DEV" -eq 1 ]; then
  (cd "$PROJECT_ROOT" && "$VENV_PY" -m pip install --quiet -e "$SPEC")
else
  (cd "$PROJECT_ROOT" && "$VENV_PY" -m pip install --quiet "$SPEC")
fi
green "הותקן."

mkdir -p "$BIN_DIR"
cat > "$BIN_DIR/sbpy" <<SHIM
#!/usr/bin/env bash
export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8
exec "$VENV_PY" -m sbpy "\$@"
SHIM
chmod +x "$BIN_DIR/sbpy"
green "נוצרה פקודת sbpy ב-$BIN_DIR"

case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *) warn "הוסף ל-shell שלך:  export PATH=\"\$PATH:$BIN_DIR\"" ;;
esac

green "$("$VENV_PY" -m sbpy --version)"
echo
green "הכל מוכן."
echo "    sbpy              פותח את הסביבה האינטראקטיבית"
echo "    sbpy run app.py   מריץ קובץ עם אבחון"
echo "    sbpy sfb app.py   מחפש באגים"
echo "    sbpy doctor       בודק שהכל מחובר"
echo
[ -n "${GEMINI_API_KEY:-}" ] || warn "אין GEMINI_API_KEY - SBpy יעבוד מקומית בלבד (וזה תקין)."
echo
