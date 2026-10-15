"""A thin client for the Metabase HTTP API, enough to build the §8 dashboards."""

import json
import time
import urllib.error
import urllib.request


class MetabaseError(RuntimeError):
    pass


class Metabase:
    def __init__(self, base_url: str):
        self.base = base_url.rstrip("/")
        self.session = None

    def call(self, method, path, body=None):
        headers = {"Content-Type": "application/json"}
        if self.session:
            headers["X-Metabase-Session"] = self.session
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as exc:
            raise MetabaseError(f"{method} {path}: {exc.code} {exc.read().decode()[:300]}") from exc
        return json.loads(raw) if raw else None

    def wait_until_up(self, seconds=240):
        deadline = time.time() + seconds
        while time.time() < deadline:
            try:
                if self.call("GET", "/api/health").get("status") == "ok":
                    return
            except (MetabaseError, OSError, ValueError):
                pass
            time.sleep(3)
        raise MetabaseError("Metabase did not become healthy in time.")

    def sign_in(self, email, password, site_name):
        """Log in; on a fresh instance (no user yet) run first-time setup instead."""
        try:
            self.session = self.call("POST", "/api/session", {"username": email, "password": password})["id"]
            return
        except MetabaseError:
            token = self.call("GET", "/api/session/properties").get("setup-token")
            if not token:
                raise
        out = self.call(
            "POST",
            "/api/setup",
            {
                "token": token,
                "user": {"first_name": "EOPP", "last_name": "Admin", "email": email, "password": password},
                "prefs": {"site_name": site_name, "allow_tracking": False},
            },
        )
        self.session = out["id"]
