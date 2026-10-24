import factory
from django.contrib.auth import get_user_model
from door.models import Profile, Order, OrderFile, Notification

User = get_user_model()


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User
        skip_postgeneration_save = True

    username = factory.Sequence(lambda n: f"user{n}@example.com")
    email = factory.LazyAttribute(lambda o: o.username)
    password = factory.PostGenerationMethodCall('set_password', 'pass123')


class ProfileFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Profile

    user = factory.SubFactory(UserFactory)
    store_name = "Тестовый магазин"
    manager_name = "Тестовый Менеджер"
    phone = "+70000000000"
    city = "Москва"
    street = "Тверская"
    house = "10"


class OrderFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Order

    shop = factory.SubFactory(UserFactory)
    title = "Монтаж дверей"
    city = "Москва"
    street = "Тверская"
    house = "10"
    status = Order.Status.WAITING_CALL