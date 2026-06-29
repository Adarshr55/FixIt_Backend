"""
Management command to seed all existing data with embeddings.
Run once after deploying: python manage.py seed_embeddings
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta


class Command(BaseCommand):
    help = 'Seed vector embeddings for all existing categories, services and bookings'

    def add_arguments(self, parser):
        parser.add_argument(
            '--type',
            type=str,
            default='all',
            help='What to seed: all | categories | services | issues'
        )

    def handle(self, *args, **options):
        seed_type = options['type']

        if seed_type in ('all', 'categories'):
            self._seed_categories()

        if seed_type in ('all', 'services'):
            self._seed_services()

        if seed_type in ('all', 'issues'):
            self._seed_issues()

        self.stdout.write(self.style.SUCCESS('Seeding complete.'))

    def _seed_categories(self):
        from services.models import ServiceCategory
        from ai_engine.embedding_service import embed_category

        categories = ServiceCategory.objects.filter(is_active=True)
        total      = categories.count()
        self.stdout.write(f'Seeding {total} categories...')

        success = 0
        for cat in categories:
            if embed_category(cat.id):
                success += 1
                self.stdout.write(f'  [OK] {cat.name}')
            else:
                self.stdout.write(
                    self.style.WARNING(f'  [FAIL] {cat.name} failed')
                )

        self.stdout.write(
            self.style.SUCCESS(f'Categories: {success}/{total} embedded')
        )

    def _seed_services(self):
        from services.models import ProviderService
        from ai_engine.embedding_service import embed_service

        services = ProviderService.objects.filter(
            verification_status='verified',
            is_active=True,
        )
        total = services.count()
        self.stdout.write(f'Seeding {total} verified services...')

        success = 0
        for svc in services:
            if embed_service(svc.id):
                success += 1
            else:
                self.stdout.write(
                    self.style.WARNING(f'  [FAIL] service id={svc.id} failed')
                )

        self.stdout.write(
            self.style.SUCCESS(f'Services: {success}/{total} embedded')
        )

    def _seed_issues(self):
        from bookings.models import Booking
        from ai_engine.embedding_service import embed_issue

        # only last 6 months — older data less relevant
        six_months_ago = timezone.now() - timedelta(days=180)
        bookings = Booking.objects.filter(
            status='completed',
            completed_at__gte=six_months_ago,
            issue_description__isnull=False,
        ).exclude(issue_description='')

        total = bookings.count()
        self.stdout.write(f'Seeding {total} completed booking issues...')

        success = 0
        for booking in bookings:
            if embed_issue(booking.id):
                success += 1

        self.stdout.write(
            self.style.SUCCESS(f'Issues: {success}/{total} embedded')
        )