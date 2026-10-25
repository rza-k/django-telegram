# Django Telegram Bot

The fastest way to build a production-ready Telegram bot on Django.

---
## 🚀 Overview

# django-telegram
A typed Telegram Bot API client for Django.

`django-telegram` gives you every Telegram Bot API method as a plain Python method, and every Telegram type as a [Pydantic](https://docs.pydantic.dev/) model. You call a method, and you get a typed object back instead of a raw dictionary.

## What it does

- **All Bot API methods in one place.** Sending a message, answering a callback query, setting a webhook, and the rest of the API are available as methods on a single `Telegram` client.
- **All Telegram types included.** Updates, messages, users, chats, keyboards, and every other object defined by Telegram are Pydantic models, so you get validation and editor autocompletion.
- **Responses are objects.** Access `message.chat.id` or `update.callback_query.data` directly instead of digging through nested dictionaries.
- **Built for Django.** Configuration is read from your Django settings, and the library fits into your own views and URLs.
- **Synchronous.** No event loop or async runtime required.

---

## ⚙️ Installation

```bash
pip install django-telegram-bot-api
```

or with `uv`:

```bash
uv add django-telegram-bot-api
```

---

## ⚡ Quick Start

Here's the minimal setup to get a bot responding to `/start`.

### 1. Add the app and configure settings
### 1. Configure settings

Add a `TELEGRAM` dictionary to your Django settings. You do **not** need to add `django_telegram` to `INSTALLED_APPS`.

```python
# settings.py
TELEGRAM = {
    "BOT_TOKEN": "your-telegram-bot-token",
    "TM_WEBHOOK_URL": "https://api.telegram.org",
}
```

| Key | Required | Default | Description |
|---|---|---|---|
| `BOT_TOKEN` | Yes | n/a | Your bot token from [@BotFather](https://t.me/BotFather). |
| `TM_WEBHOOK_URL` | Yes | n/a | Base URL of the Telegram Bot API. Use `https://api.telegram.org`, or the address of your own local Bot API server. |
| `PROXY_SOCKS` | No | `""` | SOCKS proxy for outgoing requests, e.g. `127.0.0.1:1080`. |

If a required key is missing, `ImproperlyConfigured` is raised and the message tells you which one.

> [!TIP]
> Keep secrets out of your repository by reading them from environment variables:
>
> ```python
> import os
>
> TELEGRAM = {
>     "BOT_TOKEN": os.environ["TELEGRAM_BOT_TOKEN"],
>     "TM_WEBHOOK_URL": os.getenv("TELEGRAM_API_URL", "https://api.telegram.org"),
> }
> ```

Once the settings are in place, the client needs no arguments:

```python
from django_telegram import Telegram

bot = Telegram()  # reads BOT_TOKEN and TM_WEBHOOK_URL from settings
```

You can still pass a token explicitly, for example in tests or when running several bots:

```python
bot = Telegram(token="123456:ABC-DEF")
```

### 2. Add the webhook URL

Create a Django app for your bot (here it is called `bot`):

```bash
python manage.py startapp bot
```

Add a view that receives Telegram's updates and passes them to the dispatcher:

```python
# bot/views.py
import logging

from django_telegram import Dispatcher, Update
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .handlers import command_handlers  # noqa: F401  (registers your handler classes)

logger = logging.getLogger(__name__)


class TelegramWebhookView(APIView):
    authentication_classes = []
    permission_classes = []

    def post(self, request: Request) -> Response:
        try:
            update = Update(**request.data)
            Dispatcher(update).dispatch()
        except Exception:
            logger.exception("Error while processing Telegram update")

        # Always answer 200, otherwise Telegram keeps retrying the same update.
        return Response({"ok": True}, status=status.HTTP_200_OK)
```

Add the route to the app:

```python
# bot/urls.py
from django.urls import path

from .views import TelegramWebhookView

app_name = "bot"

urlpatterns = [
    path("webhook/", TelegramWebhookView.as_view(), name="webhook"),
]
```

Include it in your project URLs:

```python
# config/urls.py
from django.urls import include, path

urlpatterns = [
    path("bot/", include("bot.urls", namespace="bot")),
]
```

Your webhook is now served at `https://your-domain.com/bot/webhook/`.

> [!IMPORTANT]
> **Every app that defines handlers must import them in its view module.**
>
> The dispatcher finds your handlers by looking at the subclasses of `CommandHandler`, `MessageHandler`, and the other base classes. A class only exists once the file that defines it has been imported, so if the file is never imported, the dispatcher sees nothing and the update is silently ignored.
>
> Importing your handlers at the top of the webhook view (`from .handlers import command_handlers`) guarantees they are loaded as soon as Django loads your URLs, with no extra registration step.

### 3. Write your handlers

Create a `handlers` package inside your app and add one file per handler type:

```text
bot/
├── __init__.py
├── urls.py
├── views.py
└── handlers/
    ├── __init__.py
    └── command_handlers.py
```

Handlers inherit from one of the base classes and implement `handle(self, update)`. Commands (any message that starts with `/`) go to `CommandHandler`:

```python
# bot/handlers/command_handlers.py
from django.conf import settings
from django_telegram import CommandHandler, Telegram, Update
from django_telegram.telegram_models import KeyboardButton, ReplyKeyboardMarkup

bot = Telegram(token=settings.TELEGRAM["BOT_TOKEN"])


class Commands(CommandHandler):

    def handle(self, update: Update):
        chat_id = update.message.chat.id
        text = update.message.text

        if text.startswith("/start"):
            bot.send_message(chat_id=chat_id, text="hello 3>")

        elif text.startswith("/products"):
            bot.send_message(
                chat_id=chat_id,
                text="choices one !",
                reply_markup=ReplyKeyboardMarkup(
                    keyboard=[
                        [
                            KeyboardButton(text="product 1"),
                            KeyboardButton(text="product 2"),
                        ],
                        [
                            KeyboardButton(text="product 3"),
                            KeyboardButton(text="product 4"),
                        ],
                    ],
                    resize_keyboard=True,
                ),
            )
```

The dispatcher does not look at the command name. Every command is delivered to your `CommandHandler` subclass, and you decide what to do for `/start`, `/products`, and so on inside `handle()`.

When your app grows to several handler files, import them all from the package so the view only needs one import:

```python
# bot/__init__.py
from . import command_handlers  # noqa: F401
# from . import message_handlers  # noqa: F401
# from . import callback_query_handlers  # noqa: F401
```

### 4. Handle plain messages

Any message that is not a command (no leading `/`) and has no media goes to `MessageHandler`. Create a new file next to your command handlers:

```text
bot/handlers/
├── __init__.py
├── command_handlers.py
└── message_handlers.py      ← new
```

In this example, when the user sends `product 1` (the text of the reply keyboard button from the previous step), the bot answers with a message that has an inline button attached:

```python
# bot/handlers/message_handlers.py
from django.conf import settings
from django_telegram import MessageHandler, Telegram, Update
from django_telegram.telegram_models import InlineKeyboardButton, InlineKeyboardMarkup

bot = Telegram(token=settings.TELEGRAM["BOT_TOKEN"])


class MyMessageHandler(MessageHandler):

    def handle(self, update: Update):
        chat_id = update.message.chat.id
        text = update.message.text

        if text == "product 1":
            bot.send_message(
                chat_id=chat_id,
                text="product 1",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(text="product 1", callback_data="pro1"),
                        ],
                    ],
                ),
            )
```

The `callback_data` value (`"pro1"`) is what Telegram sends back to your bot when the user presses the button. You will handle it in the next step.

Now register the new file. A handler class only exists once its file has been imported, so add it to `handlers/__init__.py`:

```python
# bot/handlers/__init__.py
from . import (
    command_handlers,  # noqa: F401
    message_handlers,  # noqa: F401
)
```

Send `product 1` to your bot: it replies with a message and an inline button.

### 5. Handle inline button presses (callback queries)

When the user presses an inline button, Telegram sends a callback query instead of a message. These go to `CallbackQueryHandler`. Create another file:

```text
bot/handlers/
├── __init__.py
├── callback_query_handlers.py   ← new
├── command_handlers.py
└── message_handlers.py
```

```python
# bot/handlers/callback_query_handlers.py
from django.conf import settings
from django_telegram import CallbackQueryHandler, Telegram, Update

bot = Telegram(token=settings.TELEGRAM["BOT_TOKEN"])


class MyCallbackQueryHandler(CallbackQueryHandler):

    def handle(self, update: Update):
        callback_data = update.callback_query.data

        if callback_data == "pro1":
            bot.answer_callback_query(
                callback_query_id=update.callback_query.id,
                text="hi this is product 1",
                show_alert=True,
            )
```

`answer_callback_query` is required for every callback query: it stops the loading spinner on the button. With `show_alert=True` the text is shown as a pop-up alert instead of a small toast.

Register the file the same way:

```python
# bot/handlers/__init__.py
from . import (
    callback_query_handlers,  # noqa: F401
    command_handlers,  # noqa: F401
    message_handlers,  # noqa: F401
)
```

### Summary

| User action | Update type | Base class | Example file |
|---|---|---|---|
| Sends `/start` | command | `CommandHandler` | `command_handlers.py` |
| Sends `product 1` | text message | `MessageHandler` | `message_handlers.py` |
| Presses an inline button | callback query | `CallbackQueryHandler` | `callback_query_handlers.py` |

Each new handler file needs one line in `handlers/__init__.py`. Your webhook view only needs `from . import handlers`.