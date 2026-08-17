from django.db import transaction
from rest_framework.permissions import AllowAny
from django.contrib.auth import login, logout, authenticate, get_user_model
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from tenants.models import Tenant, Domain, Subscription, Plan
from .models import EmailVerificationCode, PasswordResetCode
from django.utils import timezone
from datetime import timedelta
from django.conf import settings
from axes.handlers.proxy import AxesProxyHandler
from django.core.validators import validate_email
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.contrib.auth import update_session_auth_hash
from drf_spectacular.utils import extend_schema, OpenApiResponse
from .serializers import (
    RegisterSerializer,
    UserSerializer,
    LoginRequestSerializer,
    EmailVerificationRequestSerializer,
    UpdatePendingEmailRequestSerializer,
    ChangePasswordSerializer,
    ConfirmPasswordResetSerializer,
    PasswordResetRequestSerializer,
)

from utils.emails import (
    send_verification_email,
    send_update_pending_email,
    send_password_reset_email,
)

User = get_user_model()


BASE_URL = settings.BASE_URL


class RegisterView(APIView):
    permission_classes = []

    @extend_schema(
        operation_id="register",
        request=RegisterSerializer,
        responses={201: UserSerializer},
    )
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated_data = serializer.validated_data

        base_slug = validated_data["username"].lower()
        schema_name = base_slug
        domain_url = f"{base_slug}.{BASE_URL}"

        trial_end = timezone.now() + timedelta(days=settings.TRIAL_DAYS)

        # Tenant creation triggers django-tenants' own CREATE SCHEMA DDL and
        # connection handling. Keep this OUTSIDE any outer atomic() block —
        # nesting it inside savepoints is a known source of flaky failures.
        tenant = Tenant.objects.create(
            schema_name=schema_name,
            name=base_slug,
        )

        try:
            with transaction.atomic():
                user = User.objects.create_user(
                    username=validated_data["username"],
                    email=validated_data["email"],
                    password=validated_data["password"],
                    first_name=validated_data.get("first_name", ""),
                    last_name=validated_data.get("last_name", ""),
                )

                Domain.objects.create(
                    domain=domain_url,
                    tenant=tenant,
                    is_primary=True,
                )

                Subscription.objects.create(
                    tenant=tenant,
                    status=Subscription.Status.TRIALING,
                    trial_end_date=trial_end,
                )

                verification_code = EmailVerificationCode.create_for_user(user)
                # Fire the email only after the DB transaction actually commits.
                transaction.on_commit(
                    lambda: send_verification_email(user, verification_code)
                )
        except Exception:
            # Compensating cleanup: the tenant/schema was created outside the
            # atomic block above, so it isn't rolled back automatically if
            # user/domain/subscription creation fails. force_drop=True also
            # drops the schema, not just the row.
            tenant.delete(force_drop=True)
            raise

        return Response(
            {
                "user": UserSerializer(user).data,
                "tenant": {
                    "schema_name": tenant.schema_name,
                    "domain": domain_url,
                },
                "subscription": {
                    "status": Subscription.Status.TRIALING,
                    "trial_end_date": trial_end,
                },
            },
            status=status.HTTP_201_CREATED,
        )


class LoginView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(
        operation_id="login",
        request=LoginRequestSerializer,
        responses={200: OpenApiResponse(description="Login successful")},
    )
    def post(self, request):
        username_or_email = request.data.get("username_or_email", "").strip()
        password = request.data.get("password")

        if not all([username_or_email, password]):
            return Response(
                {"error": "username_or_email and password are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = User.objects.filter(username=username_or_email).first()
        if not user:
            user = User.objects.filter(email__iexact=username_or_email).first()

        if not user:
            return Response(
                {"error": "Invalid credentials."}, status=status.HTTP_401_UNAUTHORIZED
            )

        username = user.username

        if AxesProxyHandler.is_locked(request, credentials={"username": username}):
            return Response(
                {
                    "error": "Account locked: too many login attempts. Please try again later."
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        user = authenticate(request, username=username, password=password)
        if not user:
            return Response(
                {"detail": "Invalid credentials."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        login(request, user, backend="django.contrib.auth.backends.ModelBackend")

        return Response(
            {
                "detail": "Login successful.",
            },
            status=status.HTTP_200_OK,
        )


class LogoutView(APIView):

    @extend_schema(
        operation_id="logout",
        request=None,
        responses={200: OpenApiResponse(description="Logged out")},
    )
    def post(self, request):
        logout(request)
        return Response(
            {"detail": "logged out successfully"}, status=status.HTTP_200_OK
        )


class SendEmailVerificationView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        operation_id="request_email_verification",
        request=EmailVerificationRequestSerializer,
        responses={
            200: OpenApiResponse(description="Verification email sent if applicable")
        },
    )
    def post(self, request):
        email = request.data.get("email", "").strip().lower()
        if not email:
            return Response(
                {"error": "email is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            validate_email(email)
        except ValidationError:
            return Response(
                {"error": "Enter a valid email address."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = User.objects.filter(email__iexact=email).first()

        generic_response = Response(
            {
                "detail": "If that account exists and is unverified, a new link has been sent."
            },
            status=status.HTTP_200_OK,
        )

        if user and user.email_verified:
            return Response(
                {
                    "detail": "This account is already verified. Update your email from your profile settings instead."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not user:
            return generic_response

        existing_code = EmailVerificationCode.objects.filter(user=user).first()
        if existing_code and existing_code.is_valid:
            return Response(
                {
                    "error": "A verification link was already sent recently. Please check your inbox before requesting another."
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        verification_code = EmailVerificationCode.create_for_user(user)
        send_verification_email(user, verification_code)

        return generic_response


class UpdatePendingEmailRequestView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        operation_id="update_pending_email",
        request=UpdatePendingEmailRequestSerializer,
        responses={
            200: OpenApiResponse(description="Email updated, verification sent")
        },
    )
    def post(self, request):
        username = request.data.get("username")
        password = request.data.get("password")
        new_email = request.data.get("new_email")

        if not all([username, password, new_email]):
            return Response(
                {"error": "username, password, and new_email are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if AxesProxyHandler.is_locked(request, credentials={"username": username}):
            return Response(
                {
                    "error": "Account locked: too many login attempts. Please try again later."
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        user = authenticate(request, username=username, password=password)
        if user is None:
            return Response(
                {"detail": "Invalid credentials."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        if user.email_verified:
            return Response(
                {
                    "detail": "This account is already verified. Update your email from your profile settings instead."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if user.email == new_email:
            return Response(
                {"detail": "That is already your current email."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if User.objects.filter(email__iexact=new_email).exclude(pk=user.pk).exists():
            return Response(
                {"detail": "That email is already in use."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        existing_code = EmailVerificationCode.objects.filter(user=user).first()
        if existing_code and existing_code.is_valid:
            return Response(
                {
                    "detail": "A verification link was already sent. Please check your inbox before requesting another."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            user.email = new_email
            user.save(update_fields=["email"])

            verification_code = EmailVerificationCode.create_for_user(user)
            send_update_pending_email(user, verification_code)

        return Response(
            {"detail": "Email updated. A new verification link has been sent."},
            status=status.HTTP_200_OK,
        )


class VerifyEmailView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        operation_id="confirm_email_verification",
        request=None,
        responses={200: OpenApiResponse(description="Email verified")},
    )
    def post(self, request, code):
        record = EmailVerificationCode.objects.filter(code=code).first()
        if not record or not record.is_valid:
            return Response(
                {"error": "Invalid or expired verification link."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = record.user

        if user.email_verified:
            record.mark_used()
            return Response(
                {"detail": "Email already verified."},
                status=status.HTTP_200_OK,
            )

        with transaction.atomic():
            user.email_verified = True
            user.save(update_fields=["email_verified"])

            record.mark_used()

            login(request, user, backend="django.contrib.auth.backends.ModelBackend")

        return Response(
            {"detail": "Email verified."},
            status=status.HTTP_200_OK,
        )


class RequestPasswordResetView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        operation_id="request_password_reset",
        request=PasswordResetRequestSerializer,
        responses={
            200: OpenApiResponse(description="Reset link sent if account exists")
        },
    )
    def post(self, request):
        email = request.data.get("email", "").strip().lower()
        if not email:
            return Response(
                {"error": "email is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            validate_email(email)
        except ValidationError:
            return Response(
                {"error": "Enter a valid email address."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        generic_response = Response(
            {"detail": "If that account exists, a password reset link has been sent."},
            status=status.HTTP_200_OK,
        )

        user = User.objects.filter(email__iexact=email).first()
        if not user:
            return generic_response

        existing_code = PasswordResetCode.objects.filter(user=user).first()
        if existing_code and not existing_code.is_valid:
            return Response(
                {
                    "error": "A reset link was already sent recently. Please check your inbox before requesting another."
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        if existing_code:
            existing_code.mark_used()

        reset_code = PasswordResetCode.create_for_user(user, valid_minutes=5)
        send_password_reset_email(user, reset_code)

        return generic_response


class ConfirmPasswordResetView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        operation_id="confirm_password_reset",
        request=ConfirmPasswordResetSerializer,
        responses={200: OpenApiResponse(description="Password reset successful")},
    )
    def post(self, request, code):
        new_password = request.data.get("new_password", "")
        if not new_password:
            return Response(
                {"error": "new_password is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        record = PasswordResetCode.objects.filter(code=code).first()
        if not record or not record.is_valid:
            return Response(
                {"error": "Invalid or expired reset link."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = record.user

        try:
            validate_password(new_password, user=user)
        except ValidationError as e:
            return Response({"error": e.messages}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            user.set_password(new_password)
            user.save(update_fields=["password"])
            record.mark_used()

        return Response(
            {"detail": "Password reset successful. You can now log in."},
            status=status.HTTP_200_OK,
        )


class ChangePasswordView(APIView):

    @extend_schema(
        operation_id="change_password",
        request=ChangePasswordSerializer,
        responses={200: OpenApiResponse(description="Password changed")},
    )
    def post(self, request):
        current_password = request.data.get("current_password", "")
        new_password = request.data.get("new_password", "")

        if not all([current_password, new_password]):
            return Response(
                {"error": "current_password and new_password are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not request.user.check_password(current_password):
            return Response(
                {"error": "Current password is incorrect."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if current_password == new_password:
            return Response(
                {"error": "New password must be different from the current password."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            validate_password(new_password, user=request.user)
        except ValidationError as e:
            return Response({"error": e.messages}, status=status.HTTP_400_BAD_REQUEST)

        request.user.set_password(new_password)
        request.user.save(update_fields=["password"])

        update_session_auth_hash(request, request.user)

        return Response(
            {"detail": "Password changed successfully."},
            status=status.HTTP_200_OK,
        )


class MeView(APIView):
    @extend_schema(
        operation_id="me",
        responses={200: UserSerializer},
    )
    def get(self, request):
        serializer = UserSerializer(request.user)
        return Response(serializer.data)
