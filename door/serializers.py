import os

from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from .models import (
    Employee, Notification, Order, OrderFile, PriceItem, PriceList, Profile,
)

User = get_user_model()

MAX_UPLOAD_SIZE = 20 * 1024 * 1024  # 20 МБ
MAX_FILES_PER_REQUEST = 10
ALLOWED_EXTENSIONS = {
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".csv", ".txt",
    ".jpg", ".jpeg", ".png", ".webp", ".zip", ".rar", ".7z",
}


def _check_file(f):
    ext = os.path.splitext(f.name)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise serializers.ValidationError(f"Тип файла «{ext or 'без расширения'}» не поддерживается")
    if f.size > MAX_UPLOAD_SIZE:
        raise serializers.ValidationError(f"Файл «{f.name}» больше 20 МБ")


# ---------- авторизация (экран «Авторизация» / «Регистрация») ----------

class RegisterSerializer(serializers.Serializer):
    # ровно 5 полей с макета регистрации
    store_name = serializers.CharField(max_length=255, label="Название магазина")
    manager_name = serializers.CharField(max_length=255, label="ФИО менеджера")
    phone = serializers.CharField(max_length=32, label="Контактный телефон")
    email = serializers.EmailField(label="Email")
    password = serializers.CharField(
        write_only=True, label="Пароль", style={"input_type": "password"},
    )

    def validate_email(self, value):
        value = value.strip().lower()
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("Пользователь с таким email уже существует")
        return value

    def validate_password(self, value):
        validate_password(value)
        return value

    @transaction.atomic
    def create(self, validated_data):
        user = User.objects.create_user(
            username=validated_data["email"],
            email=validated_data["email"],
            password=validated_data["password"],
            first_name=validated_data["manager_name"][:150],
        )
        Profile.objects.create(
            user=user,
            store_name=validated_data["store_name"],
            manager_name=validated_data["manager_name"],
            phone=validated_data["phone"],
        )
        return user


class LoginSerializer(serializers.Serializer):
    # поле «Логин» на макете = email
    username = serializers.CharField(label="Логин")
    password = serializers.CharField(
        write_only=True, label="Пароль", style={"input_type": "password"},
    )

    def validate(self, attrs):
        username = attrs["username"].strip()
        user = (
            authenticate(username=username.lower(), password=attrs["password"])
            or authenticate(username=username, password=attrs["password"])
        )
        if user is None:
            raise serializers.ValidationError("Неверный логин или пароль")
        if not user.is_active:
            raise serializers.ValidationError("Аккаунт отключён")
        if not hasattr(user, "profile"):  # например, суперпользователь из админки
            raise serializers.ValidationError("Для этого аккаунта нет профиля магазина")
        attrs["user"] = user
        return attrs


# ---------- личный кабинет ----------

class ProfileSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(source="user.email", read_only=True)
    avatar_letter = serializers.CharField(read_only=True)

    class Meta:
        model = Profile
        fields = (
            "id", "avatar_letter",
            "store_name", "manager_name", "phone", "email",
            "city", "street", "house",
            "created_at",
        )


class ProfileUpdateSerializer(serializers.ModelSerializer):
    """PATCH /me/ — по одному полю (карандаш у каждого поля в ЛК)."""
    email = serializers.EmailField(required=False, write_only=True, label="Email")

    class Meta:
        model = Profile
        fields = ("store_name", "manager_name", "phone", "email", "city", "street", "house")
        extra_kwargs = {
            "store_name": {"label": "Название магазина"},
            "manager_name": {"label": "ФИО менеджера"},
            "phone": {"label": "Контактный телефон"},
            "city": {"label": "Город"},
            "street": {"label": "Улица"},
            "house": {"label": "Дом"},
        }

    def validate_email(self, value):
        value = value.strip().lower()
        if User.objects.filter(username=value).exclude(pk=self.instance.user_id).exists():
            raise serializers.ValidationError("Пользователь с таким email уже существует")
        return value

    @transaction.atomic
    def update(self, instance, validated_data):
        user = instance.user
        email = validated_data.pop("email", None)
        if email is not None:
            user.username = email  # логин = email
            user.email = email
        if "manager_name" in validated_data:
            user.first_name = validated_data["manager_name"][:150]
        user.save()
        return super().update(instance, validated_data)


class ChangePasswordSerializer(serializers.Serializer):
    """Карандаш у поля «Пароль» в ЛК."""
    old_password = serializers.CharField(
        write_only=True, label="Текущий пароль", style={"input_type": "password"},
    )
    new_password = serializers.CharField(
        write_only=True, label="Новый пароль", style={"input_type": "password"},
    )

    def validate_old_password(self, value):
        if not self.context["request"].user.check_password(value):
            raise serializers.ValidationError("Неверный текущий пароль")
        return value

    def validate_new_password(self, value):
        validate_password(value, self.context["request"].user)
        return value


# ---------- прайс ----------

class PriceItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = PriceItem
        fields = ("id", "name", "price")


class PriceListSerializer(serializers.ModelSerializer):
    name = serializers.CharField(read_only=True)
    url = serializers.SerializerMethodField()

    class Meta:
        model = PriceList
        fields = ("id", "title", "name", "url", "created_at")

    @extend_schema_field(OpenApiTypes.URI)
    def get_url(self, obj):
        request = self.context.get("request")
        url = obj.file.url
        return request.build_absolute_uri(url) if request else url


# ---------- заявки ----------

class EmployeeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Employee
        fields = ("id", "full_name", "phone")


class OrderFileSerializer(serializers.ModelSerializer):
    name = serializers.CharField(read_only=True)
    url = serializers.SerializerMethodField()

    class Meta:
        model = OrderFile
        fields = ("id", "name", "source", "url", "created_at")

    @extend_schema_field(OpenApiTypes.URI)
    def get_url(self, obj):
        request = self.context.get("request")
        url = obj.file.url
        return request.build_absolute_uri(url) if request else url


class OrderFileUploadSerializer(serializers.ModelSerializer):
    """Область «Добавьте файл загрузив по клику или перетащив его в область»."""

    class Meta:
        model = OrderFile
        fields = ("file",)
        extra_kwargs = {"file": {"label": "Файл"}}

    def validate_file(self, value):
        _check_file(value)
        return value


class OrderListSerializer(serializers.ModelSerializer):
    """
    Строка списка: номер, «Монтаж дверей», дата, статус.
    В списках ЛК/«Активные заявки» на макете показана дата назначения работ (scheduled_date),
    в поиске и уведомлениях — дата заявки (created_at). Отдаём обе.
    """
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Order
        fields = (
            "id", "number", "title",
            "status", "status_display",
            "created_at", "scheduled_date",
        )


class OrderDetailSerializer(serializers.ModelSerializer):
    """Карточка заявки (только просмотр, без карандашей)."""
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    order_type_display = serializers.CharField(source="get_order_type_display", read_only=True)
    contact = serializers.SerializerMethodField()
    manager = EmployeeSerializer(read_only=True)
    installer = EmployeeSerializer(read_only=True)
    manager_files = serializers.SerializerMethodField()
    shop_files = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = (
            "id", "number", "title",
            "order_type", "order_type_display",
            "status", "status_display",
            "contact", "city", "street", "house",
            "manager", "installer",
            "comment", "created_at",
            "desired_date_from", "desired_date_to", "scheduled_date",
            "manager_files", "shop_files",
        )

    @extend_schema_field({
        "type": "object",
        "properties": {
            "full_name": {"type": "string"},
            "phone": {"type": "string"},
        },
    })
    def get_contact(self, obj):
        return obj.contact

    def _files(self, obj, source):
        files = [f for f in obj.files.all() if f.source == source]
        return OrderFileSerializer(files, many=True, context=self.context).data

    @extend_schema_field(OrderFileSerializer(many=True))
    def get_manager_files(self, obj):
        return self._files(obj, OrderFile.Source.MANAGER)

    @extend_schema_field(OrderFileSerializer(many=True))
    def get_shop_files(self, obj):
        return self._files(obj, OrderFile.Source.SHOP)


class OrderCreateSerializer(serializers.ModelSerializer):
    """
    Экран «Создание новой заявки»: Тип заявки, Город, Улица, Дом, Комментарий,
    Дата выполнения (диапазон), файлы. Пустой адрес берётся из профиля магазина.
    Контакт (ФИО, телефон) всегда из профиля — на макете его нельзя редактировать.
    """
    files = serializers.ListField(
        child=serializers.FileField(),
        required=False,
        write_only=True,
        allow_empty=True,
        label="Файлы",
    )

    class Meta:
        model = Order
        fields = (
            "order_type",
            "city", "street", "house",
            "comment",
            "desired_date_from", "desired_date_to",
            "files",
        )
        extra_kwargs = {
            "order_type": {"required": False, "label": "Тип заявки"},
            "city": {"required": False, "allow_blank": True, "label": "Город"},
            "street": {"required": False, "allow_blank": True, "label": "Улица"},
            "house": {"required": False, "allow_blank": True, "label": "Дом"},
            "comment": {"label": "Комментарий"},
            "desired_date_from": {"label": "Дата выполнения с"},
            "desired_date_to": {"label": "Дата выполнения по"},
        }

    def validate_files(self, files):
        if len(files) > MAX_FILES_PER_REQUEST:
            raise serializers.ValidationError(f"Не больше {MAX_FILES_PER_REQUEST} файлов за раз")
        for f in files:
            _check_file(f)
        return files

    def validate(self, attrs):
        profile = getattr(self.context["request"].user, "profile", None)
        if profile is None:
            raise serializers.ValidationError("У пользователя нет профиля магазина")

        defaults = {"city": profile.city, "street": profile.street, "house": profile.house}
        errors = {}
        for field, default in defaults.items():
            if not (attrs.get(field) or "").strip():
                if default:
                    attrs[field] = default
                else:
                    errors[field] = "Обязательное поле"
        if errors:
            raise serializers.ValidationError(errors)

        # диапазон «Дата выполнения»
        date_from = attrs.get("desired_date_from")
        date_to = attrs.get("desired_date_to")
        if date_to and not date_from:
            raise serializers.ValidationError({"desired_date_from": "Укажите начало диапазона"})
        if date_from and not date_to:
            attrs["desired_date_to"] = date_to = date_from  # выбран один день
        if date_from:
            if date_from < timezone.localdate():
                raise serializers.ValidationError({"desired_date_from": "Дата не может быть в прошлом"})
            if date_to < date_from:
                raise serializers.ValidationError({"desired_date_to": "Конец диапазона раньше начала"})
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        files = validated_data.pop("files", [])
        order = Order.objects.create(**validated_data)  # shop приходит из save(shop=...)
        for f in files:
            OrderFile.objects.create(order=order, source=OrderFile.Source.SHOP, file=f)
        return order


# ---------- уведомления ----------

class NotificationOrderSerializer(serializers.ModelSerializer):
    """В строке уведомления: номер, «Монтаж дверей», дата заявки и статус."""
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Order
        fields = ("id", "number", "title", "created_at", "status", "status_display")


class NotificationSerializer(serializers.ModelSerializer):
    order = NotificationOrderSerializer(read_only=True)

    class Meta:
        model = Notification
        fields = ("id", "text", "is_read", "created_at", "order")