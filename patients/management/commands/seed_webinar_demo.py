import os
import sys
from django.core.management.base import BaseCommand

class Command(BaseCommand):
    help = 'Seeds fresh, presentation-grade dummy data for the live webinar demonstration.'

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE('Running Webinar Demo Dataset Generator...'))
        scratch_script = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            'scratch',
            'seed_live_webinar_demo.py'
        )
        if os.path.exists(scratch_script):
            with open(scratch_script, 'r', encoding='utf-8') as f:
                code = f.read()
            # Execute in global scope with __file__ defined
            exec(compile(code, scratch_script, 'exec'), {'__name__': '__main__', '__file__': scratch_script})
            self.stdout.write(self.style.SUCCESS('Webinar demo data seeded successfully!'))
        else:
            self.stderr.write(self.style.ERROR(f'Seed script not found at {scratch_script}'))
