import os
import random
import django
from datetime import date, datetime, time, timedelta

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from patients.models import (
    Doctor, Patient, Appointment, Visit, ClinicalNotes,
    TreatmentMaster, TreatmentRecord, Billing, BillingItem
)

def seed_data():
    print("=== Starting Data Seeding for AshDent HMS (Sept 01, 2026 to Sept 28, 2026) ===")

    # 1. DOCTORS (4 Doctors)
    doctors_info = [
        {
            'name': 'Dr. Navas Kp',
            'color': '#3b82f6', # Blue
            'specialization': 'General Dentistry & Endodontics',
            'qualification': 'BDS, MDS (Endodontics)',
            'experience_years': 10,
            'phone': '9876543210',
            'email': 'dr.navas@ashdent.com',
            'consultation_fee': 500.00
        },
        {
            'name': 'Dr. Priya Nair',
            'color': '#ec4899', # Pink
            'specialization': 'Orthodontics & Dentofacial Orthopedics',
            'qualification': 'BDS, MDS (Orthodontics)',
            'experience_years': 8,
            'phone': '9876543211',
            'email': 'dr.priya@ashdent.com',
            'consultation_fee': 700.00
        },
        {
            'name': 'Dr. Arjun Das',
            'color': '#10b981', # Green
            'specialization': 'Oral & Maxillofacial Surgery',
            'qualification': 'BDS, MDS (Oral Surgery)',
            'experience_years': 12,
            'phone': '9876543212',
            'email': 'dr.arjun@ashdent.com',
            'consultation_fee': 800.00
        },
        {
            'name': 'Dr. Ananya Sharma',
            'color': '#8b5cf6', # Purple
            'specialization': 'Pediatric & Aesthetic Dentistry',
            'qualification': 'BDS, Dip. Aesthetic Dentistry',
            'experience_years': 7,
            'phone': '9876543213',
            'email': 'dr.ananya@ashdent.com',
            'consultation_fee': 600.00
        }
    ]

    doctors = []
    for d_info in doctors_info:
        doc, created = Doctor.objects.get_or_create(
            name=d_info['name'],
            defaults=d_info
        )
        if not created:
            # Update fields to ensure consistency
            for k, v in d_info.items():
                setattr(doc, k, v)
            doc.save()
        doctors.append(doc)
        print(f"Doctor: {doc.name} ({doc.specialization})")

    # 2. PATIENTS (25 Realistic Patients)
    patient_names_data = [
        ("Arjun Menon", "Male", 33, "9876501001", date(1993, 4, 15)),
        ("Priya Krishnan", "Female", 37, "9876501002", date(1989, 9, 22)),
        ("Rahul Kumar", "Male", 30, "9876501003", date(1996, 12, 1)),
        ("Lakshmi Devi", "Female", 51, "9876501004", date(1975, 3, 8)),
        ("Mohammed Rafiq", "Male", 25, "9876501005", date(2001, 7, 19)),
        ("Kavita Reddy", "Female", 29, "9876501006", date(1997, 2, 14)),
        ("Sunita Verma", "Female", 44, "9876501007", date(1982, 11, 30)),
        ("Ramesh Gupta", "Male", 52, "9876501008", date(1974, 8, 12)),
        ("Amit Patel", "Male", 38, "9876501009", date(1988, 5, 25)),
        ("Sneha Kulkarni", "Female", 26, "9876501010", date(2000, 10, 5)),
        ("Arjun Malhotra", "Male", 41, "9876501011", date(1985, 1, 18)),
        ("Pooja Bhatia", "Female", 32, "9876501012", date(1994, 6, 21)),
        ("Deepak Mehta", "Male", 48, "9876501013", date(1978, 4, 9)),
        ("Neha Saxena", "Female", 35, "9876501014", date(1991, 7, 16)),
        ("Sanjay Verma", "Male", 56, "9876501015", date(1970, 9, 3)),
        ("Ritu Singh", "Female", 28, "9876501016", date(1998, 12, 28)),
        ("Manoj Kumar", "Male", 43, "9876501017", date(1983, 3, 11)),
        ("Divya Sharma", "Female", 31, "9876501018", date(1995, 8, 19)),
        ("Suresh Nair", "Male", 60, "9876501019", date(1966, 5, 4)),
        ("Anish Varma", "Male", 27, "9876501020", date(1999, 11, 23)),
        ("Meera Pillai", "Female", 39, "9876501021", date(1987, 10, 17)),
        ("Karthik Iyer", "Male", 34, "9876501022", date(1992, 2, 8)),
        ("Aisha Khan", "Female", 23, "9876501023", date(2003, 6, 14)),
        ("Vikramaditya Joshi", "Male", 47, "9876501024", date(1979, 1, 29)),
        ("Shweta Roy", "Female", 36, "9876501025", date(1990, 4, 3))
    ]

    patients = []
    for idx, (name, gender, age, phone, dob) in enumerate(patient_names_data):
        assigned_doc = doctors[idx % len(doctors)]
        pat, created = Patient.objects.get_or_create(
            phone=phone,
            defaults={
                'name': name,
                'gender': gender,
                'age': age,
                'dob': dob,
                'doctor': assigned_doc,
                'status': 'Active',
                'notes': f'Regular patient assigned to {assigned_doc.name}'
            }
        )
        if not created:
            pat.name = name
            pat.gender = gender
            pat.age = age
            pat.dob = dob
            pat.doctor = assigned_doc
            pat.save()
        patients.append(pat)

    print(f"Total Patients in Database: {len(patients)}")

    # 3. TREATMENTS MASTER (for clinical records & billing)
    treatments_data = [
        ("Consultation & Diagnosis", 500, "Consultation"),
        ("Scaling & Polishing (Full Mouth)", 1200, "Treatment"),
        ("Root Canal Treatment (Single Canal)", 3500, "Treatment"),
        ("Composite Tooth-Colored Filling", 1500, "Treatment"),
        ("Dental Extraction (Simple)", 1000, "Treatment"),
        ("Surgical Extraction / Impaction", 4500, "Treatment"),
        ("Porcelain Fused Crown (PFM)", 6000, "Treatment"),
        ("Zirconia Premium Crown", 11000, "Treatment"),
        ("Digital Intraoral X-Ray (RVG)", 300, "X-Ray"),
        ("Teeth Whitening / Bleaching", 7500, "Treatment")
    ]

    treatment_masters = []
    for t_name, t_price, t_fee in treatments_data:
        tm, _ = TreatmentMaster.objects.get_or_create(
            name=t_name,
            defaults={'price': t_price, 'fee_type': t_fee, 'is_active': True}
        )
        treatment_masters.append(tm)

    # 4. APPOINTMENTS (Sept 01, 2026 to Sept 28, 2026)
    start_date = date(2026, 9, 1)
    end_date = date(2026, 9, 28)
    curr_date = start_date

    time_slots = [
        time(9, 0), time(10, 15), time(11, 30),
        time(14, 0), time(15, 15), time(16, 30), time(17, 45)
    ]

    complaints_pool = [
        "Severe tooth pain in lower left molar",
        "Routine dental checkup & cleaning",
        "Bleeding gums while brushing",
        "Sensitivity to cold & sweet items",
        "Chipped front upper incisor",
        "Wisdom tooth pain & swelling",
        "Stained teeth seeking cosmetic whitening",
        "Loose crown on upper right premolar"
    ]

    total_created_appts = 0

    while curr_date <= end_date:
        # Determine number of appointments for today (3 to 6)
        num_appts = random.randint(4, 6)
        used_slots = random.sample(time_slots, num_appts)
        used_slots.sort()

        for slot_time in used_slots:
            pat = random.choice(patients)
            doc = pat.doctor if (random.random() < 0.7 and pat.doctor) else random.choice(doctors)

            # Determine status based on date
            if curr_date < end_date:
                # Past dates: mostly Completed, occasional Follow-up, Cancelled, Missed
                r = random.random()
                if r < 0.78:
                    status = 'Completed'
                elif r < 0.88:
                    status = 'Follow-up'
                elif r < 0.94:
                    status = 'Cancelled'
                else:
                    status = 'Missed'
            else:
                # Today (Sept 28, 2026): Active mix
                r = random.random()
                if slot_time < time(12, 0):
                    status = random.choice(['Completed', 'Engaged', 'Waiting'])
                elif slot_time < time(15, 0):
                    status = random.choice(['Waiting', 'Engaged', 'Scheduled'])
                else:
                    status = random.choice(['Scheduled', 'Scheduled', 'Follow-up'])

            is_virtual = (random.random() < 0.15)
            meeting_link = f"https://meet.jit.si/AshDent_Consultation_{random.randint(10000, 99999)}" if is_virtual else None

            # Create or update appointment
            appt, created = Appointment.objects.get_or_create(
                patient=pat,
                date=curr_date,
                time=slot_time,
                defaults={
                    'doctor': doc,
                    'status': status,
                    'is_virtual': is_virtual,
                    'meeting_link': meeting_link,
                    'telemedicine_notes': 'Virtual consultation via Jitsi Meet' if is_virtual else None
                }
            )

            if not created:
                appt.doctor = doc
                appt.status = status
                appt.is_virtual = is_virtual
                if meeting_link:
                    appt.meeting_link = meeting_link
                appt.save()

            total_created_appts += 1

            # For Completed or Follow-up appointments, create Visit, Clinical Notes & Billing for clinical realistic experience
            if status in ['Completed', 'Follow-up']:
                visit, _ = Visit.objects.get_or_create(
                    patient=pat,
                    appointment=appt
                )

                # Clinical Notes
                cnotes, cn_created = ClinicalNotes.objects.get_or_create(
                    appointment=appt,
                    defaults={
                        'chief_complaint': random.choice(complaints_pool),
                        'patient_type': 'Adult',
                        'notes': f'Patient reported for evaluation. Treatment performed smoothly by {doc.name}.',
                        'treatment_plan': 'Follow up in 2 weeks for review.',
                        'follow_up_date': curr_date + timedelta(days=14) if status == 'Follow-up' else None,
                        'follow_up_status': 'Pending' if status == 'Follow-up' else 'Completed'
                    }
                )

                # Treatment Records
                chosen_treatment = random.choice(treatment_masters)
                TreatmentRecord.objects.get_or_create(
                    visit=visit,
                    treatment=chosen_treatment,
                    defaults={
                        'price': chosen_treatment.price,
                        'fee_type': chosen_treatment.fee_type,
                        'doctor': doc,
                        'status': 'Completed',
                        'notes': f'Executed {chosen_treatment.name}'
                    }
                )

                # Billing
                billing, b_created = Billing.objects.get_or_create(
                    patient=pat,
                    visit=visit,
                    defaults={
                        'doctor': doc,
                        'clinical_note': cnotes,
                        'bill_type': 'Clinical',
                        'total_amount': chosen_treatment.price,
                        'paid_amount': chosen_treatment.price,
                        'balance_amount': 0.0,
                        'payment_method': random.choice(['UPI', 'Cash', 'Card']),
                        'status': 'Paid',
                        'notes': f'Payment received for {chosen_treatment.name}'
                    }
                )
                if b_created:
                    BillingItem.objects.create(
                        billing=billing,
                        treatment=chosen_treatment,
                        qty=1,
                        price=chosen_treatment.price
                    )

        curr_date += timedelta(days=1)

    print(f"Successfully generated {total_created_appts} appointments between Sept 01, 2026 and Sept 28, 2026.")
    print("=== Data Seeding Completed Cleanly ===")

if __name__ == '__main__':
    seed_data()
