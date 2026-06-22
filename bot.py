import asyncio
import logging
import time
import json
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
API_BASE_URL = "https://partner.gamesdrop.io/api/v1/offers"

# ==========================================
# НАСТРОЙКА ЛОГИРОВАНИЯ
# ==========================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
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
    entering_game_id = State()

# ==========================================
# ФУНКЦИИ ДЛЯ РАБОТЫ С API GAMESDROP
# ==========================================

async def sync_catalog():
    """Получить список товаров из каталога с таймаутом"""
    url = f"{API_BASE_URL}/sync"
    headers = {"Authorization": GAMESDROP_TOKEN, "Content-Type": "application/json"}
    payload = {"limit": 50, "page": 1}
    
    timeout = aiohttp.ClientTimeout(total=10)
    
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, headers=headers, json=payload) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    rows = data.get("rows", [])
                    logger.info(f"Загружено {len(rows)} товаров")
                    return rows
                else:
                    error_text = await resp.text()
                    logger.error(f"Ошибка синхронизации: {resp.status} - {error_text}")
                    return []
    except asyncio.TimeoutError:
        logger.error("Таймаут при запросе к API GamesDrop")
        return []
    except aiohttp.ClientError as e:
        logger.error(f"Ошибка соединения: {e}")
        return []
    except Exception as e:
        logger.error(f"Неожиданная ошибка: {e}")
        return []

async def get_balance():
    """Проверить баланс магазина"""
    url = f"{API_BASE_URL}/balance"
    headers = {"Authorization": GAMESDROP_TOKEN}
    
    timeout = aiohttp.ClientTimeout(total=10)
    
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("balance", 0)
                return None
    except Exception as e:
        logger.error(f"Ошибка при получении баланса: {e}")
        return None

async def create_order(offer_id: int, price: float, game_user_id: str, transaction_id: str):
    """Создать заказ и получить ссылку на оплату"""
    url = f"{API_BASE_URL}/create-order"
    headers = {"Authorization": GAMESDROP_TOKEN, "Content-Type": "application/json"}
    payload = {
        "offerId": offer_id,
        "price": price,
        "transactionId": transaction_id,
        "customer": {"gameUserId": game_user_id},
        "paymentMethod": "card",
        "returnUrl": "https://t.me/your_bot_username"
    }
    
    timeout = aiohttp.ClientTimeout(total=15)
    
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, headers=headers, json=payload) as resp:
                if resp.status == 200:
                    return await resp.json()
                error_text = await resp.text()
                logger.error(f"Ошибка заказа: {resp.status} - {error_text}")
                return {"error": f"Status {resp.status}", "detail": error_text}
    except asyncio.TimeoutError:
        logger.error("Таймаут при создании заказа")
        return {"error": "Timeout", "detail": "Сервер не отвечает"}
    except Exception as e:
        logger.error(f"Ошибка при создании заказа: {e}")
        return {"error": "Exception", "detail": str(e)}

async def check_order_status(order_id: int):
    """Проверить статус заказа"""
    url = f"{API_BASE_URL}/order-status"
    headers = {"Authorization": GAMESDROP_TOKEN, "Content-Type": "application/json"}
    payload = {"orderId": order_id}
    
    timeout = aiohttp.ClientTimeout(total=10)
    
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, headers=headers, json=payload) as resp:
                if resp.status == 200:
                    return await resp.json()
                return None
    except Exception as e:
        logger.error(f"Ошибка при проверке статуса: {e}")
        return None

async def monitor_order(order_id: int, chat_id: int):
    """Фоновая проверка статуса заказа (каждые 10 секунд)"""
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
        "👋 Привет! Я бот для пополнения игр.\n\n"
        "📋 Доступные команды:\n"
        "/catalog - показать товары\n"
        "/balance - проверить баланс\n"
        "/ping - проверить связь с GamesDrop\n"
        "/debug - полная диагностика API\n\n"
        "💡 Если каталог не грузится, используй /debug"
    )

@dp.message(Command("ping"))
async def ping_api(message: Message):
    """Проверка доступности API GamesDrop"""
    await message.answer("🔄 Проверяю связь с GamesDrop...")
    try:
        timeout = aiohttp.ClientTimeout(total=5)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get("https://partner.gamesdrop.io") as resp:
                await message.answer(f"✅ Статус сайта: {resp.status} (OK)")
    except asyncio.TimeoutError:
        await message.answer("❌ Таймаут: сайт GamesDrop не отвечает")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

@dp.message(Command("balance"))
async def cmd_balance(message: Message):
    """Проверка баланса"""
    await message.answer("🔄 Проверяю баланс...")
    balance = await get_balance()
    if balance is not None:
        await message.answer(f"💰 Текущий баланс: **{balance} USD**", parse_mode="Markdown")
    else:
        await message.answer("❌ Не удалось получить баланс. Проверь токен.")

@dp.message(Command("debug"))
async def debug_api(message: Message):
    """Полная диагностика API"""
    await message.answer("🔄 Запускаю полную диагностику...\n\n")
    
    headers = {"Authorization": GAMESDROP_TOKEN, "Content-Type": "application/json"}
    timeout = aiohttp.ClientTimeout(total=10)
    
    # 1. Проверка баланса (GET)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(f"{API_BASE_URL}/balance", headers=headers) as resp:
                text = await resp.text()
                await message.answer(
                    f"**1. Баланс (GET)**\n"
                    f"Статус: {resp.status}\n"
                    f"Ответ: `{text[:200]}`",
                    parse_mode="Markdown"
                )
    except Exception as e:
        await message.answer(f"❌ Ошибка при запросе баланса: {e}")
    
    # 2. Проверка каталога (POST)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(f"{API_BASE_URL}/sync", headers=headers, json={"limit": 2, "page": 1}) as resp:
                text = await resp.text()
                await message.answer(
                    f"**2. Каталог (POST /sync)**\n"
                    f"Статус: {resp.status}\n"
                    f"Ответ: `{text[:300]}`",
                    parse_mode="Markdown"
                )
    except Exception as e:
        await message.answer(f"❌ Ошибка при запросе каталога: {e}")
    
    # 3. Проверка конкретного товара (POST)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(f"{API_BASE_URL}/find-one", headers=headers, json={"offerId": 999}) as resp:
                text = await resp.text()
                await message.answer(
                    f"**3. Товар 999 (POST /find-one)**\n"
                    f"Статус: {resp.status}\n"
                    f"Ответ: `{text[:200]}`",
                    parse_mode="Markdown"
                )
    except Exception as e:
        await message.answer(f"❌ Ошибка при запросе товара: {e}")

@dp.message(Command("catalog"))
async def cmd_catalog(message: Message):
    await message.answer("🔄 Загружаю каталог...")
    items = await sync_catalog()
    
    if not items:
        await message.answer(
            "❌ Каталог пуст или ошибка загрузки.\n\n"
            "Возможные причины:\n"
            "1. Неверный токен GamesDrop\n"
            "2. У тебя нет доступа к товарам\n"
            "3. Пустой баланс\n\n"
            "Используй /debug для диагностики."
        )
        return
    
    keyboard = []
    for item in items[:10]:
        name = item.get("offerGroupName", "Товар")
        price = item.get("price", 0)
        currency = item.get("currency", "USD")
        offer_id = item.get("offerGroupId")
        keyboard.append([InlineKeyboardButton(
            text=f"{name} - {price} {currency}",
            callback_data=f"buy_{offer_id}"
        )])
    
    keyboard.append([InlineKeyboardButton("🔄 Обновить", callback_data="refresh")])
    await message.answer(
        "📦 Выбери товар:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
    )

# ==========================================
# ОБРАБОТЧИКИ КНОПОК
# ==========================================

@dp.callback_query(F.data.startswith("buy_"))
async def process_buy(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    offer_id = int(callback.data.split("_")[1])
    
    url = f"{API_BASE_URL}/find-one"
    headers = {"Authorization": GAMESDROP_TOKEN, "Content-Type": "application/json"}
    
    try:
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, headers=headers, json={"offerId": offer_id}) as resp:
                if resp.status != 200:
                    await callback.message.answer("❌ Ошибка получения товара.")
                    return
                offer_data = await resp.json()
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка: {e}")
        return
    
    await state.update_data(
        offer_id=offer_id,
        price=offer_data.get("price"),
        offer_name=offer_data.get("offerName")
    )
    
    await state.set_state(OrderStates.entering_game_id)
    await callback.message.answer(
        f"✅ {offer_data.get('offerName')}\n"
        f"💰 {offer_data.get('price')} {offer_data.get('currency')}\n\n"
        "Введи свой ID в игре (gameUserId):"
    )

@dp.message(OrderStates.entering_game_id)
async def process_game_id(message: Message, state: FSMContext):
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
            "⏳ Ссылка действительна 30 мин.",
            reply_markup=keyboard
        )
        asyncio.create_task(monitor_order(order_id, message.chat.id))
    else:
        await message.answer(f"❌ Не удалось получить ссылку на оплату. Заказ {order_id}.")
    
    await state.clear()

@dp.callback_query(F.data == "refresh")
async def refresh_catalog(callback: CallbackQuery):
    await callback.answer("Обновляю...")
    await cmd_catalog(callback.message)

# ==========================================
# ЛОВУШКА ДЛЯ НЕИЗВЕСТНЫХ КОМАНД
# ==========================================

@dp.message()
async def catch_all(message: Message):
    """Обработчик всех неизвестных сообщений (для отладки)"""
    await message.answer(
        f"⚠️ Неизвестная команда.\n"
        f"Ты написал: `{message.text}`\n\n"
        f"📋 Доступные команды:\n"
        f"/start - приветствие\n"
        f"/catalog - показать товары\n"
        f"/balance - проверить баланс\n"
        f"/ping - проверить связь с GamesDrop\n"
        f"/debug - полная диагностика API",
        parse_mode="Markdown"
    )
    logger.info(f"Unknown message: {message.text}")

# ==========================================
# ЗАПУСК БОТА
# ==========================================

async def main():
    logger.info("🚀 Бот запускается...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())