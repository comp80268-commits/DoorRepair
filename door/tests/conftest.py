# door/tests/conftest.py
import pytest
from django.contrib.auth import get_user_model
from door.models import Profile, Order, Employee

User = get_user_model()

@pytest.fixture
def api_client():
    """Клиент для запросов к API"""
    from rest_framework.test import APIClient
    return APIClient()

@pytest.fixture
def user_password():
    return "StrongPassword123!"

@pytest.fixture
def shop_user(db, user_password):
    """Создает пользователя-магазин с профилем"""
    user = User.objects.create_user(
        username="shop@example.com",
        email="shop@example.com",
        password=user_password
    )
    Profile.objects.create(
        user=user,
        store_name="Магазин Дверей",
        manager_name="Иванов Иван",
        phone="+79991234567",
        city="Москва",
        street="Ленина",
        house="1"
    )
    return user

@pytest.fixture
def auth_client(api_client, shop_user):
    """Авторизованный клиент"""
    api_client.force_authenticate(user=shop_user)
    return api_client

@pytest.fixture
def employee_manager(db):
    return Employee.objects.create(
        full_name="Петров Петр",
        role=Employee.Role.MANAGER
    )