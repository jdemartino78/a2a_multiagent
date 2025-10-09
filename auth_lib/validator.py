# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import requests
import jwt

# Cache for OIDC discovery and JWKS
oidc_config = None
jwks = None


def get_oidc_config():
    """Fetches and caches the OIDC configuration."""
    global oidc_config
    if oidc_config is None:
        try:
            oidc_config_url = os.environ.get(
                "OIDC_CONFIG_URL", "http://localhost:5000/.well-known/openid-configuration"
            )
            response = requests.get(oidc_config_url)
            response.raise_for_status()
            oidc_config = response.json()
        except requests.exceptions.RequestException as e:
            return None, f"Error fetching OIDC config: {e}"
    return oidc_config, None


def get_jwks():
    """Fetches and caches the JSON Web Key Set (JWKS)."""
    global jwks
    if jwks is None:
        config, error = get_oidc_config()
        if error:
            return None, error
        jwks_uri = config.get("jwks_uri")
        if not jwks_uri:
            return None, "jwks_uri not found in OIDC configuration."
        try:
            response = requests.get(jwks_uri)
            response.raise_for_status()
            jwks = response.json()
        except requests.exceptions.RequestException as e:
            return None, f"Error fetching JWKS: {e}"
    return jwks, None


def is_token_valid(token: str, required_tenant_id: str = None):
    """
    Validates a JWT token. If required_tenant_id is provided, it also
    validates that the tenant_id claim in the token matches.
    """
    if not token:
        return False, "Token is empty."

    jwks_data, error = get_jwks()
    if error:
        return False, f"Failed to get JWKS: {error}"

    try:
        header = jwt.get_unverified_header(token)
        kid = header.get("kid")
        if not kid:
            return False, "Token header missing 'kid'."

        key = next((
            k for k in jwks_data.get("keys", []) if k.get("kid") == kid
        ), None)
        if not key:
            return False, "No matching key found in JWKS."

        public_key = jwt.algorithms.RSAAlgorithm.from_jwk(key)

        decoded_token = jwt.decode(
            token,
            key=public_key,
            issuer="http://localhost:5000",
            audience="http://localhost:8081",
            algorithms=[header["alg"]],
            options={"verify_exp": True, "verify_aud": True, "verify_iss": True},
        )

        if required_tenant_id:
            token_tenant_id = decoded_token.get("tenant_id")
            if not token_tenant_id:
                return False, "'tenant_id' claim not found in token."

            if token_tenant_id != required_tenant_id:
                return False, f"Token 'tenant_id' ({token_tenant_id}) does not match required tenant_id ({required_tenant_id})."

        return True, decoded_token
    except jwt.ExpiredSignatureError:
        return False, "Token has expired."
    except jwt.InvalidAudienceError:
        return False, "Invalid audience."
    except jwt.InvalidIssuerError:
        return False, "Invalid issuer."
    except jwt.InvalidTokenError as e:
        return False, f"Invalid token: {e}"
    except Exception as e:
        return False, f"An unexpected error occurred during token validation: {e}"
