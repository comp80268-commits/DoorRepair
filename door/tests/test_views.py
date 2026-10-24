from datetime import date, timedelta

import pytest
from django.urls import reverse
from rest_framework import status
from door.models import Notification, Order
from django.core.files.uploadedfile import SimpleUploadedFile


@pytest.mark.django_db
def test_login_view(api_client, shop_user, user_password):
    """Тест входа: возвращает токены и профиль"""
    url = reverse('login-list')
    data = {"username": "shop@example.com", "password": user_password}

    response = api_client.post(url, data, format='json')

    assert response.status_code == status.HTTP_200_OK
    assert 'access' in response.data
    assert 'refresh' in response.data
    assert response.data['profile']['store_name'] == "Магазин Дверей"


@pytest.mark.django_db
def test_create_order_with_file_and_notification(auth_client, shop_user):
    """
    Комплексный тест: создание заявки с файлом + проверка уведомления (сигнала).
    """
    url = reverse('orders-list')

    file = SimpleUploadedFile("act.pdf", b"content", content_type="application/pdf")
    data = {
        "order_type": "montage",
        "comment": "Тестовая заявка",
        "desired_date_from": (date.today() + timedelta(days=1)).isoformat(),
        "desired_date_to": (date.today() + timedelta(days=5)).isoformat(),
        "files": [file]
    }

    response = auth_client.post(url, data, format='multipart')

    assert response.status_code == status.HTTP_201_CREATED, response.data
    assert response.data['number'] is not None

    order = Order.objects.first()
    assert order.files.count() == 1

    # Проверка сигнала (notification)
    notification = Notification.objects.filter(user=shop_user).first()
    assert notification is not None
    assert "принята в обработку" in notification.text


@pytest.mark.django_db
def test_order_status_change_signal(auth_client, shop_user):
    """Тест: при смене статуса создается уведомление"""
    # Создаем заявку напрямую через ORM
    order = Order.objects.create(
        shop=shop_user, city="M", street="S", house="1", status=Order.Status.WAITING_CALL
    )
    Notification.objects.all().delete()  # чистим уведомления о создании

    # Меняем статус (как в админке)
    order.status = Order.Status.COMPLETED
    order.save()

    notification = Notification.objects.filter(user=shop_user).last()
    assert notification is not None
    assert "Статус заявки" in notification.text
    assert "Завершен" in notification.text


@pytest.mark.django_db
def test_search_orders(auth_client, shop_user):
    """Тест поиска по номеру заявки"""
    order = Order.objects.create(
        shop=shop_user, city="M", street="S", house="1"
    )
    order.refresh_from_db()

    url = reverse('orders-search')
    response = auth_client.get(f"{url}?q={order.number}")

    assert response.status_code == status.HTTP_200_OK
    assert len(response.data) == 1
    assert response.data[0]['number'] == order.number