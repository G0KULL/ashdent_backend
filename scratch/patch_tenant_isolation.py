import re

views_path = 'ashdent-back/patients/views.py'
with open(views_path, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. StaffListView: filter by company for non-superusers
old_staff_list_match = re.search(r'staff = Staff\.objects\.all\(\)\.order_by\("-created_at", "-id"\)', content)
if old_staff_list_match:
    new_staff_list = '''scope = get_request_scope(request)
        if not scope.is_super and scope.company:
            staff = Staff.objects.filter(company=scope.company).order_by("-created_at", "-id")
        else:
            staff = Staff.objects.all().order_by("-created_at", "-id")'''
    content = content[:old_staff_list_match.start()] + new_staff_list + content[old_staff_list_match.end():]
    print("StaffListView company isolation added.")
else:
    print("WARNING: StaffListView query not matched.")

# 2. StaffUpdateView: check company isolation
old_staff_update = '''        try:
            staff = Staff.objects.get(pk=pk)
            data = request.data
            req_user = get_authenticated_user(request)'''
new_staff_update = '''        try:
            staff = Staff.objects.get(pk=pk)
            scope = get_request_scope(request)
            if not scope.is_super and scope.company and staff.company_id and str(staff.company_id) != str(scope.company.id):
                return Response({'detail': 'Staff member not found or unauthorized.'}, status=404)
            data = request.data
            req_user = get_authenticated_user(request)'''

if old_staff_update in content:
    content = content.replace(old_staff_update, new_staff_update, 1)
    print("StaffUpdateView company isolation added.")
else:
    print("WARNING: StaffUpdateView target not matched.")

# 3. StaffCreateView: assign company and branch
old_staff_create = '''            staff = Staff.objects.create(
                user=user,
                name=name,
                role=role,
                staff_level=staff_level,
                phone=phone,
                email=email,
                gender=gender,
                age=age,
                dob=dob,
                blood_group=blood_group,
                address=address,
                status=status,
                is_active=False if status == 'Inactive' else True,
                emergency_contact=emergency_contact,
                permissions=permissions,
                doctor_profile=doctor_profile,
                base_salary=base_salary,
                additional_details=additional_details
            )'''

new_staff_create = '''            scope = get_request_scope(request)
            target_company = scope.company
            if doctor_profile and target_company:
                doctor_profile.company = target_company
                doctor_profile.save()

            target_branch = None
            br_param = data.get('primary_branch') or data.get('branch_id') or (scope.branch.id if scope.branch else None)
            if br_param and scope.has_access_to_branch(br_param):
                target_branch = Branch.objects.filter(pk=br_param, company=target_company, is_active=True).first()

            staff = Staff.objects.create(
                user=user,
                name=name,
                role=role,
                staff_level=staff_level,
                phone=phone,
                email=email,
                gender=gender,
                age=age,
                dob=dob,
                blood_group=blood_group,
                address=address,
                status=status,
                is_active=False if status == 'Inactive' else True,
                emergency_contact=emergency_contact,
                permissions=permissions,
                doctor_profile=doctor_profile,
                base_salary=base_salary,
                additional_details=additional_details,
                company=target_company,
                primary_branch=target_branch,
                accessible_branches=[str(target_branch.id)] if target_branch else []
            )'''

if old_staff_create in content:
    content = content.replace(old_staff_create, new_staff_create, 1)
    print("StaffCreateView company/branch assignment added.")
else:
    print("WARNING: StaffCreateView target not matched.")

# 4. AppointmentCreateView: enforce branch, doctor, patient isolation
old_appt_checks = '''        branch_id = request.data.get('branch') or request.headers.get('X-Branch-Id') or (scope.branch.id if scope.branch else None)
        branch = Branch.objects.filter(pk=branch_id).first() if branch_id else (scope.branch or Branch.objects.first())

        doctor = None
        if doc_id:
            doctor = Doctor.objects.filter(id=doc_id).first()
            if not doctor:
                return Response({'error': 'Selected doctor does not exist.'}, status=400)'''

new_appt_checks = '''        branch_id = request.data.get('branch') or request.headers.get('X-Branch-Id') or (scope.branch.id if scope.branch else None)
        branch = Branch.objects.filter(pk=branch_id).first() if branch_id else (scope.branch or Branch.objects.first())

        if not scope.is_super:
            if branch and branch.company_id and scope.company and str(branch.company_id) != str(scope.company.id):
                return Response({'error': 'Unauthorized: Branch belongs to another company.'}, status=status.HTTP_403_FORBIDDEN)
            if branch and not scope.has_access_to_branch(branch.id):
                return Response({'error': 'Unauthorized: You do not have access to this branch.'}, status=status.HTTP_403_FORBIDDEN)

        doctor = None
        if doc_id:
            doctor = Doctor.objects.filter(id=doc_id).first()
            if not doctor:
                return Response({'error': 'Selected doctor does not exist.'}, status=400)
            if not scope.is_super and scope.company and doctor.company_id and str(doctor.company_id) != str(scope.company.id):
                return Response({'error': 'Selected doctor does not belong to your company.'}, status=400)

        patient_id = request.data.get('patient')
        if patient_id:
            patient_obj = Patient.objects.filter(pk=patient_id).first()
            if not patient_obj or (not scope.is_super and scope.company and patient_obj.company_id and str(patient_obj.company_id) != str(scope.company.id)):
                return Response({'error': 'Selected patient does not belong to your company or not found.'}, status=400)'''

if old_appt_checks in content:
    content = content.replace(old_appt_checks, new_appt_checks, 1)
    print("AppointmentCreateView company/branch isolation checks added.")
else:
    print("WARNING: AppointmentCreateView checks not matched.")

with open(views_path, 'w', encoding='utf-8') as f:
    f.write(content)

print("patch_tenant_isolation.py completed!")

