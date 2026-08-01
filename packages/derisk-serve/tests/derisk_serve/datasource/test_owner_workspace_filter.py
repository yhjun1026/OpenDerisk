"""ConnectConfigDao.list_accessible_by_workspace 测试。

过滤语义:空间可见数据源 = 本空间自持(owner_workspace_id == X) + 全局(NULL)。
"""
import pytest

from derisk.storage.metadata import db
from derisk_serve.datasource.manages.connect_config_db import (
    ConnectConfigDao,
    ConnectConfigEntity,
)


@pytest.fixture
def dao(tmp_path):
    db_path = tmp_path / "test.db"
    db.init_db(f"sqlite:///{db_path}")
    db.create_all()

    session = ConnectConfigDao().get_raw_session()
    session.add_all(
        [
            ConnectConfigEntity(
                db_name="global_db", db_type="sqlite", db_path="/tmp/a.db",
                db_host="", db_port=0, db_user="", db_pwd="", comment="",
                user_id="", owner_workspace_id=None,
            ),
            ConnectConfigEntity(
                db_name="ws1_db", db_type="duckdb", db_path="/tmp/b.db",
                db_host="", db_port=0, db_user="", db_pwd="", comment="",
                user_id="", owner_workspace_id=1,
            ),
            ConnectConfigEntity(
                db_name="ws2_db", db_type="duckdb", db_path="/tmp/c.db",
                db_host="", db_port=0, db_user="", db_pwd="", comment="",
                user_id="", owner_workspace_id=2,
            ),
        ]
    )
    session.commit()
    session.close()
    return ConnectConfigDao()


def test_workspace_sees_own_plus_global(dao):
    names = {e.db_name for e in dao.list_accessible_by_workspace(1)}
    assert names == {"global_db", "ws1_db"}


def test_other_workspace_excluded(dao):
    names = {e.db_name for e in dao.list_accessible_by_workspace(2)}
    assert names == {"global_db", "ws2_db"}


def test_db_type_filter(dao):
    names = {e.db_name for e in dao.list_accessible_by_workspace(1, db_type="duckdb")}
    assert names == {"ws1_db"}
