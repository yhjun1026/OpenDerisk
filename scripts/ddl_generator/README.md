# DDL Generator - 企业级多数据库 DDL 生成器

## 概述

DDL Generator 是 Derisk 项目的数据库 schema 管理工具，能够从 SQLAlchemy ORM 模型自动生成多种数据库的 DDL 脚本。

**核心特性**：
- ✅ 单一数据源：ORM 模型是唯一真相
- ✅ 多数据库支持：MySQL、PostgreSQL，易于扩展
- ✅ 原生 SQLAlchemy 支持：利用 dialect 系统，无需手动类型映射
- ✅ 增量 DDL 生成：自动检测 schema 变化（Phase 2）
- ✅ 企业级架构：清晰的代码结构、完善的测试

## 快速开始

### 1. 生成所有数据库的 DDL

```bash
# 生成 MySQL 和 PostgreSQL DDL（默认）
python scripts/generate_ddl.py

# 输出位置
# assets/schema/mysql/derisk.sql
# assets/schema/postgresql/derisk.sql
```

### 2. 生成特定数据库的 DDL

```bash
# 仅生成 MySQL DDL
python scripts/generate_ddl.py --dialect mysql

# 仅生成 PostgreSQL DDL
python scripts/generate_ddl.py --dialect postgresql
```

### 3. 自定义输出目录

```bash
python scripts/generate_ddl.py --output-dir ./custom/schema
```

### 4. 预览模式（不写文件）

```bash
python scripts/generate_ddl.py --dry-run
```

### 5. 查看支持的数据库

```bash
python scripts/generate_ddl.py --list-dialects
```

## 集成到发布流程

`scripts/prepare_release.sh` 已自动集成 DDL 生成器，每次发布时会同时生成 MySQL 和 PostgreSQL 两个版本的 DDL：

```bash
# 发布准备脚本会自动执行：
python scripts/generate_ddl.py --dialect mysql,postgresql
```

## 架构设计

详细架构设计请参考：[DDL Generator 架构设计](../docs/ddl-generator-architecture.md)

### 核心组件

1. **Schema Reflector**：从 SQLAlchemy MetaData 反射表结构
2. **Dialect Adapters**：数据库方言适配器（MySQL、PostgreSQL）
3. **Schema Comparator**：差异检测引擎（Phase 2）
4. **DDL Writer**：输出管理器

### 目录结构

```
scripts/
├── generate_ddl.py              # CLI 工具入口
├── test_ddl_generator.py        # 测试脚本
└── ddl_generator/
    ├── core.py                  # 核心逻辑
    ├── comparator.py            # Schema 比较器（Phase 2）
    └── adapters/
        ├── __init__.py
        ├── mysql.py             # MySQL 适配器（Phase 2 可拆分）
        └── postgresql.py        # PostgreSQL 适配器（Phase 2 可拆分）

assets/schema/
├── mysql/
│   ├── derisk.sql               # 全量 DDL
│   └── upgrades/                # 增量 DDL（Phase 2）
└── postgresql/
    ├── derisk.sql
    └── upgrades/
```

## 开发指南

### 添加新的数据库支持

1. 创建新的 Dialect Adapter：

```python
# scripts/ddl_generator/adapters/oracle.py
from ddl_generator.core import DialectAdapter

class OracleAdapter(DialectAdapter):
    dialect_name = "oracle"

    @staticmethod
    def quote_identifier(name: str) -> str:
        return f'"{name}"'  # Oracle uses double quotes

    def generate_full_ddl(self, schema: UnifiedSchema) -> List[str]:
        # Implementation
        pass

    def generate_incremental_ddl(self, old_schema, new_schema) -> List[str]:
        # Phase 2 implementation
        pass
```

2. 注册适配器：

```python
# scripts/ddl_generator/core.py
from ddl_generator.adapters.oracle import OracleAdapter

class DDLGenerator:
    def __init__(self, metadata, version):
        self.adapters = {
            "mysql": MySQLAdapter(),
            "postgresql": PostgreSQLAdapter(),
            "oracle": OracleAdapter(),  # Add this line
        }
```

3. 测试新适配器：

```bash
python scripts/test_ddl_generator.py
python scripts/generate_ddl.py --dialect oracle
```

### 扩展 Schema 反射

如果需要反射额外的元数据（如触发器、存储过程），修改 `SchemaReflector`：

```python
class SchemaReflector:
    def _reflect_table(self, table: Table) -> TableDef:
        table_def = TableDef(name=table.name)

        # Reflect columns (existing)
        for column in table.columns:
            col_def = self._reflect_column(column)
            table_def.columns[col_def.name] = col_def

        # NEW: Reflect triggers (example)
        if hasattr(table, 'triggers'):
            for trigger in table.triggers:
                trigger_def = self._reflect_trigger(trigger)
                table_def.triggers.append(trigger_def)

        return table_def
```

## 测试

### 运行测试套件

```bash
# 运行所有测试
python scripts/test_ddl_generator.py

# 预期输出
# ✓ Basic Reflection
# ✓ MySQL DDL
# ✓ PostgreSQL DDL
# ✓ File Output
```

### 手动验证生成的 DDL

**MySQL**：

```bash
# 启动 MySQL 测试实例（Docker）
docker run --name mysql-test -e MYSQL_ROOT_PASSWORD=test -p 3306:3306 -d mysql:8.0

# 执行生成的 DDL
mysql -h 127.0.0.1 -u root -ptest < assets/schema/mysql/derisk.sql

# 验证表是否创建成功
mysql -h 127.0.0.1 -u root -ptest -e "SHOW TABLES FROM derisk;"
```

**PostgreSQL**：

```bash
# 启动 PostgreSQL 测试实例（Docker）
docker run --name postgres-test -e POSTGRES_PASSWORD=test -p 5432:5432 -d postgres:15

# 执行生成的 DDL
psql -h 127.0.0.1 -U postgres -f assets/schema/postgresql/derisk.sql

# 验证表是否创建成功
psql -h 127.0.0.1 -U postgres -c "\dt"
```

## 常见问题

### Q: 为什么生成的 DDL 与手写的不同？

**A**: DDL Generator 使用 SQLAlchemy 原生的类型系统，确保与 ORM 模型 100% 一致。手写 DDL 可能包含额外的优化或数据库特有的语法，这些可以通过 `dialect_options` 在模型中指定。

### Q: 如何处理数据库特有的功能？

**A**: 通过 SQLAlchemy 的 `dialect_options` 指定：

```python
class MyModel(Model):
    __tablename__ = "my_table"
    __table_args__ = (
        # MySQL 特有选项
        {'mysql_engine': 'InnoDB', 'mysql_charset': 'utf8mb4'},
        # PostgreSQL 特有选项
        # {'postgresql_partition_by': 'RANGE (created_at)'},
    )
```

### Q: 增量 DDL 什么时候支持？

**A**: Phase 2（预计 2-3 天）会实现完整的增量 DDL 生成功能，包括：
- 自动检测新增/删除的表和列
- 生成 ALTER TABLE 语句
- 生成带时间戳的迁移文件
- 安全删除（DROP 语句默认注释）

### Q: 如何在 CI/CD 中使用？

**A**: 在 CI 中添加验证步骤：

```yaml
# .github/workflows/ci.yml
- name: Verify DDL is up-to-date
  run: |
    python scripts/generate_ddl.py --dialect mysql,postgresql --output-dir /tmp/schema
    diff -r assets/schema/ /tmp/schema/ || (echo "DDL is outdated! Run: python scripts/generate_ddl.py" && exit 1)
```

## 路线图

### Phase 1: 核心框架（当前）

- ✅ Schema Reflector 实现
- ✅ MySQL 和 PostgreSQL 适配器
- ✅ CLI 工具
- ✅ 基础测试

### Phase 2: 增量 DDL（计划中）

- ⏳ Schema Comparator 实现
- ⏳ ALTER TABLE 语句生成
- ⏳ 版本管理和迁移文件生成
- ⏳ 安全删除策略

### Phase 3: 高级功能（未来）

- ⏳ 支持更多数据库（Oracle、SQL Server）
- ⏳ 数据迁移支持（INSERT 语句生成）
- ⏳ 逆向工程（从数据库生成模型）
- ⏳ 可视化工具（Web UI）

## 维护者

- 初始实现：Derisk Team
- 架构设计：基于企业级最佳实践
- 问题反馈：GitHub Issues

## 相关文档

- [架构设计详解](../docs/ddl-generator-architecture.md)
- [开发指南](../CLAUDE.md)
- [数据库配置](../docs/database-configuration.md)