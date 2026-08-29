"""Server-side read-only Google Sheets adapter."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote
from uuid import NAMESPACE_URL, uuid5

import httpx

from reefproof.authored_sources.models import (
    SOURCE_TAB_NAMES,
    AuthoredSourceSnapshot,
    AuthoredSourceTab,
    source_snapshot_hash,
)
from reefproof.authored_sources.protocol import CredentialProvider

_READ_ONLY_SCOPE = "https://www.googleapis.com/auth/spreadsheets.readonly"
_SHEETS_API = "https://sheets.googleapis.com/v4/spreadsheets"
_MAX_SOURCE_ROW = 10_000


class GoogleServiceAccountCredentialProvider:
    """Acquire short-lived read-only headers without exposing SDK types downstream."""

    def __init__(self, credential_file: Path) -> None:
        self._credential_file = credential_file

    def authorization_headers(self) -> dict[str, str]:
        from google.auth.transport.requests import Request
        from google.oauth2.service_account import Credentials

        credentials = Credentials.from_service_account_file(
            str(self._credential_file), scopes=(_READ_ONLY_SCOPE,)
        )
        credentials.refresh(Request())
        if not credentials.token:
            raise RuntimeError("Google credential provider returned no access token")
        return {"Authorization": f"Bearer {credentials.token}"}


class GoogleSheetsSource:
    def __init__(
        self,
        *,
        spreadsheet_id: str,
        source_alias: str,
        credentials: CredentialProvider,
        client: httpx.Client | None = None,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._spreadsheet_id = spreadsheet_id
        self._source_alias = source_alias
        self._credentials = credentials
        self._client = client or httpx.Client(timeout=20.0, follow_redirects=False)
        self._now = now

    def fetch(self) -> AuthoredSourceSnapshot:
        headers = self._credentials.authorization_headers()
        spreadsheet_url = f"{_SHEETS_API}/{quote(self._spreadsheet_id, safe='')}"
        metadata = self._get_json(
            spreadsheet_url,
            headers=headers,
            params={"fields": "spreadsheetId,properties.title,sheets.properties.title"},
        )
        available_tabs = {
            sheet.get("properties", {}).get("title")
            for sheet in metadata.get("sheets", [])
            if isinstance(sheet, dict)
        }
        required_tabs = {name.value for name in SOURCE_TAB_NAMES}
        missing = sorted(required_tabs - available_tabs)
        if missing:
            raise ValueError(f"Google Sheet is missing required tab(s): {', '.join(missing)}")

        ranges = tuple(f"'{name.value}'!A1:ZZ{_MAX_SOURCE_ROW}" for name in SOURCE_TAB_NAMES)
        values = self._get_json(
            f"{spreadsheet_url}/values:batchGet",
            headers=headers,
            params=[("majorDimension", "ROWS"), *(("ranges", item) for item in ranges)],
        )
        by_range = {
            str(item.get("range", "")).split("!", 1)[0].strip("'"): item
            for item in values.get("valueRanges", [])
            if isinstance(item, dict)
        }
        tabs = tuple(
            AuthoredSourceTab(
                name=name,
                source_range=ranges[index],
                rows=tuple(
                    tuple(str(value) for value in row)
                    for row in by_range.get(name.value, {}).get("values", [])
                ),
            )
            for index, name in enumerate(SOURCE_TAB_NAMES)
        )
        fetched_at = self._now()
        digest = source_snapshot_hash(tabs)
        return AuthoredSourceSnapshot(
            source_snapshot_id=str(uuid5(NAMESPACE_URL, f"{self._spreadsheet_id}:{digest}")),
            source_alias=self._source_alias,
            spreadsheet_id=self._spreadsheet_id,
            spreadsheet_title=str(metadata.get("properties", {}).get("title", "")),
            fetched_at=fetched_at,
            tabs=tabs,
            snapshot_hash=digest,
        )

    def _get_json(self, url: str, **kwargs: Any) -> dict[str, Any]:
        response = self._client.get(url, **kwargs)
        response.raise_for_status()
        document = response.json()
        if not isinstance(document, dict):
            raise ValueError("Google Sheets API returned a non-object response")
        return document
