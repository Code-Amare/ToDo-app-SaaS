from django.db import transaction
from rest_framework.permissions import AllowAny
from django.contrib.auth import login, logout, authenticate, get_user_model
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from tenants.models import Tenant, Domain, Subscription, Plan
from .serializers import RegisterSerializer, UserSerializer
from .models import EmailVerificationCode
from django.utils import timezone
from datetime import timedelta
from django.conf import settings
from axes.handlers.proxy import AxesProxyHandler
from django.core.validators import validate_email
from django.core.exceptions import ValidationError

from utils.emails import send_verification_email, send_update_pending_email

User = get_user_model()


BASE_URL = settings.BASE_URL

class RegisterView(APIView):
    permission_classes = []

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated_data = serializer.validated_data

        base_slug = validated_data["username"].lower()
        schema_name = base_slug
        domain_url = f"{base_slug}.{BASE_URL}"

        trial_end = timezone.now() + timedelta(days=settings.TRIAL_DAYS)

        with transaction.atomic():
            user = serializer.Meta.model.objects.create_user(
                username=validated_data["username"],
                email=validated_data["email"],
                password=validated_data["password"],
                first_name=validated_data.get("first_name", ""),
                last_name=validated_data.get("last_name", ""),
            )

            tenant = Tenant.objects.create(
                schema_name=schema_name,
                name=base_slug,
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
            send_verification_email(user, verification_code)

            login(request, user, backend="django.contrib.auth.backends.ModelBackend")

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


class LogoutView(APIView):
    def post(self, request):
        logout(request)
        return Response({
            "detail": "logged out successfully"
        }, status=status.HTTP_200_OK)


class SendEmailVerificationView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        email = request.data.get("email").strip().lower()
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
            {"detail": "If that account exists and is unverified, a new link has been sent."},
            status=status.HTTP_200_OK,
        )

        if user and user.email_verified:
            return Response(
                {"detail": "This account is already verified. Update your email from your profile settings instead."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not user:
            return generic_response

            

        existing_code = EmailVerificationCode.objects.filter(user=user).first()
        if existing_code and existing_code.is_valid:
            return Response(
                {"error": "A verification link was already sent recently. Please check your inbox before requesting another."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        verification_code = EmailVerificationCode.create_for_user(user)
        send_verification_email(user, verification_code)

        return generic_response

    
class UpdatePendingEmailRequestView(APIView):
    permission_classes = [AllowAny]

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
                {"error": "Account locked: too many login attempts. Please try again later."},
                status=status.HTTP_403_FORBIDDEN,)
            

        user = authenticate(request, username=username, password=password)
        if user is None:
            return Response(
                {"detail": "Invalid credentials."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        if user.email_verified:
            return Response(
                {"detail": "This account is already verified. Update your email from your profile settings instead."},
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
                {"detail": "A verification link was already sent. Please check your inbox before requesting another."},
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

    
class MeView(APIView):
    def get(self, request):
        serializer = UserSerializer(request.user)
        return Response(serializer.data)