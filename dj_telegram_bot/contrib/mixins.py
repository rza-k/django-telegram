from django.contrib.auth.hashers import make_password
from django.db import models
from django.utils.translation import gettext_lazy as _


class TelegramUserMixin(models.Model):
    user_id = models.BigIntegerField(unique=True, verbose_name=_("user id"))
    step = models.CharField(
        max_length=30, default="home", verbose_name=_("current step")
    )

    class Meta:
        abstract = True

    def __str__(self):
        return str(self.user_id)

    @classmethod
    def get_or_create_telegram_user(cls, tg_user):
        fields = {f.name for f in cls._meta.concrete_fields}
        values = {
            "username": tg_user.username or str(tg_user.id),
            "first_name": tg_user.first_name,
            "last_name": tg_user.last_name or "",
        }
        defaults = {k: v for k, v in values.items() if k in fields}
        if "password" in fields:
            defaults["password"] = make_password(str(tg_user.id))

        obj, _ = cls.objects.get_or_create(user_id=tg_user.id, defaults=defaults)
        return obj
