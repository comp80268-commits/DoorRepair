import io
import os
import zipfile

from django.db.models import Q
from django.http import FileResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import mixins, permissions, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView

from .models import Notification, Order, OrderFile, PriceItem, PriceList
from .serializers import (
    ChangePasswordSerializer,
    LoginSerializer,
    NotificationSerializer,
    OrderCreateSerializer,
    OrderDetailSerializer,
    OrderFileSerializer,
    OrderFileUploadSerializer,
    OrderListSerializer,
    PriceItemSerializer,
    PriceListSerializer,
    ProfileSerializer,
    ProfileUpdateSerializer,
    RegisterSerializer,
)

# ---------- схемы ответов для Swagger ----------

TokensSerializer = inline_serializer(
    "Tokens",
    fields={"access": serializers.CharField(), "refresh": serializers.CharField()},
)

AuthResponseSerializer = inline_serializer(
    "AuthResponse",
    fields={
        "access": serializers.CharField(),
        "refresh": serializers.CharField(),
        "profile": ProfileSerializer(),
    },
)


class LogoutSerializer(serializers.Serializer):
    """Настоящий класс (не inline), чтобы его можно было указать как serializer_class."""
    refresh = serializers.CharField()


NewOrderFormSerializer = inline_serializer(
    "NewOrderForm",
    fields={
        "next_number": serializers.CharField(),
        "contact": inline_serializer(
            "NewOrderContact",
            fields={
                "full_name": serializers.CharField(),
                "phone": serializers.CharField(),
            },
        ),
        "order_types": serializers.ListField(
            child=inline_serializer(
                "OrderTypeChoice",
                fields={"value": serializers.CharField(), "label": serializers.CharField()},
            )
        ),
        "defaults": inline_serializer(
            "NewOrderDefaults",
            fields={
                "city": serializers.CharField(),
                "street": serializers.CharField(),
                "house": serializers.CharField(),
            },
        ),
    },
)

UnreadCountSerializer = inline_serializer("UnreadCount", fields={"count": serializers.IntegerField()})
MarkedReadSerializer = inline_serializer("MarkedRead", fields={"updated": serializers.IntegerField()})


# ---------- вспомогательные функции ----------

def _tokens_for(user):
    refresh = RefreshToken.for_user(user)
    return {"access": str(refresh.access_token), "refresh": str(refresh)}


def _get_profile(user):
    """Профиль магазина. У суперпользователя его нет, поэтому 403, а не 500."""
    profile = getattr(user, "profile", None)
    if profile is None:
        raise PermissionDenied("У этого пользователя нет профиля магазина")
    return profile


def _auth_response(user, http_status=status.HTTP_200_OK):
    return Response(
        {**_tokens_for(user), "profile": ProfileSerializer(_get_profile(user)).data},
        status=http_status,
    )


def _case_variants(text):
    """
    SQLite сравнивает без учёта регистра только латиницу, поэтому для кириллицы
    («ад00521250», «монтаж») перебираем несколько вариантов регистра.
    """
    return {text, text.lower(), text.upper(), text.capitalize(), text.title()}


# ---------- авторизация ----------
# GenericViewSet + serializer_class: страница DRF показывает отдельные поля формы.

@extend_schema(tags=["Авторизация"])
class RegisterViewSet(viewsets.GenericViewSet):
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    @extend_schema(
        summary="Регистрация магазина",
        request=RegisterSerializer,
        responses={201: AuthResponseSerializer},
    )
    def create(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return _auth_response(user, status.HTTP_201_CREATED)


@extend_schema(tags=["Авторизация"])
class LoginViewSet(viewsets.GenericViewSet):
    serializer_class = LoginSerializer
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    @extend_schema(
        summary="Вход (логин = email)",
        request=LoginSerializer,
        responses={200: AuthResponseSerializer},
    )
    def create(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return _auth_response(serializer.validated_data["user"])


@extend_schema(tags=["Авторизация"])
class LogoutViewSet(viewsets.GenericViewSet):
    serializer_class = LogoutSerializer
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        summary="Выход: refresh-токен перестаёт работать",
        request=LogoutSerializer,
        responses={204: None},
    )
    def create(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            RefreshToken(serializer.validated_data["refresh"]).blacklist()
        except TokenError:
            return Response({"refresh": ["Недействительный токен"]}, status=status.HTTP_400_BAD_REQUEST)
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(tags=["Авторизация"], summary="Обновить access-токен по refresh-токену")
class TokenRefreshDocView(TokenRefreshView):
    authentication_classes = []
    permission_classes = [permissions.AllowAny]


# ---------- личный кабинет ----------

@extend_schema(tags=["Личный кабинет"])
class MeViewSet(viewsets.GenericViewSet):
    """
    GET   /me/                  — данные профиля
    PATCH /me/                  — изменить любые поля профиля и адреса
    POST  /me/change-password/  — сменить пароль
    """
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        if self.action == "partial_update":
            return ProfileUpdateSerializer
        if self.action == "change_password":
            return ChangePasswordSerializer
        return ProfileSerializer

    @extend_schema(summary="Данные профиля магазина", responses=ProfileSerializer)
    def retrieve(self, request, *args, **kwargs):
        return Response(ProfileSerializer(_get_profile(request.user)).data)

    @extend_schema(
        summary="Изменить поля профиля и адреса (можно по одному)",
        request=ProfileUpdateSerializer,
        responses=ProfileSerializer,
    )
    def partial_update(self, request, *args, **kwargs):
        serializer = self.get_serializer(_get_profile(request.user), data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        profile = serializer.save()
        return Response(ProfileSerializer(profile).data)

    @extend_schema(
        summary="Сменить пароль (в ответ новая пара токенов)",
        request=ChangePasswordSerializer,
        responses=TokensSerializer,
    )
    def change_password(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = request.user
        user.set_password(serializer.validated_data["new_password"])
        user.save()
        return Response(_tokens_for(user))


# ---------- прайс ----------

@extend_schema(tags=["Прайс-лист"])
class PriceItemViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """GET /price-items/ — экран со списком услуг и ценами."""
    queryset = PriceItem.objects.all()
    serializer_class = PriceItemSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None

    @extend_schema(summary="Позиции прайса: наименование и цена")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)


@extend_schema(tags=["Прайс-лист"])
class PriceListViewSet(viewsets.ViewSet):
    """
    GET /price-list/           — информация о файле прайс-листа
    GET /price-list/download/  — карточка «Скачать прайс-лист»
    """
    permission_classes = [permissions.IsAuthenticated]

    def _latest(self):
        item = PriceList.objects.filter(is_active=True).order_by("-created_at").first()
        if item is None:
            raise NotFound("Прайс-лист пока не загружен")
        return item

    @extend_schema(summary="Текущий файл прайс-листа", responses=PriceListSerializer)
    def retrieve(self, request, *args, **kwargs):
        return Response(PriceListSerializer(self._latest(), context={"request": request}).data)

    @extend_schema(
        summary="Скачать прайс-лист",
        responses={(200, "application/octet-stream"): OpenApiTypes.BINARY},
    )
    @action(detail=False, methods=["get"])
    def download(self, request):
        item = self._latest()
        return FileResponse(item.file.open("rb"), as_attachment=True, filename=item.name)


# ---------- заявки ----------

@extend_schema(tags=["Заявки"])
class OrderViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    """
    GET  /orders/                     — «Активные заявки» (все заявки магазина)
    GET  /orders/recent/              — последние 6 заявок для ЛК + кнопка «Посмотреть все»
    GET  /orders/search/?q=...        — «Поиск заявки»
    GET  /orders/new/                 — данные для экрана «Создание новой заявки»
    POST /orders/                     — «Создать заявку» (JSON или multipart с файлами в поле files)
    GET  /orders/{id}/                — карточка заявки
    POST /orders/{id}/files/          — загрузка файла магазином (multipart, поле file)
    GET  /orders/{id}/download-files/ — «Скачать все файлы» (?source=manager | shop)
    """
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    RECENT_LIMIT = 6

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Order.objects.none()
        # магазин видит только свои заявки
        return (
            Order.objects.filter(shop=self.request.user)
            .select_related("shop__profile", "manager", "installer")
            .prefetch_related("files")
        )

    def get_serializer_class(self):
        if self.action in ("list", "recent", "search"):
            return OrderListSerializer
        if self.action == "create":
            return OrderCreateSerializer
        if self.action == "upload_file":
            return OrderFileUploadSerializer
        return OrderDetailSerializer

    @extend_schema(summary="Список заявок магазина", responses=OrderListSerializer(many=True))
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(summary="Карточка заявки", responses=OrderDetailSerializer)
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @extend_schema(
        summary="Создать заявку (JSON или multipart с файлами в поле files)",
        request={
            "application/json": OrderCreateSerializer,
            "multipart/form-data": OrderCreateSerializer,
        },
        responses={201: OrderDetailSerializer},
    )
    def create(self, request, *args, **kwargs):
        _get_profile(request.user)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order = serializer.save(shop=request.user)
        order = self.get_queryset().get(pk=order.pk)  # заново, чтобы подтянулись файлы и номер
        data = OrderDetailSerializer(order, context=self.get_serializer_context()).data
        return Response(data, status=status.HTTP_201_CREATED)

    @extend_schema(
        summary="Последние 6 заявок для личного кабинета",
        responses=OrderListSerializer(many=True),
    )
    @action(detail=False, methods=["get"])
    def recent(self, request):
        orders = self.get_queryset()[: self.RECENT_LIMIT]
        return Response(self.get_serializer(orders, many=True).data)

    @extend_schema(
        summary="Поиск заявок по номеру или названию",
        parameters=[
            OpenApiParameter(
                "q", OpenApiTypes.STR, required=True,
                description="Например АД00521250",
            )
        ],
        responses=OrderListSerializer(many=True),
    )
    @action(detail=False, methods=["get"])
    def search(self, request):
        q = (request.query_params.get("q") or "").strip()
        if not q:
            return Response([])
        condition = Q()
        for variant in _case_variants(q):
            condition |= Q(number__icontains=variant) | Q(title__icontains=variant)
        orders = self.get_queryset().filter(condition)
        return Response(self.get_serializer(orders, many=True).data)

    @extend_schema(
        summary="Данные для экрана «Создание новой заявки»",
        responses=NewOrderFormSerializer,
    )
    @action(detail=False, methods=["get"], url_path="new")
    def new_form(self, request):
        """Номер заявки, контакт, типы и адрес по умолчанию — до отправки формы."""
        profile = _get_profile(request.user)
        last_id = Order.objects.order_by("-pk").values_list("pk", flat=True).first() or 0
        return Response({
            # ориентировочный номер: окончательный выдаётся при создании
            "next_number": Order.format_number(last_id + 1),
            "contact": {"full_name": profile.manager_name, "phone": profile.phone},
            "order_types": [{"value": v, "label": l} for v, l in Order.Type.choices],
            "defaults": {
                "city": profile.city,
                "street": profile.street,
                "house": profile.house,
            },
        })

    @extend_schema(
        summary="Загрузить файл от магазина (multipart, поле file)",
        request={"multipart/form-data": OrderFileUploadSerializer},
        responses={201: OrderFileSerializer},
    )
    @action(
        detail=True, methods=["post"], url_path="files",
        parser_classes=[MultiPartParser, FormParser],
    )
    def upload_file(self, request, pk=None):
        order = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order_file = serializer.save(order=order, source=OrderFile.Source.SHOP)
        data = OrderFileSerializer(order_file, context=self.get_serializer_context()).data
        return Response(data, status=status.HTTP_201_CREATED)

    @extend_schema(
        summary="Скачать файлы заявки архивом («Скачать все файлы»)",
        parameters=[
            OpenApiParameter(
                "source", OpenApiTypes.STR, enum=["manager", "shop"], required=False,
                description="manager — файлы менеджера, shop — файлы магазина, без параметра — все",
            )
        ],
        responses={(200, "application/zip"): OpenApiTypes.BINARY},
    )
    @action(detail=True, methods=["get"], url_path="download-files")
    def download_files(self, request, pk=None):
        order = self.get_object()
        files = order.files.all()
        source = request.query_params.get("source")
        if source in (OrderFile.Source.MANAGER, OrderFile.Source.SHOP):
            files = files.filter(source=source)

        buffer = io.BytesIO()
        used_names = set()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for item in files:
                if not item.file or not item.file.storage.exists(item.file.name):
                    continue
                name = item.name
                base, ext = os.path.splitext(name)
                i = 1
                while name in used_names:  # одинаковые имена не затирают друг друга
                    name = f"{base}_{i}{ext}"
                    i += 1
                used_names.add(name)
                with item.file.open("rb") as fh:
                    archive.writestr(name, fh.read())

        if not used_names:
            raise NotFound("Файлов нет")

        buffer.seek(0)
        return FileResponse(
            buffer, as_attachment=True,
            filename=f"{order.number}_files.zip", content_type="application/zip",
        )


# ---------- уведомления ----------

@extend_schema(tags=["Уведомления"])
class NotificationViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """
    GET  /notifications/               — «Уведомления по заявкам» (?is_read=false — только новые)
    GET  /notifications/unread-count/  — зелёная точка у колокольчика
    POST /notifications/{id}/read/     — отметить прочитанным
    POST /notifications/read-all/      — отметить все прочитанными
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = NotificationSerializer
    filterset_fields = ["is_read"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Notification.objects.none()
        return Notification.objects.filter(user=self.request.user).select_related("order")

    @extend_schema(summary="Список уведомлений по заявкам")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(summary="Количество непрочитанных уведомлений", responses=UnreadCountSerializer)
    @action(detail=False, methods=["get"], url_path="unread-count")
    def unread_count(self, request):
        return Response({"count": self.get_queryset().filter(is_read=False).count()})

    @extend_schema(summary="Отметить уведомление прочитанным", request=None, responses=NotificationSerializer)
    @action(detail=True, methods=["post"])
    def read(self, request, pk=None):
        notification = self.get_object()
        if not notification.is_read:
            notification.is_read = True
            notification.save(update_fields=["is_read"])
        return Response(self.get_serializer(notification).data)

    @extend_schema(summary="Отметить все уведомления прочитанными", request=None, responses=MarkedReadSerializer)
    @action(detail=False, methods=["post"], url_path="read-all")
    def read_all(self, request):
        updated = self.get_queryset().filter(is_read=False).update(is_read=True)
        return Response({"updated": updated})