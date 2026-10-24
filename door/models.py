from django.conf import settings
from django.db import models


class Profile(models.Model):
    """Профиль магазина: экран «ЛК» (название, ФИО, телефон, адрес магазина)."""
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    store_name = models.CharField("Название магазина", max_length=255)
    manager_name = models.CharField("ФИО менеджера", max_length=255)
    phone = models.CharField("Контактный телефон", max_length=32)

    # блок «Адрес магазина»
    city = models.CharField("Город", max_length=128, blank=True, default="")
    street = models.CharField("Улица", max_length=255, blank=True, default="")
    house = models.CharField("Дом", max_length=32, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Профиль магазина"
        verbose_name_plural = "Профили магазинов"

    @property
    def avatar_letter(self):
        # красный квадрат с буквой «А» в ЛК
        return self.store_name[:1].upper() if self.store_name else ""

    def __str__(self):
        return f"{self.store_name} — {self.manager_name}"


class Employee(models.Model):
    """Сотрудники сервиса: «Менеджер» и «Специалист по монтажу» в карточке заявки."""

    class Role(models.TextChoices):
        MANAGER = "manager", "Менеджер"
        INSTALLER = "installer", "Специалист по монтажу"

    full_name = models.CharField("ФИО", max_length=255)
    phone = models.CharField("Телефон", max_length=32, blank=True)
    role = models.CharField("Должность", max_length=20, choices=Role.choices)

    class Meta:
        verbose_name = "Сотрудник"
        verbose_name_plural = "Сотрудники"

    def __str__(self):
        return f"{self.full_name} ({self.get_role_display()})"


class Order(models.Model):
    class Type(models.TextChoices):
        MONTAGE = "montage", "Монтаж"  # на макете единственный тип

    class Status(models.TextChoices):
        WAITING_CALL = "waiting_call", "Ожидает звонок"
        WAITING_SERVICE = "waiting_service", "Ожидает услугу"
        COMPLETED = "completed", "Завершен"

    # null (а не ""), чтобы unique не конфликтовал до выдачи номера
    number = models.CharField(
        "Номер заявки", max_length=20, unique=True, null=True, blank=True, editable=False
    )
    shop = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="orders",
        verbose_name="Магазин",
    )
    title = models.CharField("Название", max_length=255, default="Монтаж дверей")
    order_type = models.CharField(
        "Тип заявки", max_length=20, choices=Type.choices, default=Type.MONTAGE
    )
    status = models.CharField(
        "Статус", max_length=20, choices=Status.choices, default=Status.WAITING_CALL
    )

    # адрес монтажа (по умолчанию — адрес магазина, можно изменить карандашом)
    city = models.CharField("Город", max_length=128)
    street = models.CharField("Улица", max_length=255)
    house = models.CharField("Дом", max_length=32)

    manager = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="managed_orders",
        limit_choices_to={"role": Employee.Role.MANAGER},
        verbose_name="Менеджер",
    )
    installer = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="installed_orders",
        limit_choices_to={"role": Employee.Role.INSTALLER},
        verbose_name="Специалист по монтажу",
    )

    comment = models.TextField("Комментарий магазина", blank=True)
    created_at = models.DateTimeField("Дата заявки", auto_now_add=True)

    # «Дата выполнения: 15.01.2026 - 22.01.2026» — диапазон из календаря при создании
    desired_date_from = models.DateField("Дата выполнения (с)", null=True, blank=True)
    desired_date_to = models.DateField("Дата выполнения (по)", null=True, blank=True)

    # «Дата назначения работ» — ставит сервис
    scheduled_date = models.DateField("Дата назначения работ", null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "Заявка"
        verbose_name_plural = "Заявки"

    @staticmethod
    def format_number(pk):
        # АД + 8 цифр, как на макете: АД00521250
        return f"АД{pk:08d}"

    @property
    def contact(self):
        """Контакт в шапке заявки (ФИО и телефон) — это менеджер магазина из профиля."""
        profile = getattr(self.shop, "profile", None)
        return {
            "full_name": profile.manager_name if profile else "",
            "phone": profile.phone if profile else "",
        }

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.number:
            self.number = self.format_number(self.pk)
            # update(), чтобы не вызывать сигналы повторно
            type(self).objects.filter(pk=self.pk).update(number=self.number)

    def __str__(self):
        return f"{self.number} — {self.title}"


def order_file_path(instance, filename):
    return f"orders/{instance.order_id}/{instance.source}/{filename}"


class OrderFile(models.Model):
    class Source(models.TextChoices):
        MANAGER = "manager", "От менеджера"
        SHOP = "shop", "От магазина"

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="files")
    # в админке файлы добавляет менеджер; API-загрузка магазина задаёт SHOP явно
    source = models.CharField(
        "Кто прикрепил", max_length=10, choices=Source.choices, default=Source.MANAGER
    )
    file = models.FileField("Файл", upload_to=order_file_path)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        verbose_name = "Файл заявки"
        verbose_name_plural = "Файлы заявок"

    @property
    def name(self):
        return self.file.name.rsplit("/", 1)[-1]

    def __str__(self):
        return f"{self.order.number}: {self.name}"


class PriceItem(models.Model):
    """Строка прайса: экран со списком услуг и ценами (иконка «документ»)."""
    name = models.CharField("Наименование", max_length=500)
    price = models.DecimalField("Цена, ₽", max_digits=10, decimal_places=2)
    position = models.PositiveIntegerField("Порядок", default=0)

    class Meta:
        ordering = ["position", "id"]
        verbose_name = "Позиция прайса"
        verbose_name_plural = "Позиции прайса"

    def __str__(self):
        return f"{self.name} — {self.price}"


class PriceList(models.Model):
    """Файл для карточки «Скачать прайс-лист». Отдаётся самый свежий активный."""
    title = models.CharField("Название", max_length=255, default="Прайс-лист")
    file = models.FileField("Файл", upload_to="price_lists/")
    is_active = models.BooleanField("Активен", default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Файл прайс-листа"
        verbose_name_plural = "Файлы прайс-листа"

    @property
    def name(self):
        return self.file.name.rsplit("/", 1)[-1]

    def __str__(self):
        return self.title


class Notification(models.Model):
    """Экран «Уведомления по заявкам». Создаётся автоматически сигналами (signals.py)."""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
        verbose_name="Магазин",
    )
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="notifications",
        verbose_name="Заявка",
    )
    text = models.CharField("Текст", max_length=500)
    is_read = models.BooleanField("Прочитано", default=False)  # непрочитанные — красным
    created_at = models.DateTimeField("Дата", auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "Уведомление"
        verbose_name_plural = "Уведомления"
        indexes = [models.Index(fields=["user", "is_read"])]

    def __str__(self):
        return self.text