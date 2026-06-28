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
# ========== КОНФИГУРАЦИЯ (ЗАМЕНИ!!!) ==========
# ==========================================
BOT_TOKEN = "8920475030:AAGXrQmacyPlsuUuO7kM2OK1m7h1JYQ29nc"   # Например: 123456:ABC-DEF
GAMESDROP_TOKEN = "zUFq5AsmGRQDwECpsVmmFMWVRj2RkMBIjOu2ZmuicGtd"      # Например: dropp_abcdef123456
ADMIN_ID = 5267683182                          # ТВОЙ Telegram ID (узнай у @userinfobot)
BOT_USERNAME = "master_uc_bot"           # Например: (без @)

# ==========================================
# ========== ТОВАРЫ (РЕДАКТИРУЙ ЗДЕСЬ) ==========
# ==========================================
ITEMS = [
    {"id": 371, "name": "60 UC", "price": 0.90, "currency": "$"},
    {"id": 125, "name": "325 UC", "price": 4.46, "currency": "$"},
    {"id": 126, "name": "660 UC", "price": 8.92, "currency": "$"},
]

# ==========================================
# НАСТРОЙКА ЛОГОВ
# ==========================================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ==========================================
# СОЗДАНИЕ БОТА
# ==========================================
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ==========================================
# СОСТОЯНИЯ (для диалога с игроком)
# ==========================================
class OrderStates(StatesGroup):
    waiting_for_uid = State()  # Ожидаем, когда игрок введет свой UID

# ==========================================
# ФУНКЦИЯ ЗАПРОСА К API GAMESDROP
# ==========================================
API_BASE_URL = "https://partner.gamesdrop.io/api/v1/offers"

async def create_gamesdrop_order(offer_id: int, price: float, game_user_id: str, transaction_id: str):
    """Создать заказ в GamesDrop с UID игрока"""
    url = f"{API_BASE_URL}/create-order"
    headers = {"Authorization": GAMESDROP_TOKEN, "Content-Type": "application/json"}
    payload = {
        "offerId": offer_id,
        "price": price,
        "transactionId": transaction_id,
        "customer": {
            "gameUserId": game_user_id,
            "email": f"user_{game_user_id}@example.com"
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
                logger.error(f"Ошибка GamesDrop: {resp.status} - {error_text}")
                return {"error": f"Status {resp.status}", "detail": error_text}
    except Exception as e:
        logger.error(f"Ошибка соединения: {e}")
        return {"error": "Exception", "detail": str(e)}

async def check_order_status(order_id: int):
    """Узнать статус заказа"""
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
        logger.error(f"Ошибка проверки статуса: {e}")
        return None

# ==========================================
# ========== КОМАНДЫ ДЛЯ ИГРОКА ==========
# ==========================================

@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "👋 Привет! Я бот для пополнения PUBG Mobile.\n\n"
        "📦 Нажми /catalog, чтобы выбрать товар."
    )

@dp.message(Command("catalog"))
async def cmd_catalog(message: Message):
    keyboard = []
    for item in ITEMS:
        keyboard.append([InlineKeyboardButton(
            text=f"{item['name']} - {item['price']} {item['currency']}",
            callback_data=f"buy_{item['id']}"
        )])
    
    await message.answer(
        "📦 Выбери нужный пакет UC:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
    )

# ==========================================
# ========== ОБРАБОТЧИК ВЫБОРА ТОВАРА ==========
# ==========================================

@dp.callback_query(F.data.startswith("buy_"))
async def process_buy(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    
    # Находим выбранный товар
    offer_id = int(callback.data.split("_")[1])
    item = next((x for x in ITEMS if x["id"] == offer_id), None)
    
    if not item:
        await callback.message.answer("❌ Товар не найден.")
        return

    # Сохраняем данные о заказе в память
    await state.update_data(
        offer_id=offer_id,
        price=item["price"],
        name=item["name"]
    )
    
    # Просим игрока ввести UID
    await state.set_state(OrderStates.waiting_for_uid)
    await callback.message.answer(
        f"✅ Ты выбрал: {item['name']}\n"
        f"💰 Цена: {item['price']} {item['currency']}\n\n"
        "🔢 Введи свой ID в PUBG Mobile (только цифры):"
    )

# ==========================================
# ========== ОБРАБОТЧИК ПОЛУЧЕНИЯ UID ==========
# ==========================================

@dp.message(OrderStates.waiting_for_uid)
async def process_uid(message: Message, state: FSMContext):
    game_user_id = message.text.strip()
    
    # Простая проверка на цифры
    if not game_user_id.isdigit():
        await message.answer("❌ ID должен состоять только из цифр. Попробуй снова.")
        return

    # Получаем данные о товаре из памяти
    user_data = await state.get_data()
    offer_id = user_data.get("offer_id")
    price = user_data.get("price")
    item_name = user_data.get("name")
    
    # Генерируем уникальный ID заказа
    transaction_id = f"tg_{message.from_user.id}_{int(time.time())}"
    
    # Отправляем запрос в GamesDrop
    await message.answer("⏳ Создаю заказ...")
    result = await create_gamesdrop_order(offer_id, price, game_user_id, transaction_id)
    
    # ----- ЕСЛИ ОШИБКА (например, нет баланса) -----
    if "error" in result:
        await message.answer(
            f"❌ Техническая ошибка: {result.get('detail', 'Неизвестная')}\n"
            "Попробуй позже или напиши администратору."
        )
        await state.clear()
        return

    # ----- ЕСЛИ ВСЁ ХОРОШО -----
    order_id = result.get("orderId")
    payment_url = result.get("paymentUrl")
    
    if payment_url:
        # 1. Отправляем игроку кнопку на оплату
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💳 Перейти к оплате", url=payment_url)]
        ])
        await message.answer(
            f"✅ Заказ создан!\n"
            f"Номер заказа: `{order_id}`\n\n"
            "Нажми кнопку ниже, чтобы оплатить картой или СБП.\n"
            "⏳ Ссылка активна 30 минут.",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
        
        # 2. ОТПРАВЛЯЕМ УВЕДОМЛЕНИЕ АДМИНИСТРАТОРУ (ТЕБЕ!)
        admin_text = (
            f"🔔 **НОВЫЙ ЗАКАЗ!**\n\n"
            f"👤 Игрок: @{message.from_user.username or 'Без юзернейма'}\n"
            f"🆔 ID игрока: {message.from_user.id}\n"
            f"📦 Товар: {item_name}\n"
            f"🔢 UID: {game_user_id}\n"
            f"💲 Цена: {price} USD\n"
            f"📋 Номер заказа: {order_id}\n"
            f"🔗 Ссылка: {payment_url}\n\n"
            f"Ожидай оплаты от игрока."
        )
        await bot.send_message(ADMIN_ID, admin_text, parse_mode="Markdown")
        
        # 3. Запускаем фоновую проверку оплаты (на всякий случай)
        asyncio.create_task(monitor_payment(order_id, message.chat.id, item_name))

    else:
        await message.answer("❌ Не удалось получить ссылку на оплату. Попробуй снова.")
    
    await state.clear()

# ==========================================
# ========== ФОНОВАЯ ПРОВЕРКА СТАТУСА ==========
# ==========================================

async def monitor_payment(order_id: int, chat_id: int, item_name: str):
    """Проверяем статус заказа каждые 10 секунд (макс 5 минут)"""
    await asyncio.sleep(5)  # Даем время на открытие ссылки
    
    for _ in range(30):  # 30 раз по 10 секунд = 5 минут
        await asyncio.sleep(10)
        status_data = await check_order_status(order_id)
        if not status_data:
            continue
        
        status = status_data.get("status")
        
        if status == "COMPLETED":
            # Уведомляем игрока
            await bot.send_message(
                chat_id,
                f"✅ Поздравляем! Товар '{item_name}' успешно зачислен.\n"
                "Спасибо за покупку! 🎮"
            )
            # Уведомляем админа об успехе
            await bot.send_message(
                ADMIN_ID,
                f"✅ Заказ {order_id} успешно выполнен и оплачен!"
            )
            return
            
        elif status in ["CANCELED", "FAILED"]:
            await bot.send_message(
                chat_id,
                f"❌ Заказ был отменен. Если ты оплатил, деньги вернутся в течение суток."
            )
            return
    
    # Если время вышло
    await bot.send_message(
        chat_id,
        "⏳ Время проверки истекло. Если ты оплатил, товар зачислится автоматически в течение часа."
    )

# ==========================================
# ========== ЛОВУШКА ДЛЯ НЕИЗВЕСТНЫХ КОМАНД ==========
# ==========================================

@dp.message()
async def catch_all(message: Message):
    await message.answer(
        "⚠️ Неизвестная команда.\n"
        "Используй /start или /catalog."
    )

# ==========================================
# ========== ЗАПУСК БОТА ==========
# ==========================================

async def main():
    logger.info("🚀 Новый бот запущен и готов к работе!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())