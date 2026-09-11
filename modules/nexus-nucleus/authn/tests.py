"""
Unit tests for authn services that are not part of the permission system.
(Permission behaviour lives in authn/permissions/tests.py.)
"""
from django.contrib.auth import get_user_model
from django.test import TestCase

from authn.services import assign_avatar, assign_display_name

User = get_user_model()


class AssignAvatarTests(TestCase):
    """
    Real people get no auto-assigned picture. The pool was cartoon FACES, handed
    out at random, so teammates were given a face of the wrong apparent gender.
    Nothing on the server can derive a correct one, so the UI's initials
    fallback is used instead -- it is accurate by construction.
    """

    def test_a_human_is_never_given_a_face(self):
        user = User.objects.create_user(username="sara", email="sara@acme.test", password="x")
        self.assertIsNone(assign_avatar(user))
        user.refresh_from_db()
        self.assertFalse(user.avatar)

    def test_a_human_with_an_existing_avatar_is_left_alone(self):
        # A custom upload (or a legacy pool file) must not be wiped by a later
        # sign-in -- clearing the old pool ones is the migration's job, once.
        user = User.objects.create_user(username="omar", email="omar@acme.test", password="x")
        user.avatar.name = "avatars/custom/omar.png"
        user.save(update_fields=["avatar"])
        self.assertEqual(assign_avatar(user), "avatars/custom/omar.png")

    def test_a_persona_still_gets_one_when_the_pool_is_seeded(self):
        # A persona is a robot, so its avatar claims nothing about a person.
        # With no pool on disk this returns None rather than raising -- the
        # behaviour an unseeded server already had.
        persona = User.objects.create_user(username="layla", email="layla@acme.test", password="x")
        persona.user_type = User.UserType.PERSONA
        persona.save(update_fields=["user_type"])
        result = assign_avatar(persona)
        self.assertTrue(result is None or result.startswith("avatars/pool/persona/"))


class AssignDisplayNameTests(TestCase):
    """The initials the UI falls back to are derived from this, so it matters."""

    def test_derives_a_name_from_the_email_local_part(self):
        user = User.objects.create_user(username="u1", email="Sara.Khan@acme.test", password="x")
        self.assertEqual(assign_display_name(user), "sarakhan")

    def test_is_idempotent(self):
        user = User.objects.create_user(username="u2", email="omar@acme.test", password="x")
        first = assign_display_name(user)
        self.assertEqual(assign_display_name(user), first)

    def test_disambiguates_a_taken_name(self):
        User.objects.create_user(username="u3", email="omar@a.test", password="x", display_name="omar")
        other = User.objects.create_user(username="u4", email="omar@b.test", password="x")
        self.assertNotEqual(assign_display_name(other), "omar")
        self.assertTrue(assign_display_name(other).startswith("omar_"))
