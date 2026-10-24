# door/tests/test_serializers.py
import pytest
from door.serializers import RegisterSerializer, OrderCreateSerializer
from door.tests.factories import ProfileFactory
from django.contrib.auth import get_user_model

User = get_user_model()


@pytest.mark.django_db
def test_register_serializer():
    """Тест регистрации: создается User и Profile"""
    data = {
        "store_name": "Новый Магазин",
        "manager_name": "Новый Менеджер",
        "phone": "+79990001122",
        "email": "new@test.com",
        "password": "VeryStrongPass123!"
    }
    serializer = RegisterSerializer(data=data)
    assert serializer.is_valid()
    user = serializer.save()

    assert user.email == "new@test.com"
    assert user.profile.store_name == "Новый Магазин"
    assert user.check_password("VeryStrongPass123!")


@pytest.mark.django_db
def test_order_create_serializer_address_default():
    """
    Тест: Если адрес не передан, он берется из профиля магазина.
    """
    from rest_framework.test import APIRequestFactory
    from django.contrib.auth.models import AnonymousUser

    user = ProfileFactory().user
    # Эмулируем request с пользователем
    factory = APIRequestFactory()
    request = factory.post('/')
    request.user = user

    data = {
        "order_type": "montage",
        "comment": "Без адреса"
    }
    serializer = OrderCreateSerializer(data=data, context={'request': request})
    assert serializer.is_valid()

    order = serializer.save(shop=user)
    # Адрес должен совпадать с профилем
    assert order.city == user.profile.city
    assert order.street == user.profile.street
    assert order.house == user.profile.house