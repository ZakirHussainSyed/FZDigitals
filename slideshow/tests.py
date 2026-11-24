from datetime import date, datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from .models import (
    Device, DevicePairing, MediaFile, Mosque, PrayerTime, PrayerTimeOverride,
    TakbirAnnouncement,
)


def image(name='pic.png'):
    return SimpleUploadedFile(name, b'fake-image-bytes', content_type='image/png')


class MediaAuthorizationTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user('owner', password='pw')
        self.other = User.objects.create_user('other', password='pw')
        self.media = MediaFile.objects.create(
            user=self.owner, screen=1, title='pic', content_type='image', file=image()
        )

    def test_media_list_requires_login(self):
        res = self.client.get('/api/media/?screen=1')
        self.assertEqual(res.status_code, 302)

    def test_media_list_only_returns_own_media(self):
        self.client.force_login(self.other)
        res = self.client.get('/api/media/?screen=1')
        self.assertEqual(res.json()['files'], [])

    def test_upload_requires_login(self):
        res = self.client.post('/api/upload/', {'files': image(), 'screen': 1})
        self.assertEqual(res.status_code, 302)
        self.assertEqual(MediaFile.objects.count(), 1)

    def test_upload_rejects_non_media_files(self):
        self.client.force_login(self.owner)
        payload = SimpleUploadedFile('notes.txt', b'hello', content_type='text/plain')
        res = self.client.post('/api/upload/', {'files': payload, 'screen': 1})
        self.assertEqual(res.status_code, 400)
        self.assertEqual(MediaFile.objects.count(), 1)

    def test_delete_requires_login(self):
        res = self.client.post(f'/api/media/{self.media.pk}/delete/')
        self.assertEqual(res.status_code, 302)
        self.assertTrue(MediaFile.objects.filter(pk=self.media.pk).exists())

    def test_delete_of_another_users_media_is_not_found(self):
        self.client.force_login(self.other)
        res = self.client.post(f'/api/media/{self.media.pk}/delete/')
        self.assertEqual(res.status_code, 404)
        self.assertTrue(MediaFile.objects.filter(pk=self.media.pk).exists())

    def test_owner_can_delete_own_media(self):
        self.client.force_login(self.owner)
        res = self.client.post(f'/api/media/{self.media.pk}/delete/')
        self.assertEqual(res.status_code, 200)
        self.assertFalse(MediaFile.objects.filter(pk=self.media.pk).exists())


class DeviceSlideshowTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user('owner', password='pw')
        self.pairing = DevicePairing.objects.create(user=self.owner, screen=2)
        MediaFile.objects.create(
            user=self.owner, screen=2, title='pic', content_type='image', file=image()
        )

    def pair(self, browser_id='BR-DEADBEEF'):
        res = self.client.get(f'/api/pairing/{self.pairing.pairing_id}/?browser_id={browser_id}')
        return res.json()

    def test_pairing_returns_device_token_and_no_user_id(self):
        data = self.pair()
        self.assertTrue(data['success'])
        self.assertEqual(data['device_token'], Device.objects.get(device_id='BR-DEADBEEF').token)
        self.assertNotIn('user_id', data)

    def test_slideshow_requires_matching_token(self):
        self.pair()
        res = self.client.get('/api/device/BR-DEADBEEF/slideshow/')
        self.assertEqual(res.status_code, 403)
        res = self.client.get('/api/device/BR-DEADBEEF/slideshow/?token=wrong')
        self.assertEqual(res.status_code, 403)

    def test_slideshow_returns_media_with_token(self):
        token = self.pair()['device_token']
        res = self.client.get(f'/api/device/BR-DEADBEEF/slideshow/?token={token}')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.json()['files']), 1)


class DeviceRegistrationTests(TestCase):
    def test_register_requires_login(self):
        res = self.client.post(
            '/api/device/register/',
            data='{"device_id": "BR-11112222"}',
            content_type='application/json',
        )
        self.assertEqual(res.status_code, 302)
        self.assertFalse(Device.objects.filter(device_id='BR-11112222').exists())


class MosquePrayerDateTests(TestCase):
    def test_prayer_times_save_uses_mosque_local_date(self):
        user = User.objects.create_user('mosque', password='pw')
        mosque = Mosque.objects.create(
            user=user,
            name='ICOE Main',
            latitude='47.6101201',
            longitude='-122.1441715',
            timezone='America/Los_Angeles',
        )
        self.client.force_login(user)
        pst_evening_utc_next_day = datetime(2026, 11, 22, 1, 15, tzinfo=ZoneInfo('UTC'))
        form_data = {'website_url': ''}
        for field, hour, minute, ampm in (
            ('fajr', '5', '15', 'AM'),
            ('dhuhr', '1', '00', 'PM'),
            ('asr', '4', '00', 'PM'),
            ('maghrib', '6', '00', 'PM'),
            ('isha', '8', '00', 'PM'),
        ):
            form_data.update({
                f'{field}_hour': hour,
                f'{field}_minute': minute,
                f'{field}_ampm': ampm,
            })

        with patch('slideshow.views.timezone.now', return_value=pst_evening_utc_next_day):
            response = self.client.post('/prayer-times/', form_data)
            api_response = self.client.get('/api/public/mosques/', {
                'bbox': '47.60,-122.15,47.62,-122.13',
            })

        self.assertEqual(response.status_code, 302)
        self.assertTrue(PrayerTime.objects.filter(mosque=mosque, date=date(2026, 11, 21)).exists())
        self.assertTrue(
            PrayerTimeOverride.objects.filter(mosque=mosque, date=date(2026, 11, 21)).exists()
        )
        self.assertIn('max-age=3600', api_response['Cache-Control'])
        mosque_data = api_response.json()['mosques'][0]
        self.assertEqual(mosque_data['timings']['fajr'], '5:15 am')


class TakbirAnnouncementTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            'admin', 'admin@example.com', 'password')

    def test_public_feed_only_returns_published_announcements_without_http_cache(self):
        published = TakbirAnnouncement.objects.create(
            title='Hadith', body='Message', source='Reference',
            is_published=True, created_by=self.admin, published_at=datetime.now(ZoneInfo('UTC')),
        )
        TakbirAnnouncement.objects.create(title='Draft', body='Not public')

        response = self.client.get('/api/public/announcements/')

        self.assertEqual(response.status_code, 200)
        self.assertIn('no-store', response['Cache-Control'])
        self.assertEqual([item['id'] for item in response.json()['announcements']], [published.id])

    def test_only_superusers_can_manage_announcements(self):
        regular_user = User.objects.create_user('regular', password='password')
        self.client.force_login(regular_user)
        response = self.client.get('/takbir/announcements/')
        self.assertEqual(response.status_code, 403)

    def test_superuser_can_publish_announcement(self):
        self.client.force_login(self.admin)
        response = self.client.post('/takbir/announcements/', {
            'action': 'create',
            'title': 'Community update',
            'body': 'Message',
            'source': 'Takbir',
            'publish': '1',
        })

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], '/takbir/announcements/')
        announcement = TakbirAnnouncement.objects.get()
        self.assertTrue(announcement.is_published)
        self.assertEqual(announcement.created_by, self.admin)
        self.assertIsNotNone(announcement.published_at)


class ApproximateLocationTests(TestCase):
    @patch('slideshow.views.requests.get')
    @patch('slideshow.views.timezone_for_coords', return_value='America/Los_Angeles')
    def test_approximate_location_includes_timezone(self, _timezone_for_coords, mock_get):
        mock_get.return_value.json.return_value = {
            'status': 'success',
            'lat': 47.6101,
            'lon': -122.1442,
        }

        response = self.client.get(
            '/api/approx-location/',
            HTTP_X_FORWARDED_FOR='203.0.113.10',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['latitude'], 47.6101)
        self.assertEqual(response.json()['longitude'], -122.1442)
        self.assertEqual(response.json()['timezone'], 'America/Los_Angeles')


class TakbirAppShellTests(TestCase):
    def test_takbir_map_renders_persistent_four_tab_navigation(self):
        response = self.client.get('/mosque-map/', HTTP_HOST='takbir-al-ula.com')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-tab="prayer"')
        self.assertContains(response, 'data-tab="mosques"')
        self.assertContains(response, 'data-tab="notifications"')
        self.assertContains(response, 'data-tab="website"')
        self.assertContains(response, 'takbir_prayer_core.js')
        self.assertNotContains(response, 'class="login-btn"')

    def test_announcement_admin_page_can_be_embedded_same_origin(self):
        admin = User.objects.create_superuser('takbir-admin', 'admin@example.com', 'password')
        self.client.force_login(admin)

        response = self.client.get('/takbir/announcements/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['X-Frame-Options'], 'SAMEORIGIN')
