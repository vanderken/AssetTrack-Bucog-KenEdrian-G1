from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.core.exceptions import ValidationError
from assets.models import Department
from .models import User, Company


class RegistrationForm(UserCreationForm):
    email = forms.EmailField(required=True)
    first_name = forms.CharField(required=True, max_length=150)
    last_name = forms.CharField(required=True, max_length=150)
    role = forms.ChoiceField(choices=User.ROLE_CHOICES)
    department = forms.ModelChoiceField(
        queryset=Department.objects.all(),
        required=False,
        empty_label="-- No department --",
    )

    class Meta:
        model = User
        fields = [
            "username", "first_name", "last_name", "email", "role", "department",
            "password1", "password2",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if name == "role":
                field.widget.attrs["class"] = "form-select"
            else:
                field.widget.attrs["class"] = "form-control"

    def clean_email(self):
        email = self.cleaned_data.get("email", "").strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError("An account with this email already exists.")
        return email

    def clean_username(self):
        username = self.cleaned_data.get("username", "").strip()
        if User.objects.filter(username__iexact=username).exists():
            raise ValidationError("This username is already taken.")
        return username


class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["first_name", "last_name", "email", "contact_number", "department", "profile_photo"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if name != "profile_photo":
                field.widget.attrs["class"] = "form-control"

    def clean_email(self):
        email = self.cleaned_data.get("email", "").strip().lower()
        if User.objects.exclude(pk=self.instance.pk).filter(email__iexact=email).exists():
            raise ValidationError("An account with this email already exists.")
        return email


class CompanyForm(forms.ModelForm):
    class Meta:
        model = Company
        fields = ["name", "address", "code"]
        widgets = {
            "address": forms.Textarea(attrs={"rows": 3, "placeholder": "Enter company address"}),
            "code": forms.TextInput(attrs={"placeholder": "e.g. CMP-A83B1C"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")


class CompanyJoinForm(forms.Form):
    company_code = forms.CharField(
        label="Company Code",
        max_length=32,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. CMP-A83B1C"}),
    )
