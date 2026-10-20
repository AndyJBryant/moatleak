import json, os, pathlib, pytest


@pytest.fixture(scope="session")
def snapshot():
    p = os.environ.get("MOATLEAK_SNAPSHOT")
    if not p:
        pytest.skip("MOATLEAK_SNAPSHOT not set")
    p = pathlib.Path(p).expanduser()
    return p / "home", json.loads((p / "ground-truth.json").read_text())
