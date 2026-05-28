import json
import shutil
import tempfile
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import (
    CustomerProfile,
    DiagnosticFileAsset,
    EngineerProfile,
    HelpRequest,
    RequiredVehiclePart,
)
from .utils import decode_vin, validate_vin


VALID_VIN = "WDB1234567A123456"


class MockNHTSAResponse:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def read(self):
        return json.dumps(
            {
                "Results": [
                    {
                        "Manufacturer": "MERCEDES-BENZ CARS",
                        "Make": "MERCEDES-BENZ",
                        "Model": "C-Class",
                        "ModelYear": "2020",
                        "BodyClass": "Sedan/Saloon",
                        "EngineModel": "M274",
                        "TransmissionStyle": "Automatic",
                        "PlantCity": "Sindelfingen",
                        "PlantCountry": "Germany",
                        "VehicleType": "Passenger Car",
                        "FuelTypePrimary": "Gasoline",
                        "ErrorText": "",
                    }
                ]
            }
        ).encode("utf-8")


def make_customer(username):
    user = User.objects.create_user(username=username, password="TestPass123!")
    profile = CustomerProfile.objects.create(
        user=user,
        full_name=f"{username} Customer",
        phone_number="08000000000",
        email=f"{username}@example.com",
        state="Lagos",
        city="Ikeja",
        vehicle_brand="Mercedes-Benz",
        vehicle_model="C300",
        vehicle_year=2020,
        vin_number=VALID_VIN,
    )
    return user, profile


def make_engineer(username, approved=True, available=True, document=None):
    user = User.objects.create_user(username=username, password="TestPass123!")
    profile = EngineerProfile.objects.create(
        user=user,
        full_name=f"{username} Engineer",
        phone_number="08100000000",
        email=f"{username}@example.com",
        state="Lagos",
        city="Ikeja",
        specialization="Diagnostics",
        years_of_experience=4,
        is_approved=approved,
        is_available=available,
        id_type=EngineerProfile.IDType.DRIVERS_LICENCE,
        id_number=f"ID-{username}",
        verification_document=document,
        verification_status=(
            EngineerProfile.VerificationStatus.APPROVED
            if approved else EngineerProfile.VerificationStatus.PENDING
        ),
    )
    return user, profile


def make_job(customer, engineer=None):
    return HelpRequest.objects.create(
        customer=customer,
        assigned_engineer=engineer,
        vehicle_registration_number="LAG-123-AA",
        vin_number=VALID_VIN,
        car_brand="Mercedes-Benz",
        car_model="C300",
        year=2020,
        problem_description="Engine warning light.",
        state="Lagos",
        city="Ikeja",
        status=HelpRequest.Status.ASSIGNED if engineer else HelpRequest.Status.PENDING,
    )


class VINDecoderTests(TestCase):
    @patch("portal.utils.urlopen", return_value=MockNHTSAResponse())
    def test_vin_validation_and_placeholder_result(self, _urlopen):
        with self.assertRaises(ValidationError):
            validate_vin("WDB123I")
        result = decode_vin(VALID_VIN)
        self.assertEqual(result["wmi"], "WDB")
        self.assertEqual(result["vds"], "123456")
        self.assertEqual(result["vis"], "7A123456")
        self.assertEqual(result["model"], "C-Class")

    @patch("portal.utils.urlopen", return_value=MockNHTSAResponse())
    def test_public_vin_center_returns_vehicle_parts_and_file_references(self, _urlopen):
        RequiredVehiclePart.objects.create(
            part_name="Engine control module",
            part_number="A0009001234",
            category=RequiredVehiclePart.Category.ELECTRICAL,
            compatible_make="MERCEDES-BENZ",
            compatible_model="C-Class",
            year_from=2018,
            year_to=2022,
        )
        DiagnosticFileAsset.objects.create(
            file_type=DiagnosticFileAsset.FileType.CBF,
            uploaded_file="diagnostic_file_library/MED40_variant.cbf",
            original_file_name="MED40_variant.cbf",
            ecu_name="MED40",
            ecu_part_number="A0009001234",
            compatible_brand="MERCEDES-BENZ",
            compatible_models="C-Class",
        )
        response = self.client.post(reverse("vin_decoder"), {"vin": VALID_VIN})
        self.assertContains(response, "Live NHTSA result")
        self.assertContains(response, "C-Class")
        self.assertContains(response, "Required parts for this car")
        self.assertContains(response, "Engine control module")
        self.assertContains(response, "Compatible diagnostic files")
        self.assertContains(response, "MED40")

    def test_vin_center_has_one_public_search_form(self):
        response = self.client.get(reverse("vin_decoder"))
        self.assertContains(response, "One VIN search for the full diagnostic workflow")
        self.assertContains(response, "Built for your own Mercedes catalogue")
        self.assertNotContains(response, "PartSouq")
        self.assertNotContains(response, "Mercedes ECU / part number (optional)")


class AccountAndRequestTests(TestCase):
    def test_customer_can_register_and_submit_request(self):
        response = self.client.post(
            reverse("register_customer"),
            {
                "contact": "newcustomer@example.com",
                "password1": "SecurePassword123!",
                "password2": "SecurePassword123!",
            },
        )
        self.assertRedirects(response, reverse("customer_dashboard"))
        profile = CustomerProfile.objects.get(email="newcustomer@example.com")
        self.assertEqual(profile.vehicle_brand, "")
        response = self.client.post(
            reverse("request_help"),
            {
                "vehicle_registration_number": "ABC-001-LA",
                "vin_number": VALID_VIN,
                "car_brand": "Toyota",
                "car_model": "Camry",
                "year": "2019",
                "problem_description": "Brake vibration",
                "state": "Lagos",
                "city": "Lekki",
                "urgency": "urgent",
            },
        )
        job = HelpRequest.objects.get(customer=profile)
        self.assertRedirects(response, reverse("request_detail", args=[job.pk]))

    def test_customer_can_register_and_login_with_phone_number(self):
        response = self.client.post(
            reverse("register_customer"),
            {
                "contact": "08010000000",
                "password1": "SecurePassword123!",
                "password2": "SecurePassword123!",
            },
        )
        self.assertRedirects(response, reverse("customer_dashboard"))
        self.client.logout()
        login_response = self.client.post(
            reverse("login"),
            {"username": "08010000000", "password": "SecurePassword123!"},
        )
        self.assertRedirects(login_response, reverse("dashboard_redirect"), fetch_redirect_response=False)
        self.assertRedirects(self.client.get(reverse("dashboard_redirect")), reverse("customer_dashboard"))

    def test_customer_can_complete_optional_vehicle_profile(self):
        user = User.objects.create_user(username="quickcustomer", password="TestPass123!")
        CustomerProfile.objects.create(user=user, email="quick@example.com")
        self.client.force_login(user)
        response = self.client.post(
            reverse("customer_profile"),
            {
                "full_name": "Quick Customer",
                "state": "Lagos",
                "city": "Lekki",
                "vehicle_brand": "Toyota",
                "vehicle_model": "Camry",
                "vehicle_year": "2019",
                "vin_number": VALID_VIN,
            },
        )
        self.assertRedirects(response, reverse("customer_dashboard"))
        self.assertContains(self.client.get(reverse("customer_dashboard")), "Toyota Camry")

    def test_customer_cannot_view_another_customers_request(self):
        user, _ = make_customer("owner")
        _, other_customer = make_customer("other")
        other_job = make_job(other_customer)
        self.client.force_login(user)
        response = self.client.get(reverse("request_detail", args=[other_job.pk]))
        self.assertEqual(response.status_code, 403)

    def test_customer_dashboard_renders_new_control_center(self):
        user, profile = make_customer("dashboardcustomer")
        make_job(profile)
        self.client.force_login(user)
        response = self.client.get(reverse("customer_dashboard"))
        self.assertContains(response, "Customer control center")
        self.assertContains(response, "Request diagnostics")
        self.assertContains(response, "VIN Decoder")
        self.assertContains(response, "Service request timeline")

    def test_engineer_registration_requires_valid_id_for_verification(self):
        media_root = tempfile.mkdtemp()
        with override_settings(MEDIA_ROOT=media_root):
            id_file = SimpleUploadedFile("drivers-licence.pdf", b"valid-id-copy", content_type="application/pdf")
            response = self.client.post(
                reverse("register_engineer"),
                {
                    "username": "newengineer",
                    "full_name": "New Engineer",
                    "phone_number": "08033333333",
                    "email": "newengineer@example.com",
                    "state": "Lagos",
                    "city": "Ikeja",
                    "specialization": "Mercedes Diagnostics",
                    "years_of_experience": "5",
                    "is_available": "on",
                    "id_type": EngineerProfile.IDType.DRIVERS_LICENCE,
                    "id_number": "LIC-203040",
                    "verification_document": id_file,
                    "password1": "SecurePassword123!",
                    "password2": "SecurePassword123!",
                },
            )
            profile = EngineerProfile.objects.get(user__username="newengineer")
            self.assertRedirects(response, reverse("engineer_dashboard"))
            self.assertFalse(profile.is_approved)
            self.assertEqual(profile.verification_status, EngineerProfile.VerificationStatus.PENDING)
            self.assertTrue(profile.verification_document.name.endswith(".pdf"))
        shutil.rmtree(media_root, ignore_errors=True)


class EngineerAndAdminAccessTests(TestCase):
    def setUp(self):
        _, self.customer = make_customer("client")
        self.engineer_user, self.engineer = make_engineer("assigned")
        self.other_user, self.other_engineer = make_engineer("outsider")
        self.job = make_job(self.customer, self.engineer)

    def test_assigned_engineer_can_update_only_assigned_job(self):
        other_job = make_job(self.customer, self.other_engineer)
        self.client.force_login(self.engineer_user)
        response = self.client.post(
            reverse("update_job_status", args=[self.job.pk]),
            {"status": HelpRequest.Status.IN_PROGRESS},
        )
        self.assertRedirects(response, reverse("request_detail", args=[self.job.pk]))
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, HelpRequest.Status.IN_PROGRESS)
        response = self.client.get(reverse("update_job_status", args=[other_job.pk]))
        self.assertEqual(response.status_code, 404)

    def test_unapproved_engineer_cannot_access_assigned_work(self):
        pending_user, pending_engineer = make_engineer("pending", approved=False)
        pending_job = make_job(self.customer, pending_engineer)
        self.client.force_login(pending_user)
        self.assertEqual(self.client.get(reverse("request_detail", args=[pending_job.pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse("workshop_records")).status_code, 403)

    def test_staff_can_assign_only_approved_available_engineers(self):
        unavailable_user, unavailable = make_engineer("busy", available=False)
        staff = User.objects.create_superuser(username="admin", email="admin@example.com", password="AdminPass123!")
        unassigned = make_job(self.customer)
        self.client.force_login(staff)
        page = self.client.get(reverse("assign_request", args=[unassigned.pk]))
        self.assertContains(page, self.engineer.full_name)
        self.assertNotContains(page, unavailable.full_name)
        response = self.client.post(reverse("assign_request", args=[unassigned.pk]), {"assigned_engineer": self.engineer.pk})
        self.assertRedirects(response, reverse("request_detail", args=[unassigned.pk]))
        unassigned.refresh_from_db()
        self.assertEqual(unassigned.status, HelpRequest.Status.ASSIGNED)

    def test_engineer_and_admin_dashboards_render_new_dispatch_design(self):
        self.client.force_login(self.engineer_user)
        response = self.client.get(reverse("engineer_dashboard"))
        self.assertContains(response, "Engineer dispatch hub")
        self.client.logout()
        staff = User.objects.create_superuser(username="operations", email="ops@example.com", password="AdminPass123!")
        self.client.force_login(staff)
        response = self.client.get(reverse("operations_dashboard"))
        self.assertContains(response, "Service Dispatch Center")

    def test_staff_reviews_identity_document_and_approves_engineer(self):
        media_root = tempfile.mkdtemp()
        with override_settings(MEDIA_ROOT=media_root):
            pending_user, pending_engineer = make_engineer(
                "verifyme",
                approved=False,
                document=SimpleUploadedFile("nin.pdf", b"id document", content_type="application/pdf"),
            )
            staff = User.objects.create_superuser(username="reviewadmin", email="review@example.com", password="AdminPass123!")
            self.client.force_login(staff)
            review_page = self.client.get(reverse("engineer_verification_review", args=[pending_engineer.pk]))
            self.assertContains(review_page, "Download submitted ID document")
            response = self.client.post(
                reverse("engineer_verification_review", args=[pending_engineer.pk]),
                {"verification_status": "approved", "verification_notes": "Identification verified."},
            )
            self.assertRedirects(response, reverse("operations_dashboard"))
            pending_engineer.refresh_from_db()
            self.assertTrue(pending_engineer.is_approved)
            self.assertEqual(pending_engineer.reviewed_by, staff)
        shutil.rmtree(media_root, ignore_errors=True)

    def test_non_staff_cannot_download_engineer_id(self):
        media_root = tempfile.mkdtemp()
        with override_settings(MEDIA_ROOT=media_root):
            pending_user, pending_engineer = make_engineer(
                "securedoc",
                approved=False,
                document=SimpleUploadedFile("passport.pdf", b"id document", content_type="application/pdf"),
            )
            self.client.force_login(self.engineer_user)
            self.assertEqual(self.client.get(reverse("download_engineer_id", args=[pending_engineer.pk])).status_code, 403)
        shutil.rmtree(media_root, ignore_errors=True)

    def test_staff_cannot_approve_engineer_without_identity_document(self):
        pending_user, pending_engineer = make_engineer("nodocument", approved=False)
        staff = User.objects.create_superuser(username="idadmin", email="idadmin@example.com", password="AdminPass123!")
        self.client.force_login(staff)
        response = self.client.post(
            reverse("engineer_verification_review", args=[pending_engineer.pk]),
            {"verification_status": "approved", "verification_notes": "Attempted approval."},
        )
        self.assertContains(response, "A valid submitted ID document is required before approval")
        pending_engineer.refresh_from_db()
        self.assertFalse(pending_engineer.is_approved)


class DiagnosticFileLibraryTests(TestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp()
        self.media_override = override_settings(MEDIA_ROOT=self.media_root)
        self.media_override.enable()
        self.engineer_user, self.engineer = make_engineer("fileengineer")
        self.customer_user, _ = make_customer("blockedcustomer")

    def tearDown(self):
        self.media_override.disable()
        shutil.rmtree(self.media_root, ignore_errors=True)

    def test_approved_engineer_can_upload_and_search_cbf_compatibility_asset(self):
        self.client.force_login(self.engineer_user)
        uploaded = SimpleUploadedFile(
            "MED40_variant.cbf",
            b"MERCEDES ECU MED40 hardware A0009001234 software SW204 CBF variant data",
            content_type="application/octet-stream",
        )
        response = self.client.post(
            reverse("add_diagnostic_file"),
            {
                "file_type": "cbf",
                "uploaded_file": uploaded,
                "ecu_name": "MED40",
                "ecu_part_number": "A0009001234",
                "hardware_number": "HW204",
                "software_number": "SW204",
                "compatible_brand": "Mercedes-Benz",
                "compatible_models": "W204 C-Class",
                "year_range": "2011-2014",
                "engine_or_variant": "M271",
                "diagnostic_tool": "Vediamo",
                "compatibility_notes": "Confirmed in workshop archive.",
            },
        )
        asset = DiagnosticFileAsset.objects.get()
        self.assertRedirects(response, reverse("diagnostic_file_detail", args=[asset.pk]))
        self.assertIn("MERCEDES ECU MED40", asset.extracted_text_preview)
        page = self.client.get(reverse("diagnostic_file_library"), {"search": "W204"})
        self.assertContains(page, "MED40")
        self.assertContains(page, "W204 C-Class")

    def test_customer_cannot_access_diagnostic_file_library(self):
        self.client.force_login(self.customer_user)
        self.assertEqual(self.client.get(reverse("diagnostic_file_library")).status_code, 403)

    def test_public_can_find_secure_cbf_file_center_entry(self):
        response = self.client.get(reverse("home"))
        self.assertContains(response, "Advanced vehicle diagnostics and technical support services")
        self.assertContains(response, "Diagnostic services built around real workshop needs")
        self.assertContains(response, "CBF / SMR-D / CFF")
        self.assertContains(response, "images/automind-logo.svg")
        self.assertContains(response, reverse("diagnostic_file_library"))
        self.client.logout()
        redirect_response = self.client.get(reverse("diagnostic_file_library"))
        self.assertRedirects(
            redirect_response,
            f"{reverse('login')}?next={reverse('diagnostic_file_library')}",
        )


class RequiredPartsLookupTests(TestCase):
    def setUp(self):
        self.engineer_user, self.engineer = make_engineer("partsengineer")
        self.customer_user, _ = make_customer("partscustomer")

    def test_old_parts_lookup_route_moves_to_vin_center(self):
        response = self.client.get(reverse("parts_lookup"))
        self.assertRedirects(response, reverse("vin_decoder"))

    def test_customer_cannot_manage_parts_catalogue(self):
        self.client.force_login(self.customer_user)
        self.assertEqual(self.client.get(reverse("parts_catalogue")).status_code, 403)

    def test_approved_engineer_can_add_part_catalogue_requirement(self):
        self.client.force_login(self.engineer_user)
        response = self.client.post(
            reverse("add_required_part"),
            {
                "part_name": "Brake pad set",
                "part_number": "A2044200000",
                "category": "brake",
                "is_required": "on",
                "exact_vin": "",
                "compatible_make": "MERCEDES-BENZ",
                "compatible_model": "C-Class",
                "year_from": "2018",
                "year_to": "2022",
                "engine_or_variant": "",
                "quantity": "1",
                "notes": "Confirmed replacement part.",
            },
        )
        self.assertRedirects(response, reverse("parts_catalogue"))
        self.assertTrue(RequiredVehiclePart.objects.filter(part_number="A2044200000").exists())
