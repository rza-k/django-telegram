from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


class Conf:
    @property
    def _s(self) -> dict:
        return getattr(settings, "TELEGRAM", {})

    def _require(self, name):
        try:
            return self._s[name]
        except KeyError:
            raise ImproperlyConfigured(
                f"settings.TELEGRAM['{name}'] is required"
            ) from None

    # ---- اجباری (ایندکس) ----
    @property
    def BOT_TOKEN(self) -> str:
        return self._require("BOT_TOKEN")

    @property
    def TM_WEBHOOK_URL(self) -> str:
        return self._require("TM_WEBHOOK_URL")

    # ---- اختیاری (get با پیش‌فرض) ----
    @property
    def PROXY_SOCKS(self) -> str:
        return self._s.get("PROXY_SOCKS", "")


conf = Conf()
