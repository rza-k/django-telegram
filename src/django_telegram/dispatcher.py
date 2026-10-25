from .handlers import (
    CallbackQueryHandler,
    ChosenInlineResultHandler,
    CommandHandler,
    InlineQueryHandler,
    MessageHandler,
)
from .telegram_models import Update


class Dispatcher:
    """
    Dispatcher routes an incoming Telegram update to the user's handler
    subclasses, based on the type of content in the update.

    Attributes:
        update (Update): The incoming update object from Telegram.

    Methods:
        dispatch():
            - command (text starts with '/')                    -> CommandHandler subclasses
            - regular message                                    -> MessageHandler subclasses
            - callback query                                     -> CallBackQueryHandler subclasses
            - inline query                                       -> InlineQueryHandler subclasses
            - chosen inline result                               -> ChosenInlineResultHandler subclasses
            - anything else                                      -> ignored
    """

    def __init__(self, update: Update | dict | str | bytes):
        if isinstance(update, Update):
            self.update = update
        elif isinstance(update, (str, bytes)):
            self.update = Update.model_validate_json(update)
        else:
            self.update = Update.model_validate(update)

    def dispatch(self):
        base = self._pick_base()
        if base is None:
            return

        for cls in base.__subclasses__():
            cls().handle(self.update)

    def _pick_base(self):
        message = self.update.message

        if message:
            if message.text and message.text.startswith("/"):
                return CommandHandler
            return MessageHandler

        if self.update.callback_query:
            return CallbackQueryHandler

        if self.update.inline_query:
            return InlineQueryHandler

        if self.update.chosen_inline_result:
            return ChosenInlineResultHandler

        return None
