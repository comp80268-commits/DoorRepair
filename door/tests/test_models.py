# door/tests/test_models.py
import pytest
from door.models import Order, OrderFile
from door.tests.factories import OrderFactory, ProfileFactory


@pytest.mark.django_db
def test_order_number_generation():
    """Проверяем, что номер заявки генерируется автоматически (АД + 8 цифр)"""
    order = OrderFactory()
    order.refresh_from_db()

    assert order.number is not None
    assert order.number.startswith("АД")
    assert len(order.number) == 10  # АД + 8 цифр
    assert order.number == f"АД{order.pk:08d}"


@pytest.mark.django_db
def test_avatar_letter():
    """Проверяем свойство avatar_letter у профиля"""
    profile = ProfileFactory(store_name="Дверной Мир")
    assert profile.avatar_letter == "Д"


@pytest.mark.django_db
def test_contact_property():
    """Проверяем, что contact берется из профиля магазина"""
    order = OrderFactory()
    # Создаем профиль для магазина заявки
    ProfileFactory(user=order.shop, manager_name="Сидоров", phone="12345")

    contact = order.contact
    assert contact["full_name"] == "Сидоров"
    assert contact["phone"] == "12345"