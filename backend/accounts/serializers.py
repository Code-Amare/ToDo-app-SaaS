from django.contrib.auth import get_user_model
from rest_framework import serializers
import cloudinary.uploader
from django.contrib.auth.password_validation import validate_password

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    profile_pic = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "email_verified",
            "profile_pic",
        ]
        read_only_fields = [
            "id",
            "email_verified",
            "profile_pic",
        ]

    def get_profile_pic(self, obj):
        if obj.profile_pic:
            return obj.profile_pic.url
        return None


class RegisterSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(required=True)
    password = serializers.CharField(
        write_only=True,
        validators=[validate_password],
    )

    class Meta:
        model = User
        fields = [
            "username",
            "email",
            "password",
            "first_name",
            "last_name",
        ]

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError(
                "A user with this email already exists."
            )
        return value

    def create(self, validated_data):
        user = User.objects.create_user(
            username=validated_data["username"],
            email=validated_data["email"],
            password=validated_data["password"],
            first_name=validated_data.get("first_name", ""),
            last_name=validated_data.get("last_name", ""),
        )
        return user



class UpdateUserSerializer(serializers.ModelSerializer):
    profile_pic = serializers.ImageField(required=False, allow_null=True)
    remove_profile_pic = serializers.BooleanField(write_only=True, required=False, default=False)

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "email_verified",
            "profile_pic",
            "remove_profile_pic",
        ]
        read_only_fields = [
            "id",
            "email",
            "email_verified",
        ]

    def validate(self, attrs):
        remove_pic = attrs.get("remove_profile_pic", False)
        new_pic = attrs.get("profile_pic", None)
        instance = self.instance

        has_field_change = any(
            attrs.get(field) is not None and getattr(instance, field) != attrs.get(field)
            for field in ("username", "first_name", "last_name")
        )
        has_pic_change = new_pic is not None or (remove_pic and instance.profile_pic)

        if not has_field_change and not has_pic_change:
            raise serializers.ValidationError("No changes detected.")

        return attrs

    def update(self, instance, validated_data):
        remove_pic = validated_data.pop("remove_profile_pic", False)
        new_pic = validated_data.pop("profile_pic", None)

        if remove_pic or new_pic is not None:
            if instance.profile_pic:
                cloudinary.uploader.destroy(instance.profile_pic.public_id)
            instance.profile_pic = None

        if new_pic is not None:
            instance.profile_pic = new_pic

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        instance.save()
        return instance