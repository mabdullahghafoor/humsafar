"""
Starting content for the healthcare directory and the home-care provider directory (Task 6.1).

The platform maintains this content (FR-I1, FR-J1), so it ships with the database migration 0016.

IMPORTANT (clarification 121):
  * The national emergency numbers (Edhi 115, Chhipa 1020, Aman 1021, Rescue 1122, Police 15, Fire 16) are real.
  * Every other entry is a DEMO ENTRY (`is_sample = true`): realistic type, city and position so search and
    "nearby" can be shown, but made-up names and made-up phone numbers. Replace them with real, checked entries
    before the final demo. The app can show a "sample" label from the `is_sample` field.
"""

# (name, type, phone, lat, lng, address, city, services, open_24h, is_sample)
ORGANIZATIONS = [
    # --- Real national emergency numbers (no single location) ---
    ("Edhi Foundation Ambulance", "ambulance", "115", None, None, None, "Nationwide", "Emergency ambulance, 24 hours", True, False),
    ("Chhipa Welfare Ambulance", "ambulance", "1020", None, None, None, "Nationwide", "Emergency ambulance, 24 hours", True, False),
    ("Aman Ambulance", "ambulance", "1021", None, None, None, "Nationwide", "Emergency ambulance, 24 hours", True, False),
    ("Rescue 1122", "emergency_service", "1122", None, None, None, "Nationwide", "Emergency rescue and ambulance (where the service operates)", True, False),
    ("Police Emergency", "emergency_service", "15", None, None, None, "Nationwide", "Police emergency line", True, False),
    ("Fire Brigade", "emergency_service", "16", None, None, None, "Nationwide", "Fire emergency line", True, False),
    # --- Demo entries (made-up names and numbers) ---
    ("Demo City General Hospital", "hospital", "0300-0000001", 31.5497, 74.3436, "Mall Road (demo address)", "Lahore", "Emergency, general medicine, surgery, pharmacy", True, True),
    ("Demo Lahore Heart Clinic", "clinic", "0300-0000002", 31.5204, 74.3587, "Gulberg (demo address)", "Lahore", "Heart check-up, ECG, blood pressure care", False, True),
    ("Demo Lahore Care Pharmacy", "pharmacy", "0300-0000003", 31.5580, 74.3300, "Anarkali (demo address)", "Lahore", "Medicines, home delivery", True, True),
    ("Demo Karachi National Hospital", "hospital", "0300-0000004", 24.8607, 67.0011, "Saddar (demo address)", "Karachi", "Emergency, general medicine, dialysis", True, True),
    ("Demo Karachi Family Clinic", "clinic", "0300-0000005", 24.8138, 67.0300, "Clifton (demo address)", "Karachi", "Family doctor, elderly care, vaccination", False, True),
    ("Demo Karachi Diagnostic Lab", "laboratory", "0300-0000006", 24.9056, 67.0822, "Gulshan (demo address)", "Karachi", "Blood tests, X-ray, home sample collection", False, True),
    ("Demo Islamabad Medical Centre", "hospital", "0300-0000007", 33.6844, 73.0479, "G-8 (demo address)", "Islamabad", "Emergency, general medicine, physiotherapy", True, True),
    ("Demo Islamabad Blood Bank", "blood_bank", "0300-0000008", 33.7100, 73.0600, "F-7 (demo address)", "Islamabad", "Blood and plasma", False, True),
    ("Demo Islamabad Night Pharmacy", "pharmacy", "0300-0000009", 33.6900, 73.0550, "F-8 (demo address)", "Islamabad", "Medicines, open all night", True, True),
]

# (name, specialization, service_charge, charge_unit, contact, bio, city, experience_years, is_sample) - charges in PKR
PROVIDERS = [
    ("Demo Nurse Ayesha", "nurse", 2500, "per_visit", "0300-1000001", "Registered nurse. Injections, wound dressing, drips and vital checks at home.", "Lahore", 8, True),
    ("Demo Nurse Hina", "nurse", 3000, "per_visit", "0300-1000002", "Elderly and post-surgery nursing care at home.", "Karachi", 6, True),
    ("Demo Physiotherapist Imran", "physiotherapist", 3500, "per_visit", "0300-1000003", "Back pain, stroke recovery and mobility exercises at home.", "Islamabad", 10, True),
    ("Demo Physiotherapist Sana", "physiotherapist", 3000, "per_visit", "0300-1000004", "Knee and hip rehabilitation, exercises for elderly people.", "Lahore", 5, True),
    ("Demo Attendant Bilal", "attendant", 1500, "per_day", "0300-1000005", "Daily help: bathing, feeding, walking, medicine reminders.", "Karachi", 4, True),
    ("Demo Attendant Rukhsana", "attendant", 45000, "per_month", "0300-1000006", "Full-time live-in attendant for elderly or bed-bound patients.", "Islamabad", 12, True),
    ("Demo Home Doctor Dr. Kamran", "doctor", 4000, "per_visit", "0300-1000007", "General physician, home visits for check-ups and prescriptions.", "Lahore", 15, True),
    ("Demo Lab Technician Faisal", "lab_technician", 800, "per_visit", "0300-1000008", "Blood sample collection at home, reports sent the same day.", "Karachi", 7, True),
]
