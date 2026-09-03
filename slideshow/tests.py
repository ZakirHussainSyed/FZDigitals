from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from .models import Device, DevicePairing, MediaFile


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
