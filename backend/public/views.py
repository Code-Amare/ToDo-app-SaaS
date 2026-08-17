from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from drf_spectacular.utils import extend_schema, OpenApiResponse


class TestView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        operation_id="test",
        responses={200: OpenApiResponse(description="Test if API works")},
    )
    def get(self, request):
        return Response({"detail": "backend works."}, status=status.HTTP_200_OK)
