from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import TodoViewSet, TestView

router = DefaultRouter()
router.register("todos", TodoViewSet, basename="todo")

urlpatterns = [
    path("", include(router.urls)),
    path("test/", TestView.as_view()),
]
