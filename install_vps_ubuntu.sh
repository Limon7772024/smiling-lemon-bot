#!/usr/bin/env bash
# ==============================================================================
#  🍋 SMILING-LEMON v6.3 — автоустановка бота 24/7 на VPS Ubuntu 22.04 / 24.04
# ==============================================================================
#  Запуск одной командой:
#      cd ~/shpora-network && sudo bash install_vps_ubuntu.sh
# ==============================================================================

set -euo pipefail

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
say()  { echo -e "${GREEN}==>${NC} $*"; }
warn() { echo -e "${YELLOW}[!]${NC} $*"; }
die()  { echo -e "${RED}[ОШИБКА]${NC} $*"; exit 1; }

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_USER="${SUDO_USER:-root}"
SERVICE_NAME="shpora-bot"

say "Папка проекта: $APP_DIR"

[[ $EUID -eq 0 ]] || die "Запустите скрипт через sudo:  sudo bash install_vps_ubuntu.sh"
[[ -f "$APP_DIR/run_polling.py" ]] || die "В папке нет run_polling.py — распакуйте архив бота сюда."
[[ -f "$APP_DIR/requirements.txt" ]] || die "В папке нет requirements.txt."

if [[ ! -f "$APP_DIR/.env" ]]; then
  if [[ -f "$APP_DIR/.env.example" ]]; then
    cp "$APP_DIR/.env.example" "$APP_DIR/.env"
    warn "Создан шаблон .env. Впишите туда ваши BOT_TOKEN, LLM_API_KEY и ADMIN_IDS:"
    warn "   nano $APP_DIR/.env   (Ctrl+O -> Enter -> Ctrl+X)"
    die "Заполните .env и запустите скрипт ещё раз."
  else
    die "Нет файла .env!"
  fi
fi

# Strip accidental Windows CRLF inside .env just in case it was copied from Windows!
sed -i 's/\r$//' "$APP_DIR/.env"

grep -q "^BOT_TOKEN=.\+" "$APP_DIR/.env" || die "В .env пустой BOT_TOKEN!"
grep -q "^LLM_API_KEY=.\+" "$APP_DIR/.env" || die "В .env пустой LLM_API_KEY!"

# --- 0. Автоматический 2 ГБ Swap (защита Chromium от нехватки памяти) ---------
SWAP_MB=$(free -m | awk '/^Swap:/ {print $2}')
if [[ "${SWAP_MB:-0}" -lt 1500 ]] && [[ ! -f /swapfile ]]; then
  say "Добавляю 2 ГБ подкачки (Swap), чтобы рендер карточек работал стабильно..."
  (fallocate -l 2G /swapfile || dd if=/dev/zero of=/swapfile bs=1M count=2048 status=none) && \
  chmod 600 /swapfile && mkswap /swapfile >/dev/null && swapon /swapfile && \
  grep -q '/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab || warn "Swap пропущен (контейнер без прав на swap — не страшно на 2 ГБ RAM)."
fi

# --- 1. Системные пакеты и шрифты ---------------------------------------------
say "Ставлю Python, шрифты украинского языка и системные библиотеки (2–4 минуты)..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq \
  python3 python3-venv python3-pip python3-dev \
  build-essential curl unzip ca-certificates \
  fonts-dejavu fonts-liberation fonts-noto-core

# --- 2. Виртуальное окружение Python (чистый Linux venv, не Windows venv!) ----
if [[ -d "$APP_DIR/venv" ]] && [[ ! -x "$APP_DIR/venv/bin/python" ]]; then
  say "Удаляю папку venv от Windows и создаю чистый Linux venv..."
  rm -rf "$APP_DIR/venv"
fi

say "Создаю виртуальное окружение и ставлю библиотеки бота (1–3 минуты)..."
python3 -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/python" -m pip install -q --upgrade pip wheel setuptools
"$APP_DIR/venv/bin/pip" install -q -r "$APP_DIR/requirements.txt"

say "Устанавливаю браузер Chromium для рисования карточек в клеточку..."
"$APP_DIR/venv/bin/python" -m playwright install --with-deps chromium || {
  "$APP_DIR/venv/bin/python" -m playwright install chromium
  "$APP_DIR/venv/bin/python" -m playwright install-deps chromium || true
}

chown -R "$APP_USER":"$APP_USER" "$APP_DIR"

# --- 3. Круглосуточная служба systemd 24/7 ------------------------------------
say "Настраиваю автозапуск 24/7 ($SERVICE_NAME.service)..."
cat > /etc/systemd/system/$SERVICE_NAME.service <<EOF_SVC
[Unit]
Description=Smiling-lemon Telegram Bot v6.3 (@ShporaNMT_bot)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$APP_USER
WorkingDirectory=$APP_DIR
Environment=PYTHONUNBUFFERED=1
ExecStart=$APP_DIR/venv/bin/python $APP_DIR/run_polling.py
Restart=always
RestartSec=5
StandardOutput=append:/var/log/shpora-bot.log
StandardError=append:/var/log/shpora-bot.log

[Install]
WantedBy=multi-user.target
EOF_SVC

touch /var/log/shpora-bot.log && chown "$APP_USER":"$APP_USER" /var/log/shpora-bot.log
systemctl daemon-reload
systemctl enable "$SERVICE_NAME" >/dev/null
systemctl restart "$SERVICE_NAME"
sleep 6

if systemctl is-active --quiet "$SERVICE_NAME"; then
  say "УРА! Бот @ShporaNMT_bot работает 24/7 на сервере! Компьютер можно выключать!"
  echo
  echo "  Посмотреть живой лог:  tail -n 30 -f /var/log/shpora-bot.log"
  echo "  Перезапустить бота:    sudo systemctl restart $SERVICE_NAME"
else
  warn "Служба не запустилась — вот последние строки лога:"
  tail -n 40 /var/log/shpora-bot.log
  exit 1
fi
