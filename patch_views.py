import os

backup_path = 'patients/finance_views.py'
main_path = 'patients/finance_views.py'
temp_path = 'patients/temp_view.py'

with open(backup_path, 'r') as f:
    lines = f.readlines()

idx = next((i for i, line in enumerate(lines) if line.startswith('class TransactionSummaryAPIView')), -1)
if idx != -1:
    new_lines = lines[:idx]
else:
    new_lines = lines

with open(temp_path, 'r') as f:
    temp_lines = f.readlines()

new_lines.extend(temp_lines)

with open(main_path, 'w') as f:
    f.writelines(new_lines)

print("Replaced successfully!")
