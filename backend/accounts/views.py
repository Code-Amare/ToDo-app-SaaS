from django.db import transaction, connection
from django_tenants.utils import schema_context
from django.contrib.auth import login, logout
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from tenants.models import Tenant, Domain, Subscription, Plan
from .serializers import RegisterSerializer, UserSerializer
from django.utils import timezone
from datetime import timedelta
from django.conf import settings


BASE_URL = settings.BASE_URL

class RegisterView(APIView):
    permission_classes = []  # public endpoint

    def post(self, request, *args, **kwargs):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated_data = serializer.validated_data

        base_slug = validated_data["username"].lower()
        schema_name = base_slug
        domain_url = f"{base_slug}.{BASE_URL}"

        trial_end = timezone.now() + timedelta(days=settings.TRIAL_DAYS)

        with transaction.atomic():
            # accounts is shared now — user is created directly, no schema_context needed
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



class MeView(APIView):
    def get(self, request, *args, **kwargs):
        serializer = UserSerializer(request.user)
        return Response(serializer.data)