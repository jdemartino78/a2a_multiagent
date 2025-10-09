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

import json
from jwcrypto import jwk
import os

def generate_jwks():
    """
    Reads a PEM-encoded public key, converts it to a JWK, and saves it
    to a jwks.json file.
    """
    public_key_path = 'pubkey.pub'
    jwks_path = 'jwks.json'
    sample_jwks_path = 'sample.jwks.json'

    if not os.path.exists(public_key_path):
        print(f"Error: Public key file not found at '{public_key_path}'.")
        print("Please generate the key pair first using 'ssh-keygen'.")
        return

    if not os.path.exists(sample_jwks_path):
        print(f"Error: Sample JWKS file not found at '{sample_jwks_path}'.")
        return

    # Read the PEM public key
    with open(public_key_path, 'rb') as f:
        pem_data = f.read()

    # Convert PEM to JWK
    try:
        key = jwk.JWK.from_pem(pem_data)
        # Export the public part as a dictionary
        jwk_data = key.export(as_dict=True)
        # Add required fields for OIDC
        jwk_data['use'] = 'sig'
        jwk_data['alg'] = 'RS256'
        # Use a consistent key ID
        jwk_data['kid'] = 'a2a-mock-idp-key'

    except Exception as e:
        print(f"An error occurred during JWK conversion: {e}")
        return

    # Load the sample jwks structure
    with open(sample_jwks_path, 'r') as f:
        jwks_structure = json.load(f)

    # Replace the placeholder key with the generated one
    jwks_structure['keys'] = [jwk_data]

    # Write the final jwks.json file
    with open(jwks_path, 'w') as f:
        json.dump(jwks_structure, f, indent=2)

    print(f"Successfully generated '{jwks_path}' with the new public key.")

if __name__ == "__main__":
    generate_jwks()
