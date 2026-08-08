from pathlib import Path

STYLESHEET = (
    Path(__file__).parents[2] / "src" / "reefproof" / "api" / "web" / "static" / "workbench.css"
)


def test_aquarium_motion_is_decorative_and_reduced_motion_safe() -> None:
    stylesheet = STYLESHEET.read_text()

    assert "@keyframes water-caustics" in stylesheet
    assert "@keyframes particle-drift" in stylesheet
    assert "@keyframes particle-pulse" in stylesheet
    assert "@media (prefers-reduced-motion: reduce)" in stylesheet
    assert ".aquarium-scene::before {\n    animation: none !important;" in stylesheet
