from pathlib import Path

STATIC_DIRECTORY = Path(__file__).parents[2] / "src" / "reefproof" / "api" / "web" / "static"
STYLESHEET = STATIC_DIRECTORY / "workbench.css"
REEF_ASSET = STATIC_DIRECTORY / "reef-tank-high-poly-v1.webp"


def test_workbench_reef_asset_is_optimized_and_used_by_the_aquarium() -> None:
    asset = REEF_ASSET.read_bytes()
    stylesheet = STYLESHEET.read_text()

    assert asset[:4] == b"RIFF"
    assert asset[8:12] == b"WEBP"
    assert len(asset) < 500_000
    assert 'url("/assets/reef-tank-high-poly-v1.webp")' in stylesheet


def test_aquarium_layers_refraction_diffusion_and_reduced_motion_support() -> None:
    stylesheet = STYLESHEET.read_text()

    assert "@keyframes water-refraction" in stylesheet
    assert "mask-image: repeating-radial-gradient" in stylesheet
    assert "backdrop-filter: blur(0.16rem) saturate(1.04)" in stylesheet
    assert "rgb(213 249 255 / 22%)" in stylesheet
    assert "soft-light, screen, screen" in stylesheet
    assert "3.7rem 3.1rem" in stylesheet
    assert "filter: blur(1rem)" in stylesheet
    assert "@media (prefers-reduced-motion: reduce)" in stylesheet
    assert ".aquarium-scene::before {\n    animation: none !important;" in stylesheet
