"""Authenticated, query-only SQLite explorer routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query

from reefproof.api.sessions import AuthenticatedSession, OperatorSessions, SessionDependencies
from reefproof.storage.explorer import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    DatabaseSchema,
    SQLiteExplorer,
    TablePage,
)


def register_database_explorer_routes(
    app: FastAPI,
    *,
    explorer: SQLiteExplorer,
    operator_sessions: OperatorSessions,
    session_dependencies: SessionDependencies,
) -> None:
    """Register bounded diagnostics without adding database mutation authority."""

    required_session = Depends(session_dependencies.required)

    @app.get("/v1/database/schema", response_model=DatabaseSchema)
    def database_schema(
        _session: AuthenticatedSession = required_session,
    ) -> DatabaseSchema:
        return explorer.schema()

    @app.get("/v1/database/tables/{table_name}", response_model=TablePage)
    def database_table(
        table_name: str,
        _session: AuthenticatedSession = required_session,
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
    ) -> TablePage:
        try:
            return explorer.table_page(table_name, offset=offset, limit=limit)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="table not available") from error
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
