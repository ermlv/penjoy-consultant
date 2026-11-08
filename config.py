"""Настройки PENJOY-бота. Деплой: bothost.ru (см. README.md).

Всё, что помечено «ЗАМЕНИТЬ» — подставить свои значения.
Если на тарифе есть панель «Переменные окружения», лучше задать их там
(BOT_TOKEN подставляется Bothost автоматически).
"""
import os
from pathlib import Path


def _load_dotenv(path: Path) -> None:
    """Мини-загрузчик .env (без зависимостей). os.environ имеет приоритет:
    на bothost.ru BOT_TOKEN подставляется платформой автоматически."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


_load_dotenv(Path(__file__).resolve().parent / ".env")

# --- Telegram -----------------------------------------------------------
BOT_TOKEN = os.getenv("BOT_TOKEN") or "ВСТАВЬТЕ_ТОКЕН_ОТ_BOTFATHER"

# Telegram ID владельца: сюда приходят заказы и вопросы.
ADMIN_ID = int(os.getenv("ADMIN_ID", "3588541"))

# --- Хранилище (bothost: /app/data переживает обновления кода из Git) ---
DATA_DIR = Path(os.getenv("DATA_DIR", "/app/data"))
try:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    _probe = DATA_DIR / ".write-test"
    _probe.write_text("ok")
    _probe.unlink()
except Exception:
    # локальный запуск: база рядом с кодом
    DATA_DIR = Path(__file__).resolve().parent / "data"
    DATA_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = DATA_DIR / "penjoy.db"

# --- Файлы-вложения (PDF) ----------------------------------------------
# Кладём сюда: gayd.pdf, issue1.pdf … issue8.pdf, checklist.pdf
FILES_DIR = Path(__file__).resolve().parent / "files"

# --- Товар и деньги -----------------------------------------------------
PRICE = 990            # за один номер
PRICE_SET = 2700       # комплект №1–№3 (вместо 2970)

DELIVERY = {
    "pickup": {"title": "Самовывоз (МО)", "cost": 0},
    "courier": {"title": "Курьер по МО (по тарифу)", "cost": None},
    "cdek": {"title": "СДЭК/Почта по РФ", "cost": 250},
}

# Оплата переводом по СБП.
SBP_PHONE = "+7 916 366-66-36"
SBP_NAME = "Андрей"
SBP_BANK = "Т-Банк"

# --- Тираж --------------------------------------------------------------
# Фактические остатки: всего 25 экз. (данные автора, 2026-11-08).
# Распределение по номерам — ЗАМЕНИТЬ на фактическое (или командой
# админа /setstock 1 8, /setstock 2 9, /setstock 3 8).
STOCK_DEFAULT = {"1": 9, "2": 8, "3": 8}

ISSUES = {
    "1": "№1 · 2018 — Пен-шоу в Москве, анатомия ручки",
    "2": "№2 · 2019 — Пен-шоу в Москве (итоги), перезаправка картриджей",
    "3": "№3 · 2019 — стимпанк-ручка и Бах, обзоры ручек",
}

# --- Рассылка дожима ----------------------------------------------------
DRIP_STEPS = (3, 7, 14, 21, 30)   # дни от старта контакта
DRIP_CHECK_EVERY = 3600           # сек, как часто бот проверяет дожим
