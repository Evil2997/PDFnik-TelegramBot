from pdfnik_contracts.pdf_content import BotDocument
from aiogram.types import BufferedInputFile
from main_app.core.constants import broker, bot, storage

@broker.subscriber("pdf.send")
async def pdf_consumer(data: dict):
    doc_model = BotDocument.model_validate(data)

    pdf_bytes = await storage.read_bytes(doc_model.storage_key)
    file = BufferedInputFile(pdf_bytes, doc_model.filename)

    await bot.send_document(doc_model.chat_id, file)
