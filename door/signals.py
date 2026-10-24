"""
Автоматические уведомления магазину (экран «Уведомления по заявкам»):
  - заявка создана          -> «Ваша заявка №... принята в обработку»
  - назначена дата монтажа  -> «По вашей заявке №... назначена дата монтажа: 30 мая»
  - менеджер добавил файл   -> «К заявке №... добавлен новый файл: Акт выполненных работ»
  - изменился статус        -> «Статус заявки №... изменен на "Завершен"»
"""
import os

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from .models import Notification, Order, OrderFile

MONTHS = [
    "", "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
]


def _day_month(d):
    return f"{d.day} {MONTHS[d.month]}"


def _notify(order, text):
    Notification.objects.create(user_id=order.shop_id, order=order, text=text)


@receiver(pre_save, sender=Order)
def remember_old_values(sender, instance, **kwargs):
    """Запоминаем состояние до сохранения, чтобы понять, что изменилось."""
    if instance.pk:
        instance._old_values = (
            Order.objects.filter(pk=instance.pk).values("status", "scheduled_date").first()
        )
    else:
        instance._old_values = None


@receiver(post_save, sender=Order)
def order_notifications(sender, instance, created, **kwargs):
    if created:
        # номер выдаётся сразу после первого сохранения, поэтому считаем его здесь
        number = instance.number or Order.format_number(instance.pk)
        _notify(instance, f"Ваша заявка №{number} принята в обработку")
        return

    old = getattr(instance, "_old_values", None)
    if not old:
        return

    if instance.scheduled_date and instance.scheduled_date != old["scheduled_date"]:
        _notify(
            instance,
            f"По вашей заявке №{instance.number} назначена дата монтажа: "
            f"{_day_month(instance.scheduled_date)}",
        )

    if instance.status != old["status"]:
        _notify(
            instance,
            f'Статус заявки №{instance.number} изменен на "{instance.get_status_display()}"',
        )


@receiver(post_save, sender=OrderFile)
def file_notification(sender, instance, created, **kwargs):
    # уведомляем только о файлах, которые добавил менеджер
    if created and instance.source == OrderFile.Source.MANAGER:
        name = os.path.splitext(instance.name)[0]
        _notify(instance.order, f"К заявке №{instance.order.number} добавлен новый файл: {name}")