# DDL Generator 示例配置

本文档展示如何在 ORM 模型中配置数据库特定选项，以充分利用 DDL Generator 的能力。

## 基础模型定义

```python
from derisk.storage.metadata import Model
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, Index, UniqueConstraint
from datetime import datetime


class ChatHistoryEntity(Model):
    """聊天历史记录表"""

    __tablename__ = "chat_history"

    # 基础列定义
    id = Column(Integer, primary_key=True, autoincrement=True, comment="自增ID")
    conv_uid = Column(String(255), nullable=False, comment="对话唯一ID")
    summary = Column(Text, nullable=False, comment="对话摘要")

    # 时间戳字段
    gmt_created = Column(
        DateTime,
        default=datetime.now,
        comment="创建时间"
    )

    # 索引定义（方式1：在 __table_args__ 中定义）
    __table_args__ = (
        UniqueConstraint("conv_uid", name="uk_conv_uid"),
        Index("idx_user_name", "user_name"),
        Index("idx_created_time", "gmt_created"),
        # 数据库特定选项
        {
            'mysql_engine': 'InnoDB',
            'mysql_charset': 'utf8mb4',
            'mysql_collation': 'utf8mb4_unicode_ci',
        }
    )


# 索引定义（方式2：独立定义）
class MessageEntity(Model):
    """消息表"""

    __tablename__ = "chat_history_message"

    id = Column(Integer, primary_key=True, autoincrement=True)
    conv_uid = Column(String(255), nullable=False)
    message_detail = Column(Text)

    # 独立定义索引（SQLAlchemy 会自动收集）
    idx_conv_uid = Index("conv_uid")
    idx_message_time = Index("gmt_created")
```

## MySQL 特定配置

```python
class MySQLSpecificModel(Model):
    """MySQL 特定配置示例"""

    __tablename__ = "mysql_specific_table"

    __table_args__ = (
        # MySQL 特有选项
        {
            'mysql_engine': 'InnoDB',           # 存储引擎
            'mysql_charset': 'utf8mb4',         # 字符集
            'mysql_collation': 'utf8mb4_unicode_ci',  # 排序规则
            'mysql_row_format': 'DYNAMIC',      # 行格式
        }
    )

    # MySQL 特有列类型
    long_text = Column(Text(4294967295))  # LONGTEXT
    json_data = Column(JSON)               # MySQL 5.7+ JSON 类型
```

## PostgreSQL 特定配置

```python
from sqlalchemy.dialects.postgresql import JSONB, ARRAY

class PostgreSQLSpecificModel(Model):
    """PostgreSQL 特定配置示例"""

    __tablename__ = "postgresql_specific_table"

    __table_args__ = (
        # PostgreSQL 特有选项
        {
            # 注意：PostgreSQL 通常不需要这些选项
            # 但可以用于分区表等高级功能
            # 'postgresql_partition_by': 'RANGE (created_at)',
        }
    )

    # PostgreSQL 特有列类型
    jsonb_data = Column(JSONB)            # JSONB 类型（二进制 JSON）
    tags = Column(ARRAY(String))          # 数组类型
```

## 跨数据库兼容配置

```python
from sqlalchemy import JSON

class CrossDatabaseModel(Model):
    """跨数据库兼容的模型定义"""

    __tablename__ = "cross_database_table"

    __table_args__ = (
        # 不指定数据库特定选项，让 SQLAlchemy 使用默认值
        # DDL Generator 会根据目标数据库自动适配
        {}
    )

    # 使用标准 SQLAlchemy 类型（推荐）
    # 这些类型会在不同数据库上自动映射到正确的类型：
    # - Integer -> INT (MySQL) / INTEGER (PostgreSQL)
    # - String(255) -> VARCHAR(255) (both)
    # - Text -> TEXT (MySQL) / TEXT (PostgreSQL)
    # - Boolean -> TINYINT(1) (MySQL) / BOOLEAN (PostgreSQL)
    # - DateTime -> DATETIME (MySQL) / TIMESTAMP (PostgreSQL)
    # - JSON -> JSON (both)

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.now)
    metadata_json = Column(JSON)
```

## 类型映射表

DDL Generator 会自动处理以下类型映射：

| SQLAlchemy 类型 | MySQL 类型 | PostgreSQL 类型 |
|----------------|-----------|----------------|
| Integer        | INT       | INTEGER         |
| BigInteger     | BIGINT    | BIGINT          |
| SmallInteger   | SMALLINT  | SMALLINT        |
| String(N)      | VARCHAR(N)| VARCHAR(N)      |
| Text           | TEXT      | TEXT            |
| Boolean        | TINYINT(1)| BOOLEAN         |
| DateTime       | DATETIME  | TIMESTAMP       |
| JSON           | JSON      | JSON            |
| Float          | FLOAT     | REAL            |

## 自定义类型

如果需要自定义类型，可以通过 `TypeDecorator` 实现：

```python
from sqlalchemy.types import TypeDecorator, String

class EncryptedString(TypeDecorator):
    """自定义加密字符串类型"""

    impl = String
    cache_ok = True

    def __init__(self, length=None):
        self.length = length
        super().__init__(length)

    def get_col_spec(self, **kw):
        if self.length:
            return f"VARCHAR({self.length})"
        return "TEXT"


class SecureModel(Model):
    __tablename__ = "secure_table"

    encrypted_data = Column(EncryptedString(500))
```

## 约束和索引最佳实践

```python
class BestPracticeModel(Model):
    """约束和索引最佳实践"""

    __tablename__ = "best_practice_table"

    # 主键
    id = Column(Integer, primary_key=True, autoincrement=True)

    # 唯一约束（推荐在 __table_args__ 中定义）
    email = Column(String(255), nullable=False)
    username = Column(String(100), nullable=False)

    # 外键
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # 普通索引字段
    status = Column(String(20), index=True)

    __table_args__ = (
        # 唯一约束（推荐方式）
        UniqueConstraint("email", name="uk_email"),
        UniqueConstraint("username", name="uk_username"),

        # 复合索引
        Index("idx_user_status", "user_id", "status"),

        # 函数索引（PostgreSQL 特有，需要特殊处理）
        # Index("idx_lower_email", func.lower(email)),  # 仅 PostgreSQL 支持

        # 数据库选项
        {}
    )
```

## 分区表配置（高级）

```python
# MySQL 分区表
class MySQLPartitionedModel(Model):
    __tablename__ = "partitioned_logs"

    id = Column(BigInteger, primary_key=True)
    created_at = Column(DateTime, nullable=False)
    log_data = Column(Text)

    __table_args__ = (
        {
            'mysql_partition_by': 'RANGE (YEAR(created_at))',
            'mysql_partitions': [
                "PARTITION p2024 VALUES LESS THAN (2025)",
                "PARTITION p2025 VALUES LESS THAN (2026)",
                "PARTITION pmax VALUES LESS THAN MAXVALUE",
            ]
        }
    )


# PostgreSQL 分区表（需要在 DDL 中手动处理）
class PostgreSQLPartitionedModel(Model):
    __tablename__ = "partitioned_logs"

    id = Column(BigInteger, primary_key=True)
    created_at = Column(DateTime, nullable=False)
    log_data = Column(Text)

    __table_args__ = (
        {
            'postgresql_partition_by': 'RANGE (created_at)',
        }
    )
```

## 注意事项

1. **避免数据库特定语法**：除非必要，尽量使用标准 SQLAlchemy 类型
2. **注释所有字段**：使用 `comment` 参数添加注释，DDL Generator 会保留
3. **统一命名规范**：
   - 表名：小写下划线分隔（如 `chat_history`）
   - 索引名：`idx_` 前缀（如 `idx_user_name`）
   - 唯一约束：`uk_` 前缀（如 `uk_email`）
4. **外键约束**：在生产环境建议启用，开发环境可以禁用以提高性能

## 运行 DDL Generator

配置好模型后，运行：

```bash
# 生成所有数据库的 DDL
python scripts/generate_ddl.py

# 验证生成的 DDL
python scripts/test_ddl_generator.py
```

生成的 DDL 文件位于：
- MySQL: `assets/schema/mysql/derisk.sql`
- PostgreSQL: `assets/schema/postgresql/derisk.sql`