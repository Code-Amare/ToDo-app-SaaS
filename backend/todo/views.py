from rest_framework import viewsets, permissions
from drf_spectacular.utils import extend_schema_view, extend_schema
from .models import Todo
from .serializers import TodoSerializer
from rest_framework.response import Response
from rest_framework import status
from rest_framework.views import APIView


@extend_schema_view(
    list=extend_schema(operation_id="list_todos", summary="List your todos"),
    retrieve=extend_schema(operation_id="get_todo", summary="Get a single todo"),
    create=extend_schema(operation_id="create_todo", summary="Create a todo"),
    update=extend_schema(operation_id="update_todo", summary="Replace a todo"),
    partial_update=extend_schema(
        operation_id="partial_update_todo", summary="Update part of a todo"
    ),
    destroy=extend_schema(operation_id="delete_todo", summary="Delete a todo"),
)
class TodoViewSet(viewsets.ModelViewSet):
    serializer_class = TodoSerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_fields = ["completed", "priority"]

    def get_queryset(self):
        return Todo.objects.filter(user=self.request.user).select_related("user")

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class TestView(APIView):
    def get(self, request):
        from django.db import connection

        print("CURRENT SCHEMA:", connection.schema_name)
        return Response({"detail": "Tenant work"}, status=status.HTTP_200_OK)
