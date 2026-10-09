import os
import django

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from patients.models import ToothMaster

def populate_teeth():
    # Helper to create tooth
    def add_t(num, t_type, cat, pos):
        ToothMaster.objects.get_or_create(
            tooth_number=num,
            defaults={'type': t_type, 'category': cat, 'position': pos}
        )

    # PERMANENT TEETH
    # Upper Right
    for n in [18,17,16]: add_t(n, 'molar', 'permanent', 'upper_right')
    for n in [15,14]: add_t(n, 'premolar', 'permanent', 'upper_right')
    add_t(13, 'canine', 'permanent', 'upper_right')
    for n in [12,11]: add_t(n, 'incisor', 'permanent', 'upper_right')

    # Upper Left
    for n in [21,22]: add_t(n, 'incisor', 'permanent', 'upper_left')
    add_t(23, 'canine', 'permanent', 'upper_left')
    for n in [24,25]: add_t(n, 'premolar', 'permanent', 'upper_left')
    for n in [26,27,28]: add_t(n, 'molar', 'permanent', 'upper_left')

    # Lower Left
    for n in [31,32]: add_t(n, 'incisor', 'permanent', 'lower_left')
    add_t(33, 'canine', 'permanent', 'lower_left')
    for n in [34,35]: add_t(n, 'premolar', 'permanent', 'lower_left')
    for n in [36,37,38]: add_t(n, 'molar', 'permanent', 'lower_left')

    # Lower Right
    for n in [48,47,46]: add_t(n, 'molar', 'permanent', 'lower_right')
    for n in [45,44]: add_t(n, 'premolar', 'permanent', 'lower_right')
    add_t(43, 'canine', 'permanent', 'lower_right')
    for n in [42,41]: add_t(n, 'incisor', 'permanent', 'lower_right')

    # PRIMARY TEETH
    # UR
    for n in [55,54]: add_t(n, 'molar', 'primary', 'upper_right')
    add_t(53, 'canine', 'primary', 'upper_right')
    for n in [52,51]: add_t(n, 'incisor', 'primary', 'upper_right')
    # UL
    for n in [61,62]: add_t(n, 'incisor', 'primary', 'upper_left')
    add_t(63, 'canine', 'primary', 'upper_left')
    for n in [64,65]: add_t(n, 'molar', 'primary', 'upper_left')
    # LL
    for n in [71,72]: add_t(n, 'incisor', 'primary', 'lower_left')
    add_t(73, 'canine', 'primary', 'lower_left')
    for n in [74,75]: add_t(n, 'molar', 'primary', 'lower_left')
    # LR
    for n in [85,84]: add_t(n, 'molar', 'primary', 'lower_right')
    add_t(83, 'canine', 'primary', 'lower_right')
    for n in [82,81]: add_t(n, 'incisor', 'primary', 'lower_right')

    print("Tooth Master Data Populated Successfully!")

if __name__ == "__main__":
    populate_teeth()
