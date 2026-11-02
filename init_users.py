import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from django.contrib.auth.models import User
from patients.models import Staff

def init_db():
    # Create Admin/Doctor
    username = 'admin'
    password = 'password123'
    name = 'Dr. Navas Kp'
    
    if not User.objects.filter(username=username).exists():
        user = User.objects.create_superuser(username=username, password=password, first_name=name)
        Staff.objects.create(user=user, name=name, role='Admin', phone='9876543210')
        print(f"Success! Created user '{username}' with password '{password}'")
    else:
        print(f"Info: User '{username}' already exists.")

if __name__ == '__main__':
    init_db()
