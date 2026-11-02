import os
import django
import sys

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from patients.models import CommunicationTemplate, TaxSetting

# Create default communication templates
templates = [
    {
        "category": "Appointment",
        "type": "Confirmation",
        "text": "Dear [Name], your dental appointment is confirmed for today. Please arrive 10 mins early. Thank you!",
        "email_enabled": True,
        "sms_enabled": True,
        "whatsapp_enabled": True
    },
    {
        "category": "Follow-up",
        "type": "Reminder",
        "text": "Dear [Name], this is a gentle reminder regarding your follow-up appointment. Please let us know if you need to reschedule.",
        "email_enabled": True,
        "sms_enabled": True,
        "whatsapp_enabled": True
    },
    {
        "category": "Billing",
        "type": "Payment Receipt",
        "text": "Dear [Name], we have received your payment for your recent dental procedure. Thank you for choosing our clinic!",
        "email_enabled": True,
        "sms_enabled": True,
        "whatsapp_enabled": True
    },
    {
        "category": "Greeting",
        "type": "Welcome",
        "text": "Welcome [Name]! We are excited to assist you with your dental care and help you maintain a healthy smile.",
        "email_enabled": True,
        "sms_enabled": True,
        "whatsapp_enabled": True
    },
    {
        "category": "Greeting",
        "type": "Birthday Wish",
        "text": "Happy Birthday [Name]! 🎂 Wishing you a wonderful day filled with joy and smiles from all of us at the dental clinic!",
        "email_enabled": True,
        "sms_enabled": True,
        "whatsapp_enabled": True
    },
    {
        "category": "Appointment",
        "type": "Missed Appointment",
        "text": "Dear [Name], we noticed you missed your scheduled appointment today. Please call us to reschedule at your convenience.",
        "email_enabled": True,
        "sms_enabled": True,
        "whatsapp_enabled": True
    },
    {
        "category": "Clinical",
        "type": "Post-Op Care",
        "text": "Dear [Name], please take your prescribed medications on time and avoid hard or hot foods today. Take rest and feel free to reach out if you have any discomfort.",
        "email_enabled": True,
        "sms_enabled": True,
        "whatsapp_enabled": True
    },
    {
        "category": "Reminder",
        "type": "Routine Dental Checkup",
        "text": "Dear [Name], it has been 6 months since your last dental checkup! Regular cleanings protect your teeth. Book your slot today.",
        "email_enabled": True,
        "sms_enabled": True,
        "whatsapp_enabled": True
    }
]

for t in templates:
    CommunicationTemplate.objects.get_or_create(
        category=t["category"],
        type=t["type"],
        defaults={
            "text": t["text"],
            "email_enabled": t["email_enabled"],
            "sms_enabled": t["sms_enabled"],
            "whatsapp_enabled": t["whatsapp_enabled"]
        }
    )

print("Communication templates populated successfully!")
