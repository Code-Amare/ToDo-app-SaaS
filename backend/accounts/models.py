from django.db import models
from cloudinary.models import CloudinaryField
from django.contrib.auth.models import AbstractUser
from django.utils import timezone
from datetime import timedelta
import uuid


class User(AbstractUser):
    email = models.EmailField(unique=True)
    email_verified = models.BooleanField(default=False)
    profile_pic = CloudinaryField(
        "SaaS/todo/profile_pic",
        blank=True,
        null=True,
    )   

    def save(self, *args, **kwargs):
        self.username = self.username.strip().lower()
        self.email = self.email.strip().lower()

        super().save(*args, **kwargs)



class BaseVerificationCode(models.Model):
    code = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        abstract = True

    def __str__(self):
        return f"{self.user.username} — {self.code}"

    @property
    def is_valid(self):
        return self.expires_at > timezone.now() 

    def mark_used(self):
        self.delete()

    @classmethod
    def create_for_user(cls, user, valid_minutes=5):
        cls.objects.filter(user=user).delete()
        return cls.objects.create(
            user=user,
            expires_at=timezone.now() + timedelta(minutes=valid_minutes),
        )


class EmailVerificationCode(BaseVerificationCode):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="email_verification_code",
    )
 