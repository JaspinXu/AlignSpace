import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402  (sys.path must be set before the app package is imported)

@pytest.fixture(autouse=True)
def offline_environment(monkeypatch):
    monkeypatch.setenv('ALIGNSPACE_ANALYSIS_MODE', 'offline')
    monkeypatch.setenv('ALIGNSPACE_SECURE_COOKIES', 'false')
