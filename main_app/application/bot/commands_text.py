# /home/dmitriy/PycharmProjects/Telegram-Bot/main_app/application/bot/commands_text.py
# repo: PDFnik-TelegramBot

START_TEXT = """
Hi! 👋

I collect your messages — text and photos — and turn them into a single PDF file.
I can also transcribe voice messages and YouTube videos.

Send content in any order.
When you're done — type /done.

Ready to help! 📄✨
"""

HELP_TEXT = """
📘 How to use PDFnik

I collect multiple messages and combine them into one PDF.

How it works:
1) Send text or images.
2) When done — type /done.
3) Get your PDF file.

Supported content:
• ✍️ Text messages
• 🖼️ Photos and screenshots
• 🎤 Voice messages → transcript
• 🎬 YouTube links → transcript + PDF

Commands:
/done   — build PDF right now
/cancel — discard current session
/help   — this guide
"""

CANCEL_EMPTY_TEXT = "✅ Session is already empty. Send content whenever you're ready!"

CANCEL_WITH_CONTENT_TEXT = (
    "🗑 Session cleared.\n\n"
    "Collected: {photo_count} photos, {text_count} text messages.\n"
    "All data removed — start fresh whenever you're ready."
)
