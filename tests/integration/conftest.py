import os
from collections.abc import Iterator

import pytest

from cyberbrein.storage.repository import metadata


@pytest.fixture
def postgres_url() -> str:
    return os.environ.get(
        "CYBERBREIN_TEST_DATABASE_URL",
        "postgresql+psycopg2:///cyberbrein_poc",
    )


@pytest.fixture
def clean_postgis(postgres_url: str) -> Iterator[str]:
    from sqlalchemy import create_engine

    engine = create_engine(postgres_url)
    metadata.drop_all(engine)
    yield postgres_url
    metadata.drop_all(engine)
    engine.dispose()
