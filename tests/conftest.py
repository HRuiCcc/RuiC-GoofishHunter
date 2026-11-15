import os
import tempfile
from pathlib import Path

# 必须在 import hunter.* 之前设好，config 在导入时就把路径算出来了
_TEST_ROOT = Path(tempfile.mkdtemp(prefix="hunter-test-"))
os.environ["HUNTER_DATA_DIR"] = str(_TEST_ROOT)

import pytest  # noqa: E402

from hunter.config import Paths  # noqa: E402
from hunter import db as dbmod  # noqa: E402
from hunter.db import init_db  # noqa: E402


@pytest.fixture()
def fresh_db(tmp_path, monkeypatch):
    """每个用例一个干净的库，避免用例之间互相看见数据。"""
    paths = Paths(
        data=tmp_path,
        db=tmp_path / "test.db",
        profiles=tmp_path / "profiles",
        states=tmp_path / "states",
        logs=tmp_path / "logs",
        shots=tmp_path / "shots",
    )
    paths.ensure()
    monkeypatch.setattr(dbmod, "PATHS", paths)
    init_db()
    return paths


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    return Path(__file__).parent / "fixtures"
