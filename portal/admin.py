from django.contrib import admin
from django.utils import timezone

from .models import (
    CustomerProfile,
    DiagnosticFileAsset,
    EngineerProfile,
    HelpRequest,
    MercedesECURecord,
    RequiredVehiclePart,
    VINDecodeRecord,
    WorkshopRecord,
)


@admin.register(CustomerProfile)
class CustomerProfileAdmin(admin.ModelAdmin):
    list_display = ("full_name", "phone_number", "email", "state", "city", "vehicle_brand", "vehicle_model")
    search_fields = ("full_name", "phone_number", "email", "vin_number")
    list_filter = ("state", "vehicle_brand")


@admin.action(description="Approve selected engineers")
def approve_engineers(modeladmin, request, queryset):
    approvable = queryset.exclude(verification_document="")
    updated = approvable.update(
        is_approved=True,
        verification_status=EngineerProfile.VerificationStatus.APPROVED,
        reviewed_by=request.user,
        reviewed_at=timezone.now(),
    )
    modeladmin.message_user(request, f"{updated} engineer application(s) approved with submitted ID documents.")


@admin.action(description="Reject selected engineer applications")
def reject_engineers(modeladmin, request, queryset):
    queryset.update(
        is_approved=False,
        verification_status=EngineerProfile.VerificationStatus.REJECTED,
        reviewed_by=request.user,
        reviewed_at=timezone.now(),
    )


@admin.register(EngineerProfile)
class EngineerProfileAdmin(admin.ModelAdmin):
    list_display = ("full_name", "specialization", "id_type", "verification_status", "state", "is_available", "is_approved")
    list_filter = ("verification_status", "is_approved", "is_available", "state", "specialization")
    search_fields = ("full_name", "phone_number", "email", "specialization", "id_number")
    readonly_fields = ("reviewed_by", "reviewed_at")
    actions = [approve_engineers, reject_engineers]


@admin.register(HelpRequest)
class HelpRequestAdmin(admin.ModelAdmin):
    list_display = ("vehicle_registration_number", "customer", "state", "urgency", "status", "assigned_engineer", "created_at")
    list_filter = ("status", "urgency", "state", "created_at")
    search_fields = ("vehicle_registration_number", "vin_number", "customer__full_name", "customer__phone_number")
    autocomplete_fields = ("customer", "assigned_engineer")


@admin.register(WorkshopRecord)
class WorkshopRecordAdmin(admin.ModelAdmin):
    list_display = ("vehicle_registration_number", "customer_name", "service_date", "next_service_date", "engineer_assigned", "cost")
    list_filter = ("service_date", "next_service_date")
    search_fields = ("vehicle_registration_number", "vin", "customer_name", "contact_number")
    autocomplete_fields = ("engineer_assigned",)


@admin.register(MercedesECURecord)
class MercedesECURecordAdmin(admin.ModelAdmin):
    list_display = ("vin", "ecu_name", "ecu_hardware_number", "ecu_software_number", "tool_used", "flash_date", "engineer_assigned")
    list_filter = ("tool_used", "flash_date")
    search_fields = ("vin", "ecu_name", "ecu_hardware_number", "ecu_software_number", "cff_file_name")
    autocomplete_fields = ("engineer_assigned",)


@admin.register(DiagnosticFileAsset)
class DiagnosticFileAssetAdmin(admin.ModelAdmin):
    list_display = ("original_file_name", "file_type", "ecu_name", "compatible_models", "hardware_number", "software_number", "created_at")
    list_filter = ("file_type", "compatible_brand", "created_at")
    search_fields = (
        "original_file_name", "ecu_name", "ecu_part_number", "hardware_number",
        "software_number", "compatible_models", "engine_or_variant",
    )
    readonly_fields = ("original_file_name", "extracted_text_preview", "uploaded_by", "created_at")


@admin.register(RequiredVehiclePart)
class RequiredVehiclePartAdmin(admin.ModelAdmin):
    list_display = ("part_number", "part_name", "category", "compatible_make", "compatible_model", "year_from", "year_to", "is_required")
    list_filter = ("category", "is_required", "compatible_make")
    search_fields = ("part_number", "part_name", "compatible_model", "exact_vin", "engine_or_variant")
    readonly_fields = ("added_by", "created_at")


@admin.register(VINDecodeRecord)
class VINDecodeRecordAdmin(admin.ModelAdmin):
    list_display = ("vin", "make", "model", "model_year", "source", "api_available", "requested_by", "created_at")
    list_filter = ("api_available", "source", "created_at")
    search_fields = ("vin", "wmi", "make", "model", "part_number_query")
    readonly_fields = ("created_at",)


admin.site.site_header = "AutoMind Diagnostics Administration"
admin.site.site_title = "AutoMind Admin"
admin.site.index_title = "Service Operations"
