from aiogram import Bot
from aiogram.types import BufferedInputFile
from faststream.rabbit import RabbitBroker
from pdfnik_contracts.pdf_content import BotDocument

from main_app.core.logger import logger
from main_app.infrastructure.storage import LocalFileStorage


def register_pdf_send_consumer(
        broker: RabbitBroker,
        bot: Bot,
        storage: LocalFileStorage,
) -> None:
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
