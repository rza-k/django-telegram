# django-telegram-bot-api

A typed Telegram Bot API client for Django.

Every Bot API method is a plain Python method, every Telegram type is a [Pydantic](https://docs.pydantic.dev/) model, and responses come back as typed objects instead of raw dictionaries.

```bash
pip install django-telegram-bot-api
```

```python
from django_telegram import Telegram

bot = Telegram()  # reads BOT_TOKEN from your Django settings
message = bot.send_message(chat_id=123456, text="Hello!")
print(message.chat.id)
```

> The package is installed as `django-telegram-bot-api` and imported as `django_telegram`.

## Features

- **Every Bot API method** on a single `Telegram` client: send messages, answer callback queries, set webhooks, and the rest of the API.
- **Every Telegram type** as a Pydantic model, with validation and editor autocompletion.
- **Typed responses.** Use `message.chat.id` or `update.callback_query.data` instead of digging through dictionaries.
- **A small dispatcher.** Write one class per kind of update (commands, messages, button presses, inline queries) and the library routes incoming updates to it.
- **Built for Django.** Configuration comes from your Django settings, and you keep your own views and URLs.
- **Synchronous.** No event loop or async runtime required.

## Contents

- [Installation](#installation)
- [Quick start](#quick-start)
- [Handling updates](#handling-updates)
- [More examples](#more-examples)
- [Calling the API directly](#calling-the-api-directly)
- [Configuration reference](#configuration-reference)

## Installation

```bash
pip install django-telegram-bot-api
```

or with [uv](https://docs.astral.sh/uv/):

```bash
uv add django-telegram-bot-api
```

You do **not** need to add `django_telegram` to `INSTALLED_APPS`.

Requirements are listed in `pyproject.toml` (Python 3.13+ at the time of writing).

## Quick start

This walks you from zero to a bot that answers `/start`. It has five steps:

1. Configure your settings
2. Create the bot client
3. Write a handler
4. Add the webhook view and URL
5. Tell Telegram where your webhook is

### 1. Configure your settings

Create a bot with [@BotFather](https://t.me/BotFather) to get a token, then add a `TELEGRAM` dictionary to your Django settings:

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

### 2. Create the bot client

Create a Django app for your bot (this guide calls it `bot`):

```bash
python manage.py startapp bot
```

Add it to `INSTALLED_APPS`, then create one shared client that all your handlers will import:

```python
# bot/client.py
from django_telegram import Telegram

bot = Telegram()  # reads BOT_TOKEN and TM_WEBHOOK_URL from settings
```

> [!NOTE]
> You can still pass a token explicitly, for example in tests or when running several bots: `Telegram(token="123456:ABC-DEF")`.

Your app will end up looking like this:

```text
bot/
├── __init__.py
├── client.py
├── urls.py
├── views.py
└── handlers/
    ├── __init__.py
    └── command_handlers.py
```

### 3. Write a handler

Handlers are classes. You inherit from one base class per kind of update and implement `handle(self, update)`. Commands (any message that starts with `/`) go to `CommandHandler`:

```python
# bot/handlers/command_handlers.py
from django_telegram import CommandHandler, Update

from bot.client import bot


class Commands(CommandHandler):

    def handle(self, update: Update):
        chat_id = update.message.chat.id
        text = update.message.text

        if text.startswith("/start"):
            bot.send_message(chat_id=chat_id, text="Hello!")
```

Now register the file by importing it in your app's `__init__.py`:

```python
# bot/__init__.py
from .handlers import command_handlers  # noqa: F401
```

> [!IMPORTANT]
> **A handler only exists once its file has been imported.**
>
> The dispatcher finds your handlers by looking at the subclasses of `CommandHandler`, `MessageHandler`, and the other base classes. If the file that defines a class is never imported, the dispatcher sees nothing and the update is silently ignored.
>
> Django loads `bot/__init__.py` when it starts (because `bot` is in `INSTALLED_APPS`), so your handlers are registered before the first update arrives. Each time you add a handler file, add it to the import in `bot/__init__.py`.

> [!NOTE]
> `bot/__init__.py` runs before Django's app registry is ready. If a handler file imports your Django models at the top, startup fails with `AppRegistryNotReady`. Import the models inside `handle()` instead.

### 4. Add the webhook view and URL

The view receives Telegram's updates and passes them to the dispatcher:

```python
# bot/views.py
import logging

from django_telegram import Dispatcher, Update
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

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

Add the route to the app, then include the app in your project URLs:

```python
# bot/urls.py
from django.urls import path

from .views import TelegramWebhookView

app_name = "bot"

urlpatterns = [
    path("webhook/", TelegramWebhookView.as_view(), name="webhook"),
]
```

```python
# config/urls.py
from django.urls import include, path

urlpatterns = [
    path("bot/", include("bot.urls", namespace="bot")),
]
```

Your webhook is now served at `https://your-domain.com/bot/webhook/`.

> [!NOTE]
> The view uses Django REST framework only because it is convenient. The library itself does not depend on it. Any Django view that builds an `Update` from the request body and calls `Dispatcher(update).dispatch()` works. `authentication_classes = []` and `permission_classes = []` make sure your project's default DRF permissions do not reject Telegram's requests.

### 5. Tell Telegram where your webhook is

Telegram needs to know which URL to send updates to. Register it once with a `curl` request to the Bot API (replace `<BOT_TOKEN>` with your bot token and the URL with your own):

```bash
curl -X POST "https://api.telegram.org/bot<BOT_TOKEN>/setWebhook" \
  -d "url=https://your-domain.com/bot/webhook/"
```

If it worked, Telegram answers:

```json
{"ok": true, "result": true, "description": "Webhook was set"}
```

To check the current webhook at any time:

```bash
curl "https://api.telegram.org/bot<BOT_TOKEN>/getWebhookInfo"
```

If you use your own local Bot API server, replace `https://api.telegram.org` with its address (the same value as `TM_WEBHOOK_URL` in your settings).

Telegram only delivers webhooks over **HTTPS** to a public address. While developing locally, expose your server with a tunnel such as [ngrok](https://ngrok.com/) or [cloudflared](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/) and use the tunnel URL.

Now send `/start` to your bot. It should answer `Hello!`.
## Handling updates

`Dispatcher` looks at an incoming update, decides what kind it is, and calls `handle(update)` on your subclass of the matching base class.

| What the user does | Base class to inherit from |
|---|---|
| Sends a command such as `/start` | `CommandHandler` |
| Sends anything else (text, photo, document, voice, ...) | `MessageHandler` |
| Presses an inline button | `CallbackQueryHandler` |
| Types `@yourbot something` in any chat | `InlineQueryHandler` |
| Picks one of your inline results | `ChosenInlineResultHandler` |

Things to know:

- **The dispatcher does not look at the command name or the text.** Every command goes to your `CommandHandler` subclass, and you decide what to do for `/start`, `/help`, and so on inside `handle()`.
- **One class per kind is the intended setup.** If you define several subclasses of the same base class, all of them are called, in the order they were defined.
- **Updates with no matching handler are ignored.** If you do not write a `CallbackQueryHandler`, button presses are simply dropped.
- **Handlers run inside the web request.** Hand slow work (long downloads, heavy computation) to a task queue such as Celery.

The next section shows one example of each.

## More examples

All examples assume the shared client from step 2 (`from bot.client import bot`) and the layout below. Remember to import each new file in `bot/__init__.py`.

```text
bot/handlers/
├── __init__.py              (empty)
├── command_handlers.py
├── message_handlers.py
└── callback_query_handlers.py
```

```python
# bot/__init__.py
from .handlers import (
    callback_query_handlers,  # noqa: F401
    command_handlers,  # noqa: F401
    message_handlers,  # noqa: F401
)
```

### Commands: several commands and a reply keyboard

```python
# bot/handlers/command_handlers.py
from django_telegram import CommandHandler, Update
from django_telegram.telegram_models import KeyboardButton, ReplyKeyboardMarkup

from bot.client import bot


class Commands(CommandHandler):

    def handle(self, update: Update):
        chat_id = update.message.chat.id
        text = update.message.text

        if text.startswith("/start"):
            bot.send_message(chat_id=chat_id, text="Hello!")

        elif text.startswith("/help"):
            bot.send_message(
                chat_id=chat_id,
                text="Send /products to see what we sell.",
            )

        elif text.startswith("/products"):
            bot.send_message(
                chat_id=chat_id,
                text="Choose one:",
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

        else:
            bot.send_message(chat_id=chat_id, text="Unknown command.")
```

### Commands: reading arguments

Telegram sends everything after the command in the same text, so `/greet Reza` arrives as `"/greet Reza"`:

```python
class Commands(CommandHandler):

    def handle(self, update: Update):
        chat_id = update.message.chat.id
        parts = update.message.text.split()

        command = parts[0]   # "/greet"
        args = parts[1:]     # ["Reza"]

        if command == "/greet":
            name = args[0] if args else "stranger"
            bot.send_message(chat_id=chat_id, text=f"Hello, {name}!")
```

> [!TIP]
> In groups, Telegram may send commands as `/greet@yourbot`. If your bot is used in groups, strip the suffix with `command.split("@")[0]`.

### Messages: reply keyboard text and an inline button

When the user presses a **reply keyboard** button, Telegram sends its text as a normal message, so you handle it in a `MessageHandler`. Here the bot answers with a message that has an **inline button** attached:

```python
# bot/handlers/message_handlers.py
from django_telegram import MessageHandler, Update
from django_telegram.telegram_models import InlineKeyboardButton, InlineKeyboardMarkup

from bot.client import bot


class Messages(MessageHandler):

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
                            InlineKeyboardButton(text="Details", callback_data="pro1"),
                            InlineKeyboardButton(text="Buy", callback_data="buy:1"),
                        ],
                        [
                            InlineKeyboardButton(text="Open website", url="https://example.com"),
                        ],
                    ],
                ),
            )

        else:
            bot.send_message(chat_id=chat_id, text=f"You said: {text}")
```

A button either has a `callback_data` (Telegram sends it back to your bot when pressed) or a `url` (Telegram opens the link and tells your bot nothing).

### Messages: photos and documents

There is no separate handler for media. Photos, documents, voice messages, and the like arrive in the same `MessageHandler`, with `message.text` empty and the matching field filled in. Check which one is present inside `handle()`:

```python
# bot/handlers/message_handlers.py
from django_telegram import MessageHandler, Update

from bot.client import bot


class Messages(MessageHandler):

    def handle(self, update: Update):
        message = update.message
        chat_id = message.chat.id

        if message.photo:
            # Telegram sends several sizes; the last one is the largest.
            file_id = message.photo[-1].file_id
            bot.send_message(chat_id=chat_id, text=f"Nice photo! file_id: {file_id}")

        elif message.document:
            bot.send_message(
                chat_id=chat_id,
                text=f"Got your file: {message.document.file_name}",
            )

        elif message.voice:
            bot.send_message(chat_id=chat_id, text="Got your voice message.")

        else:
            bot.send_message(chat_id=chat_id, text=f"You said: {message.text}")
```

If your bot handles both text buttons and media, put all the branches in the same `handle()`, since there is one `MessageHandler` subclass.

### Callback queries: alerts, toasts, and editing the message

When the user presses an inline button, Telegram sends a callback query instead of a message:

```python
# bot/handlers/callback_query_handlers.py
from django_telegram import CallbackQueryHandler, Update

from bot.client import bot


class Callbacks(CallbackQueryHandler):

    def handle(self, update: Update):
        query = update.callback_query
        data = query.data

        if data == "pro1":
            # Pop-up alert with an OK button
            bot.answer_callback_query(
                callback_query_id=query.id,
                text="hi this is product 1",
                show_alert=True,
            )

        elif data.startswith("buy:"):
            product_id = data.split(":")[1]

            # Small toast at the top of the screen
            bot.answer_callback_query(
                callback_query_id=query.id,
                text=f"Product {product_id} added to your cart",
            )

            # Replace the text of the message that held the button
            bot.edit_message_text(
                chat_id=query.message.chat.id,
                message_id=query.message.message_id,
                text=f"Product {product_id} is in your cart.",
            )
```

> [!IMPORTANT]
> Always call `answer_callback_query` for every callback query, even with no text. It stops the loading spinner on the button.

Putting data in `callback_data` (`"buy:1"`) is the usual way to tell buttons apart. Telegram limits it to 64 bytes.

### Inline queries

When someone types `@yourbot something` in any chat, Telegram sends an inline query. Answer it with a list of results:

```python
# bot/handlers/inline_query_handlers.py
from django_telegram import InlineQueryHandler, Update

from bot.client import bot


class InlineQueries(InlineQueryHandler):

    def handle(self, update: Update):
        query = update.inline_query

        bot.answer_inline_query(
            inline_query_id=query.id,
            results=[
                {
                    "type": "article",
                    "id": "1",
                    "title": f"Search for {query.query}",
                    "input_message_content": {"message_text": query.query},
                },
            ],
        )
```

Inline mode must be enabled for your bot in [@BotFather](https://t.me/BotFather) (`/setinline`). Do not forget to import the file in `bot/__init__.py`.

## Calling the API directly

You do not need handlers to use the client. Anywhere in your Django project (a view, a management command, a Celery task, a signal), you can call the API and work with the typed response:

```python
from bot.client import bot

# Send a message and read the response
message = bot.send_message(chat_id=123456, text="Your order has shipped.")
print(message.message_id, message.chat.id, message.date)

# Send a message with formatting
bot.send_message(
    chat_id=123456,
    text="<b>Order #42</b> is on its way.",
    parse_mode="HTML",
)
```

Because the types are Pydantic models, you also get `message.model_dump()` and `message.model_dump_json()` for free.

A common use is notifying users from your own code, for example when an order changes status:

```python
# orders/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver

from bot.client import bot
from .models import Order


@receiver(post_save, sender=Order)
def notify_customer(sender, instance, **kwargs):
    if instance.status == "shipped":
        bot.send_message(
            chat_id=instance.customer.telegram_id,
            text=f"Order #{instance.pk} has shipped.",
        )
```

## Configuration reference

All settings live in the `TELEGRAM` dictionary in your Django settings.

| Key | Required | Default | Description |
|---|---|---|---|
| `BOT_TOKEN` | Yes | n/a | Bot token from [@BotFather](https://t.me/BotFather). |
| `TM_WEBHOOK_URL` | Yes | n/a | Base URL of the Telegram Bot API (`https://api.telegram.org` or your own local Bot API server). |
| `PROXY_SOCKS` | No | `""` | SOCKS proxy for outgoing requests, e.g. `127.0.0.1:1080`. |

Settings are read when the client is created, not when Django starts, and `override_settings` works as usual in your tests.