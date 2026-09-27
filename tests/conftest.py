import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))


@pytest.fixture
def sample_db(tmp_path):
    from make_sample_db import make
    return make(tmp_path / "sample.db")


@pytest.fixture
def reader(sample_db):
    from schemadoc.introspect import SchemaReader
    r = SchemaReader(f"sqlite:///{sample_db}")
    yield r
    r.close()
