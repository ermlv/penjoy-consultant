"""PENJOY-бот: лид-магнит, сбор заказов, автоворонка дожима.

Воронка и тексты: FUNNEL.md §4. Деплой: bothost.ru (см. README.md).
Запуск: python bot.py (локально) или через панель Bothost.
"""
import asyncio
import csv
import io
import logging
import re
import time

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import (BaseFilter, Command, CommandObject, CommandStart,
                             StateFilter)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (BufferedInputFile, CallbackQuery, FSInputFile,
                           Message)

import config as C
import db
import kb
import texts

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("penjoy")

bot = Bot(token=C.BOT_TOKEN,
          default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
router = Router()
dp.include_router(router)


# ------------------------------------------------------------------ FSM
class OrderSG(StatesGroup):
    issue = State()
    qty = State()
    delivery = State()
    name = State()
    address = State()
    phone = State()
    confirm = State()


class EmailSG(StatesGroup):
    email = State()


# ------------------------------------------------------------- helpers
def stock_line() -> tuple:
    s = db.get_stock()
    line = f"№1 — {s.get('1', 0)} экз., №2 — {s.get('2', 0)}, №3 — {s.get('3', 0)}"
    return line, sum(s.values())


async def send_pdf(message: Message, filename: str, caption: str = "") -> None:
    path = C.FILES_DIR / filename
    if path.exists():
        await message.answer_document(FSInputFile(path),
                                      caption=caption or None)
    else:
        await message.answer(
            f"Файл {filename} пока не загружен — все номера есть на сайте: "
            "http://ermlv.ru/penjoy"
        )


async def notify_admin(text: str) -> None:
    try:
        await bot.send_message(C.ADMIN_ID, text)
    except Exception:
        log.exception("Не смог написать админу (ADMIN_ID верный?)")


async def deliver_lead(message: Message, first_name: str) -> None:
    """Шаг 2 воронки: гайд + электронный №1."""
    await send_pdf(message, "gayd.pdf", "Гайд «Как выбрать первую перьевую»")
    await send_pdf(message, "issue1.pdf", "PENJOY №1 (2018) — PDF")
    await message.answer(texts.lead_delivered(first_name))


# ------------------------------------------------------------- /start
@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, command: CommandObject) -> None:
    args = (command.args or "").strip().lower()
    source = args if args in ("avito", "vk", "tg", "site", "ref") else "unknown"
    db.upsert_user(message.from_user.id, message.from_user.username or "",
                   message.from_user.first_name or "", source)
    await state.clear()
    welcome = texts.WELCOME_AVITO if source == "avito" else texts.WELCOME_DEFAULT
    await message.answer(welcome, reply_markup=kb.MENU)
    await message.answer(texts.SEG_QUESTION, reply_markup=kb.SEG)


@router.callback_query(F.data.startswith("seg:"))
async def cb_segment(cq: CallbackQuery, state: FSMContext) -> None:
    segment = cq.data.split(":")[1]
    db.set_user_field(cq.from_user.id, "segment", segment)
    await cq.answer()
    await deliver_lead(cq.message, cq.from_user.first_name or "")
    line, total = stock_line()
    await cq.message.answer(texts.print_offer(line, total), reply_markup=kb.OFFER)


@router.callback_query(F.data == "later")
async def cb_later(cq: CallbackQuery) -> None:
    await cq.answer()
    await cq.message.answer(texts.LATER)


# --------------------------------------------------- электронные номера
class IssueRequest(BaseFilter):
    """Сообщение «номер N» или «№N» — запрос электронного номера."""
    ISSUE_RE = re.compile(r"^\s*(?:номер|№)\s*([1-8])\s*$", re.IGNORECASE)

    async def __call__(self, message: Message) -> bool:
        return bool(message.text and self.ISSUE_RE.match(message.text))


@router.message(StateFilter(None), IssueRequest())
async def issue_request(message: Message) -> None:
    n = IssueRequest.ISSUE_RE.match(message.text).group(1)
    await send_pdf(message, f"issue{n}.pdf", f"PENJOY №{n} — PDF")


# ------------------------------------------------------------- меню
@router.message(StateFilter(None), F.text == "📖 Забрать гайд")
async def menu_guide(message: Message) -> None:
    await message.answer(texts.GUIDE_RESEND)
    await deliver_lead(message, message.from_user.first_name or "")


@router.message(StateFilter(None), F.text == "📦 Заказать печатный")
async def menu_order(message: Message, state: FSMContext) -> None:
    await state.set_state(OrderSG.issue)
    await message.answer(texts.ASK_ISSUE, reply_markup=kb.issue_kb())


@router.message(StateFilter(None), F.text == "ℹ️ Доставка и оплата")
async def menu_info(message: Message) -> None:
    await message.answer(texts.DELIVERY_INFO)


@router.message(StateFilter(None), F.text == "✍️ Вопрос про ручки")
async def menu_question(message: Message) -> None:
    await message.answer(texts.ASK_QUESTION)


# ------------------------------------------------------------- заказ
@router.callback_query(F.data == "order")
async def order_start(cq: CallbackQuery, state: FSMContext) -> None:
    await cq.answer()
    await state.set_state(OrderSG.issue)
    await cq.message.answer(texts.ASK_ISSUE, reply_markup=kb.issue_kb())


@router.callback_query(F.data.startswith("order_issue:"), OrderSG.issue)
async def order_issue(cq: CallbackQuery, state: FSMContext) -> None:
    key = cq.data.split(":")[1]
    await cq.answer()
    if key == "set":
        await state.update_data(issue="Комплект №1–№3", qty=1, price=C.PRICE_SET)
        await state.set_state(OrderSG.delivery)
        await cq.message.answer(texts.ASK_DELIVERY, reply_markup=kb.delivery_kb())
        return
    await state.update_data(issue=C.ISSUES[key], issue_key=key, qty=1,
                            price=C.PRICE)
    await state.set_state(OrderSG.qty)
    await cq.message.answer(texts.ASK_QTY, reply_markup=kb.QTY)


@router.callback_query(F.data.startswith("qty:"), OrderSG.qty)
async def order_qty(cq: CallbackQuery, state: FSMContext) -> None:
    qty = int(cq.data.split(":")[1])
    await state.update_data(qty=qty)
    await cq.answer()
    data = await state.get_data()
    stock = db.get_stock().get(data.get("issue_key", ""), 0)
    if data.get("issue_key") and qty > stock:
        await cq.message.answer(
            f"⚠️ По этому номеру осталось {stock} экз. — напишите мне, "
            "договоримся (можно часть другим номером)."
        )
    await state.set_state(OrderSG.delivery)
    await cq.message.answer(texts.ASK_DELIVERY, reply_markup=kb.delivery_kb())


@router.callback_query(F.data.startswith("deliv:"), OrderSG.delivery)
async def order_delivery(cq: CallbackQuery, state: FSMContext) -> None:
    key = cq.data.split(":")[1]
    await state.update_data(delivery_key=key,
                            delivery_title=C.DELIVERY[key]["title"],
                            delivery_cost=C.DELIVERY[key]["cost"])
    await cq.answer()
    await state.set_state(OrderSG.name)
    await cq.message.answer(texts.ASK_NAME)


@router.message(OrderSG.name, F.text)
async def order_name(message: Message, state: FSMContext) -> None:
    await state.update_data(name=message.text.strip())
    data = await state.get_data()
    if data["delivery_key"] == "pickup":
        await state.update_data(address="самовывоз (МО)")
        await state.set_state(OrderSG.phone)
        await message.answer(texts.ASK_PHONE)
    else:
        await state.set_state(OrderSG.address)
        await message.answer(texts.ASK_ADDRESS)


@router.message(OrderSG.address, F.text)
async def order_address(message: Message, state: FSMContext) -> None:
    await state.update_data(address=message.text.strip())
    await state.set_state(OrderSG.phone)
    await message.answer(texts.ASK_PHONE)


@router.message(OrderSG.phone, F.text)
async def order_phone(message: Message, state: FSMContext) -> None:
    phone = message.text.strip()
    if not re.search(r"\d{6,}", phone):
        await message.answer("Похоже, в номере мало цифр. Пришлите телефон ещё раз.")
        return
    await state.update_data(phone=phone)
    data = await state.get_data()
    total = data["price"] * data["qty"] + (data["delivery_cost"] or 0)
    await state.update_data(total=total)
    await state.set_state(OrderSG.confirm)
    await message.answer(
        texts.order_summary(data["issue"], data["qty"], data["delivery_title"],
                            data["delivery_cost"], data["name"],
                            data["address"], phone, total),
        reply_markup=kb.CONFIRM,
    )


@router.callback_query(F.data == "confirm:yes", OrderSG.confirm)
async def order_confirm(cq: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    order_id = db.add_order(cq.from_user.id, data["issue"], data["qty"],
                            data["delivery_title"], data["name"],
                            data["address"], data["phone"], data["total"])
    await state.clear()
    await cq.answer()
    await cq.message.answer(texts.payment(order_id, data["total"],
                                          tariff=data["delivery_cost"] is None),
                            reply_markup=kb.PAID)
    await notify_admin(texts.admin_order(db.get_order(order_id)))


@router.callback_query(F.data == "paid")
async def cb_paid(cq: CallbackQuery) -> None:
    order = db.last_order(cq.from_user.id)
    await cq.answer()
    if order and order["status"] == "new":
        db.set_order_status(order["id"], "paid_unconfirmed")
        db.set_user_field(cq.from_user.id, "purchase", 1)  # дожим стоп
        await notify_admin(texts.admin_paid(order["id"], order["total"]))
    await cq.message.answer(texts.AFTER_PAID, reply_markup=kb.MENU)


# ------------------------------------------------------------- email
@router.callback_query(F.data == "leave_email")
async def cb_email(cq: CallbackQuery, state: FSMContext) -> None:
    await cq.answer()
    await state.set_state(EmailSG.email)
    await cq.message.answer(texts.ASK_EMAIL)


@router.message(EmailSG.email, F.text)
async def email_save(message: Message, state: FSMContext) -> None:
    email = message.text.strip()
    if "@" not in email or "." not in email:
        await message.answer(texts.EMAIL_BAD)
        return
    db.set_user_field(message.from_user.id, "email", email)
    await state.clear()
    await message.answer(texts.EMAIL_SAVED)


# ------------------------------------------------------------- отписка
@router.callback_query(F.data == "unsub")
async def cb_unsub(cq: CallbackQuery) -> None:
    db.set_user_field(cq.from_user.id, "unsubscribed", 1)
    await cq.answer()
    await cq.message.answer(texts.UNSUB_DONE)


# ------------------------------------------------------------- админ
def is_admin(message: Message) -> bool:
    return message.from_user.id == C.ADMIN_ID


@router.message(Command("stock"))
async def cmd_stock(message: Message) -> None:
    line, total = stock_line()
    await message.answer(f"Остатки: {line}. Всего {total} экз.")


@router.message(Command("setstock"))
async def cmd_setstock(message: Message) -> None:
    if not is_admin(message):
        return
    parts = (message.text or "").split()
    if len(parts) != 3 or parts[1] not in ("1", "2", "3"):
        await message.answer("Формат: /setstock 1 8")
        return
    db.set_stock(parts[1], int(parts[2]))
    line, total = stock_line()
    await message.answer(f"Обновлено. {line} (всего {total})")


@router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    if not is_admin(message):
        return
    s = db.stats()
    await message.answer(
        "📊 Воронка за всё время\n"
        f"Контактов: {s['users']} (с сегментацией: {s['leads']})\n"
        f"Заявок: {s['orders']}\n"
        f"Оплаченных: {s['paid']}\n"
        f"Выручка: {s['revenue']}₽"
    )


@router.message(Command("confirm"))
async def cmd_confirm(message: Message) -> None:
    if not is_admin(message):
        return
    parts = (message.text or "").split()
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("Формат: /confirm 3")
        return
    order = db.get_order(int(parts[1]))
    if not order:
        await message.answer("Заказ не найден.")
        return
    db.set_order_status(order["id"], "paid")
    db.set_user_field(order["user_id"], "purchase", 1)
    await message.answer(f"Заказ №{order['id']} — оплата подтверждена.")
    await bot.send_message(order["user_id"],
                           "Оплата подтверждена ✅ Готовлю отправку.")


@router.message(Command("reject"))
async def cmd_reject(message: Message) -> None:
    if not is_admin(message):
        return
    parts = (message.text or "").split()
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("Формат: /reject 3")
        return
    db.set_order_status(int(parts[1]), "rejected")
    await message.answer(f"Заказ №{parts[1]} — отклонён.")


@router.message(Command("export"))
async def cmd_export(message: Message) -> None:
    if not is_admin(message):
        return
    users, orders = db.export_rows()
    buf_users = io.StringIO()
    w = csv.DictWriter(buf_users, fieldnames=[
        "user_id", "username", "first_name", "source", "segment",
        "email", "purchase", "unsubscribed", "created_at"])
    w.writeheader()
    w.writerows(users)
    buf_orders = io.StringIO()
    w2 = csv.DictWriter(buf_orders, fieldnames=[
        "id", "user_id", "issue", "qty", "delivery", "name", "address",
        "phone", "total", "status", "created_at"])
    w2.writeheader()
    w2.writerows(orders)
    await message.answer_document(
        BufferedInputFile(buf_users.getvalue().encode(), "users.csv"),
        caption="Пользователи")
    await message.answer_document(
        BufferedInputFile(buf_orders.getvalue().encode(), "orders.csv"),
        caption="Заказы")


# --------------------------------------------------- свободный текст → админ
@router.message(StateFilter(None), F.text)
async def any_text(message: Message) -> None:
    uname = f"@{message.from_user.username}" if message.from_user.username \
        else str(message.from_user.id)
    await notify_admin(f"💬 Вопрос от {uname}:\n{message.text}")
    await message.answer(
        "Спасибо! Вопрос получил — отвечу в ближайшее время. "
        "Если срочно: @ermlv")


# ------------------------------------------------------------- дожим
async def send_drip(user: dict, step: int) -> None:
    if step == 3:
        text = texts.d3(user.get("segment") or "new")
    elif step == 7:
        text = texts.d7()
    elif step == 14:
        text = texts.d14(stock_line()[0])
    elif step == 21:
        text = texts.d21()
    else:
        text = texts.d30()
    await bot.send_message(user["user_id"], text, reply_markup=kb.drip_kb(step))


async def drip_loop() -> None:
    while True:
        try:
            now = int(time.time())
            for step in C.DRIP_STEPS:
                for user in db.drip_due(now, step):
                    try:
                        await send_drip(user, step)
                        db.mark_drip(user["user_id"], step, now)
                    except Exception:
                        log.exception("Дожим день %s → %s", step, user["user_id"])
        except Exception:
            log.exception("Сбой цикла дожима")
        await asyncio.sleep(C.DRIP_CHECK_EVERY)


# ------------------------------------------------------------- main
async def main() -> None:
    db.init_db()
    line, total = stock_line()
    log.info("Остатки на старте: %s (всего %s)", line, total)
    await bot.delete_webhook(drop_pending_updates=True)  # polling, не webhook
    asyncio.create_task(drip_loop())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
