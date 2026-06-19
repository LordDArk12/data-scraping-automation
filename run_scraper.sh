#!/usr/bin/env bash
# =============================================================================
# EY Data Scraping Automation Runner
# Проверяет окружение, зависимости и запускает ETL-пайплайн.
# =============================================================================
set -euo pipefail

# --- Цвета для читаемости ---
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"
PYTHON_CMD="python3"

echo -e "${YELLOW}========================================${NC}"
echo -e "${YELLOW}  EY Data Scraping Automation Runner   ${NC}"
echo -e "${YELLOW}========================================${NC}"
echo "Проект: $SCRIPT_DIR"
echo ""

# --- 1. Проверка Python ---
if ! command -v "$PYTHON_CMD" &>/dev/null; then
    echo -e "${RED}[ERROR] Python 3 не найден. Установите Python 3.8+${NC}"
    exit 1
fi

PYTHON_VERSION=$("$PYTHON_CMD" --version 2>&1 | awk '{print $2}')
echo -e "${GREEN}[OK] Python найден: $PYTHON_VERSION${NC}"

# --- 2. Виртуальное окружение (best practice) ---
if [ ! -d "$VENV_DIR" ]; then
    echo "[INFO] Создание виртуального окружения..."
    "$PYTHON_CMD" -m venv "$VENV_DIR"
fi

# shellcheck source=/dev/null
source "$VENV_DIR/bin/activate"

# --- 3. Проверка и установка зависимостей ---
REQUIREMENTS_FILE="$SCRIPT_DIR/requirements.txt"
if [ ! -f "$REQUIREMENTS_FILE" ]; then
    echo -e "${RED}[ERROR] Файл requirements.txt не найден!${NC}"
    exit 1
fi

echo "[INFO] Проверка зависимостей из requirements.txt..."
pip install -q --upgrade pip
pip install -q -r "$REQUIREMENTS_FILE"
echo -e "${GREEN}[OK] Все зависимости установлены${NC}"

# --- 4. Запуск ETL ---
echo ""
echo -e "${YELLOW}>>> Запуск scraper.py...${NC}"
echo "----------------------------------------"

cd "$SCRIPT_DIR"
if "$PYTHON_CMD" scraper.py; then
    echo ""
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}  СКРЕЙПИНГ УСПЕШНО ЗАВЕРШЁН          ${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo "Результаты:"
    echo "  • CSV:  $SCRIPT_DIR/output/data.csv"
    echo "  • Excel: $SCRIPT_DIR/output/scraped_data.xlsx"
    exit 0
else
    echo ""
    echo -e "${RED}========================================${NC}"
    echo -e "${RED}  ОШИБКА ВО ВРЕМЯ ВЫПОЛНЕНИЯ          ${NC}"
    echo -e "${RED}========================================${NC}"
    exit 1
fi
