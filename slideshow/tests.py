from datetime import date, datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.http import HttpResponse
from django.template.loader import get_template
from django.test import TestCase

from .models import (
    Device, DevicePairing, MediaFile, Mosque, PrayerTime, PrayerTimeOverride,
    TakbirAnnouncement, MosqueAnnouncement, UserProfile,
)
from .languages import INDIAN_LANGUAGES, prayer_labels_for


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


class MultilingualQuranContentTests(TestCase):
    def test_scheduled_language_catalog_and_regional_prayer_labels(self):
        self.assertEqual(len(INDIAN_LANGUAGES), 22)
        self.assertEqual(prayer_labels_for('mr')['fajr'], 'फज्र')
        self.assertEqual(prayer_labels_for('gu')['jummah2'], 'જુમા 2')
        self.assertEqual(prayer_labels_for('ur')['jummah2'], 'جمعہ ۲')

    def test_quranic_package_is_public_versioned_and_review_marked(self):
        response = self.client.get('/api/public/quranic-content/')

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['success'])
        self.assertEqual(payload['version'], 3)
        self.assertEqual(len(payload['entries']), 10)
        self.assertEqual(payload['available_translation_languages'], ['en', 'ur', 'te'])
        self.assertEqual(payload['arabic_source']['provider'], 'Tanzil Project')
        self.assertTrue(all('te' in entry['translations'] for entry in payload['entries']))
        self.assertTrue(all(entry['review_status'] == 'draft' for entry in payload['entries']))
        self.assertIn('max-age=86400', response['Cache-Control'])

    def test_device_feed_includes_selected_language_prayer_labels(self):
        user = User.objects.create_user('gujarati-mosque', password='pw')
        mosque = Mosque.objects.create(
            user=user,
            name='Gujarati Mosque',
            regional_language='gu',
            timezone='Asia/Kolkata',
        )
        device = Device.objects.create(
            device_id='TV-GUJARATI',
            token='a' * 64,
            user=user,
            mosque=mosque,
        )
        central = TakbirAnnouncement.objects.create(
            title='Central notice', body='Central message', is_published=True,
            created_by=user, published_at=datetime.now(ZoneInfo('UTC')),
        )
        local = MosqueAnnouncement.objects.create(
            mosque=mosque, content_type='text', title='Local notice', body='Local message')

        response = self.client.get(
            f'/api/device/{device.device_id}/slideshow/?token={device.token}')

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['regional_language'], 'gu')
        self.assertEqual(payload['prayer_labels']['fajr'], 'ફજર')
        slides = {slide['id']: slide for slide in payload['files']}
        self.assertEqual(slides[f'central-{central.id}']['body'], 'Central message')
        self.assertEqual(slides[f'mosque-{local.id}']['body'], 'Local message')


class MosqueAnnouncementTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('mosque-admin', password='pw')
        self.mosque = Mosque.objects.create(user=self.user, name='Test Mosque')
        UserProfile.objects.create(user=self.user, vertical='mosque')

    def test_mosque_dashboard_opens_announcements_and_slideshow_remains_available(self):
        self.client.force_login(self.user)

        response = self.client.get(f'/{self.user.id}/')
        self.assertRedirects(response, '/mosque-announcements/', fetch_redirect_response=False)

        with patch('slideshow.views.render', return_value=HttpResponse()) as render_template:
            response = self.client.get('/mosque-slideshow/')
        self.assertEqual(response.status_code, 200)
        render_template.assert_called_once()
        self.assertEqual(render_template.call_args.args[1], 'slideshow/index.html')

    def test_non_mosque_dashboard_still_opens_slideshow(self):
        other = User.objects.create_user('regular-dashboard', password='pw')
        UserProfile.objects.create(user=other, vertical='bank')
        self.client.force_login(other)

        with patch('slideshow.views.render', return_value=HttpResponse()):
            response = self.client.get(f'/{other.id}/')

        self.assertEqual(response.status_code, 200)

    def test_account_can_create_text_announcement_and_limit_is_two(self):
        self.client.force_login(self.user)
        response = self.client.post('/mosque-announcements/', {
            'action': 'create',
            'content_type': 'text',
            'title': 'First notice',
            'body': 'First message',
        })
        self.assertEqual(response.status_code, 302)
        MosqueAnnouncement.objects.create(
            mosque=self.mosque, content_type='text', title='Second notice', body='Second message')

        response = self.client.post('/mosque-announcements/', {
            'action': 'create',
            'content_type': 'text',
            'title': 'Third notice',
            'body': 'Third message',
        })

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.mosque.announcements.count(), 2)

    def test_account_can_create_photo_announcement(self):
        self.client.force_login(self.user)
        response = self.client.post('/mosque-announcements/', {
            'action': 'create',
            'content_type': 'image',
            'image': image('notice.png'),
        })

        self.assertEqual(response.status_code, 302)
        announcement = self.mosque.announcements.get()
        self.assertEqual(announcement.content_type, 'image')
        self.assertGreater(announcement.file_size, 0)
        announcement.image.delete(save=False)

    def test_announcements_template_renders_and_non_mosque_accounts_are_redirected(self):
        rendered = get_template('slideshow/mosque_announcements.html').render({
            'mosque': self.mosque,
            'announcements': [],
            'max_announcements': 2,
        })
        self.assertIn('Announcements for Test Mosque', rendered)

        other = User.objects.create_user('not-mosque', password='pw')
        UserProfile.objects.create(user=other, vertical='bank')
        self.client.force_login(other)
        response = self.client.get('/mosque-announcements/')
        self.assertEqual(response.status_code, 302)

    def test_announcement_requires_exactly_one_content_mode(self):
        with self.assertRaises(ValidationError):
            MosqueAnnouncement.objects.create(
                mosque=self.mosque,
                content_type='text',
                title='Text',
                body='Message',
                image=image(),
            )


class TakbirAnnouncementAdminTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            'announcement-admin', 'announcement-admin@example.com', 'password')

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

    @patch('slideshow.views.requests.get')
    def test_location_name_returns_area_and_country(self, mock_get):
        mock_get.return_value.raise_for_status.return_value = None
        mock_get.return_value.json.return_value = {
            'address': {
                'city': 'Bellevue',
                'state': 'Washington',
                'country': 'United States',
            },
        }

        response = self.client.get(
            '/api/location-name/',
            {'latitude': '47.6101', 'longitude': '-122.1442'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['success'])
        self.assertEqual(response.json()['name'], 'Bellevue, United States')


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
