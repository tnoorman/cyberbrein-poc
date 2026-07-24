import os
from collections.abc import Iterator

import pytest
from sqlalchemy.engine import make_url

from cyberbrein.storage.repository import metadata


@pytest.fixture
def postgres_url() -> str:
    return os.environ.get(
        "CYBERBREIN_TEST_DATABASE_URL",
        "postgresql+psycopg2:///cyberbrein_test",
    )


@pytest.fixture
def clean_postgis(postgres_url: str) -> Iterator[str]:
    from sqlalchemy import create_engine

    database_name = make_url(postgres_url).database or ""
    if not database_name.endswith("_test"):
        raise RuntimeError("integration tests require a database name ending in _test")
    engine = create_engine(postgres_url)
    metadata.drop_all(engine)
    yield postgres_url
    metadata.drop_all(engine)
    engine.dispose()
