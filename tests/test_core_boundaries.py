from pathlib import Path


def test_core_has_no_mangome_or_blueberry_imports() -> None:
    root = Path(__file__).parents[1] / "src" / "pomelome"
    forbidden = ("import mangome", "from mangome", "import blueberry", "from blueberry")
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8").lower()
        assert not any(token in text for token in forbidden), path
