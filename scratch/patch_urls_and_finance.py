import re

# 1. Patch patients/urls.py
urls_path = 'ashdent-back/patients/urls.py'
with open(urls_path, 'r', encoding='utf-8') as f:
    u_content = f.read()

if 'TokenRefreshView' not in u_content:
    u_content = "from rest_framework_simplejwt.views import TokenRefreshView\n" + u_content
    # Add token refresh route near login
    login_str = "path('login/', LoginView.as_view()),"
    refresh_routes = "path('login/', LoginView.as_view()),\n    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),\n    path('auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh_alt'),"
    u_content = u_content.replace(login_str, refresh_routes, 1)
    with open(urls_path, 'w', encoding='utf-8') as f:
        f.write(u_content)
    print("urls.py updated with TokenRefreshView routes.")
else:
    print("TokenRefreshView already in urls.py.")

# 2. Patch patients/finance_views.py to remove all empty auth/permission overrides
finance_path = 'ashdent-back/patients/finance_views.py'
with open(finance_path, 'r', encoding='utf-8') as f:
    f_content = f.read()

f_content = re.sub(r'(\n\s*authentication_classes\s*=\s*\[\s*\]\s*\n\s*permission_classes\s*=\s*\[\s*\]\s*)', '\n', f_content)
with open(finance_path, 'w', encoding='utf-8') as f:
    f_content = f.write(f_content)
print("finance_views.py stripped of empty auth overrides.")


