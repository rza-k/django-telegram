from __future__ import annotations

from functools import lru_cache
from typing import Any, ClassVar, cast

from django.contrib.auth import get_user_model
from django.core.exceptions import FieldDoesNotExist, ImproperlyConfigured
from django.utils.functional import cached_property

from dj_telegram_bot.contrib.mixins import TelegramUserMixin

# Re-exported for backward compatibility
from dj_telegram_bot.contrib.services import BotStatusService, MessageService
from dj_telegram_bot.core.routing import (  # noqa: F401
    Route,
    Router,
    before_handler,
    before_handlers,
    callback_handler,
    callback_step_handler,
    chosen_handler,
    command_handler,
    default_router,
    inline_handler,
    message_handler,
    message_step_handler,
)
from dj_telegram_bot.core.telegram import Telegram
from dj_telegram_bot.core.types import (
    CallbackQuery,
    Chat,
    InlineQuery,
    Message,
    Update,
    User,
)


@lru_cache()
def user_model_supported(model) -> bool:
    """True if the model uses the mixin, or has real `user_id` and `step` fields."""

    if issubclass(model, TelegramUserMixin):
        return True

    for name in ("user_id", "step"):
        try:
            if model._meta.get_field(name).is_relation:
                return False
        except FieldDoesNotExist:
            return False

    return True


class BaseHandler:
    """
    Base handler class that provides common utilities for processing Telegram updates,
    such as accessing user, chat, and message details.
    """

    handler_type: ClassVar[str | None] = None
    key_attribute: ClassVar[str | None] = None
    uses_step: ClassVar[bool] = False
    router: ClassVar[Router] = default_router

    def __init__(self, update: Update, bot: Telegram):
        self.update = update
        self.bot = bot

    @property
    def inline_query(self) -> InlineQuery:
        return cast(InlineQuery, self.update.inline_query)

    @property
    def callback_query(self) -> CallbackQuery:
        return cast(CallbackQuery, self.update.callback_query)

    @property
    def callback_data(self) -> str:
        return str(self.callback_query.data) if self.callback_query else ""

    @property
    def query(self) -> str:
        return self.inline_query.query if self.inline_query else ""

    @property
    def message(self) -> Message:
        cq = self.callback_query
        if cq and isinstance(cq.message, Message):
            return cast(Message, cq.message)

        return cast(Message, self.update.message)

    @property
    def text(self) -> str:
        message = self.message or self.update.channel_post
        if not message:
            return ""

        return message.text or message.caption or ""

    @property
    def command(self) -> str:
        if self.text.startswith("/"):
            return self.text.lstrip("/")

        return ""

    @property
    def chat(self) -> Chat:
        """
        Returns the chat object from the update, if available.
        """
        cq = self.callback_query
        if cq and cq.message:
            return cast(Chat, cq.message.chat)

        if cq and cq.inline_message_id:
            return cast(Chat, cq.from_user)

        if self.inline_query and self.inline_query.id:
            return cast(Chat, self.inline_query.from_user)

        if self.update.message:
            return cast(Chat, self.update.message.chat)

        if self.update.channel_post:
            return self.update.channel_post.chat

        return cast(Chat, None)

    @property
    def user(self) -> User:
        """
        Returns the user object who sent the update, if available.
        """
        user = None
        if self.message:
            user = self.message.from_user

        if self.callback_query:
            user = self.callback_query.from_user

        if self.inline_query:
            user = self.inline_query.from_user

        if self.update.channel_post:
            user = self.update.channel_post.sender_chat

        return cast(User, user)

    @property
    def user_id(self) -> int:
        return self.user.id if self.user else 0

    @property
    def chat_id(self) -> int:
        return self.chat.id if self.chat else 0

    @property
    def inline_message_id(self) -> str | None:
        cq = self.update.callback_query
        return cq.inline_message_id if cq else None

    @cached_property
    def _db_user(self):
        """Internal: the DB user, or None (no user in the update, or unsupported model)."""
        user = self.user
        model = get_user_model()
        if not user or not user_model_supported(model):
            return None

        if not self.is_private():
            try:
                self.bot.send_chat_action(self.chat_id, "typing")
            except Exception:
                return None

        if not issubclass(model, TelegramUserMixin):
            return model.objects.filter(user_id=user.id).first()  # read only

        return model.get_or_create_telegram_user(user)

    @property
    def user_obj(self):
        if not user_model_supported(get_user_model()):
            raise ImproperlyConfigured(
                "user_obj needs `user_id` and `step` fields on your AUTH_USER_MODEL. "
                "Inherit from `TelegramUserMixin` or add them yourself."
            )

        user = self._db_user
        if user is None:
            raise LookupError("No database user found for this update.")

        return user

    def set_step(self, step: str) -> None:
        user = self.user_obj
        user.step = step
        user.save(update_fields=["step"])

    @property
    def user_step(self) -> str:
        return self._db_user.step if self._db_user else ""

    def is_private(self) -> bool:
        if self.is_inline_callback():
            # location is unknown (could be a group or someone else's chat)
            return False

        if self.inline_query and self.inline_query.from_user:
            return self.inline_query.chat_type in ["private", "sender"]

        if self.chat:
            return self.chat.type == "private"

        return False

    def is_group(self) -> bool:
        if self.chat:
            return self.chat.type in ("supergroup", "group")

        return False

    def is_update_mode(self):
        if self._db_user and self._db_user.is_superuser:
            return False

        status = BotStatusService.get_status()
        if status.is_update:
            self.bot.send_message(self.chat_id, text=status.update_msg)
            return True

        return False

    def is_user_block(self):
        if self._db_user and not self._db_user.is_active:
            default_msg = "شما در ربات بلاک شده اید"
            msg = MessageService.get_msg_by_step("block")
            self.bot.send_message(self.chat_id, text=msg.text if msg else default_msg)
            return True

        return False

    def is_inline_callback(self) -> bool:
        return bool(self.inline_message_id)

    def has_joined_channel(self, chat_id, user_id):
        chat_id = str(chat_id)
        if chat_id.lstrip("-").isdigit():
            chat_id = int(chat_id)
        else:
            chat_id = chat_id if "@" in chat_id else "@" + chat_id

        rsp = self.bot.get_chat_member(chat_id, user_id)
        return rsp.status != "left"

    def _execute(self, route: Route) -> Any:
        owner, name = route.owner, route.name
        if owner is None or name is None:  # is plain function
            return route.func(self)

        if isinstance(self, owner):
            inst = self
        else:
            inst = owner(self.update, self.bot)
            # reuse the already-fetched DB user instead of querying again
            if "_db_user" in self.__dict__:
                inst.__dict__["_db_user"] = self.__dict__["_db_user"]

        return getattr(inst, name)()

    def handle(self) -> bool:
        self._db_user  # load/create the user before any before_handler runs

        if any(check(self) for check in before_handlers):
            return True

        if not self.handler_type or not self.key_attribute:
            return False

        key = getattr(self, self.key_attribute, None)
        if key is None:
            return False

        step = self.user_step if self.uses_step else ""
        route = self.router.find(self.handler_type, key, step)
        if not route:
            return False

        self._execute(route)
        return True


class CommandHandler(BaseHandler):
    handler_type = "command"
    key_attribute = "command"


class MessageHandler(BaseHandler):
    handler_type = "message"
    key_attribute = "text"
    uses_step = True


class CallBackQueryHandler(BaseHandler):
    handler_type = "callback"
    key_attribute = "callback_data"
    uses_step = True


class InlineQueryHandler(BaseHandler):
    handler_type = "inline"
    key_attribute = "query"


class ChosenInlineResultHandler(BaseHandler):
    handler_type = "chosen"
    key_attribute = "result_id"

    @property
    def chosen(self):
        return self.update.chosen_inline_result

    @property
    def result_id(self) -> str:
        return self.chosen.result_id if self.chosen else ""

    @property
    def query(self) -> str:
        return self.chosen.query if self.chosen else ""

    @property
    def user(self):
        return self.chosen.from_user if self.chosen else super().user
