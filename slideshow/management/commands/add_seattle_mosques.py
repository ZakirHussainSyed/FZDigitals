from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from slideshow.models import Mosque
import json
import os


class Command(BaseCommand):
    help = 'Add 3 Seattle-area mosques from OSM data and link to specific usernames'

    def handle(self, *args, **options):
        # OSM data for the 3 mosques
        mosques_data = [
            {
                'osm_id': 'osm_43239fc6cb',
                'name': 'Islamic Center',
                'address': 'Bellevue',
                'latitude': 47.6101893,
                'longitude': -122.1440816,
                'username': 'icoe_main'
            },
            {
                'osm_id': 'osm_b69d05e880',
                'name': 'Islamic Center',
                'address': '',
                'latitude': 47.6291396,
                'longitude': -122.151019,
                'username': 'icoe_north'
            },
            {
                'osm_id': 'osm_f00e4257a7',
                'name': 'Masjid Madeena',
                'address': 'Bellevue',
                'latitude': 47.6178515,
                'longitude': -122.1222275,
                'username': 'madeenamasjid'
            }
        ]

        for mosque_info in mosques_data:
            username = mosque_info['username']
            osm_id = mosque_info['osm_id']

            # Check if user exists
            try:
                user = User.objects.get(username=username)
            except User.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR(f"User '{username}' does not exist. Skipping mosque {osm_id}")
                )
                continue

            # Check if mosque already exists for this user
            existing = Mosque.objects.filter(
                user=user,
                name=mosque_info['name'],
                latitude=mosque_info['latitude'],
                longitude=mosque_info['longitude']
            ).first()

            if existing:
                self.stdout.write(
                    self.style.WARNING(f" Mosque already exists for user '{username}': {existing.name}")
                )
                continue

            # Create the mosque
            mosque = Mosque.objects.create(
                user=user,
                name=mosque_info['name'],
                address=mosque_info['address'],
                latitude=mosque_info['latitude'],
                longitude=mosque_info['longitude'],
                timezone='America/Los_Angeles',
                sync_enabled=False
            )

            self.stdout.write(
                self.style.SUCCESS(
                    f"Created mosque '{mosque.name}' for user '{username}' "
                    f"(OSM ID: {osm_id}, lat: {mosque.latitude}, lon: {mosque.longitude})"
                )
            )

        self.stdout.write(self.style.SUCCESS("Done adding Seattle mosques"))
