import os
import sys
import unittest

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
import django
django.setup()

from patients.test_staff_onboarding import StaffOnboardingSecurityTestCase

if __name__ == '__main__':
    suite = unittest.TestLoader().loadTestsFromTestCase(StaffOnboardingSecurityTestCase)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(not result.wasSuccessful())
