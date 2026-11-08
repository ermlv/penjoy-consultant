"""Клавиатуры PENJOY-бота."""
from aiogram.types import (InlineKeyboardButton, InlineKeyboardMarkup,
                           KeyboardButton, ReplyKeyboardMarkup)
from aiogram.utils.keyboard import InlineKeyboardBuilder

import config as C

# --- постоянное меню (клавиатура внизу) ---------------------------------
MENU = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📖 Забрать гайд")],
        [KeyboardButton(text="📦 Заказать печатный"),
         KeyboardButton(text="ℹ️ Доставка и оплата")],
        [KeyboardButton(text="✍️ Вопрос про ручки")],
    ],
    resize_keyboard=True,
)

# --- сегментация --------------------------------------------------------
SEG = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="🖋 Уже пишу", callback_data="seg:existing")],
    [InlineKeyboardButton(text="🌱 Выбираю первую", callback_data="seg:new")],
    [InlineKeyboardButton(text="🎁 Ищу в подарок", callback_data="seg:gift")],
])

# --- оффер печатного ----------------------------------------------------
OFFER = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="📦 Заказать печатный", callback_data="order")],
    [InlineKeyboardButton(text="Позже, спасибо", callback_data="later")],
])

# --- заказ: номер -------------------------------------------------------
def issue_kb():
    b = InlineKeyboardBuilder()
    for key, title in C.ISSUES.items():
        b.button(text=title.split(" — ")[0], callback_data=f"order_issue:{key}")
    b.button(text="🎁 Комплект №1–№3 — 2700₽", callback_data="order_issue:set")
    b.adjust(1)
    return b.as_markup()


# --- заказ: количество --------------------------------------------------
QTY = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="1", callback_data="qty:1"),
     InlineKeyboardButton(text="2", callback_data="qty:2"),
     InlineKeyboardButton(text="3", callback_data="qty:3")],
])

# --- заказ: доставка ----------------------------------------------------
def delivery_kb():
    b = InlineKeyboardBuilder()
    for key, d in C.DELIVERY.items():
        price = "" if d["cost"] == 0 else f" — {d['cost']}₽"
        b.button(text=f"{d['title']}{price}", callback_data=f"deliv:{key}")
    b.adjust(1)
    return b.as_markup()


# --- подтверждение заказа ----------------------------------------------
CONFIRM = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="✅ Всё верно, оформить", callback_data="confirm:yes"),
     InlineKeyboardButton(text="🔁 Начать заново", callback_data="order")],
])

# --- после оплаты -------------------------------------------------------
PAID = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="✅ Я оплатил", callback_data="paid")],
])

# --- дожим --------------------------------------------------------------
def drip_kb(step: int):
    rows = [[InlineKeyboardButton(text="📦 Заказать печатный", callback_data="order")]]
    if step == 30:
        rows.append([InlineKeyboardButton(text="✉️ Узнать о новом номере первым",
                                          callback_data="leave_email")])
    rows.append([InlineKeyboardButton(text="Отписать от напоминаний",
                                      callback_data="unsub")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
