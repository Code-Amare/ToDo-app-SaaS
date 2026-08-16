from django.conf import settings
from django.template.loader import render_to_string
from .send_email import send_email

BASE_URL = settings.BASE_URL

def send_verification_email(user, verification_code):
    verify_url = f"https://{BASE_URL}/accounts/email/verify/{verification_code.code}/"

    html_content = render_to_string(
        "accounts/emails/verify_email.html",
        {
            "user": user,
            "verify_url": verify_url,
        },
    )

    send_email(
        to_email=user.email,
        subject="Verify your email",
        html_content=html_content,
    )


def send_update_pending_email(user, verification_code):
    verify_url = f"https://{BASE_URL}/accounts/unverified-email/update/{verification_code.code}/"

    html_content = render_to_string(
        "accounts/emails/update_pending_email.html",
        {
            "user": user,
            "verify_url": verify_url,
        },
    )

    send_email(
        to_email=user.email,
        subject="Confirm your updated email",
        html_content=html_content,
    )


def send_welcome_email(user):
    html_content = render_to_string(
        "emails/welcome.html",
        {"user": user},
    )

    send_email(
        to_email=user.email,
        subject="Welcome aboard!",
        html_content=html_content,
    )


def send_trial_ending_email(user, subscription):
    html_content = render_to_string(
        "emails/trial_ending.html",
        {
            "user": user,
            "trial_end_date": subscription.trial_end_date,
            "billing_url": f"https://{BASE_URL}/billing",
        },
    )

    send_email(
        to_email=user.email,
        subject="Your free trial is ending soon",
        html_content=html_content,
    )


def send_trial_expired_email(user):
    html_content = render_to_string(
        "emails/trial_expired.html",
        {
            "user": user,
            "billing_url": f"https://{BASE_URL}/billing",
        },
    )

    send_email(
        to_email=user.email,
        subject="Your trial has ended",
        html_content=html_content,
    )