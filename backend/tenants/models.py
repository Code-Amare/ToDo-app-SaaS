from django.db import models
from django.utils import timezone
from datetime import timedelta
from django_tenants.models import TenantMixin, DomainMixin

class Tenant(TenantMixin):
    name = models.CharField(max_length=100)
    created_on = models.DateField(auto_now_add=True)

    # default true, schema will be automatically created and synced when it is saved
    auto_create_schema = True

class Domain(DomainMixin):
    pass



class Plan(models.Model):
    class BillingPeriod(models.TextChoices):
        MONTHLY = "monthly", "Monthly"
        YEARLY = "yearly", "Yearly"

    title = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=8, decimal_places=2)
    billing_period = models.CharField(max_length=10, choices=BillingPeriod.choices)
    stripe_price_id = models.CharField(max_length=100)  # price_xxx from Stripe dashboard

    def __str__(self):
        return f"{self.title} ({self.billing_period})"


class Subscription(models.Model):
    class Status(models.TextChoices):
        TRIALING = "trialing", "Trialing"
        ACTIVE = "active", "Active"
        PAST_DUE = "past_due", "Past due"
        CANCELED = "canceled", "Canceled"
        EXPIRED = "expired", "Expired"

    tenant = models.OneToOneField(
        "tenants.Tenant", on_delete=models.CASCADE, related_name="subscription"
    )
    plan = models.ForeignKey(
        Plan, on_delete=models.PROTECT, related_name="subscriptions",
        null=True, blank=True,  # null while on trial — no plan chosen yet
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.TRIALING)

    trial_end_date = models.DateTimeField(null=True, blank=True)
    current_period_end = models.DateTimeField(null=True, blank=True)

    stripe_customer_id = models.CharField(max_length=100, blank=True, null=True)
    stripe_subscription_id = models.CharField(max_length=100, blank=True, null=True)

    def __str__(self):
        return f"{self.tenant.schema_name} — {self.status}"

    @property
    def is_trialing(self):
        return self.status == self.Status.TRIALING and (
            self.trial_end_date is None or self.trial_end_date > timezone.now()
        )