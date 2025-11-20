from main_app.contracts import BotDocument
from aiogram.types import BufferedInputFile
from main_app.main_constants import broker, bot, storage

@broker.subscriber("bot_documents")
async def send_pdf(data: dict):
    doc_model = BotDocument.model_validate(data)

    pdf_bytes = await storage.read_bytes(doc_model.storage_key)
    file = BufferedInputFile(pdf_bytes, doc_model.filename)

    await bot.send_document(doc_model.chat_id, file)
