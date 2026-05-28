import re
import uuid

from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.db.models import Q

from .models import (
    CustomerProfile,
    DiagnosticFileAsset,
    EngineerProfile,
    HelpRequest,
    MercedesECURecord,
    RequiredVehiclePart,
    WorkshopRecord,
)
from .utils import decode_vin, validate_vin


class BootstrapFormMixin:
    def apply_bootstrap(self):
        for field in self.fields.values():
            css_class = "form-check-input" if isinstance(field.widget, forms.CheckboxInput) else "form-control"
            current = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = f"{current} {css_class}".strip()


class LoginForm(BootstrapFormMixin, AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "Email address or phone number"
        self.fields["username"].widget.attrs["placeholder"] = "Email, phone number or admin username"
        self.apply_bootstrap()

    def clean(self):
        identifier = self.cleaned_data.get("username", "").strip()
        user = None
        if identifier:
            user = User.objects.filter(email__iexact=identifier).first()
            if not user:
                customer = CustomerProfile.objects.filter(phone_number=identifier).select_related("user").first()
                engineer = EngineerProfile.objects.filter(phone_number=identifier).select_related("user").first()
                user = customer.user if customer else engineer.user if engineer else None
        if user:
            self.cleaned_data["username"] = user.username
        return super().clean()


class RegistrationBaseForm(BootstrapFormMixin, UserCreationForm):
    full_name = forms.CharField(max_length=150)
    phone_number = forms.CharField(max_length=30)
    email = forms.EmailField()
    state = forms.ChoiceField(choices=CustomerProfile._meta.get_field("state").choices)
    city = forms.CharField(max_length=80)

    class Meta:
        model = User
        fields = ["username", "full_name", "phone_number", "email", "state", "city", "password1", "password2"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_bootstrap()

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError("An account already uses this email address.")
        return email

    def create_user(self):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        user.save()
        return user


class CustomerRegistrationForm(BootstrapFormMixin, UserCreationForm):
    contact = forms.CharField(
        max_length=254,
        label="Email address or phone number",
        help_text="Use your email address or mobile number.",
    )

    class Meta:
        model = User
        fields = ["contact", "password1", "password2"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["contact"].widget.attrs["placeholder"] = "Email address or phone number"
        self.apply_bootstrap()

    def clean_contact(self):
        contact = self.cleaned_data["contact"].strip()
        if "@" in contact:
            contact = contact.lower()
            try:
                validate_email(contact)
            except ValidationError:
                raise ValidationError("Enter a valid email address or phone number.")
            if User.objects.filter(email__iexact=contact).exists():
                raise ValidationError("An account already uses this email address.")
            return contact
        digits = re.sub(r"\D", "", contact)
        if len(digits) < 7:
            raise ValidationError("Enter a valid email address or phone number.")
        if CustomerProfile.objects.filter(phone_number=contact).exists() or EngineerProfile.objects.filter(phone_number=contact).exists():
            raise ValidationError("An account already uses this phone number.")
        return contact

    @transaction.atomic
    def save(self, commit=True):
        contact = self.cleaned_data["contact"]
        is_email = "@" in contact
        user = super().save(commit=False)
        user.username = f"customer_{uuid.uuid4().hex[:20]}"
        user.email = contact if is_email else ""
        user.save()
        CustomerProfile.objects.create(
            user=user,
            phone_number="" if is_email else contact,
            email=contact if is_email else None,
        )
        return user


class CustomerProfileForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = CustomerProfile
        fields = [
            "full_name", "state", "city", "vehicle_brand", "vehicle_model",
            "vehicle_year", "vin_number",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.required = False
        self.apply_bootstrap()

    def clean_vin_number(self):
        vin = self.cleaned_data.get("vin_number", "").strip().upper()
        if vin:
            validate_vin(vin)
        return vin


class EngineerRegistrationForm(RegistrationBaseForm):
    specialization = forms.CharField(max_length=150)
    years_of_experience = forms.IntegerField(min_value=0)
    is_available = forms.BooleanField(required=False, initial=True, label="Available for assignments")
    id_type = forms.ChoiceField(choices=EngineerProfile.IDType.choices, label="Valid ID type")
    id_number = forms.CharField(max_length=80, label="ID number")
    verification_document = forms.FileField(
        label="Upload valid ID document",
        help_text="Accepted formats: JPG, PNG or PDF. Maximum size: 5 MB.",
    )

    class Meta(RegistrationBaseForm.Meta):
        fields = RegistrationBaseForm.Meta.fields[:-2] + [
            "specialization", "years_of_experience", "is_available", "id_type",
            "id_number", "verification_document", "password1", "password2"
        ]

    def clean_verification_document(self):
        document = self.cleaned_data["verification_document"]
        extension = document.name.rsplit(".", 1)[-1].lower() if "." in document.name else ""
        if extension not in {"jpg", "jpeg", "png", "pdf"}:
            raise ValidationError("Upload a JPG, PNG or PDF identity document.")
        if document.size > 5 * 1024 * 1024:
            raise ValidationError("Identity document must be no larger than 5 MB.")
        return document

    @transaction.atomic
    def save(self, commit=True):
        user = self.create_user()
        EngineerProfile.objects.create(
            user=user,
            full_name=self.cleaned_data["full_name"],
            phone_number=self.cleaned_data["phone_number"],
            email=self.cleaned_data["email"],
            state=self.cleaned_data["state"],
            city=self.cleaned_data["city"],
            specialization=self.cleaned_data["specialization"],
            years_of_experience=self.cleaned_data["years_of_experience"],
            is_available=self.cleaned_data["is_available"],
            id_type=self.cleaned_data["id_type"],
            id_number=self.cleaned_data["id_number"],
            verification_document=self.cleaned_data["verification_document"],
        )
        return user


class EngineerVerificationReviewForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = EngineerProfile
        fields = ["verification_status", "verification_notes"]
        widgets = {"verification_notes": forms.Textarea(attrs={"rows": 4})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["verification_status"].choices = [
            (EngineerProfile.VerificationStatus.APPROVED, "Approve engineer"),
            (EngineerProfile.VerificationStatus.REJECTED, "Reject application"),
        ]
        self.apply_bootstrap()

    def clean_verification_status(self):
        status = self.cleaned_data["verification_status"]
        if status == EngineerProfile.VerificationStatus.APPROVED and not self.instance.verification_document:
            raise ValidationError("A valid submitted ID document is required before approval.")
        return status


def validate_request_media(file):
    if file and file.size > 20 * 1024 * 1024:
        raise ValidationError("Attachment must be no larger than 20 MB.")


class HelpRequestForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = HelpRequest
        fields = [
            "vehicle_registration_number", "vin_number", "car_brand", "car_model", "year",
            "problem_description", "attachment", "state", "city", "urgency",
        ]
        widgets = {"problem_description": forms.Textarea(attrs={"rows": 5})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_bootstrap()

    def clean_attachment(self):
        file = self.cleaned_data.get("attachment")
        validate_request_media(file)
        return file


class AssignmentForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = HelpRequest
        fields = ["assigned_engineer"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        assigned_id = self.instance.assigned_engineer_id if self.instance else None
        self.fields["assigned_engineer"].queryset = EngineerProfile.objects.filter(
            Q(is_available=True) | Q(pk=assigned_id),
            is_approved=True,
            verification_status=EngineerProfile.VerificationStatus.APPROVED,
        ).order_by("state", "full_name")
        self.apply_bootstrap()


class JobStatusForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = HelpRequest
        fields = ["status"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["status"].choices = [
            (HelpRequest.Status.ASSIGNED, "Assigned"),
            (HelpRequest.Status.IN_PROGRESS, "In Progress"),
            (HelpRequest.Status.COMPLETED, "Completed"),
            (HelpRequest.Status.CANCELLED, "Cancelled"),
        ]
        self.apply_bootstrap()


class EngineerAvailabilityForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = EngineerProfile
        fields = ["is_available"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_bootstrap()


class WorkshopRecordForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = WorkshopRecord
        fields = [
            "help_request", "vehicle_registration_number", "vin", "customer_name",
            "contact_number", "service_date", "next_service_date", "work_done",
            "mileage", "cost", "engineer_assigned", "notes",
        ]
        widgets = {
            "service_date": forms.DateInput(attrs={"type": "date"}),
            "next_service_date": forms.DateInput(attrs={"type": "date"}),
            "work_done": forms.Textarea(attrs={"rows": 4}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user and not user.is_staff:
            engineer = user.engineer_profile
            self.fields["help_request"].queryset = HelpRequest.objects.filter(assigned_engineer=engineer)
            self.fields["engineer_assigned"].queryset = EngineerProfile.objects.filter(pk=engineer.pk)
            self.fields["engineer_assigned"].initial = engineer
        self.apply_bootstrap()


class MercedesECURecordForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = MercedesECURecord
        fields = [
            "help_request", "vin", "ecu_name", "ecu_hardware_number", "ecu_software_number",
            "variant_coding_backup", "cff_file_name", "smr_d_or_cbf_file_used",
            "flash_date", "tool_used", "coding_notes", "uploaded_file", "engineer_assigned",
        ]
        widgets = {
            "flash_date": forms.DateInput(attrs={"type": "date"}),
            "variant_coding_backup": forms.Textarea(attrs={"rows": 3}),
            "coding_notes": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user and not user.is_staff:
            engineer = user.engineer_profile
            self.fields["help_request"].queryset = HelpRequest.objects.filter(assigned_engineer=engineer)
            self.fields["engineer_assigned"].queryset = EngineerProfile.objects.filter(pk=engineer.pk)
            self.fields["engineer_assigned"].initial = engineer
        self.apply_bootstrap()

    def clean_uploaded_file(self):
        file = self.cleaned_data.get("uploaded_file")
        validate_request_media(file)
        return file


class DiagnosticFileAssetForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = DiagnosticFileAsset
        fields = [
            "file_type", "uploaded_file", "ecu_name", "ecu_part_number", "hardware_number",
            "software_number", "compatible_brand", "compatible_models", "year_range",
            "engine_or_variant", "diagnostic_tool", "compatibility_notes",
        ]
        widgets = {"compatibility_notes": forms.Textarea(attrs={"rows": 4})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_bootstrap()

    def clean_uploaded_file(self):
        file = self.cleaned_data.get("uploaded_file")
        validate_request_media(file)
        return file


class RequiredVehiclePartForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = RequiredVehiclePart
        fields = [
            "part_name", "part_number", "category", "is_required", "exact_vin",
            "compatible_make", "compatible_model", "year_from", "year_to",
            "engine_or_variant", "quantity", "notes",
        ]
        widgets = {"notes": forms.Textarea(attrs={"rows": 4})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_bootstrap()

    def clean(self):
        cleaned = super().clean()
        exact_vin = cleaned.get("exact_vin")
        if exact_vin:
            cleaned["exact_vin"] = exact_vin.upper().strip()
        year_from = cleaned.get("year_from")
        year_to = cleaned.get("year_to")
        if year_from and year_to and year_from > year_to:
            raise ValidationError("Year from must be earlier than or equal to year to.")
        return cleaned


class VINDecoderForm(BootstrapFormMixin, forms.Form):
    vin = forms.CharField(max_length=17, validators=[validate_vin], label="Vehicle Identification Number")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["vin"].widget.attrs["placeholder"] = "Enter 17-character VIN"
        self.apply_bootstrap()

    def decode(self):
        return decode_vin(self.cleaned_data["vin"])
