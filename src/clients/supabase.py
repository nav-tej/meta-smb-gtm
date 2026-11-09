"""Small server-only Supabase Auth and PostgREST HTTP adapter."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import httpx

from src.config import get_settings


class SupabaseError(Exception):
    """Sanitized upstream error, safe to translate to an API response."""

    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def configured() -> bool:
    """Whether both public authentication and server persistence are configured."""
    settings = get_settings()
    return all(
        getattr(settings, field, "")
        for field in ("supabase_url", "supabase_publishable_key", "supabase_secret_key")
    )


class SupabaseClient:
    """Never expose provider response bodies. HTTP clients are per-request so no
    connection outlives its event loop (test harnesses and serverless reuse)."""

    def __init__(self) -> None:
        self.timeout = httpx.Timeout(20, connect=5)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        access_token: str | None = None,
        secret: bool = False,
        params: dict[str, str] | None = None,
    ) -> Any:
        settings = get_settings()
        key = getattr(settings, "supabase_secret_key" if secret else "supabase_publishable_key", "")
        base_url = getattr(settings, "supabase_url", "").rstrip("/")
        if not key or not base_url:
            raise SupabaseError(503, "Accounts are not configured yet.")
        headers = {"apikey": key, "Accept": "application/json"}
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"
        elif key.startswith("eyJ"):
            headers["Authorization"] = f"Bearer {key}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=False) as http:
                result = await http.request(
                    method, base_url + path, json=body, headers=headers, params=params
                )
        except httpx.HTTPError as err:
            raise SupabaseError(503, "Account service is unavailable. Try again shortly.") from err
        if result.is_error or result.is_redirect:
            status = result.status_code
            if status in {400, 401, 403, 422}:
                raise SupabaseError(
                    401, "Sign in failed. Check your details and confirm your email."
                )
            if status == 429:
                raise SupabaseError(429, "Too many account requests. Try again shortly.")
            raise SupabaseError(503, "Account service is unavailable. Try again shortly.")
        if not result.content:
            return {}
        try:
            return result.json()
        except ValueError as err:
            raise SupabaseError(503, "Account service returned an invalid response.") from err

    async def auth(
        self,
        path: str,
        method: str = "GET",
        body: dict[str, Any] | None = None,
        access_token: str | None = None,
        secret: bool = False,
    ) -> dict[str, Any]:
        """Call a fixed Auth endpoint with a publishable key and optional verified JWT."""
        result = await self._request(
            method, "/auth/v1/" + path, body=body, access_token=access_token, secret=secret
        )
        if not isinstance(result, dict):
            raise SupabaseError(503, "Account service returned an invalid response.")
        return result

    async def rpc(self, name: str, params: dict[str, Any]) -> dict[str, Any]:
        """Invoke a server-only database function."""
        result = await self._request("POST", "/rest/v1/rpc/" + name, body=params, secret=True)
        if not isinstance(result, dict):
            raise SupabaseError(503, "Account service returned an invalid response.")
        return result

    async def workspace(self, user_id: str) -> list[dict[str, Any]]:
        """Read a workspace using the identity already verified by the Auth server."""
        result = await self._request(
            "GET",
            "/rest/v1/muse_workspaces",
            secret=True,
            params={
                "user_id": "eq." + user_id,
                "select": "document,version,updated_at",
                "limit": "1",
            },
        )
        if not isinstance(result, list):
            raise SupabaseError(503, "Account service returned an invalid response.")
        return result

    async def _storage(
        self, method: str, path: str, *, content: bytes | None = None, **kwargs: Any
    ) -> httpx.Response:
        settings = get_settings()
        key = getattr(settings, "supabase_secret_key", "")
        base_url = getattr(settings, "supabase_url", "").rstrip("/")
        if not key or not base_url:
            raise SupabaseError(503, "Storage is not configured yet.")
        headers = {"apikey": key, **kwargs.pop("headers", {})}
        if key.startswith("eyJ"):
            headers["Authorization"] = f"Bearer {key}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=False) as http:
                return await http.request(
                    method,
                    f"{base_url}/storage/v1/{path}",
                    content=content,
                    headers=headers,
                    **kwargs,
                )
        except httpx.HTTPError as err:
            raise SupabaseError(503, "Storage is unavailable. Try again shortly.") from err

    async def put_object(
        self, bucket: str, name: str, data: bytes, mime: str, *, upsert: bool = False
    ) -> None:
        """Store an object (overwrites only with upsert=True). Server key only."""
        result = await self._storage(
            "POST",
            f"object/{bucket}/{name}",
            content=data,
            headers={"Content-Type": mime, "x-upsert": "true" if upsert else "false"},
        )
        if result.is_error:
            raise SupabaseError(503, "Storage did not accept the file.")

    async def get_object(self, bucket: str, name: str) -> bytes | None:
        """Read an object's bytes, or None when it does not exist."""
        result = await self._storage("GET", f"object/{bucket}/{name}")
        if result.status_code in {400, 404}:
            return None
        if result.is_error:
            raise SupabaseError(503, "Storage is unavailable. Try again shortly.")
        return result.content

    async def list_objects(self, bucket: str, prefix: str) -> list[str]:
        """Names of objects directly under prefix/ (up to 1000)."""
        result = await self._storage(
            "POST", f"object/list/{bucket}", json={"prefix": prefix, "limit": 1000}
        )
        if result.is_error:
            raise SupabaseError(503, "Storage is unavailable. Try again shortly.")
        return [f"{prefix}/{item['name']}" for item in result.json() if item.get("id")]

    async def delete_objects(self, bucket: str, names: list[str]) -> None:
        if not names:
            return
        result = await self._storage("DELETE", f"object/{bucket}", json={"prefixes": names})
        if result.is_error:
            raise SupabaseError(503, "Storage is unavailable. Try again shortly.")


@lru_cache
def get_supabase_client() -> SupabaseClient:
    """Return the process-wide server HTTP adapter."""
    return SupabaseClient()
