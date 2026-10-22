import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pytest
from app.config import settings
@pytest.fixture(autouse=True)
def test_token(monkeypatch): monkeypatch.setattr(settings,"token","test-token-"+"x"*40)
