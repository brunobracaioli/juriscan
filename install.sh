#!/usr/bin/env bash
set -e

SKILL_NAME="juriscan"
SKILL_TARGET="$HOME/.claude/skills/$SKILL_NAME"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== JuriScan — Installer ==="
echo ""

# 1. Check Python version
python3 -c "import sys; assert sys.version_info >= (3, 10), f'Python 3.10+ required, got {sys.version}'" 2>/dev/null || {
    echo "[ERROR] Python 3.10+ is required."
    exit 1
}
echo "[OK] Python $(python3 --version 2>&1 | cut -d' ' -f2)"

# 2. Install Python dependencies
echo ""
echo "Installing Python dependencies..."
pip install pypdf pytesseract Pillow jsonschema 2>/dev/null \
    || pip install --user pypdf pytesseract Pillow jsonschema 2>/dev/null \
    || { echo "[WARN] Could not install Python packages. Run: pip install -r $SCRIPT_DIR/requirements.txt"; }
echo "[OK] Python dependencies"

# 3. Check system dependencies
echo ""
HAS_ISSUES=0

if command -v pdftotext &>/dev/null; then
    echo "[OK] poppler-utils (pdftotext)"
else
    echo "[WARN] poppler-utils not found. Install with:"
    echo "       Ubuntu/Debian: sudo apt-get install poppler-utils"
    echo "       macOS: brew install poppler"
    HAS_ISSUES=1
fi

if command -v tesseract &>/dev/null; then
    echo "[OK] tesseract-ocr"
else
    echo "[WARN] tesseract-ocr not found (optional — needed for scanned PDFs). Install with:"
    echo "       Ubuntu/Debian: sudo apt-get install tesseract-ocr tesseract-ocr-por"
    echo "       macOS: brew install tesseract tesseract-lang"
    HAS_ISSUES=1
fi

# 4. Install as Claude Code skill
echo ""
if [ "$SCRIPT_DIR" = "$SKILL_TARGET" ]; then
    echo "[OK] Already installed at $SKILL_TARGET"
else
    mkdir -p "$HOME/.claude/skills"
    if [ -e "$SKILL_TARGET" ]; then
        echo "[INFO] Removing previous installation at $SKILL_TARGET"
        rm -rf "$SKILL_TARGET"
    fi
    ln -sf "$SCRIPT_DIR" "$SKILL_TARGET"
    echo "[OK] Installed as symlink: $SKILL_TARGET -> $SCRIPT_DIR"
fi

# 5. Summary
echo ""
echo "=== Installation Complete ==="
echo ""
echo "The skill is now available in Claude Code."
echo "Trigger it by mentioning: análise de processo, contradições, prazos, timeline jurídica, etc."
echo ""
if [ $HAS_ISSUES -eq 1 ]; then
    echo "[!] Some optional system dependencies are missing — see warnings above."
fi
