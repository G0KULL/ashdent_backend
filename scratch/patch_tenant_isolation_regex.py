import re

views_path = 'ashdent-back/patients/views.py'
with open(views_path, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. AppointmentCreateView: Add branch, doctor, and patient checks
pattern_appt = r'(branch\s*=\s*Branch\.objects\.filter\(pk=branch_id\)\.first\(\)\s*if\s*branch_id\s*else\s*\(scope\.branch\s*or\s*Branch\.objects\.first\(\)\))'
m_appt = re.search(pattern_appt, content)
if m_appt:
    appt_insertion = """

        if not scope.is_super:
            if branch and branch.company_id and scope.company and str(branch.company_id) != str(scope.company.id):
                return Response({'error': 'Unauthorized: Branch belongs to another company.'}, status=status.HTTP_403_FORBIDDEN)
            if branch and not scope.has_access_to_branch(branch.id):
                return Response({'error': 'Unauthorized: You do not have access to this branch.'}, status=status.HTTP_403_FORBIDDEN)

        patient_id = request.data.get('patient')
        if patient_id:
            patient_obj = Patient.objects.filter(pk=patient_id).first()
            if not patient_obj or (not scope.is_super and scope.company and patient_obj.company_id and str(patient_obj.company_id) != str(scope.company.id)):
                return Response({'error': 'Selected patient does not belong to your company or not found.'}, status=400)"""

    content = content[:m_appt.end()] + appt_insertion + content[m_appt.end():]
    print("AppointmentCreateView patched with branch and patient checks.")
else:
    print("WARNING: AppointmentCreateView not matched!")

# Also in AppointmentCreateView: doctor company check
pattern_doc = r'(doctor\s*=\s*Doctor\.objects\.filter\(id=doc_id\)\.first\(\)\s*if\s*not\s*doctor:\s*return\s*Response\(\{\'error\':\s*\'Selected doctor does not exist\.\'\}\,\s*status=400\))'
m_doc = re.search(pattern_doc, content)
if m_doc:
    doc_insertion = """
            if not scope.is_super and scope.company and doctor.company_id and str(doctor.company_id) != str(scope.company.id):
                return Response({'error': 'Selected doctor does not belong to your company.'}, status=400)"""
    content = content[:m_doc.end()] + doc_insertion + content[m_doc.end():]
    print("AppointmentCreateView patched with doctor company check.")
else:
    print("WARNING: Appointment doctor check not matched.")

# 2. StaffUpdateView: Add company isolation check
pattern_staff_up = r'(class\s+StaffUpdateView\(APIView\):\s*def\s+put\(self,\s*request,\s*pk\):\s*try:\s*staff\s*=\s*Staff\.objects\.get\(pk=pk\))'
m_sup = re.search(pattern_staff_up, content)
if m_sup:
    sup_insertion = """
            scope = get_request_scope(request)
            if not scope.is_super and scope.company and staff.company_id and str(staff.company_id) != str(scope.company.id):
                return Response({'detail': 'Staff member not found or unauthorized.'}, status=404)"""
    content = content[:m_sup.end()] + sup_insertion + content[m_sup.end():]
    print("StaffUpdateView patched with company isolation.")
else:
    print("WARNING: StaffUpdateView not matched.")

# 3. StaffCreateView: Set company and branch
pattern_staff_create = r'(staff\s*=\s*Staff\.objects\.create\([^)]*additional_details=additional_details\s*\))'
m_sc = re.search(pattern_staff_create, content)
if m_sc:
    old_call = m_sc.group(0)
    # prepend scope resolution and append company & branch
    new_call = """scope = get_request_scope(request)
            target_company = scope.company
            if doctor_profile and target_company:
                doctor_profile.company = target_company
                doctor_profile.save()

            target_branch = None
            br_param = data.get('primary_branch') or data.get('branch_id') or (scope.branch.id if scope.branch else None)
            if br_param and scope.has_access_to_branch(br_param):
                target_branch = Branch.objects.filter(pk=br_param, company=target_company, is_active=True).first()

            """ + old_call[:-1] + """,
                company=target_company,
                primary_branch=target_branch,
                accessible_branches=[str(target_branch.id)] if target_branch else []
            )"""
    content = content[:m_sc.start()] + new_call + content[m_sc.end():]
    print("StaffCreateView patched with company & branch assignment.")
else:
    print("WARNING: StaffCreateView not matched.")

with open(views_path, 'w', encoding='utf-8') as f:
    f.write(content)

print("views.py regex patching completed!")

