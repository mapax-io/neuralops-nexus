"""
Unit tests for authn services outside the permission system.
(Permission behaviour lives in authn/permissions/tests.py.)
"""
import shutil
import tempfile
import time
from io import BytesIO
from unittest.mock import patch

import jwt as pyjwt
from cryptography.hazmat.primitives.asymmetric import ec
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings
from jwt.jwk_set_cache import JWKSetCache
from PIL import Image

from authn.services import (
    AVATAR_MAX_BYTES, AvatarError, assign_display_name, clear_profile_photo,
    set_profile_photo,
)
from authn.supabase import jwks_client, verify_supabase_token

User = get_user_model()

MEDIA = tempfile.mkdtemp(prefix="nx-avatar-test-")


def png_upload(name="photo.png", size=(800, 600), mode="RGB"):
    buf = BytesIO()
    Image.new(mode, size, (10, 120, 200)).save(buf, format="PNG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")


@override_settings(MEDIA_ROOT=MEDIA)
class ProfilePhotoTests(TestCase):
    """
    Uploads are user-supplied bytes. Nothing about the request is trusted --
    not the filename, not the content type, not the extension.
    """

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(MEDIA, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.user = User.objects.create_user(username="sara", email="sara@acme.test", password="x")

    # ── it works ─────────────────────────────────────────────────────────────

    def test_an_uploaded_image_becomes_the_users_photo(self):
        path = set_profile_photo(self.user, png_upload())
        self.user.refresh_from_db()
        self.assertEqual(self.user.avatar.name, path)
        self.assertTrue(path.startswith("avatars/custom/"))

    def test_it_is_re_encoded_rather_than_stored_as_sent(self):
        # Re-encoding is what proves it is really an image, drops EXIF, and
        # stops a file that is both a valid image and a valid script surviving.
        set_profile_photo(self.user, png_upload())
        self.user.refresh_from_db()
        self.user.avatar.open("rb")
        self.assertEqual(Image.open(self.user.avatar.file).format, "JPEG")

    def test_it_is_scaled_down(self):
        set_profile_photo(self.user, png_upload(size=(2000, 1500)))
        self.user.refresh_from_db()
        self.user.avatar.open("rb")
        self.assertLessEqual(max(Image.open(self.user.avatar.file).size), 512)

    def test_transparency_is_flattened_onto_white_not_black(self):
        path = set_profile_photo(self.user, png_upload(mode="RGBA"))
        self.assertTrue(path.endswith(".jpg"))

    # ── it refuses what it should ────────────────────────────────────────────

    def test_a_non_image_is_refused(self):
        bad = SimpleUploadedFile("photo.png", b"not an image at all", content_type="image/png")
        with self.assertRaises(AvatarError):
            set_profile_photo(self.user, bad)
        self.user.refresh_from_db()
        self.assertFalse(self.user.avatar)

    def test_an_oversize_file_is_refused_before_decoding(self):
        big = png_upload()
        big.size = AVATAR_MAX_BYTES + 1
        with self.assertRaises(AvatarError):
            set_profile_photo(self.user, big)

    # ── the filename is the server's, never the client's ─────────────────────

    def test_the_stored_name_ignores_the_uploaded_filename(self):
        path = set_profile_photo(self.user, png_upload(name="../../../etc/passwd.png"))
        self.assertNotIn("..", path)
        self.assertTrue(path.startswith("avatars/custom/"))
        self.assertIn(str(self.user.id), path)

    def test_replacing_a_photo_uses_a_new_name(self):
        # A fresh name each time, so a cached old photo is never served in place
        # of a new one.
        first = set_profile_photo(self.user, png_upload())
        second = set_profile_photo(self.user, png_upload())
        self.assertNotEqual(first, second)

    # ── removing it ──────────────────────────────────────────────────────────

    def test_clearing_falls_back_to_a_default_rather_than_nothing(self):
        set_profile_photo(self.user, png_upload())
        result = clear_profile_photo(self.user)
        self.user.refresh_from_db()
        # With no pool seeded this is None, and the UI renders initials; with a
        # pool it is a pool file. Either way the custom photo is gone.
        self.assertFalse(self.user.avatar.name.startswith("avatars/custom/"))
        self.assertTrue(result is None or result.startswith("avatars/pool/"))

    def test_clearing_when_there_was_never_a_photo_is_harmless(self):
        self.assertIsNone(clear_profile_photo(self.user) or None)


class AssignDisplayNameTests(TestCase):
    """The initials shown for an empty avatar are derived from this."""

    def test_derives_a_name_from_the_email_local_part(self):
        user = User.objects.create_user(username="u1", email="Sara.Khan@acme.test", password="x")
        self.assertEqual(assign_display_name(user), "sarakhan")

    def test_is_idempotent(self):
        user = User.objects.create_user(username="u2", email="omar@acme.test", password="x")
        self.assertEqual(assign_display_name(user), assign_display_name(user))

    def test_disambiguates_a_taken_name(self):
        User.objects.create_user(username="u3", email="omar@a.test", password="x", display_name="omar")
        other = User.objects.create_user(username="u4", email="omar@b.test", password="x")
        self.assertTrue(assign_display_name(other).startswith("omar_"))


class AvatarUrlTests(TestCase):
    """
    Avatar paths must be server-relative. An absolute URL built from
    NEURALOPS_SERVER_URL pins every image to one hostname, which is only
    correct when the client reached the server by that exact name -- so
    localhost, a LAN address, or a tunnel that is down all render broken
    images while the file sits on disk.
    """

    def setUp(self):
        self.user = User.objects.create_user(username="p", email="p@acme.test", password="x")

    def test_none_when_there_is_no_avatar(self):
        self.assertIsNone(self.user.get_avatar_url())

    def test_it_is_relative_and_carries_no_hostname(self):
        self.user.avatar.name = "avatars/pool/human/021.png"
        url = self.user.get_avatar_url()
        self.assertTrue(url.startswith("/"), url)
        self.assertNotIn("://", url)
        self.assertIn("avatars/pool/human/021.png", url)

    @override_settings(NEURALOPS_SERVER_URL="https://somewhere-else.example")
    def test_it_ignores_the_configured_server_url(self):
        # The whole point: how the server is addressed elsewhere must not
        # decide where a browser looks for the image.
        self.user.avatar.name = "avatars/pool/human/021.png"
        self.assertNotIn("somewhere-else", self.user.get_avatar_url())


def _key_pair(kid):
    private = ec.generate_private_key(ec.SECP256R1())
    public = pyjwt.algorithms.ECAlgorithm.to_jwk(private.public_key(), as_dict=True)
    public.update({"kid": kid, "use": "sig", "alg": "ES256"})
    return private, public


def _token(private, kid):
    now = int(time.time())
    claims = {
        "sub": "u1", "email": "u@example.com", "iat": now, "exp": now + 60,
        "aud": settings.SUPABASE_JWT_AUDIENCE, "iss": settings.SUPABASE_JWT_ISSUER,
    }
    return pyjwt.encode(claims, private, algorithm="ES256", headers={"kid": kid})


class JwksClientTests(SimpleTestCase):
    """Verifying a token must not hit the network for a key already seen.

    With only the 5-minute JWK-set cache, the first request after expiry
    re-fetched the set synchronously on the one sync thread, and every other
    request waited behind it for as long as that fetch took (0.4-4.5 s
    measured) -- seen as chats stuck on their loader.
    """

    def setUp(self):
        jwks_client.get_signing_key.cache_clear()
        self._expire_set()

    def _expire_set(self):
        # What the lifespan does on its own after five minutes -- forced.
        jwks_client.jwk_set_cache = JWKSetCache(jwks_client.jwk_set_cache.lifespan)

    def test_a_key_seen_once_is_never_fetched_again(self):
        private, public = _key_pair("kid-1")
        with patch.object(jwks_client, "fetch_data", return_value={"keys": [public]}) as fetch:
            self.assertEqual(verify_supabase_token(_token(private, "kid-1"))["sub"], "u1")
            self._expire_set()
            verify_supabase_token(_token(private, "kid-1"))
        self.assertEqual(fetch.call_count, 1)

    def test_an_unknown_key_id_still_refreshes_the_set(self):
        old_private, old_public = _key_pair("kid-1")
        new_private, new_public = _key_pair("kid-2")
        answers = [{"keys": [old_public]}, {"keys": [old_public, new_public]}]
        with patch.object(jwks_client, "fetch_data", side_effect=answers) as fetch:
            verify_supabase_token(_token(old_private, "kid-1"))
            self.assertEqual(verify_supabase_token(_token(new_private, "kid-2"))["sub"], "u1")
        self.assertEqual(fetch.call_count, 2)

    def test_the_one_fetch_left_cannot_hold_a_request_for_long(self):
        self.assertLessEqual(jwks_client.timeout, 10)
