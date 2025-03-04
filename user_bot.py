from pyrogram import Client, filters
from dotenv import load_dotenv
import os
import logging
import re

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Загрузка переменных окружения
load_dotenv()

# Параметры подключения
api_id = os.getenv('API_ID')
api_hash = os.getenv('API_HASH')
phone_number = os.getenv('PHONE_NUMBER')
source_channel_ids = [int(id.strip()) for id in os.getenv('SOURCE_CHANNEL_IDS', '').split(',')]
admin_bot_id = int(os.getenv('ADMIN_BOT_ID'))

# Создание клиента
app = Client(
    "user_bot", 
    api_id=api_id, 
    api_hash=api_hash,
    phone_number=phone_number
)

def check_copy_restrictions(message):
    """
    Проверяет наличие ограничений на копирование в сообщении.
    
    Args:
        message: Объект сообщения Pyrogram
    
    Returns:
        bool: True, если копирование запрещено, False в противном случае
    """
    # Расширенный список ключевых слов, указывающих на запрет копирования
    copy_restriction_keywords = [
        'не копировать', 
        'copyright', 
        'all rights reserved', 
        '©', 
        'watermark', 
        'водяной знак',
        'запрещено копирование',
        'копирование запрещено',
        'do not copy',
        'no repost',
        'не репостить',
        'без репоста'
    ]
    
    # Проверка текста сообщения
    text_to_check = message.text or message.caption or ''
    text_lower = text_to_check.lower()
    
    # Проверяем каждое ключевое слово
    for keyword in copy_restriction_keywords:
        if keyword in text_lower:
            logger.warning(f"Копирование запрещено по ключевому слову: {keyword}")
            return True
    
    # Дополнительные проверки
    try:
        # Проверка наличия водяных знаков в медиафайлах
        if message.photo or message.video:
            if message.caption and any(mark in message.caption.lower() for mark in ['watermark', 'водяной знак']):
                logger.warning("Обнаружен водяной знак в медиафайле")
                return True
        
        # Проверка прав на репост через теги
        if message.entities:
            for entity in message.entities:
                if entity.type in ['hashtag', 'cashtag']:
                    hashtag = text_lower[entity.offset:entity.offset+entity.length].lower()
                    if any(tag in hashtag for tag in ['#nocopy', '#неrepost', '#запретпоста']):
                        logger.warning(f"Обнаружен запрещающий хэштег: {hashtag}")
                        return True
    except Exception as e:
        logger.error(f"Ошибка при проверке ограничений: {e}")
    
    return False

@app.on_message(filters.chat(source_channel_ids))
async def forward_new_post(client, message):
    try:
        # Проверяем наличие всех необходимых данных
        if not all([source_channel_ids, admin_bot_id]):
            logger.error("Source channels or admin bot not configured")
            return

        # Добавляем информацию об исходном канале
        source_channel_info = f"Channel ID: {message.chat.id}"
        if message.chat.username:
            source_channel_info += f" (@{message.chat.username})"
        if message.chat.title:
            source_channel_info += f" - {message.chat.title}"

        # Проверяем наличие ограничений на копирование
        if check_copy_restrictions(message):
            logger.warning(f"Copying restricted for message {message.id} from {source_channel_info}")
            # Воссоздаем сообщение вручную
            try:
                # Добавляем информацию об исходном канале к caption или тексту
                if message.text:
                    text = message.text
                    await client.send_message(admin_bot_id, text)
                    await client.send_message(admin_bot_id, f"💬 Source: {source_channel_info}")
                    logger.info(f"Manually forwarded text message {message.id} to admin bot")
                elif message.photo:
                    file = await client.download_media(message.photo.file_id)
                    caption = message.caption or ''
                    await client.send_photo(admin_bot_id, file, caption=caption)
                    await client.send_message(admin_bot_id, f"💬 Source: {source_channel_info}")
                    logger.info(f"Manually forwarded photo message {message.id} to admin bot")
                    os.remove(file)
                elif message.video:
                    file = await client.download_media(message.video.file_id)
                    caption = message.caption or ''
                    await client.send_video(admin_bot_id, file, caption=caption)
                    await client.send_message(admin_bot_id, f"💬 Source: {source_channel_info}")
                    logger.info(f"Manually forwarded video message {message.id} to admin bot")
                    os.remove(file)
                elif message.document:
                    file = await client.download_media(message.document.file_id)
                    caption = message.caption or ''
                    await client.send_document(admin_bot_id, file, caption=caption)
                    await client.send_message(admin_bot_id, f"💬 Source: {source_channel_info}")
                    logger.info(f"Manually forwarded document message {message.id} to admin bot")
                    os.remove(file)
                elif message.voice:
                    file = await client.download_media(message.voice.file_id)
                    caption = message.caption or ''
                    await client.send_voice(admin_bot_id, file, caption=caption)
                    await client.send_message(admin_bot_id, f"💬 Source: {source_channel_info}")
                    logger.info(f"Manually forwarded voice message {message.id} to admin bot")
                    os.remove(file)
                elif message.video_note:
                    file = await client.download_media(message.video_note.file_id)
                    # Для video note нельзя добавить caption, отправим отдельным сообщением
                    await client.send_video_note(admin_bot_id, file)
                    await client.send_message(admin_bot_id, f"💬 Source: {source_channel_info}")
                    logger.info(f"Manually forwarded video note {message.id} to admin bot")
                    os.remove(file)
                else:
                    logger.warning(f"Unsupported message type for manual forwarding: {message}")
            except Exception as e:
                logger.error(f"Error manually forwarding restricted message {message.id}: {e}")
            return

        try:
            # Пересылаем сообщение админ-боту
            forwarded = await client.forward_messages(
                chat_id=admin_bot_id,
                from_chat_id=message.chat.id,
                message_ids=message.id
            )
            # Сохраняем информацию об источнике в метаданных сообщения
            if not hasattr(forwarded, '_client'):
                forwarded._client = client
            if not hasattr(forwarded, '_source_info'):
                forwarded._source_info = source_channel_info
            logger.info(f"Forwarded message {message.id} from {source_channel_info} to admin bot")
        except Exception as e:
            logger.warning(f"Error forwarding message {message.id}, trying to manually forward: {e}")
            # Если пересылка не удалась, воссоздаем сообщение вручную
            try:
                if message.text:
                    text = message.text
                    sent_msg = await client.send_message(admin_bot_id, text)
                    if not hasattr(sent_msg, '_source_info'):
                        sent_msg._source_info = source_channel_info
                    logger.info(f"Manually forwarded text message {message.id} to admin bot")
                elif message.photo:
                    file = await client.download_media(message.photo.file_id)
                    caption = message.caption or ''
                    sent_msg = await client.send_photo(admin_bot_id, file, caption=caption)
                    if not hasattr(sent_msg, '_source_info'):
                        sent_msg._source_info = source_channel_info
                    logger.info(f"Manually forwarded photo message {message.id} to admin bot")
                    os.remove(file)
                elif message.video:
                    file = await client.download_media(message.video.file_id)
                    caption = message.caption or ''
                    sent_msg = await client.send_video(admin_bot_id, file, caption=caption)
                    if not hasattr(sent_msg, '_source_info'):
                        sent_msg._source_info = source_channel_info
                    logger.info(f"Manually forwarded video message {message.id} to admin bot")
                    os.remove(file)
                elif message.document:
                    file = await client.download_media(message.document.file_id)
                    caption = message.caption or ''
                    sent_msg = await client.send_document(admin_bot_id, file, caption=caption)
                    if not hasattr(sent_msg, '_source_info'):
                        sent_msg._source_info = source_channel_info
                    logger.info(f"Manually forwarded document message {message.id} to admin bot")
                    os.remove(file)
                elif message.voice:
                    file = await client.download_media(message.voice.file_id)
                    caption = message.caption or ''
                    sent_msg = await client.send_voice(admin_bot_id, file, caption=caption)
                    if not hasattr(sent_msg, '_source_info'):
                        sent_msg._source_info = source_channel_info
                    logger.info(f"Manually forwarded voice message {message.id} to admin bot")
                    os.remove(file)
                elif message.video_note:
                    file = await client.download_media(message.video_note.file_id)
                    # Для video note нельзя добавить caption, отправим отдельным сообщением
                    sent_msg = await client.send_video_note(admin_bot_id, file)
                    if not hasattr(sent_msg, '_source_info'):
                        sent_msg._source_info = source_channel_info
                    logger.info(f"Manually forwarded video note {message.id} to admin bot")
                    os.remove(file)
                else:
                    logger.warning(f"Unsupported message type for manual forwarding: {message}")
            except Exception as e:
                logger.error(f"Error manually forwarding message {message.id}: {e}")
    except Exception as e:
        logger.error(f"Unexpected error processing message {message.id}: {e}")

def main():
    try:
        logger.info("Starting User Bot...")
        app.run()
    except Exception as e:
        logger.error(f"Error starting bot: {e}")

if __name__ == '__main__':
    main() 