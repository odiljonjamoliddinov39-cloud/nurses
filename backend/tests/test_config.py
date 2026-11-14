from app.config import Settings


def test_database_url_normalised_for_asyncpg():
    for raw in ("postgres://u:p@h:5432/d", "postgresql://u:p@h:5432/d"):
        assert Settings(database_url=raw).database_url == "postgresql+asyncpg://u:p@h:5432/d"


def test_asyncpg_url_untouched():
    url = "postgresql+asyncpg://u:p@h/d"
    assert Settings(database_url=url).database_url == url
