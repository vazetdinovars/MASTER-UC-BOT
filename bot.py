import asyncio
import logging
import time
import aiohttp
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

# ==========================================
# КОНФИГУРАЦИЯ (ЗАМЕНИ ТОКЕНЫ!!!)
# ==========================================
BOT_TOKEN = "8920475030:AAGXrQmacyPlsuUuO7kM2OK1m7h1JYQ29nc"
GAMESDROP_TOKEN = "zUFq5AsmGRQDwECpsVmmFMWVRj2RkMBIjOu2ZmuicGtd"
BOT_USERNAME = "MASTER_UC_BOT"  # Например: PUBGDonateBot (без @)
API_BASE_URL = "https://partner.gamesdrop.io/api/v1/offers"

# ==========================================
# НАСТРОЙКА ЛОГИРОВАНИЯ
# ==========================================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ==========================================
# СОЗДАНИЕ ОБЪЕКТОВ БОТА
# ==========================================
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ==========================================
# СОСТОЯНИЯ ДЛЯ ДИАЛОГА
# ==========================================
class OrderStates(StatesGroup):
    waiting_for_uid = State()  # Ожидание UID перед оплатой

# ==========================================
# ТВОИ ТОВАРЫ (ПУБГ МОБАЙЛ)
# ==========================================
ITEMS = [
    {"offer_id": 371, "name": "60 UC", "price": 0.90, "currency": "USD"},
    {"offer_id": 125, "name": "325 UC", "price": 4.46, "currency": "USD"},
    {"offer_id": 126, "name": "660 UC", "price": 8.92, "currency": "USD"},
]

# ==========================================
# ФУНКЦИИ ДЛЯ РАБОТЫ С API GAMESDROP
# ==========================================

async def get_balance():
    url = f"{API_BASE_URL}/balance"
    headers = {"Authorization": GAMESDROP_TOKEN}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("balance", 0)
                return None
    except Exception as e:
        logger.error(f"Ошибка при получении баланса: {e}")
        return None

async def create_order(offer_id: int, price: float, game_user_id: str, transaction_id: str):
    """Создать заказ с UID"""
    url = f"{API_BASE_URL}/create-order"
    headers = {"Authorization": GAMESDROP_TOKEN, "Content-Type": "application/json"}
    payload = {
        "offerId": offer_id,
        "price": price,
        "transactionId": transaction_id,
        "customer": {
            "gameUserId": game_user_id,
            "email": "user@example.com"
        },
        "paymentMethod": "card",
        "returnUrl": f"https://t.me/{BOT_USERNAME}"
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as resp:
                if resp.status == 200:
                    return await resp.json()
                error_text = await resp.text()
                logger.error(f"Ошибка заказа: {resp.status} - {error_text}")
                return {"error": f"Status {resp.status}", "detail": error_text}
    except Exception as e:
        logger.error(f"Ошибка при создании заказа: {e}")
        return {"error": "Exception", "detail": str(e)}

async def check_order_status(order_id: int):
    url = f"{API_BASE_URL}/order-status"
    headers = {"Authorization": GAMESDROP_TOKEN, "Content-Type": "application/json"}
    payload = {"orderId": order_id}
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as resp:
                if resp.status == 200:
                    return await resp.json()
                return None
    except Exception as e:
        logger.error(f"Ошибка при проверке статуса: {e}")
        return None

async def monitor_order(order_id: int, chat_id: int):
    """Фоновая проверка статуса заказа"""
    for _ in range(30):
        await asyncio.sleep(10)
        status_data = await check_order_status(order_id)
        if not status_data:
            continue
            
        status = status_data.get("status")
        if status == "COMPLETED":
            if status_data.get("isReturnDataForCustomer"):
                key = status_data.get("key", "Ключ не получен")
                await bot.send_message(chat_id, f"✅ Заказ выполнен!\n🎁 Твой ключ: `{key}`", parse_mode="Markdown")
            else:
                await bot.send_message(chat_id, f"✅ Заказ выполнен! Игровая валюта зачислена.")
            return
        elif status in ["CANCELED", "FAILED"]:
            await bot.send_message(chat_id, f"❌ Заказ отменен. Причина: {status_data.get('message', 'Неизвестно')}")
            return
    
    await bot.send_message(chat_id, "⏳ Время проверки истекло. Проверь статус позже вручную.")

# ==========================================
# КОМАНДЫ БОТА
# ==========================================

@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "👋 Привет! Я бот для пополнения PUBG Mobile.\n\n"
        "📋 Как это работает:\n"
        "1. Выбери товар в /catalog\n"
        "2. Введи свой UID (игровой ID)\n"
        "3. Оплати по ссылке\n"
        "4. Валюту зачислят автоматически\n\n"
        "📋 Доступные команды:\n"
        "/catalog - показать товары\n"
        "/balance - проверить баланс\n"
        "/ping - проверить связь"
    )

@dp.message(Command("ping"))
async def ping_api(message: Message):
    await message.answer("🔄 Проверяю связь с GamesDrop...")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("https://partner.gamesdrop.io") as resp:
                await message.answer(f"✅ Статус сайта: {resp.status} (OK)")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

@dp.message(Command("balance"))
async def cmd_balance(message: Message):
    await message.answer("🔄 Проверяю баланс...")
    balance = await get_balance()
    if balance is not None:
        await message.answer(f"💰 Текущий баланс: **{balance} USD**", parse_mode="Markdown")
    else:
        await message.answer("❌ Не удалось получить баланс. Проверь токен.")

@dp.message(Command("catalog"))
async def cmd_catalog(message: Message):
    keyboard = []
    for item in ITEMS:
        keyboard.append([InlineKeyboardButton(
            text=f"{item['name']} - {item['price']} {item['currency']}",
            callback_data=f"buy_{item['offer_id']}"
        )])
    
    await message.answer(
        "📦 Выбери товар для PUBG Mobile:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
    )

# ==========================================
# ОБРАБОТЧИКИ КНОПОК
# ==========================================

@dp.callback_query(F.data.startswith("buy_"))
async def process_buy(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    offer_id = int(callback.data.split("_")[1])
    
    item = next((x for x in ITEMS if x["offer_id"] == offer_id), None)
    if not item:
        await callback.message.answer("❌ Товар не найден.")
        return
    
    # Сохраняем данные о товаре
    await state.update_data(
        offer_id=offer_id,
        price=item["price"],
        offer_name=item["name"]
    )
    
    # Переходим в состояние ожидания UID
    await state.set_state(OrderStates.waiting_for_uid)
    await callback.message.answer(
        f"✅ {item['name']}\n"
        f"💰 {item['price']} {item['currency']}\n\n"
        "Введи свой ID в PUBG Mobile (gameUserId):"
    )

# ==========================================
# ОБРАБОТЧИК UID (перед оплатой)
# ==========================================

@dp.message(OrderStates.waiting_for_uid)
async def process_uid_before_payment(message: Message, state: FSMContext):
    game_user_id = message.text.strip()
    if not game_user_id.isdigit():
        await message.answer("❌ ID должен содержать только цифры. Попробуй снова.")
        return
    
    user_data = await state.get_data()
    offer_id = user_data.get("offer_id")
    price = user_data.get("price")
    transaction_id = f"tg_{message.from_user.id}_{int(time.time())}"
    
    await message.answer("⏳ Создаю заказ...")
    result = await create_order(offer_id, price, game_user_id, transaction_id)
    
    if "error" in result:
        await message.answer(f"❌ Ошибка: {result.get('detail', 'Неизвестно')}")
        await state.clear()
        return
    
    order_id = result.get("orderId")
    payment_url = result.get("paymentUrl")
    
    if payment_url:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💳 Оплатить картой/СБП", url=payment_url)]
        ])
        await message.answer(
            f"✅ Заказ {order_id} создан!\n"
            "Нажми кнопку для оплаты.\n"
            "⏳ Ссылка действительна 30 мин.\n\n"
            f"UID: {game_user_id}",
            reply_markup=keyboard
        )
        # Запускаем фоновую проверку статуса
        asyncio.create_task(monitor_order(order_id, message.chat.id))
    else:
        await message.answer(f"❌ Не удалось получить ссылку на оплату. Заказ {order_id}.")
    
    await state.clear()

# ==========================================
# ЛОВУШКА ДЛЯ НЕИЗВЕСТНЫХ КОМАНД
# ==========================================

@dp.message()
async def catch_all(message: Message):
    await message.answer(
        f"⚠️ Неизвестная команда.\n\n"
        f"📋 Доступные команды:\n"
        f"/start - приветствие\n"
        f"/catalog - показать товары\n"
        f"/balance - проверить баланс\n"
        f"/ping - проверить связь"
    )

# ==========================================
# ЗАПУСК БОТА
# ==========================================

async def main():
    logger.info("🚀 Бот запускается...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())