from django.urls import path
from .views import (
    RegisterView,
    LogoutView,
    SendEmailVerificationView,
    UpdatePendingEmailRequestView,
    VerifyEmailView,
    LoginView,
    RequestPasswordResetView,
    ConfirmPasswordResetView,
    ChangePasswordView,
    MeView,
)


urlpatterns = [
    path("register/", RegisterView.as_view()),
    path("login/", LoginView.as_view()),
    path("logout/", LogoutView.as_view()),
    path("email/verify/", SendEmailVerificationView.as_view()),
    path("email/verify/<uuid:code>/", VerifyEmailView.as_view(), name="verify-email"),
    path("email/update/request/", UpdatePendingEmailRequestView.as_view()),
    path("password-reset/", RequestPasswordResetView.as_view()),
    path("password-reset/<uuid:code>/", ConfirmPasswordResetView.as_view()),
    path("change-password/", ChangePasswordView.as_view()),
    path("me/", MeView.as_view()),
]
