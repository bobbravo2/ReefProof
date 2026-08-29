from pathlib import Path

from reefproof.api.workbench_pages import WORKBENCH_PAGES, workbench_page


def test_workbench_page_registry_has_unique_server_authored_identity() -> None:
    assert len({page.slug for page in WORKBENCH_PAGES}) == len(WORKBENCH_PAGES)
    assert len({page.route for page in WORKBENCH_PAGES}) == len(WORKBENCH_PAGES)
    assert workbench_page("overview").route == "/workbench"


def test_v012_vertical_slice_uses_page_owned_controllers() -> None:
    typescript_root = Path("src/reefproof/api/web/typescript")
    entrypoint = (typescript_root / "workbench.ts").read_text(encoding="utf-8")
    assert "legacyInitializers" not in entrypoint
    assert "Workbench page identity is missing." in entrypoint

    for page in (
        "overview",
        "assurance",
        "evidence",
        "source",
        "commissioning",
        "labels",
        "system-map",
        "sessions",
        "database",
    ):
        controller = typescript_root / "pages" / f"{page}.ts"
        template = Path("src/reefproof/api/web/templates/pages") / f"{page}.html"
        assert controller.is_file()
        assert template.is_file()
        source = controller.read_text(encoding="utf-8")
        assert f"mount{''.join(word.title() for word in page.split('-'))}Page" in source
        assert f'page: "{page}", mount: initialize' not in entrypoint
