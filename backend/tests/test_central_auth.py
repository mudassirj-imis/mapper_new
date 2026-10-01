import json
import unittest
from unittest.mock import patch

import httpx

from backend.services import central_auth

_KEY = "k" * 32


class CentralAuthProtocolTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.settings_patch = patch.multiple(
            central_auth.settings,
            AUTH_BASE_URL="https://central.test/auth",
            AUTH_SERVICE_ENCRYPTION_KEY=_KEY,
        )
        self.settings_patch.start()

    def tearDown(self):
        self.settings_patch.stop()

    def test_encrypt_decrypt_round_trip_uses_nonce_tag_ciphertext_layout(self):
        encrypted = central_auth.encrypt_auth_json({"email": "u", "password": "p"})
        self.assertEqual(
            central_auth.decrypt_auth_json(encrypted),
            {"email": "u", "password": "p"},
        )

    async def test_login_gets_pre_auth_token_and_decrypts_central_response(self):
        calls = []

        async def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            if request.url.path == "/auth/get_token":
                return httpx.Response(
                    200,
                    json={
                        "status": "success",
                        "code": 200,
                        "message": "ok",
                        "data": {"token": "pre-auth"},
                    },
                )
            if request.url.path == "/auth/auth1/login":
                self.assertEqual(request.headers["authorization"], "Bearer pre-auth")
                body = json.loads(request.content)
                self.assertEqual(
                    central_auth.decrypt_auth_json(body["encrypted_data"]),
                    {
                        "email": "user@example.com",
                        "password": "secret",
                        "interface_type": "W",
                    },
                )
                return httpx.Response(
                    200,
                    json={
                        "encrypted_data": central_auth.encrypt_auth_json(
                            {
                                "status": "success",
                                "code": 200,
                                "message": "ok",
                                "data": {
                                    "user": {
                                        "id": 7,
                                        "name": "Test User",
                                        "email": "user@example.com",
                                        "roles": ["Admin"],
                                    },
                                    "access_token": "access",
                                    "refresh_token": "refresh",
                                    "access_token_expires_in": 900,
                                },
                            }
                        )
                    },
                )
            return httpx.Response(404, json={"detail": "not found"})

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            base_url="https://central.test",
        ) as client:
            session = await central_auth.central_login(
                client, "user@example.com", "secret"
            )

        self.assertEqual(
            [request.url.path for request in calls],
            [
                "/auth/get_token",
                "/auth/auth1/login",
            ],
        )
        self.assertEqual(session.access_token, "access")
        self.assertEqual(session.refresh_token, "refresh")
        self.assertEqual(session.user.id, 7)
        self.assertEqual(session.user.roles, ["Admin"])

    async def test_permissions_validates_access_token_and_normalizes_user(self):
        async def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url.path, "/auth/auth1/permissions")
            self.assertEqual(request.headers["authorization"], "Bearer access")
            return httpx.Response(
                200,
                json={
                    "encrypted_data": central_auth.encrypt_auth_json(
                        {
                            "status": "success",
                            "code": 200,
                            "message": "ok",
                            "data": {
                                "user": {
                                    "id": 7,
                                    "name": "Test User",
                                    "email": "user@example.com",
                                    "roles": ["Admin"],
                                    "is_super_admin": True,
                                },
                                "permissions_by_program": {"1": {"read": True}},
                            },
                        }
                    )
                },
            )

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            base_url="https://central.test",
        ) as client:
            user = await central_auth.validate_access_token(client, "access")

        self.assertEqual(user.id, 7)
        self.assertEqual(user.roles, ["Admin"])
        self.assertTrue(user.is_super_admin)
        self.assertEqual(user.permissions, {"1": {"read": True}})

    async def test_encrypted_central_error_is_mapped_to_rejection(self):
        async def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/auth/get_token":
                return httpx.Response(200, json={"data": {"token": "pre-auth"}})
            return httpx.Response(
                401,
                json={
                    "encrypted_data": central_auth.encrypt_auth_json(
                        {
                            "status": "error",
                            "code": 401,
                            "message": "Invalid username or password",
                            "data": None,
                        }
                    )
                },
            )

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            base_url="https://central.test",
        ) as client:
            with self.assertRaises(central_auth.CentralAuthRejected) as raised:
                await central_auth.central_login(client, "bad@example.com", "bad")

        self.assertEqual(raised.exception.status_code, 401)
        self.assertIn("Invalid username", raised.exception.message)


if __name__ == "__main__":
    unittest.main()
