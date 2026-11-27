import secrets
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import Q


def generate_company_code():
    return f"CMP-{secrets.token_hex(3).upper()}"


class Company(models.Model):
    name = models.CharField(max_length=200)
    address = models.TextField(blank=True)
    code = models.CharField(max_length=32, unique=True, default=generate_company_code)
    admin = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="administered_companies",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    def regenerate_code(self):
        new_code = generate_company_code()
        while Company.objects.filter(code=new_code).exclude(pk=self.pk).exists():
            new_code = generate_company_code()
        self.code = new_code
        self.save(update_fields=["code", "updated_at"])
        return self.code


class User(AbstractUser):
    ROLE_ADMIN = "admin"
    ROLE_EMPLOYEE = "employee"
    ROLE_CHOICES = [
        (ROLE_ADMIN, "IT Admin"),
        (ROLE_EMPLOYEE, "Employee"),
    ]

    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_EMPLOYEE)
    contact_number = models.CharField(max_length=20, blank=True)
    company = models.ForeignKey(
        Company,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="members",
    )
    department = models.ForeignKey(
        "assets.Department", on_delete=models.SET_NULL, null=True, blank=True, related_name="members"
    )
    profile_photo = models.ImageField(upload_to="profile_photos/", null=True, blank=True)

    class Meta(AbstractUser.Meta):
        constraints = [
            models.CheckConstraint(
                condition=Q(role__in=["admin", "employee"]),
                name="user_role_valid",
            ),
        ]

    @property
    def is_admin_role(self):
        return self.role == self.ROLE_ADMIN

    def __str__(self):
        full = self.get_full_name()
        if full:
            return f"{full} ({self.username})"
        return self.username


class CompanyMembershipRequest(models.Model):
    TYPE_JOIN = "join"
    TYPE_LEAVE = "leave"
    TYPE_CHOICES = [
        (TYPE_JOIN, "Join"),
        (TYPE_LEAVE, "Leave"),
    ]

    STATUS_PENDING = "pending"
    STATUS_APPROVED = "approved"
    STATUS_REJECTED = "rejected"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_REJECTED, "Rejected"),
    ]

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="membership_requests",
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="company_requests",
    )
    request_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default=TYPE_JOIN)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user.username} - {self.request_type} - {self.status}"
