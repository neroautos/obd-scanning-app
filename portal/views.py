from functools import wraps
from pathlib import Path

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import FileResponse
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import (
    AssignmentForm,
    CustomerProfileForm,
    CustomerRegistrationForm,
    DiagnosticFileAssetForm,
    EngineerAvailabilityForm,
    EngineerRegistrationForm,
    EngineerVerificationReviewForm,
    HelpRequestForm,
    JobStatusForm,
    MercedesECURecordForm,
    RequiredVehiclePartForm,
    VINDecoderForm,
    WorkshopRecordForm,
)
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
from .utils import extract_readable_file_signatures


def customer_required(view_func):
    @wraps(view_func)
    @login_required
    def wrapped(request, *args, **kwargs):
        if not hasattr(request.user, "customer_profile"):
            raise PermissionDenied
        return view_func(request, *args, **kwargs)
    return wrapped


def approved_engineer_required(view_func):
    @wraps(view_func)
    @login_required
    def wrapped(request, *args, **kwargs):
        engineer = getattr(request.user, "engineer_profile", None)
        if not engineer or not engineer.is_verified:
            raise PermissionDenied
        return view_func(request, *args, **kwargs)
    return wrapped


def staff_required(view_func):
    @wraps(view_func)
    @login_required
    def wrapped(request, *args, **kwargs):
        if not request.user.is_staff:
            raise PermissionDenied
        return view_func(request, *args, **kwargs)
    return wrapped


def home(request):
    return render(request, "portal/home.html")


def register_customer(request):
    if request.user.is_authenticated:
        return redirect("dashboard_redirect")
    form = CustomerRegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        messages.success(request, "Your account is ready. Add vehicle details now or when you need support.")
        return redirect("customer_dashboard")
    return render(request, "registration/register_customer.html", {"form": form})


def register_engineer(request):
    if request.user.is_authenticated:
        return redirect("dashboard_redirect")
    form = EngineerRegistrationForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        messages.success(request, "Your engineer registration and ID were submitted for verification.")
        return redirect("engineer_dashboard")
    return render(request, "registration/register_engineer.html", {"form": form})


@login_required
def dashboard_redirect(request):
    if request.user.is_staff:
        return redirect("operations_dashboard")
    if hasattr(request.user, "customer_profile"):
        return redirect("customer_dashboard")
    if hasattr(request.user, "engineer_profile"):
        return redirect("engineer_dashboard")
    raise PermissionDenied


@customer_required
def customer_dashboard(request):
    profile = request.user.customer_profile
    jobs = profile.help_requests.select_related("assigned_engineer").all()
    context = {
        "profile": profile,
        "profile_ready": bool(profile.full_name and profile.vehicle_brand and profile.vehicle_model),
        "jobs": jobs,
        "active_jobs": jobs.exclude(status__in=[HelpRequest.Status.COMPLETED, HelpRequest.Status.CANCELLED]).count(),
        "completed_jobs": jobs.filter(status=HelpRequest.Status.COMPLETED).count(),
        "latest_job": jobs.first(),
    }
    return render(request, "portal/customer_dashboard.html", context)


@customer_required
def customer_profile(request):
    profile = request.user.customer_profile
    form = CustomerProfileForm(request.POST or None, instance=profile)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Your vehicle profile has been updated.")
        return redirect("customer_dashboard")
    return render(request, "portal/customer_profile_form.html", {"form": form, "profile": profile})


@login_required
def engineer_dashboard(request):
    engineer = getattr(request.user, "engineer_profile", None)
    if not engineer:
        raise PermissionDenied
    jobs = engineer.assigned_jobs.select_related("customer").all() if engineer.is_verified else []
    context = {
        "engineer": engineer,
        "jobs": jobs,
        "active_jobs": jobs.exclude(status__in=[HelpRequest.Status.COMPLETED, HelpRequest.Status.CANCELLED]).count()
        if engineer.is_verified else 0,
        "completed_jobs": jobs.filter(status=HelpRequest.Status.COMPLETED).count() if engineer.is_verified else 0,
    }
    return render(request, "portal/engineer_dashboard.html", context)


@approved_engineer_required
def update_availability(request):
    form = EngineerAvailabilityForm(request.POST or None, instance=request.user.engineer_profile)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Your assignment availability has been updated.")
        return redirect("engineer_dashboard")
    return render(request, "portal/availability_form.html", {"form": form})


@staff_required
def operations_dashboard(request):
    requests = HelpRequest.objects.select_related("customer", "assigned_engineer").all()
    context = {
        "requests": requests,
        "pending_requests": requests.filter(status=HelpRequest.Status.PENDING).count(),
        "active_requests": requests.filter(
            status__in=[HelpRequest.Status.ASSIGNED, HelpRequest.Status.IN_PROGRESS]
        ).count(),
        "completed_requests": requests.filter(status=HelpRequest.Status.COMPLETED).count(),
        "emergency_requests": requests.filter(urgency=HelpRequest.Urgency.EMERGENCY).count(),
        "pending_engineers": EngineerProfile.objects.filter(
            verification_status=EngineerProfile.VerificationStatus.PENDING
        ),
        "approved_engineers": EngineerProfile.objects.filter(
            is_approved=True, verification_status=EngineerProfile.VerificationStatus.APPROVED
        ).count(),
    }
    return render(request, "portal/operations_dashboard.html", context)


@customer_required
def request_help(request):
    profile = request.user.customer_profile
    initial = {
        "vin_number": profile.vin_number,
        "car_brand": profile.vehicle_brand,
        "car_model": profile.vehicle_model,
        "year": profile.vehicle_year,
        "state": profile.state,
        "city": profile.city,
    }
    form = HelpRequestForm(request.POST or None, request.FILES or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        help_request = form.save(commit=False)
        help_request.customer = profile
        help_request.save()
        messages.success(request, "Your repair request has been submitted. We will assign an engineer shortly.")
        return redirect("request_detail", pk=help_request.pk)
    return render(request, "portal/request_form.html", {"form": form})


@login_required
def request_detail(request, pk):
    job = get_object_or_404(HelpRequest.objects.select_related("customer", "assigned_engineer"), pk=pk)
    is_customer_owner = hasattr(request.user, "customer_profile") and job.customer == request.user.customer_profile
    is_assigned_engineer = (
        hasattr(request.user, "engineer_profile")
        and job.assigned_engineer == request.user.engineer_profile
        and request.user.engineer_profile.is_verified
    )
    if not (request.user.is_staff or is_customer_owner or is_assigned_engineer):
        raise PermissionDenied
    records_visible = request.user.is_staff or is_assigned_engineer
    return render(request, "portal/request_detail.html", {"job": job, "records_visible": records_visible})


@login_required
def request_attachment(request, pk):
    job = get_object_or_404(HelpRequest.objects.select_related("customer", "assigned_engineer"), pk=pk)
    owner = hasattr(request.user, "customer_profile") and job.customer == request.user.customer_profile
    engineer = (
        hasattr(request.user, "engineer_profile")
        and request.user.engineer_profile.is_verified
        and job.assigned_engineer == request.user.engineer_profile
    )
    if not (request.user.is_staff or owner or engineer) or not job.attachment:
        raise PermissionDenied
    return FileResponse(job.attachment.open("rb"), as_attachment=True, filename=Path(job.attachment.name).name)


@staff_required
def assign_request(request, pk):
    job = get_object_or_404(HelpRequest, pk=pk)
    form = AssignmentForm(request.POST or None, instance=job)
    if request.method == "POST" and form.is_valid():
        job = form.save(commit=False)
        job.status = HelpRequest.Status.ASSIGNED if job.assigned_engineer else HelpRequest.Status.PENDING
        job.save()
        messages.success(request, "Engineer assignment updated.")
        return redirect("request_detail", pk=job.pk)
    return render(request, "portal/assignment_form.html", {"form": form, "job": job})


@staff_required
def engineer_verification_review(request, pk):
    engineer = get_object_or_404(EngineerProfile, pk=pk)
    form = EngineerVerificationReviewForm(request.POST or None, instance=engineer)
    if request.method == "POST" and form.is_valid():
        engineer = form.save(commit=False)
        engineer.is_approved = engineer.verification_status == EngineerProfile.VerificationStatus.APPROVED
        engineer.reviewed_by = request.user
        engineer.reviewed_at = timezone.now()
        engineer.save()
        action = "approved" if engineer.is_approved else "rejected"
        messages.success(request, f"{engineer.full_name}'s engineer application has been {action}.")
        return redirect("operations_dashboard")
    return render(request, "portal/engineer_review.html", {"form": form, "engineer": engineer})


@staff_required
def download_engineer_id(request, pk):
    engineer = get_object_or_404(EngineerProfile, pk=pk)
    if not engineer.verification_document:
        raise PermissionDenied
    return FileResponse(
        engineer.verification_document.open("rb"),
        as_attachment=True,
        filename=Path(engineer.verification_document.name).name,
    )


@approved_engineer_required
def update_job_status(request, pk):
    job = get_object_or_404(HelpRequest, pk=pk, assigned_engineer=request.user.engineer_profile)
    form = JobStatusForm(request.POST or None, instance=job)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Job status updated.")
        return redirect("request_detail", pk=job.pk)
    return render(request, "portal/job_status_form.html", {"form": form, "job": job})


def _record_access(request):
    if request.user.is_staff:
        return None
    engineer = getattr(request.user, "engineer_profile", None)
    if engineer and engineer.is_verified:
        return engineer
    raise PermissionDenied


@login_required
def workshop_records(request):
    engineer = _record_access(request)
    records = WorkshopRecord.objects.select_related("help_request", "engineer_assigned")
    if engineer:
        records = records.filter(engineer_assigned=engineer)
    return render(request, "portal/workshop_records.html", {"records": records})


@login_required
def add_workshop_record(request):
    engineer = _record_access(request)
    form = WorkshopRecordForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        record = form.save(commit=False)
        if engineer:
            record.engineer_assigned = engineer
            if not record.help_request or record.help_request.assigned_engineer != engineer:
                raise PermissionDenied
        elif record.help_request and not record.engineer_assigned:
            record.engineer_assigned = record.help_request.assigned_engineer
        record.save()
        messages.success(request, "Workshop record saved.")
        return redirect("workshop_records")
    return render(request, "portal/record_form.html", {"form": form, "title": "New Workshop Record"})


@login_required
def ecu_records(request):
    engineer = _record_access(request)
    records = MercedesECURecord.objects.select_related("help_request", "engineer_assigned")
    if engineer:
        records = records.filter(engineer_assigned=engineer)
    return render(request, "portal/ecu_records.html", {"records": records})


@login_required
def download_ecu_file(request, pk):
    engineer = _record_access(request)
    record = get_object_or_404(MercedesECURecord, pk=pk)
    if engineer and record.engineer_assigned != engineer:
        raise PermissionDenied
    if not record.uploaded_file:
        raise PermissionDenied
    return FileResponse(record.uploaded_file.open("rb"), as_attachment=True, filename=Path(record.uploaded_file.name).name)


@login_required
def add_ecu_record(request):
    engineer = _record_access(request)
    form = MercedesECURecordForm(request.POST or None, request.FILES or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        record = form.save(commit=False)
        if engineer:
            record.engineer_assigned = engineer
            if not record.help_request or record.help_request.assigned_engineer != engineer:
                raise PermissionDenied
        elif record.help_request and not record.engineer_assigned:
            record.engineer_assigned = record.help_request.assigned_engineer
        record.save()
        messages.success(request, "Mercedes ECU record saved.")
        return redirect("ecu_records")
    return render(request, "portal/record_form.html", {"form": form, "title": "New Mercedes ECU Record"})


@login_required
def diagnostic_file_library(request):
    _record_access(request)
    search_query = request.GET.get("search", "").strip()
    file_type = request.GET.get("file_type", "").strip()
    assets = DiagnosticFileAsset.objects.select_related("uploaded_by")
    if file_type:
        assets = assets.filter(file_type=file_type)
    if search_query:
        assets = assets.filter(
            Q(original_file_name__icontains=search_query)
            | Q(ecu_name__icontains=search_query)
            | Q(ecu_part_number__icontains=search_query)
            | Q(hardware_number__icontains=search_query)
            | Q(software_number__icontains=search_query)
            | Q(compatible_models__icontains=search_query)
            | Q(engine_or_variant__icontains=search_query)
        )
    counts = {
        "total": DiagnosticFileAsset.objects.count(),
        "cbf": DiagnosticFileAsset.objects.filter(file_type=DiagnosticFileAsset.FileType.CBF).count(),
        "smr_d": DiagnosticFileAsset.objects.filter(file_type=DiagnosticFileAsset.FileType.SMR_D).count(),
        "cff": DiagnosticFileAsset.objects.filter(file_type=DiagnosticFileAsset.FileType.CFF).count(),
    }
    return render(
        request,
        "portal/diagnostic_file_library.html",
        {"assets": assets, "counts": counts, "search_query": search_query, "selected_type": file_type},
    )


@login_required
def add_diagnostic_file(request):
    _record_access(request)
    form = DiagnosticFileAssetForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        asset = form.save(commit=False)
        asset.uploaded_by = request.user
        asset.original_file_name = Path(asset.uploaded_file.name).name
        asset.extracted_text_preview = extract_readable_file_signatures(asset.uploaded_file)
        asset.save()
        messages.success(request, "Diagnostic file saved to the compatibility library.")
        return redirect("diagnostic_file_detail", pk=asset.pk)
    return render(request, "portal/diagnostic_file_form.html", {"form": form})


@login_required
def diagnostic_file_detail(request, pk):
    _record_access(request)
    asset = get_object_or_404(DiagnosticFileAsset.objects.select_related("uploaded_by"), pk=pk)
    return render(request, "portal/diagnostic_file_detail.html", {"asset": asset})


@login_required
def download_diagnostic_file(request, pk):
    _record_access(request)
    asset = get_object_or_404(DiagnosticFileAsset, pk=pk)
    return FileResponse(
        asset.uploaded_file.open("rb"),
        as_attachment=True,
        filename=asset.original_file_name or Path(asset.uploaded_file.name).name,
    )


def parts_lookup(request):
    return redirect("vin_decoder")


@login_required
def parts_catalogue(request):
    _record_access(request)
    search_query = request.GET.get("search", "").strip()
    parts = RequiredVehiclePart.objects.select_related("added_by")
    if search_query:
        parts = parts.filter(
            Q(part_name__icontains=search_query)
            | Q(part_number__icontains=search_query)
            | Q(compatible_model__icontains=search_query)
            | Q(exact_vin__icontains=search_query)
            | Q(engine_or_variant__icontains=search_query)
        )
    return render(request, "portal/parts_catalogue.html", {"parts": parts, "search_query": search_query})


@login_required
def add_required_part(request):
    _record_access(request)
    form = RequiredVehiclePartForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        part = form.save(commit=False)
        part.added_by = request.user
        part.save()
        messages.success(request, "Required vehicle part has been added to the VIN lookup catalogue.")
        return redirect("parts_catalogue")
    return render(request, "portal/required_part_form.html", {"form": form})


def _required_parts_for_vehicle(decoded):
    parts_query = Q(exact_vin__iexact=decoded["vin"])
    if decoded["api_available"] and decoded["make"] and decoded["model"]:
        model_year = int(decoded["model_year"]) if decoded["model_year"].isdigit() else None
        compatible = Q(
            exact_vin="",
            compatible_make__iexact=decoded["make"],
            compatible_model__iexact=decoded["model"],
        )
        if model_year:
            compatible &= (
                (Q(year_from__isnull=True) | Q(year_from__lte=model_year))
                & (Q(year_to__isnull=True) | Q(year_to__gte=model_year))
            )
        parts_query |= compatible
    return RequiredVehiclePart.objects.filter(parts_query).order_by("-is_required", "category", "part_name")


def _diagnostic_files_for_vehicle(decoded):
    if not (decoded["api_available"] and decoded["make"] and decoded["model"]):
        return DiagnosticFileAsset.objects.none()
    return DiagnosticFileAsset.objects.filter(
        compatible_brand__iexact=decoded["make"],
        compatible_models__icontains=decoded["model"],
    ).order_by("file_type", "ecu_name")


def vin_decoder(request):
    form = VINDecoderForm(request.POST or None)
    decoded = None
    parts = None
    diagnostic_files = None
    if request.method == "POST" and form.is_valid():
        decoded = form.decode()
        parts = _required_parts_for_vehicle(decoded)
        diagnostic_files = _diagnostic_files_for_vehicle(decoded)
        VINDecodeRecord.objects.create(
            requested_by=request.user if request.user.is_authenticated else None,
            vin=decoded["vin"],
            wmi=decoded["wmi"],
            vds=decoded["vds"],
            vis=decoded["vis"],
            manufacturer=decoded["manufacturer"],
            model_year=decoded["model_year"],
            make=decoded["make"],
            model=decoded["model"],
            body_class=decoded["body_class"],
            engine=decoded["engine"],
            transmission=decoded["transmission"],
            plant=decoded["plant"],
            vehicle_type=decoded["vehicle_type"],
            fuel_type=decoded["fuel_type"],
            source=decoded["source"],
            api_available=decoded["api_available"],
            api_message=decoded["error"],
            decoded_data=decoded["raw_data"],
        )
    return render(
        request,
        "portal/vin_decoder.html",
        {"form": form, "decoded": decoded, "parts": parts, "diagnostic_files": diagnostic_files},
    )
