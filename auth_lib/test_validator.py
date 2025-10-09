import unittest
from unittest.mock import patch, MagicMock
import jwt
from datetime import datetime, timedelta, timezone

from auth_lib.validator import is_token_valid, get_oidc_config, get_jwks

# Sample keys for testing
PRIVATE_KEY = "This is a placeholder for the private key used in tests. Do not commit the actual private key."
PUBLIC_JWK = {
  "kty": "RSA",
  "n": "1k5Z-4jsVglHTo5pWBEphw200mH9uj3Dt1w_K7Z-M5JVlHbHI3cWi_vKcZnrOtUlZOaaapOPHntDRXezL88Z7Vo2qIE5kuhotIj6DZQLHkLBENNNQ8kT6AIcXQt7boQCroEstNOls3pBKJ3CusSvRb8OX_7tOeaRJg7LN9VTK4yS4H_dvO7r8xJGZ7XVKhDtd5Jb999YVWWTRP77LDlN91qfhgSjvIzpO1M-9yuqxCAAOTAcDd5GiWsB77arxqX5e3O9XlUYzJfQ4io6cBE7Z3lfWTtqGox56FW1xh9mQQYDomC6uK-jPQzF85uHUk02MzYKyPbLN0G4tgkPZG4Adw",
  "e": "AQAB",
  "kid": "test-key-id",
  "use": "sig",
  "alg": "RS256"
}

class TestTokenValidator(unittest.TestCase):

    def setUp(self):
        # Reset caches for each test
        global oidc_config, jwks
        oidc_config = None
        jwks = None

    def _generate_test_token(self, tenant_id=None, expires_in_seconds=3600):
        payload = {
            "iss": "http://localhost:5000",
            "aud": "http://localhost:8081",
            "sub": "test-user",
            "exp": datetime.now(timezone.utc) + timedelta(seconds=expires_in_seconds),
            "iat": datetime.now(timezone.utc),
        }
        if tenant_id:
            payload["tenant_id"] = tenant_id

        headers = {"kid": "test-key-id", "alg": "RS256"}
        return jwt.encode(payload, PRIVATE_KEY, algorithm="RS256", headers=headers)

    @patch('requests.get')
    def test_valid_token_with_tenant_id(self, mock_get):
        """Test a valid token with a matching tenant ID."""
        mock_oidc_response = MagicMock()
        mock_oidc_response.json.return_value = {"jwks_uri": "http://localhost:5000/jwks.json"}
        mock_oidc_response.raise_for_status.return_value = None

        mock_jwks_response = MagicMock()
        mock_jwks_response.json.return_value = {"keys": [PUBLIC_JWK]}
        mock_jwks_response.raise_for_status.return_value = None

        mock_get.side_effect = [mock_oidc_response, mock_jwks_response]

        token = self._generate_test_token(tenant_id="tenant-abc")
        is_valid, _ = is_token_valid(token, required_tenant_id="tenant-abc")
        self.assertTrue(is_valid)

    @patch('requests.get')
    def test_valid_token_no_tenant_id_check(self, mock_get):
        """Test a valid token when no tenant ID check is required."""
        mock_oidc_response = MagicMock()
        mock_oidc_response.json.return_value = {"jwks_uri": "http://localhost:5000/jwks.json"}
        mock_oidc_response.raise_for_status.return_value = None

        mock_jwks_response = MagicMock()
        mock_jwks_response.json.return_value = {"keys": [PUBLIC_JWK]}
        mock_jwks_response.raise_for_status.return_value = None

        mock_get.side_effect = [mock_oidc_response, mock_jwks_response]

        token = self._generate_test_token(tenant_id="tenant-abc")
        is_valid, _ = is_token_valid(token) # No required_tenant_id
        self.assertTrue(is_valid)

    @patch('requests.get')
    def test_expired_token(self, mock_get):
        """Test that an expired token is rejected."""
        mock_oidc_response = MagicMock()
        mock_oidc_response.json.return_value = {"jwks_uri": "http://localhost:5000/jwks.json"}
        mock_oidc_response.raise_for_status.return_value = None

        mock_jwks_response = MagicMock()
        mock_jwks_response.json.return_value = {"keys": [PUBLIC_JWK]}
        mock_jwks_response.raise_for_status.return_value = None

        mock_get.side_effect = [mock_oidc_response, mock_jwks_response]

        token = self._generate_test_token(tenant_id="tenant-abc", expires_in_seconds=-1)
        is_valid, message = is_token_valid(token, required_tenant_id="tenant-abc")
        self.assertFalse(is_valid)
        self.assertEqual(message, "Token has expired.")

    @patch('requests.get')
    def test_mismatched_tenant_id(self, mock_get):
        """Test that a token with a mismatched tenant ID is rejected."""
        mock_oidc_response = MagicMock()
        mock_oidc_response.json.return_value = {"jwks_uri": "http://localhost:5000/jwks.json"}
        mock_oidc_response.raise_for_status.return_value = None

        mock_jwks_response = MagicMock()
        mock_jwks_response.json.return_value = {"keys": [PUBLIC_JWK]}
        mock_jwks_response.raise_for_status.return_value = None

        mock_get.side_effect = [mock_oidc_response, mock_jwks_response]

        token = self._generate_test_token(tenant_id="tenant-xyz")
        is_valid, message = is_token_valid(token, required_tenant_id="tenant-abc")
        self.assertFalse(is_valid)
        self.assertIn("does not match required tenant_id", message)

    @patch('requests.get')
    def test_missing_tenant_id_when_required(self, mock_get):
        """Test that a token without a tenant_id is rejected when one is required."""
        mock_oidc_response = MagicMock()
        mock_oidc_response.json.return_value = {"jwks_uri": "http://localhost:5000/jwks.json"}
        mock_oidc_response.raise_for_status.return_value = None

        mock_jwks_response = MagicMock()
        mock_jwks_response.json.return_value = {"keys": [PUBLIC_JWK]}
        mock_jwks_response.raise_for_status.return_value = None

        mock_get.side_effect = [mock_oidc_response, mock_jwks_response]

        token = self._generate_test_token() # No tenant_id in token
        is_valid, message = is_token_valid(token, required_tenant_id="tenant-abc")
        self.assertFalse(is_valid)
        self.assertEqual(message, "'tenant_id' claim not found in token.")


if __name__ == "__main__":
    unittest.main()
