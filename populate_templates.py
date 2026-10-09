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
        "text": "Dear {patient}, your appointment with {doctor} is confirmed for {date} at {time}. Please reply to this message to confirm your attendance. Clinic: {clinic}",
        "email_enabled": True,
        "sms_enabled": True,
        "whatsapp_enabled": True
    },
    {
        "category": "Follow-up",
        "type": "Reminder",
        "text": "Dear {patient}, this is a gentle reminder regarding your follow-up appointment on {date} at {time}. Please let us know if you need to reschedule. Thank you, {clinic}.",
        "email_enabled": True,
        "sms_enabled": True,
        "whatsapp_enabled": True
    },
    {
        "category": "Billing",
        "type": "Payment Receipt",
        "text": "Dear {patient}, we have received your payment for the recent procedure. Thank you! - {clinic}",
        "email_enabled": True,
        "sms_enabled": True,
        "whatsapp_enabled": True
    },
    {
        "category": "Greeting",
        "type": "Welcome",
        "text": "Welcome to {clinic}, {patient}! We are looking forward to helping you achieve a perfect smile.",
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
