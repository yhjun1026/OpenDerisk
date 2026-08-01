# DDL 生成器架构设计

## 设计目标

1. **单一数据源原则**：ORM 模型文件是唯一数据源，DDL 完全由模型反射生成
2. **多数据库原生支持**：利用 SQLAlchemy 的 dialect 系统，而非手动类型映射
3. **增量 DDL 智能生成**：自动检测 schema 变化，生成最小化的迁移脚本
4. **可扩展架构**：未来支持更多数据库类型（如 Oracle、SQL Server）
5. **持续维护性**：清晰的代码结构、完善的文档、充分的测试覆盖

## 架构概览

```
ORM Models (唯一数据源)
    ↓
DDL Generator Core
    ├─ Schema Reflector (从 SQLAlchemy MetaData 反射表结构)
    ├─ Dialect Adapters (数据库方言适配器)
    │   ├─ MySQLAdapter
    │   ├─ PostgreSQLAdapter
    │   └─ (未来) OracleAdapter, SQLServerAdapter...
    ├─ Schema Comparator (差异检测引擎)
    └─ DDL Writer (输出管理器)
        ├─ Full DDL (完整建表脚本)
        └─ Incremental DDL (迁移脚本)
```

## 核心模块设计

### 1. Schema Reflector（表结构反射器）

**职责**：从 SQLAlchemy MetaData 中反射所有表结构，生成统一的数据结构。

**关键点**：
- 扫描所有 `Model` 子类（自动发现，无需手动指定）
- 提取表名、列定义、索引、约束、注释等元数据
- 生成 JSON Schema 格式的中间表示（便于序列化和比较）

**输入**：`Model.metadata`（SQLAlchemy MetaData 对象）

**输出**：`UnifiedSchema` 对象

```python
{
  "tables": {
    "chat_history": {
      "columns": {
        "id": {"type": "Integer", "primary_key": true, "autoincrement": true, "comment": "..."},
        "conv_uid": {"type": "String(255)", "nullable": false, "unique": true, "comment": "..."},
        ...
      },
      "indexes": {"idx_q_user": {"columns": ["user_name"], "unique": false}},
      "constraints": {"uk_conv_uid": {"type": "unique", "columns": ["conv_uid"]}}
    }
  },
  "version": "0.1.0",
  "generated_at": "2026-07-28T10:00:00Z"
}
```

### 2. Dialect Adapters（数据库方言适配器）

**职责**：将统一 Schema 转换为特定数据库的 DDL 语句。

**设计模式**：策略模式（Strategy Pattern）

**接口定义**：

```python
from abc import ABC, abstractmethod
from typing import List

class DialectAdapter(ABC):
    """数据库方言适配器基类"""

    @property
    @abstractmethod
    def dialect_name(self) -> str:
        """方言名称，如 'mysql', 'postgresql'"""
        pass

    @abstractmethod
    def generate_full_ddl(self, schema: UnifiedSchema) -> List[str]:
        """生成完整建表 DDL"""
        pass

    @abstractmethod
    def generate_incremental_ddl(
        self,
        old_schema: UnifiedSchema,
        new_schema: UnifiedSchema
    ) -> List[str]:
        """生成增量迁移 DDL"""
        pass

    @staticmethod
    @abstractmethod
    def quote_identifier(name: str) -> str:
        """引用标识符（MySQL用反引号，PostgreSQL用双引号）"""
        pass
```

**MySQLAdapter 关键实现**：

```python
class MySQLAdapter(DialectAdapter):
    dialect_name = "mysql"

    def quote_identifier(self, name: str) -> str:
        return f"`{name}`"

    def generate_full_ddl(self, schema: UnifiedSchema) -> List[str]:
        # 使用 SQLAlchemy 的 CreateTable 编译器
        from sqlalchemy.schema import CreateTable
        from sqlalchemy.dialects import mysql

        statements = []
        for table_name, table_def in schema.tables.items():
            # 从 metadata 创建 Table 对象
            table = self._reconstruct_table(table_def)
            # 编译为 MySQL DDL
            ddl = str(CreateTable(table).compile(dialect=mysql.dialect()))
            statements.append(ddl)
        return statements
```

**PostgreSQLAdapter 关键实现**：

```python
class PostgreSQLAdapter(DialectAdapter):
    dialect_name = "postgresql"

    def quote_identifier(self, name: str) -> str:
        return f'"{name}"'

    def generate_full_ddl(self, schema: UnifiedSchema) -> List[str]:
        from sqlalchemy.schema import CreateTable
        from sqlalchemy.dialects import postgresql

        statements = []
        for table_name, table_def in schema.tables.items():
            table = self._reconstruct_table(table_def)
            ddl = str(CreateTable(table).compile(dialect=postgresql.dialect()))
            statements.append(ddl)
        return statements
```

### 3. Schema Comparator（差异检测引擎）

**职责**：比较两个版本的 Schema，识别具体的变更操作。

**核心算法**：

```python
class SchemaComparator:
    """Schema 差异检测器"""

    def compare(
        self,
        old_schema: UnifiedSchema,
        new_schema: UnifiedSchema
    ) -> SchemaDiff:
        """比较两个 schema，生成差异报告"""

        diff = SchemaDiff()

        # 1. 检测新增/删除的表
        old_tables = set(old_schema.tables.keys())
        new_tables = set(new_schema.tables.keys())

        diff.added_tables = new_tables - old_tables
        diff.removed_tables = old_tables - new_tables

        # 2. 检测公共表的列变更
        for table_name in old_tables & new_tables:
            table_diff = self._compare_table(
                old_schema.tables[table_name],
                new_schema.tables[table_name]
            )
            if table_diff.has_changes():
                diff.modified_tables[table_name] = table_diff

        return diff

    def _compare_table(self, old_table: TableDef, new_table: TableDef) -> TableDiff:
        """检测单表的变更"""
        table_diff = TableDiff()

        old_cols = set(old_table.columns.keys())
        new_cols = set(new_table.columns.keys())

        table_diff.added_columns = new_cols - old_cols
        table_diff.removed_columns = old_cols - new_cols

        # 检测列定义变更（类型、nullable、comment等）
        for col_name in old_cols & new_cols:
            if old_table.columns[col_name] != new_table.columns[col_name]:
                table_diff.modified_columns[col_name] = {
                    "old": old_table.columns[col_name],
                    "new": new_table.columns[col_name]
                }

        # 检测索引变更
        table_diff.index_changes = self._compare_indexes(old_table, new_table)

        return table_diff
```

### 4. DDL Writer（输出管理器）

**职责**：管理 DDL 文件的生成、版本命名、目录结构。

**文件命名规范**：

```
assets/schema/
├── mysql/
│   ├── derisk.sql                    # 最新全量 DDL
│   └── upgrades/
│       ├── upgrade_0.1.0_20260720_to_0.1.1_20260725.sql
│       └── upgrade_0.1.1_20260725_to_0.2.0_20260728.sql
└── postgresql/
    ├── derisk.sql
    └── upgrades/
        └── ...
```

**文件头格式**：

```sql
-- ============================================================
-- Database DDL Script for Derisk
-- Database: MySQL 8.0+
-- Version: 0.2.0
-- Generated: 2026-07-28 10:30:45
-- Source: SQLAlchemy ORM Models
--
-- Incremental DDL (if applicable):
--   Source version: 0.1.1 (generated at 2026-07-25 14:20:10)
--   Target version: 0.2.0
--   Changes detected:
--     - Added table: gpts_todos
--     - Modified table: chat_history (added column: task_id)
-- ============================================================
```

## 实现路线图

### Phase 1: 核心框架（3-5天）

1. **Schema Reflector 实现**
   - 扫描所有 Model 子类
   - 反射为 UnifiedSchema
   - 支持 JSON 序列化/反序列化（用于缓存）

2. **Dialect Adapter 框架**
   - 定义抽象基类
   - 实现 MySQLAdapter（复用现有逻辑，但用 SQLAlchemy 原生 API）
   - 实现 PostgreSQLAdapter

3. **基础测试**
   - 单元测试：每个模块的独立测试
   - 集成测试：在真实数据库上验证生成的 DDL

### Phase 2: 增量 DDL 生成（2-3天）

1. **Schema Comparator 实现**
   - 深度比较算法
   - 差异报告生成

2. **增量 DDL 生成**
   - ALTER TABLE 语句生成
   - 处理索引、约束的变更
   - 安全删除（默认注释掉 DROP 语句）

3. **版本管理**
   - 自动从现有 DDL 文件提取版本号
   - 生成带时间戳的迁移文件

### Phase 3: 工具链集成（1-2天）

1. **CLI 工具**
   - 支持命令行参数：`--dialect mysql,postgresql`
   - 支持 `--dry-run` 预览模式
   - 支持 `--output-dir` 自定义输出目录

2. **集成到 prepare_release.sh**
   - 替换现有的 `generate_mysql_ddl.py`
   - 同时生成 MySQL 和 PostgreSQL DDL

3. **CI/CD 集成**
   - 在 CI 中验证生成的 DDL 是否有效
   - 自动检测 DDL 文件是否与代码同步

### Phase 4: 文档和测试（1-2天）

1. **用户文档**
   - 如何添加新数据库支持
   - 如何自定义 DDL 生成行为
   - 常见问题排查

2. **开发者文档**
   - 架构设计详解
   - 扩展点说明
   - API 参考

3. **测试覆盖**
   - 单元测试覆盖率 > 80%
   - 集成测试覆盖所有支持的操作
   - 在真实 MySQL/PostgreSQL 实例上验证

## 关键技术决策

### 1. 为什么使用 SQLAlchemy 原生 API 而非手动解析？

**原因**：
- ✅ **稳定性**：SQLAlchemy 是成熟的 ORM，类型映射经过充分测试
- ✅ **维护性**：跟随 SQLAlchemy 版本升级，自动支持新特性
- ✅ **完整性**：自动处理复杂类型（JSON、Array、自定义类型）
- ✅ **可扩展**：通过自定义 TypeDecorator 支持业务特定类型

**对比手动解析的劣势**：
- ❌ 需要维护大量类型映射代码
- ❌ 容易遗漏 SQLAlchemy 的新特性
- ❌ 处理复杂类型时容易出错

### 2. 为什么使用统一的中间格式（UnifiedSchema）？

**原因**：
- **解耦**：反射逻辑和生成逻辑分离，便于独立测试
- **可序列化**：可以保存为 JSON，用于版本间比较
- **可扩展**：未来可以支持从其他数据源生成 DDL（如 Django models）

### 3. 如何处理数据库特有的功能？

**策略**：
- **核心功能**：通过 SQLAlchemy 标准接口支持（类型、索引、约束）
- **特有功能**：通过 `dialect_options` 扩展（如 MySQL 的 `ENGINE=InnoDB`，PostgreSQL 的 `PARTITION BY`）

**示例**：

```python
# MySQL 特有选项
table_args = (
    {'mysql_engine': 'InnoDB', 'mysql_charset': 'utf8mb4'}
)

# PostgreSQL 特有选项
table_args = (
    {'postgresql_partition_by': 'RANGE (created_at)'}
)
```

## 未来扩展方向

1. **支持更多数据库**：Oracle、SQL Server、TiDB
2. **数据迁移支持**：生成 INSERT 语句用于种子数据
3. **逆向工程**：从现有数据库生成 ORM 模型代码
4. **可视化工具**：Web UI 查看 Schema 变更历史
5. **与 Alembic 集成**：自动生成 Alembic 迁移脚本

## 测试策略

### 单元测试

```python
def test_schema_reflector():
    """测试 Schema 反射"""
    reflector = SchemaReflector()
    schema = reflector.reflect()

    assert "chat_history" in schema.tables
    assert "id" in schema.tables["chat_history"].columns
    assert schema.tables["chat_history"].columns["id"]["primary_key"] == True

def test_mysql_adapter():
    """测试 MySQL DDL 生成"""
    adapter = MySQLAdapter()
    ddl = adapter.generate_full_ddl(test_schema)

    assert "CREATE TABLE `chat_history`" in ddl[0]
    assert "ENGINE=InnoDB" in ddl[0]

def test_postgresql_adapter():
    """测试 PostgreSQL DDL 生成"""
    adapter = PostgreSQLAdapter()
    ddl = adapter.generate_full_ddl(test_schema)

    assert 'CREATE TABLE "chat_history"' in ddl[0]
    assert "ENGINE=InnoDB" not in ddl[0]  # PG 不需要
```

### 集成测试

```python
def test_mysql_ddl_execution():
    """在真实 MySQL 数据库上执行 DDL"""
    adapter = MySQLAdapter()
    ddl_statements = adapter.generate_full_ddl(schema)

    engine = create_engine("mysql+pymysql://test:test@localhost/test_db")

    with engine.connect() as conn:
        for ddl in ddl_statements:
            conn.execute(text(ddl))
        conn.commit()

    # 验证表是否创建成功
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    assert "chat_history" in tables

def test_postgresql_ddl_execution():
    """在真实 PostgreSQL 数据库上执行 DDL"""
    adapter = PostgreSQLAdapter()
    ddl_statements = adapter.generate_full_ddl(schema)

    engine = create_engine("postgresql://test:test@localhost/test_db")

    with engine.connect() as conn:
        for ddl in ddl_statements:
            conn.execute(text(ddl))
        conn.commit()

    inspector = inspect(engine)
    tables = inspector.get_table_names()
    assert "chat_history" in tables
```

## 配置管理

**配置文件示例**：`configs/ddl_generator.yaml`

```yaml
# DDL 生成器配置
generator:
  # 输出目录
  output_dir: assets/schema

  # 支持的数据库类型
  dialects:
    - mysql
    - postgresql

  # 是否生成增量 DDL
  generate_incremental: true

  # 是否在删除表/列时注释掉 DROP 语句（安全模式）
  safe_mode: true

# 数据库特定配置
dialects:
  mysql:
    default_charset: utf8mb4
    default_collation: utf8mb4_unicode_ci
    default_engine: InnoDB

  postgresql:
    default_schema: public
    # PostgreSQL 特有：是否生成 SERIAL 或 IDENTITY
    use_identity: true  # PG 10+ 推荐

# 排除规则（某些表不需要生成 DDL）
exclude:
  tables:
    - "alembic_version"  # Alembic 迁移版本表
    - "test_*"          # 测试表
```

## 总结

这个架构设计遵循以下原则：

1. ✅ **单一数据源**：ORM 模型是唯一真相
2. ✅ **原生支持**：利用 SQLAlchemy 的成熟生态
3. ✅ **可扩展**：清晰的结构，易于添加新数据库
4. ✅ **可维护**：充分的文档和测试
5. ✅ **企业级**：完善的错误处理、日志、配置管理

**实施建议**：按照 Phase 1-4 的顺序逐步实现，每个阶段都有明确的交付物和验证标准。