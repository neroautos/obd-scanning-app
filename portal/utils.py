import json
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.exceptions import ValidationError


def validate_vin(value):
    vin = (value or "").upper().strip()
    if len(vin) != 17:
        raise ValidationError("VIN must be exactly 17 characters.")
    if any(character in vin for character in "IOQ"):
        raise ValidationError("VIN cannot contain I, O, or Q.")
    if not vin.isalnum():
        raise ValidationError("VIN must contain letters and numbers only.")


def decode_vin(vin):
    """Decode a VIN through the free NHTSA vPIC API with a local-format fallback."""
    vin = (vin or "").upper().strip()
    validate_vin(vin)
    decoded = {
        "vin": vin,
        "wmi": vin[:3],
        "vds": vin[3:9],
        "vis": vin[9:],
        "manufacturer": "Not available",
        "make": "",
        "model": "",
        "model_year": "Not available",
        "body_class": "",
        "engine": "",
        "transmission": "",
        "plant": "",
        "vehicle_type": "",
        "fuel_type": "",
        "source": "NHTSA vPIC",
        "api_available": False,
        "error": "",
        "raw_data": {},
    }
    request = Request(
        settings.VPIC_API_URL.format(vin=vin),
        headers={"Accept": "application/json", "User-Agent": "AutoMind-Diagnostics/1.0"},
    )
    try:
        with urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
        result = (payload.get("Results") or [{}])[0]
        decoded.update(
            {
                "manufacturer": result.get("Manufacturer") or result.get("Make") or "Not available",
                "make": result.get("Make", ""),
                "model": result.get("Model", ""),
                "model_year": result.get("ModelYear") or "Not available",
                "body_class": result.get("BodyClass", ""),
                "engine": result.get("EngineModel") or result.get("DisplacementL", ""),
                "transmission": result.get("TransmissionStyle", ""),
                "plant": ", ".join(
                    value for value in [result.get("PlantCity", ""), result.get("PlantCountry", "")] if value
                ),
                "vehicle_type": result.get("VehicleType", ""),
                "fuel_type": result.get("FuelTypePrimary", ""),
                "api_available": True,
                "error": result.get("ErrorText", ""),
                "raw_data": result,
            }
        )
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        decoded["error"] = f"Live NHTSA lookup unavailable: {exc}"
    return decoded


def extract_readable_file_signatures(uploaded_file, max_bytes=2 * 1024 * 1024):
    """Collect printable sequences that can assist manual identification of diagnostic assets."""
    position = uploaded_file.tell()
    raw_data = uploaded_file.read(max_bytes)
    uploaded_file.seek(position)
    if not isinstance(raw_data, bytes):
        raw_data = raw_data.encode("utf-8", errors="ignore")
    sequences = re.findall(rb"[\x20-\x7e]{5,}", raw_data)
    text = "\n".join(item.decode("ascii", errors="ignore") for item in sequences)
    terms = ("mercedes", "benz", "ecu", "cff", "cbf", "smr", "flash", "software", "hardware", "variant")
    interesting = [line for line in text.splitlines() if any(term in line.lower() for term in terms)]
    preview = interesting[:30] or text.splitlines()[:30]
    return "\n".join(preview)[:4000]
