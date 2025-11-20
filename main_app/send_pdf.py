import base64

from aiogram.types import BufferedInputFile

from main_app.main_constants import broker, bot


@broker.subscriber("bot_documents")
async def send_pdf(data: dict):
    chat_id = data["chat_id"]
    filename = data["filename"]
    pdf_b64 = data["pdf_b64"]

    pdf_bytes = base64.b64decode(pdf_b64)
    doc = BufferedInputFile(pdf_bytes, filename)

    await bot.send_document(chat_id, doc)
