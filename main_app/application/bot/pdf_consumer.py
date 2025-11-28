from aiogram.types import BufferedInputFile
from pdfnik_contracts.pdf_content import BotDocument

from main_app.core.logger import logger
from main_app.infrastructure.bot_factory import bot
from main_app.infrastructure.rabbit_connector import broker
from main_app.infrastructure.storage import storage


@broker.subscriber("pdf.send")
async def pdf_consumer(data: dict):
    logger.info("Received PDF send task")
    try:
        doc_model = BotDocument.model_validate(data)
        pdf_bytes = await storage.read_bytes(doc_model.storage_key)
        file = BufferedInputFile(pdf_bytes, doc_model.filename)
        await bot.send_document(doc_model.chat_id, file)
        logger.info(f"PDF sent to chat {doc_model.chat_id}")
    except Exception as e:
        logger.error(f"Failed to send PDF: {e}")
