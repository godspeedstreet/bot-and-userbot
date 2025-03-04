from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from dotenv import load_dotenv
import os
import logging

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('admin_bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Загрузка переменных окружения
load_dotenv()

# Параметры подключения для бота
bot_token = os.getenv('BOT_TOKEN')  
api_id = os.getenv('API_ID')
api_hash = os.getenv('API_HASH')
admin_ids = [int(id.strip()) for id in os.getenv('ADMIN_IDS', '').split(',')]  
target_channels = os.getenv('TARGET_CHANNEL_USERNAMES', '').split(',')  # Список целевых каналов
user_bot_id = int(os.getenv('USER_BOT_ID'))  

# Логируем конфигурацию при запуске
logger.info("=== Bot Configuration ===")
logger.info(f"Bot Token: {bot_token}")
logger.info(f"API ID: {api_id}")
logger.info(f"Admin IDs: {admin_ids}")
logger.info(f"Target Channels: {target_channels}")
logger.info(f"User Bot ID: {user_bot_id}")

# Создание клиента
bot = Client(
    "notification_bot",
    api_id=api_id,
    api_hash=api_hash,
    bot_token=bot_token
)

# Словарь для хранения сообщений, ожидающих одобрения
pending_posts = {}

@bot.on_message(filters.command("start"))
async def start_command(client, message):
    """Обработчик команды /start"""
    try:
        user_id = message.from_user.id
        logger.info(f"Received /start command from user {user_id}")
        
        if user_id in admin_ids:
            channels_list = "\n".join([f"• {channel}" for channel in target_channels])
            await message.reply(
                f"Привет! Я бот для модерации постов. Вы являетесь администратором.\n\n"
                f"Целевые каналы для публикации:\n{channels_list}"
            )
        else:
            await message.reply("Привет! Я бот для модерации постов.")
            
    except Exception as e:
        logger.error(f"Error in start_command: {str(e)}", exc_info=True)

@bot.on_message(~filters.command("start"))
async def handle_new_post(client, message):
    """Обработка входящих сообщений от user_bot"""
    try:
        user_id = message.from_user.id
        logger.info(f"Received message from user {user_id}")
        
        # Обработка сообщений от юзер-бота
        if user_id == user_bot_id:
            # Создаем кнопки для каждого целевого канала
            buttons = [
                [InlineKeyboardButton("📢 Выложить во все каналы", callback_data=f"approve_all_{message.id}")]
            ]
            
            for channel in target_channels:
                channel = channel.strip()
                if channel:
                    buttons.append([
                        InlineKeyboardButton(f"Выложить в {channel}", callback_data=f"approve_{message.id}_{channel}")
                    ])
            
            # Добавляем кнопку отклонения
            buttons.append([InlineKeyboardButton("❌ Не выкладывать", callback_data=f"reject_{message.id}")])
            
            keyboard = InlineKeyboardMarkup(buttons)

            # Отправляем сообщение всем админам
            for admin_id in admin_ids:
                try:
                    logger.info(f"Sending notification to admin {admin_id}")
                    
                    # Проверяем тип сообщения и добавляем соответствующее описание
                    message_type = "Новый пост"
                    if message.voice:
                        message_type = "Новое голосовое сообщение"
                    elif message.video_note:
                        message_type = "Новое видеосообщение"
                    
                    # Получаем информацию об источнике из метаданных
                    source_info = getattr(message, '_source_info', '')
                    notification_text = f"⬆️ {message_type} для публикации\nВыберите действие:"
                    
                    # Пересылаем оригинальное сообщение
                    forwarded = await message.forward(admin_id)
                    
                    # Отправляем уведомление с кнопками
                    notification = await bot.send_message(
                        chat_id=admin_id,
                        text=notification_text,
                        reply_to_message_id=forwarded.id,
                        reply_markup=keyboard
                    )
                    
                    # Сохраняем информацию о посте
                    if str(message.id) not in pending_posts:
                        pending_posts[str(message.id)] = {
                            'original_message': message,
                            'admin_messages': {}
                        }
                    
                    pending_posts[str(message.id)]['admin_messages'][admin_id] = {
                        'notification': notification,
                        'forwarded': forwarded
                    }
                    
                    logger.info(f"Successfully sent notification to admin {admin_id}")
                except Exception as e:
                    logger.error(f"Error sending notification to admin {admin_id}: {str(e)}", exc_info=True)
        else:
            logger.info(f"Message from non-user-bot {user_id}, ignoring")
            
    except Exception as e:
        logger.error(f"Error in handle_new_post: {str(e)}", exc_info=True)

@bot.on_callback_query()
async def handle_callback(client, callback_query: CallbackQuery):
    """Обработка нажатий на инлайн-кнопки"""
    try:
        # Проверяем, является ли пользователь админом
        if callback_query.from_user.id not in admin_ids:
            await callback_query.answer("У вас нет прав для выполнения этого действия", show_alert=True)
            return

        data_parts = callback_query.data.split('_')
        action = data_parts[0]
        
        if action == "approve" and data_parts[1] == "all":
            message_id = data_parts[2]
        else:
            message_id = data_parts[1]
            target_channel = data_parts[2] if len(data_parts) > 2 else None
        
        post_info = pending_posts.get(message_id)
        
        if not post_info:
            await callback_query.answer("Это сообщение больше не доступно", show_alert=True)
            return

        if action == "approve":
            try:
                original_message = post_info['original_message']
                message_type = "пост"
                
                if original_message.voice:
                    message_type = "голосовое сообщение"
                elif original_message.video_note:
                    message_type = "видеосообщение"
                
                if data_parts[1] == "all":
                    # Публикуем во все каналы
                    successful_channels = []
                    failed_channels = []
                    
                    for channel in target_channels:
                        channel = channel.strip()
                        if not channel:
                            continue
                            
                        try:
                            channel_post = await original_message.copy(channel)
                            if channel_post:
                                successful_channels.append(channel)
                                logger.info(f"Successfully published {message_type} to channel {channel}")
                            else:
                                failed_channels.append(channel)
                                logger.error(f"Failed to publish {message_type} to channel {channel}")
                        except Exception as e:
                            failed_channels.append(channel)
                            logger.error(f"Error publishing to channel {channel}: {e}")
                    
                    # Формируем сообщение о результатах
                    result_message = f"✅ {message_type.capitalize()} опубликован(о) в каналы:\n"
                    if successful_channels:
                        result_message += "\n".join([f"• {channel}" for channel in successful_channels])
                    else:
                        result_message += "❌ Не удалось опубликовать ни в один канал"
                    
                    if failed_channels:
                        result_message += f"\n\n❌ Не удалось опубликовать в каналы:\n"
                        result_message += "\n".join([f"• {channel}" for channel in failed_channels])
                    
                    # Обновляем сообщения у всех админов
                    for admin_id, messages in post_info['admin_messages'].items():
                        try:
                            await messages['notification'].edit_text(result_message)
                        except Exception as e:
                            logger.error(f"Error updating admin {admin_id} message: {str(e)}")
                    
                    await callback_query.answer(
                        "Публикация во все каналы завершена", 
                        show_alert=True
                    )
                    
                    # Удаляем информацию о посте только если есть успешные публикации
                    if successful_channels:
                        del pending_posts[message_id]
                        
                else:
                    # Публикуем в один канал
                    logger.info(f"Attempting to publish message to channel {target_channel}")
                    channel_post = await original_message.copy(target_channel)
                    
                    if channel_post:
                        logger.info(f"Successfully published {message_type} to channel {target_channel}")
                        
                        # Обновляем сообщения у всех админов
                        for admin_id, messages in post_info['admin_messages'].items():
                            try:
                                await messages['notification'].edit_text(
                                    f"✅ {message_type.capitalize()} успешно опубликован(о) в канал {target_channel}"
                                )
                            except Exception as e:
                                logger.error(f"Error updating admin {admin_id} message: {str(e)}")
                        
                        await callback_query.answer(
                            f"{message_type.capitalize()} успешно опубликован(о) в канал {target_channel}", 
                            show_alert=True
                        )
                        
                        # Удаляем информацию о посте после успешной публикации
                        del pending_posts[message_id]
                    else:
                        raise Exception(f"Не удалось опубликовать {message_type} в канал {target_channel}")
                    
            except Exception as e:
                error_msg = str(e)
                logger.error(f"Error in approve action: {error_msg}", exc_info=True)
                await callback_query.answer("Произошла ошибка при публикации", show_alert=True)
                await bot.send_message(
                    callback_query.from_user.id,
                    f"Ошибка при публикации: {error_msg}"
                )
                return

        elif action == "reject":
            original_message = post_info['original_message']
            message_type = "пост"
            
            if original_message.voice:
                message_type = "голосовое сообщение"
            elif original_message.video_note:
                message_type = "видеосообщение"
                
            # Обновляем сообщения у всех админов
            for admin_id, messages in post_info['admin_messages'].items():
                try:
                    await messages['notification'].edit_text(f"❌ {message_type.capitalize()} был(о) отклонен(о)")
                except Exception as e:
                    logger.error(f"Error updating admin {admin_id} message: {str(e)}")
            
            await callback_query.answer(f"{message_type.capitalize()} отклонен(о)", show_alert=True)
            
            # Удаляем информацию о посте
            del pending_posts[message_id]
        
    except Exception as e:
        logger.error(f"Error in handle_callback: {str(e)}", exc_info=True)
        await callback_query.answer("Произошла ошибка при обработке действия", show_alert=True)
        await bot.send_message(
            callback_query.from_user.id,
            f"Произошла ошибка: {str(e)}"
        )

def main():
    try:
        logger.info("=== Starting Notification Bot ===")
        logger.info("Press Ctrl+C to stop the bot")
        bot.run()
    except Exception as e:
        logger.error(f"Error starting bot: {str(e)}", exc_info=True)

if __name__ == '__main__':
    main()