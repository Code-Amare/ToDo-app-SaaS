from django.db import models
from cloudinary.models import CloudinaryField
from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    email = models.EmailField(unique=True)
    email_verified = models.BooleanField(default=False)
    profile_pic = CloudinaryField(
        "SaaS/todo/profile_pic",
        blank=True,
        null=True,
    )
