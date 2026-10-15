#!/usr/bin/env python3
"""Shopify Admin API client via client credentials grant.

Docs:
  https://shopify.dev/docs/apps/build/authentication-authorization/client-credentials-grant
  https://shopify.dev/docs/apps/build/authentication-authorization/access-tokens
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API_VERSION = os.environ.get("SHOPIFY_API_VERSION", "2026-10")

_token = None
_token_expires_at = 0.0


def _env(name):
    value = os.environ.get(name)
    if not value:
        sys.exit(f"missing environment variable: {name}")
    return value


def _post(url, data, headers):
    request = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, json.loads(response.read().decode())
    except urllib.error.HTTPError as error:
        body = error.read().decode(errors="replace")
        try:
            return error.code, json.loads(body)
        except json.JSONDecodeError:
            return error.code, {"raw": body[:500]}


def get_token():
    global _token, _token_expires_at
    if _token and time.time() < _token_expires_at - 300:
        return _token

    domain = _env("SHOPIFY_STORE_DOMAIN")
    body = urllib.parse.urlencode(
        {
            "grant_type": "client_credentials",
            "client_id": _env("SHOPIFY_CLIENT_ID"),
            "client_secret": _env("SHOPIFY_CLIENT_SECRET"),
        }
    ).encode()

    status, payload = _post(
        f"https://{domain}/admin/oauth/access_token",
        body,
        {"Content-Type": "application/x-www-form-urlencoded"},
    )
    if status != 200 or "access_token" not in payload:
        sys.exit(f"token request failed: HTTP {status} {json.dumps(payload)}")

    _token = payload["access_token"]
    _token_expires_at = time.time() + payload["expires_in"]
    return _token


def token_info():
    domain = _env("SHOPIFY_STORE_DOMAIN")
    body = urllib.parse.urlencode(
        {
            "grant_type": "client_credentials",
            "client_id": _env("SHOPIFY_CLIENT_ID"),
            "client_secret": _env("SHOPIFY_CLIENT_SECRET"),
        }
    ).encode()
    status, payload = _post(
        f"https://{domain}/admin/oauth/access_token",
        body,
        {"Content-Type": "application/x-www-form-urlencoded"},
    )
    return status, payload


def graphql(query, variables=None):
    domain = _env("SHOPIFY_STORE_DOMAIN")
    status, payload = _post(
        f"https://{domain}/admin/api/{API_VERSION}/graphql.json",
        json.dumps({"query": query, "variables": variables or {}}).encode(),
        {
            "Content-Type": "application/json",
            "X-Shopify-Access-Token": get_token(),
        },
    )
    if status != 200:
        sys.exit(f"graphql request failed: HTTP {status} {json.dumps(payload)}")
    if payload.get("errors"):
        sys.exit(f"graphql errors: {json.dumps(payload['errors'])}")
    return payload["data"]


def main():
    status, payload = token_info()
    print(f"token endpoint: HTTP {status}")
    print(f"  scope:        {payload.get('scope')}")
    print(f"  expires_in:   {payload.get('expires_in')}")
    print(f"  access_token: {len(payload.get('access_token', ''))} chars (not printed)")

    global _token, _token_expires_at
    _token = payload["access_token"]
    _token_expires_at = time.time() + payload["expires_in"]

    data = graphql("{ shop { name myshopifyDomain } }")
    print(f"graphql api version: {API_VERSION}")
    print(json.dumps(data, indent=2))


if __name__ == "__main__":
    main()
