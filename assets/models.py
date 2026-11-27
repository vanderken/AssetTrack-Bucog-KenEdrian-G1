from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone


class Department(models.Model):
    name = models.CharField(max_length=120, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    is_custom = models.BooleanField(default=False)

    class Meta:
        verbose_name_plural = "Categories"
        ordering = ["name"]

    def __str__(self):
        return self.name


class SystemSettings(models.Model):
    self_checkout_allowed = models.BooleanField(default=False)
    overdue_days = models.PositiveIntegerField(default=7)

    field_purchase_date_enabled = models.BooleanField(default=True)
    field_brand_enabled = models.BooleanField(default=True)
    field_location_enabled = models.BooleanField(default=False)
    field_notes_enabled = models.BooleanField(default=True)
    field_warranty_expiry_enabled = models.BooleanField(default=False)

    class Meta:
        verbose_name_plural = "System Settings"

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return "System Settings"


class Device(models.Model):
    STATUS_AVAILABLE = "available"
    STATUS_BORROWED = "borrowed"
    STATUS_REPAIR = "repair"
    STATUS_CHOICES = [
        (STATUS_AVAILABLE, "Available"),
        (STATUS_BORROWED, "Borrowed"),
        (STATUS_REPAIR, "Under Repair"),
    ]

    company = models.ForeignKey(
        "accounts.Company",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="devices",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_devices",
    )
    asset_tag = models.CharField(max_length=50, unique=True, verbose_name="Asset Tag")
    serial_number = models.CharField(max_length=100, blank=True, null=True, unique=True, verbose_name="Serial Number")
    model_name = models.CharField(max_length=150, verbose_name="Model")
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="devices")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_AVAILABLE)

    brand = models.CharField(max_length=100, blank=True)
    purchase_date = models.DateField(null=True, blank=True)
    warranty_expiry = models.DateField(null=True, blank=True)
    location = models.CharField(max_length=150, blank=True)
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["asset_tag"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["category"]),
            models.Index(fields=["company"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=["available", "borrowed", "repair"]),
                name="device_status_valid",
            ),
        ]

    def __str__(self):
        return f"{self.asset_tag} - {self.model_name}"

    def save(self, *args, **kwargs):
        if self.serial_number is not None:
            cleaned = self.serial_number.strip()
            self.serial_number = cleaned if cleaned else None
        super().save(*args, **kwargs)

    @property
    def display_category(self):
        return self.category.name if self.category else ""

    @property
    def current_checkout(self):
        if hasattr(self, "prefetched_active_checkouts"):
            return self.prefetched_active_checkouts[0] if self.prefetched_active_checkouts else None
        return self.checkouts.filter(status=Checkout.STATUS_ACTIVE).select_related("employee").first()


class Checkout(models.Model):
    STATUS_PENDING = "pending"
    STATUS_ACTIVE = "active"
    STATUS_RETURNED = "returned"
    STATUS_REJECTED = "rejected"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending Approval"),
        (STATUS_ACTIVE, "Active"),
        (STATUS_RETURNED, "Returned"),
        (STATUS_REJECTED, "Rejected"),
    ]

    CONDITION_GOOD = "good"
    CONDITION_MINOR_WEAR = "minor_wear"
    CONDITION_DAMAGED = "damaged"
    CONDITION_NEEDS_REPAIR = "needs_repair"
    CONDITION_CHOICES = [
        (CONDITION_GOOD, "Good"),
        (CONDITION_MINOR_WEAR, "Minor wear"),
        (CONDITION_DAMAGED, "Damaged"),
        (CONDITION_NEEDS_REPAIR, "Needs repair"),
    ]

    company = models.ForeignKey(
        "accounts.Company",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="checkouts",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_checkouts",
    )
    device = models.ForeignKey(
        Device,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="checkouts",
    )
    requested_device_name = models.CharField(
        max_length=150,
        blank=True,
        verbose_name="Requested Device / Model",
    )
    requested_category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="requested_checkouts",
    )
    employee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="checkouts")
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="approved_checkouts"
    )

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    requested_at = models.DateTimeField(auto_now_add=True)
    checked_out_at = models.DateTimeField(null=True, blank=True)
    due_date = models.DateField(null=True, blank=True)
    returned_at = models.DateTimeField(null=True, blank=True)
    return_condition = models.CharField(
        max_length=20,
        choices=CONDITION_CHOICES,
        default=CONDITION_GOOD,
        blank=True,
        verbose_name="Condition on Return",
    )
    purpose = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-requested_at"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["employee", "status"]),
            models.Index(fields=["company"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=["pending", "active", "returned", "rejected"]),
                name="checkout_status_valid",
            ),
            models.CheckConstraint(
                condition=(
                    Q(status__in=["pending", "active", "rejected"])
                    | Q(return_condition__in=[
                        "good", "minor_wear", "damaged", "needs_repair",
                    ])
                ),
                name="returned_checkout_condition_valid",
            ),
            models.CheckConstraint(
                condition=Q(return_condition__in=[
                    "good", "minor_wear", "damaged", "needs_repair",
                ]),
                name="return_condition_valid",
            ),
        ]

    @property
    def is_overdue(self):
        if self.status != self.STATUS_ACTIVE or not self.due_date:
            return False
        return timezone.localdate() > self.due_date

    def __str__(self):
        target = self.device.asset_tag if self.device else (self.requested_device_name or "Unspecified")
        return f"{target} -> {self.employee.username} ({self.status})"


class MaintenanceLog(models.Model):
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name="maintenance_logs")
    reported_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="reported_logs")
    description = models.TextField()
    image = models.ImageField(upload_to="maintenance_photos/", null=True, blank=True)
    is_resolved = models.BooleanField(default=False)
    reported_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-reported_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(is_resolved=False) | Q(resolved_at__isnull=False),
                name="resolved_log_has_timestamp",
            ),
        ]

    def __str__(self):
        return f"{self.device.asset_tag} log #{self.pk}"
