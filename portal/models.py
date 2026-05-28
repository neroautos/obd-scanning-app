from django.contrib.auth.models import User
from django.core.validators import FileExtensionValidator, MinValueValidator
from django.db import models

from .utils import validate_vin


NIGERIAN_STATES = [
    ("Abia", "Abia"), ("Adamawa", "Adamawa"), ("Akwa Ibom", "Akwa Ibom"),
    ("Anambra", "Anambra"), ("Bauchi", "Bauchi"), ("Bayelsa", "Bayelsa"),
    ("Benue", "Benue"), ("Borno", "Borno"), ("Cross River", "Cross River"),
    ("Delta", "Delta"), ("Ebonyi", "Ebonyi"), ("Edo", "Edo"),
    ("Ekiti", "Ekiti"), ("Enugu", "Enugu"), ("FCT", "Federal Capital Territory"),
    ("Gombe", "Gombe"), ("Imo", "Imo"), ("Jigawa", "Jigawa"), ("Kaduna", "Kaduna"),
    ("Kano", "Kano"), ("Katsina", "Katsina"), ("Kebbi", "Kebbi"), ("Kogi", "Kogi"),
    ("Kwara", "Kwara"), ("Lagos", "Lagos"), ("Nasarawa", "Nasarawa"),
    ("Niger", "Niger"), ("Ogun", "Ogun"), ("Ondo", "Ondo"), ("Osun", "Osun"),
    ("Oyo", "Oyo"), ("Plateau", "Plateau"), ("Rivers", "Rivers"),
    ("Sokoto", "Sokoto"), ("Taraba", "Taraba"), ("Yobe", "Yobe"),
    ("Zamfara", "Zamfara"),
]


class CustomerProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="customer_profile")
    full_name = models.CharField(max_length=150, blank=True, default="")
    phone_number = models.CharField(max_length=30, blank=True, default="")
    email = models.EmailField(unique=True, blank=True, null=True)
    state = models.CharField(max_length=40, choices=NIGERIAN_STATES, blank=True, default="")
    city = models.CharField(max_length=80, blank=True, default="")
    vehicle_brand = models.CharField(max_length=80, blank=True, default="")
    vehicle_model = models.CharField(max_length=100, blank=True, default="")
    vehicle_year = models.PositiveIntegerField(blank=True, null=True)
    vin_number = models.CharField(max_length=17, validators=[validate_vin], blank=True, default="")

    def __str__(self):
        return self.full_name or self.email or self.phone_number or self.user.username

class EngineerProfile(models.Model):
    class VerificationStatus(models.TextChoices):
        PENDING = "pending", "Pending Review"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    class IDType(models.TextChoices):
        NIN = "nin", "National Identification Number (NIN)"
        DRIVERS_LICENCE = "drivers_licence", "Driver's Licence"
        PASSPORT = "passport", "International Passport"
        VOTERS_CARD = "voters_card", "Voter's Card"
        OTHER = "other", "Other Government ID"

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="engineer_profile")
    full_name = models.CharField(max_length=150)
    phone_number = models.CharField(max_length=30)
    email = models.EmailField(unique=True)
    state = models.CharField(max_length=40, choices=NIGERIAN_STATES)
    city = models.CharField(max_length=80)
    specialization = models.CharField(max_length=150)
    years_of_experience = models.PositiveIntegerField(default=0)
    is_available = models.BooleanField(default=True)
    is_approved = models.BooleanField(default=False)
    id_type = models.CharField(max_length=30, choices=IDType.choices, default=IDType.NIN)
    id_number = models.CharField(max_length=80, blank=True)
    verification_document = models.FileField(
        upload_to="engineer_verification/%Y/%m/",
        blank=True,
        validators=[FileExtensionValidator(["jpg", "jpeg", "png", "pdf"])],
    )
    verification_status = models.CharField(
        max_length=20, choices=VerificationStatus.choices, default=VerificationStatus.PENDING
    )
    verification_notes = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, blank=True, null=True, related_name="engineer_reviews"
    )
    reviewed_at = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return self.full_name

    @property
    def is_verified(self):
        return self.is_approved and self.verification_status == self.VerificationStatus.APPROVED


class HelpRequest(models.Model):
    class Urgency(models.TextChoices):
        NORMAL = "normal", "Normal"
        URGENT = "urgent", "Urgent"
        EMERGENCY = "emergency", "Emergency"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ASSIGNED = "assigned", "Assigned"
        IN_PROGRESS = "in_progress", "In Progress"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    customer = models.ForeignKey(CustomerProfile, on_delete=models.CASCADE, related_name="help_requests")
    assigned_engineer = models.ForeignKey(
        EngineerProfile,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="assigned_jobs",
        limit_choices_to={"is_approved": True, "verification_status": "approved"},
    )
    vehicle_registration_number = models.CharField(max_length=40)
    vin_number = models.CharField(max_length=17, validators=[validate_vin])
    car_brand = models.CharField(max_length=80)
    car_model = models.CharField(max_length=100)
    year = models.PositiveIntegerField()
    problem_description = models.TextField()
    attachment = models.FileField(
        upload_to="request_attachments/%Y/%m/",
        blank=True,
        validators=[FileExtensionValidator(["jpg", "jpeg", "png", "webp", "mp4", "mov"])],
    )
    state = models.CharField(max_length=40, choices=NIGERIAN_STATES)
    city = models.CharField(max_length=80)
    urgency = models.CharField(max_length=20, choices=Urgency.choices, default=Urgency.NORMAL)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.vehicle_registration_number} - {self.get_status_display()}"


class WorkshopRecord(models.Model):
    help_request = models.ForeignKey(
        HelpRequest, on_delete=models.SET_NULL, blank=True, null=True, related_name="workshop_records"
    )
    vehicle_registration_number = models.CharField(max_length=40)
    vin = models.CharField(max_length=17, validators=[validate_vin])
    customer_name = models.CharField(max_length=150)
    contact_number = models.CharField(max_length=30)
    service_date = models.DateField()
    next_service_date = models.DateField(blank=True, null=True)
    work_done = models.TextField()
    mileage = models.PositiveIntegerField(blank=True, null=True)
    cost = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    engineer_assigned = models.ForeignKey(
        EngineerProfile, on_delete=models.SET_NULL, blank=True, null=True, related_name="workshop_records"
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-service_date", "-created_at"]

    def __str__(self):
        return f"{self.vehicle_registration_number} - {self.service_date}"


class MercedesECURecord(models.Model):
    class Tool(models.TextChoices):
        DTS_MONACO = "dts_monaco", "DTS Monaco"
        VEDIAMO = "vediamo", "Vediamo"
        XENTRY = "xentry", "Xentry"
        OTHER = "other", "Other"

    help_request = models.ForeignKey(
        HelpRequest, on_delete=models.SET_NULL, blank=True, null=True, related_name="ecu_records"
    )
    vin = models.CharField(max_length=17, validators=[validate_vin])
    ecu_name = models.CharField(max_length=120)
    ecu_hardware_number = models.CharField(max_length=120)
    ecu_software_number = models.CharField(max_length=120)
    variant_coding_backup = models.TextField(blank=True)
    cff_file_name = models.CharField(max_length=180, blank=True)
    smr_d_or_cbf_file_used = models.CharField(max_length=180, blank=True)
    flash_date = models.DateField(blank=True, null=True)
    tool_used = models.CharField(max_length=20, choices=Tool.choices)
    coding_notes = models.TextField(blank=True)
    uploaded_file = models.FileField(upload_to="mercedes_ecu_files/%Y/%m/", blank=True)
    engineer_assigned = models.ForeignKey(
        EngineerProfile, on_delete=models.SET_NULL, blank=True, null=True, related_name="ecu_records"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Mercedes ECU record"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.vin} - {self.ecu_name}"


class DiagnosticFileAsset(models.Model):
    class FileType(models.TextChoices):
        CBF = "cbf", "CBF"
        SMR_D = "smr-d", "SMR-D"
        CFF = "cff", "CFF"

    file_type = models.CharField(max_length=10, choices=FileType.choices)
    uploaded_file = models.FileField(
        upload_to="diagnostic_file_library/%Y/%m/",
        validators=[FileExtensionValidator(["cbf", "smr-d", "smrd", "cff"])],
    )
    original_file_name = models.CharField(max_length=255, blank=True)
    ecu_name = models.CharField(max_length=120)
    ecu_part_number = models.CharField(max_length=120, blank=True)
    hardware_number = models.CharField(max_length=120, blank=True)
    software_number = models.CharField(max_length=120, blank=True)
    compatible_brand = models.CharField(max_length=80, default="Mercedes-Benz")
    compatible_models = models.CharField(
        max_length=255,
        help_text="Models or platforms confirmed for this file, e.g. W204 C-Class, W212 E-Class.",
    )
    year_range = models.CharField(max_length=80, blank=True, help_text="Optional confirmed years, e.g. 2012-2015.")
    engine_or_variant = models.CharField(max_length=150, blank=True)
    diagnostic_tool = models.CharField(max_length=100, blank=True, help_text="e.g. Vediamo or DTS Monaco.")
    compatibility_notes = models.TextField(blank=True)
    extracted_text_preview = models.TextField(blank=True, editable=False)
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Diagnostic file asset"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_file_type_display()} - {self.ecu_name} - {self.compatible_models}"


class RequiredVehiclePart(models.Model):
    class Category(models.TextChoices):
        ENGINE = "engine", "Engine"
        BRAKE = "brake", "Brake"
        ELECTRICAL = "electrical", "Electrical / ECU"
        SERVICE = "service", "Service / Maintenance"
        SUSPENSION = "suspension", "Suspension"
        TRANSMISSION = "transmission", "Transmission"
        OTHER = "other", "Other"

    part_name = models.CharField(max_length=150)
    part_number = models.CharField(max_length=120)
    category = models.CharField(max_length=30, choices=Category.choices, default=Category.OTHER)
    is_required = models.BooleanField(default=True)
    exact_vin = models.CharField(
        max_length=17,
        blank=True,
        validators=[validate_vin],
        help_text="Optional: restrict this part to one specific vehicle VIN.",
    )
    compatible_make = models.CharField(max_length=100, default="MERCEDES-BENZ")
    compatible_model = models.CharField(max_length=120)
    year_from = models.PositiveIntegerField(blank=True, null=True)
    year_to = models.PositiveIntegerField(blank=True, null=True)
    engine_or_variant = models.CharField(max_length=150, blank=True)
    quantity = models.PositiveIntegerField(default=1)
    notes = models.TextField(blank=True)
    added_by = models.ForeignKey(User, on_delete=models.SET_NULL, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Required vehicle part"
        ordering = ["category", "part_name"]

    def __str__(self):
        return f"{self.part_number} - {self.part_name}"


class VINDecodeRecord(models.Model):
    requested_by = models.ForeignKey(User, on_delete=models.SET_NULL, blank=True, null=True)
    vin = models.CharField(max_length=17, validators=[validate_vin])
    wmi = models.CharField(max_length=3)
    vds = models.CharField(max_length=6)
    vis = models.CharField(max_length=8)
    manufacturer = models.CharField(max_length=120, default="Decoder API not connected")
    model_year = models.CharField(max_length=40, default="Decoder API not connected")
    make = models.CharField(max_length=100, blank=True)
    model = models.CharField(max_length=120, blank=True)
    body_class = models.CharField(max_length=120, blank=True)
    engine = models.CharField(max_length=120, blank=True)
    transmission = models.CharField(max_length=120, blank=True)
    plant = models.CharField(max_length=150, blank=True)
    vehicle_type = models.CharField(max_length=120, blank=True)
    fuel_type = models.CharField(max_length=120, blank=True)
    source = models.CharField(max_length=80, default="NHTSA vPIC")
    api_available = models.BooleanField(default=False)
    api_message = models.TextField(blank=True)
    decoded_data = models.JSONField(blank=True, null=True)
    part_number_query = models.CharField(max_length=120, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.vin
