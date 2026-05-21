"""Disposable email helpers for single runs."""

import json
import secrets
import uuid
from urllib.error import URLError
from urllib.request import Request, urlopen

PURELYMAIL_API = "https://purelymail.com/api/v0"


def purelymail_request(endpoint: str, body: dict, api_key: str) -> dict:
    data = json.dumps(body).encode()
    req = Request(
        f"{PURELYMAIL_API}/{endpoint}",
        data=data,
        headers={"Purelymail-Api-Token": api_key, "Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def create_email(api_key: str, domain: str) -> tuple[str, str]:
    local = f"cb{uuid.uuid4().hex[:12]}"
    password = secrets.token_urlsafe(16)
    purelymail_request(
        "createUser",
        {
            "userName": local,
            "domainName": domain,
            "password": password,
            "enablePasswordReset": False,
            "sendWelcomeEmail": False,
        },
        api_key,
    )
    email = f"{local}@{domain}"
    print(f"  Created email: {email}")
    print(f"  Password: {password}")
    return email, password


def delete_email(api_key: str, email: str) -> None:
    try:
        purelymail_request("deleteUser", {"userName": email}, api_key)
        print(f"  Deleted email: {email}")
    except (URLError, Exception) as e:
        print(f"  WARNING: Failed to delete email {email}: {e}")
