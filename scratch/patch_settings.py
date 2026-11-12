import re

settings_path = 'ashdent-back/core/settings.py'

with open(settings_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Add rest_framework_simplejwt
if 'rest_framework_simplejwt' not in content:
    content = content.replace(
        "'rest_framework',",
        "'rest_framework',\n    'rest_framework_simplejwt',"
    )

jwt_config = """

from datetime import timedelta

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=60),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': False,
    'AUTH_HEADER_TYPES': ('Bearer',),
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',
}
"""

if 'REST_FRAMEWORK' not in content:
    content += jwt_config

with open(settings_path, 'w', encoding='utf-8') as f:
    f.write(content)

print("Settings successfully patched!")

