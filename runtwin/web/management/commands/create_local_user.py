import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "從環境變數建立本機管理員；不在參數或日誌輸出密碼。"

    def handle(self, *args, **options):
        username = os.getenv("RUNTWIN_ADMIN_USERNAME")
        password = os.getenv("RUNTWIN_ADMIN_PASSWORD")
        email = os.getenv("RUNTWIN_ADMIN_EMAIL", "")
        if not username or not password:
            raise CommandError("請設定 RUNTWIN_ADMIN_USERNAME 與 RUNTWIN_ADMIN_PASSWORD。")
        user_model = get_user_model()
        user, created = user_model.objects.get_or_create(username=username, defaults={"email": email, "is_staff": True, "is_superuser": True})
        if created:
            user.set_password(password)
            user.save()
            self.stdout.write(self.style.SUCCESS("管理員帳號已建立。"))
        else:
            self.stdout.write("帳號已存在；未修改密碼。")
