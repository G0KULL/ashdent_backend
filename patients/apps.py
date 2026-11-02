from django.apps import AppConfig


class PatientsConfig(AppConfig):
    default_auto_field = 'django_mongodb_backend.fields.ObjectIdAutoField'
    name = 'patients'

    def ready(self):
        from django_mongodb_backend.fields import ObjectIdAutoField
        from django.contrib.admin.models import LogEntry
        from django.contrib.auth.models import Permission, Group, User
        from django.contrib.contenttypes.models import ContentType
        import django.contrib.auth.management as auth_management

        # Patch AutoField → ObjectIdAutoField for Django built-in models
        for model in [LogEntry, Permission, Group, User, ContentType]:
            for field in model._meta.local_fields:
                if field.name == 'id' and field.__class__.__name__ in ('AutoField', 'BigAutoField'):
                    field.__class__ = ObjectIdAutoField
                    field.db_column = '_id'

        # Patch create_permissions to handle MongoDB ObjectId PKs safely
        _original_create_permissions = auth_management.create_permissions

        def _safe_create_permissions(app_config, verbosity=2, interactive=True,
                                     using=None, apps=None, **kwargs):
            try:
                _original_create_permissions(
                    app_config, verbosity=verbosity, interactive=interactive,
                    using=using, apps=apps, **kwargs
                )
            except TypeError:
                pass  # Ignore unhashable ObjectId PK issue during post-migrate

        auth_management.create_permissions = _safe_create_permissions
        from django.contrib.auth.management import create_permissions as cp
        from django.db.models.signals import post_migrate
        # Re-connect with patched version
        post_migrate.disconnect(cp, dispatch_uid="django.contrib.auth.management.create_permissions")
        post_migrate.connect(_safe_create_permissions, dispatch_uid="django.contrib.auth.management.create_permissions")
