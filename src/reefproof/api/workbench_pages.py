"""Explicit registry for server-rendered Workbench pages."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WorkbenchPage:
    slug: str
    label: str
    route: str


WORKBENCH_PAGES = (
    WorkbenchPage("overview", "Overview", "/workbench"),
    WorkbenchPage("source", "Source / Imports", "/workbench/source"),
    WorkbenchPage("commissioning", "Commissioning", "/workbench/commissioning"),
    WorkbenchPage("labels", "Labels", "/workbench/labels"),
    WorkbenchPage("system-map", "System Map", "/workbench/system-map"),
    WorkbenchPage("assurance", "Assurance", "/workbench/assurance"),
    WorkbenchPage("evidence", "Evidence", "/workbench/evidence"),
    WorkbenchPage("sessions", "Sessions", "/workbench/sessions"),
    WorkbenchPage("database", "Database", "/workbench/database"),
)


def workbench_page(slug: str) -> WorkbenchPage:
    """Return a registered page or fail closed for programmer mistakes."""

    return next(page for page in WORKBENCH_PAGES if page.slug == slug)
