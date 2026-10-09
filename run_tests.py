import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from patients.test_staff_onboarding import StaffOnboardingSecurityTestCase

def run():
    print("\nRunning Staff Onboarding Security & Role Test Suite...\n")
    test_case = StaffOnboardingSecurityTestCase()
    tests = [
        'test_1_company_admin_can_create_staff_for_own_company',
        'test_2_company_admin_cannot_create_staff_for_another_company',
        'test_3_company_admin_cannot_create_super_admin',
        'test_4_company_admin_cannot_modify_another_company_staff',
        'test_5_company_admin_cannot_list_another_company_staff',
        'test_6_company_admin_cannot_access_another_company_staff_profile',
        'test_7_super_admin_can_create_staff_for_authorized_company',
        'test_8_role_assignment_and_permissions',
        'test_13_inactive_staff_cannot_login',
        'test_14_duplicate_email_rejected',
        'test_15_duplicate_username_rejected',
        'test_18_unauthorized_users_cannot_access_onboarding'
    ]
    
    passed = 0
    failed = 0
    
    for t in tests:
        test_case.setUp()
        try:
            method = getattr(test_case, t)
            method()
            print(f"  [PASS] {t}")
            passed += 1
        except Exception as e:
            print(f"  [FAIL] {t}: {e}")
            failed += 1
        finally:
            test_case.tearDown()
            
    print(f"\nResults: {passed} PASSED, {failed} FAILED.\n")
    if failed > 0:
        sys.exit(1)

if __name__ == '__main__':
    run()
