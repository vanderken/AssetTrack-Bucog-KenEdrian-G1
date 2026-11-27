from django import forms
from django.utils import timezone

from .models import Device, Category, Department, Checkout, MaintenanceLog, SystemSettings


def _bootstrapify(fields):
    for name, field in fields.items():
        widget = field.widget
        if isinstance(widget, forms.CheckboxInput):
            widget.attrs["class"] = "form-check-input"
        elif isinstance(widget, forms.Select):
            widget.attrs["class"] = "form-select"
        else:
            widget.attrs.setdefault("class", "form-control")


DEFAULT_CATEGORIES = [
    "Laptop",
    "Computer Parts",
    "Tools",
    "Desktop",
    "Monitor",
    "Cell Phone",
    "Charger",
    "Peripheral",
]


class DeviceForm(forms.ModelForm):
    CUSTOM_CATEGORY_VALUE = "__custom__"

    category = forms.ChoiceField(
        label="Category",
        error_messages={"required": "Please select a category or choose '+ Add Custom Category / Other'."},
    )
    custom_category = forms.CharField(
        label="Custom Category Name",
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={
            "placeholder": "Enter custom category name (e.g. Server, Tablet, Audio Equipment)",
            "autocomplete": "off",
        }),
    )

    class Meta:
        model = Device
        fields = [
            "asset_tag", "serial_number", "model_name",
            "status", "brand", "purchase_date", "warranty_expiry", "location", "notes",
        ]
        widgets = {
            "serial_number": forms.TextInput(attrs={"placeholder": "Optional serial number"}),
            "purchase_date": forms.DateInput(attrs={"type": "date"}),
            "warranty_expiry": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, settings_obj=None, **kwargs):
        super().__init__(*args, **kwargs)
        choices = [("", "-- Select Category --")]
        try:
            for name in DEFAULT_CATEGORIES:
                Category.objects.get_or_create(name=name)

            all_cats = list(Category.objects.exclude(name__iexact="Other / Custom"))
            cat_by_name = {c.name.strip().lower(): c for c in all_cats}
            added_ids = set()

            for name in DEFAULT_CATEGORIES:
                c = cat_by_name.get(name.lower())
                if c:
                    choices.append((str(c.pk), c.name))
                    added_ids.add(c.pk)

            remaining = sorted([c for c in all_cats if c.pk not in added_ids], key=lambda x: x.name.lower())
            for c in remaining:
                choices.append((str(c.pk), c.name))
        except Exception:
            for idx, name in enumerate(DEFAULT_CATEGORIES, 1):
                choices.append((str(idx), name))

        choices.append((self.CUSTOM_CATEGORY_VALUE, "+ Add Custom Category / Other"))
        self.fields["category"].choices = choices

        if self.instance and self.instance.pk and self.instance.category_id:
            self.initial["category"] = str(self.instance.category_id)

        if settings_obj:
            if not settings_obj.field_purchase_date_enabled:
                self.fields.pop("purchase_date")
            if not settings_obj.field_brand_enabled:
                self.fields.pop("brand")
            if not settings_obj.field_location_enabled:
                self.fields.pop("location")
            if not settings_obj.field_notes_enabled:
                self.fields.pop("notes")
            if not settings_obj.field_warranty_expiry_enabled:
                self.fields.pop("warranty_expiry")
        _bootstrapify(self.fields)

        ordered_keys = []
        for key in self.fields:
            if key in ("category", "custom_category"):
                continue
            ordered_keys.append(key)
            if key == "model_name":
                ordered_keys.extend(["category", "custom_category"])
        self.order_fields(ordered_keys)

    def clean_serial_number(self):
        sn = (self.cleaned_data.get("serial_number") or "").strip()
        return sn if sn else None

    def clean(self):
        cleaned_data = super().clean()
        cat_val = cleaned_data.get("category")
        custom_name = (cleaned_data.get("custom_category") or "").strip()
        if cat_val == self.CUSTOM_CATEGORY_VALUE:
            if not custom_name:
                self.add_error("custom_category", "Please enter your custom category name.")
        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        cat_val = self.cleaned_data["category"]
        if cat_val == self.CUSTOM_CATEGORY_VALUE:
            custom_name = self.cleaned_data["custom_category"].strip()
            cat_obj = Category.objects.filter(name__iexact=custom_name).first()
            if not cat_obj:
                cat_obj = Category.objects.create(name=custom_name, is_custom=True)
            instance.category = cat_obj
        else:
            instance.category = Category.objects.get(pk=int(cat_val))
        if commit:
            instance.save()
        return instance


class CheckoutRequestForm(forms.ModelForm):
    requested_device_name = forms.CharField(
        max_length=150,
        required=False,
        label="Requested Device / Model Name",
        widget=forms.TextInput(attrs={"placeholder": "e.g. MacBook Pro 16\" M3, Dell UltraSharp 27\""}),
    )
    requested_category = forms.ModelChoiceField(
        queryset=Category.objects.all().order_by("name"),
        required=False,
        label="Device Category (Optional)",
        empty_label="-- Select Category --",
    )

    class Meta:
        model = Checkout
        fields = ["device", "requested_device_name", "requested_category", "purpose"]
        widgets = {
            "purpose": forms.TextInput(attrs={"placeholder": "e.g. Remote work, Client presentation, Testing"}),
        }

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.company = company
        _bootstrapify(self.fields)
        device_qs = Device.objects.filter(status=Device.STATUS_AVAILABLE).select_related("category")
        if company:
            device_qs = device_qs.filter(company=company)
        self.fields["device"].queryset = device_qs
        self.fields["device"].required = False
        self.fields["device"].empty_label = "-- Select an Existing Available Device (Optional) --"
        self.fields["device"].label = "Existing Inventory Device"

    def clean(self):
        cleaned_data = super().clean()
        device = cleaned_data.get("device")
        req_name = (cleaned_data.get("requested_device_name") or "").strip()
        if not device and not req_name:
            raise forms.ValidationError("Please select an existing available device or enter the name of the new device you need.")
        if device:
            if device.status != Device.STATUS_AVAILABLE:
                self.add_error("device", "That device is not available to request.")
            if self.company is not None and device.company_id != self.company.pk:
                self.add_error("device", "That device does not belong to your company.")
        if device and req_name:
            cleaned_data["requested_device_name"] = ""
            cleaned_data["requested_category"] = None
        return cleaned_data


class CheckoutAssignForm(forms.ModelForm):
    class Meta:
        model = Checkout
        fields = ["device", "employee", "due_date", "purpose"]
        widgets = {
            "due_date": forms.DateInput(attrs={"type": "date"}),
            "purpose": forms.TextInput(attrs={"placeholder": "e.g. Remote work, Client presentation, Project QA"}),
        }

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        _bootstrapify(self.fields)
        from accounts.models import User
        device_qs = Device.objects.filter(status=Device.STATUS_AVAILABLE).select_related("category")
        employee_qs = User.objects.filter(role=User.ROLE_EMPLOYEE)
        if company:
            device_qs = device_qs.filter(company=company)
            employee_qs = employee_qs.filter(company=company)
        self.fields["device"].queryset = device_qs
        self.fields["employee"].queryset = employee_qs
        self.fields["device"].empty_label = "-- Select Available Device --"
        self.fields["employee"].empty_label = "-- Select Company Employee --"
        self.fields["employee"].label_from_instance = lambda user: (
            f"{user.get_full_name()} (@{user.username})" if user.get_full_name() else f"@{user.username}"
        )

    def clean(self):
        cleaned_data = super().clean()
        device = cleaned_data.get("device")
        if device and Checkout.objects.filter(
            device=device, status=Checkout.STATUS_ACTIVE
        ).exists():
            self.add_error("device", "That device already has an active checkout.")
        return cleaned_data

    def clean_due_date(self):
        due_date = self.cleaned_data.get("due_date")
        if due_date and due_date < timezone.localdate():
            raise forms.ValidationError("Due date must be today or in the future.")
        return due_date


class CheckoutReturnForm(forms.Form):
    return_condition = forms.ChoiceField(choices=Checkout.CONDITION_CHOICES)
    next = forms.CharField(required=False)


class MaintenanceLogForm(forms.ModelForm):
    class Meta:
        model = MaintenanceLog
        fields = ["device", "description", "image"]
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        _bootstrapify(self.fields)
        device_qs = Device.objects.all().select_related("category")
        if company:
            device_qs = device_qs.filter(company=company)
        self.fields["device"].queryset = device_qs
        self.fields["device"].empty_label = "-- Select Device --"


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ["name", "is_custom"]


class DepartmentForm(forms.ModelForm):
    class Meta:
        model = Department
        fields = ["name"]


class SystemSettingsForm(forms.ModelForm):
    class Meta:
        model = SystemSettings
        fields = [
            "self_checkout_allowed", "overdue_days",
            "field_purchase_date_enabled", "field_brand_enabled",
            "field_location_enabled", "field_notes_enabled", "field_warranty_expiry_enabled",
        ]


def _apply_bootstrap_init(cls):
    original_init = cls.__init__
    def new_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        _bootstrapify(self.fields)
    cls.__init__ = new_init
    return cls


for _cls in [MaintenanceLogForm, CategoryForm, DepartmentForm, SystemSettingsForm]:
    _apply_bootstrap_init(_cls)
