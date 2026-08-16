from threading import Thread
from sib_api_v3_sdk import ApiClient, Configuration
from sib_api_v3_sdk.api.transactional_emails_api import TransactionalEmailsApi
from sib_api_v3_sdk.models import SendSmtpEmail
from sib_api_v3_sdk.rest import ApiException
from django.conf import settings


def send_email(
    to_email: str,
    subject: str,
    html_content: str, 
    sender_name: str = settings.DEFAULT_SENDER_NAME,
    sender_email: str = None,
):

    sender_email = sender_email or settings.BREVO_SENDER_EMAIL
    if not sender_email:
        raise ValueError(
            "BREVO_SENDER_EMAIL must be set in environment variables or passed to the function"
        )

    api_key = settings.BREVO_API_KEY
    if not api_key:
        raise ValueError("BREVO_API_KEY must be set in environment variables")

    def _send():
        try:
            configuration = Configuration()
            configuration.api_key["api-key"] = api_key
            api_instance = TransactionalEmailsApi(ApiClient(configuration))

            email = SendSmtpEmail(
                to=[{"email": to_email}],
                sender={"name": sender_name, "email": sender_email},
                subject=subject,
                html_content=html_content,
            )


            api_instance.send_transac_email(email)
        except ApiException as e:
            print("Brevo send_email error:", e)

    Thread(target=_send, daemon=True).start()