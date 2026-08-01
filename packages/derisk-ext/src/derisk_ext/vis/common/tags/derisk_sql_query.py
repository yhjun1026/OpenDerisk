"""SQL Query VIS Component.

Renders SQL query results with:
- SQL statement display
- Table results with pagination
- Database type indicator
- CSV export info for large results

Usage:
    ```d-sql-query
    {
        "sql": "SELECT * FROM users LIMIT 10",
        "db_name": "my_database",
        "db_type": "sqlite",
        "dialect": "sqlite",
        "columns": ["id", "name", "email"],
        "rows": [[1, "Alice", "alice@example.com"], ...],
        "total_rows": 100,
        "page": 1,
        "total_pages": 2,
        "page_size": 50,
        "has_more": true,
        "csv_file": null,
        "csv_export_reason": null
    }
    ```
"""

from typing import Any, Dict, Optional

from derisk.vis import Vis


class DeriskSqlQuery(Vis):
    """SQL Query visualization component.

    Provides structured data for frontend SQL query result rendering.
    Frontend should render:
    1. SQL statement with database type badge
    2. Results table with pagination controls
    3. Export/download link if CSV was generated
    """

    @classmethod
    def vis_tag(cls) -> str:
        """VIS tag identifier."""
        return "d-sql-query"

    def sync_generate_param(self, **kwargs) -> Optional[Dict[str, Any]]:
        """Generate parameters for SQL query visualization.

        Expected kwargs:
            sql: The SQL query string
            db_name: Database name
            db_type: Database type (sqlite, mysql, postgresql, etc.)
            dialect: SQL dialect (same as db_type usually)
            columns: List of column names
            rows: List of row data (each row is a list of values)
            total_rows: Total number of rows in result
            page: Current page number
            total_pages: Total number of pages
            page_size: Number of rows per page
            has_more: Whether there are more pages
            csv_file: Optional CSV file path for exported results
            csv_export_reason: Optional reason for CSV export
            raw_result: Optional raw result string for non-tabular results

        Returns:
            Dict with structured data for frontend rendering
        """
        # Required fields
        sql = kwargs.get("sql", "")
        db_name = kwargs.get("db_name", "")
        db_type = kwargs.get("db_type", "unknown")
        dialect = kwargs.get("dialect", db_type)
        columns = kwargs.get("columns", [])
        rows = kwargs.get("rows", [])
        total_rows = kwargs.get("total_rows", 0)
        page = kwargs.get("page", 1)
        total_pages = kwargs.get("total_pages", 0)
        page_size = kwargs.get("page_size", 50)
        has_more = kwargs.get("has_more", False)

        # Optional fields
        csv_file = kwargs.get("csv_file")
        csv_export_reason = kwargs.get("csv_export_reason")
        raw_result = kwargs.get("raw_result")
        # 文件模式三段信息
        file_path = kwargs.get("file_path")
        file_size = kwargs.get("file_size")
        file_format = kwargs.get("file_format")
        file_mode = kwargs.get("file_mode", False)
        file_export_error = kwargs.get("file_export_error")
        # 前端下载链接（AFS 统一入口生成）
        download_url = kwargs.get("download_url")
        preview_url = kwargs.get("preview_url")

        result = {
            "sql": sql,
            "db_name": db_name,
            "db_type": db_type,
            "dialect": dialect,
            "columns": columns,
            "rows": rows,
            "total_rows": total_rows,
            "page": page,
            "total_pages": total_pages,
            "page_size": page_size,
            "has_more": has_more,
        }

        # Add optional fields if present
        if csv_file:
            result["csv_file"] = csv_file
            result["csv_export_reason"] = csv_export_reason

        # 文件模式三段：数据量(total_rows+file_size)、样例 rows、路径 file_path
        if file_path:
            result["file_path"] = file_path
            if file_size is not None:
                result["file_size"] = file_size
            if file_format:
                result["file_format"] = file_format

        if file_mode:
            result["file_mode"] = True

        if file_export_error:
            result["file_export_error"] = file_export_error

        # 前端下载链接：优先 download_url，回退 preview_url
        if download_url:
            result["download_url"] = download_url
        if preview_url:
            result["preview_url"] = preview_url

        if raw_result:
            result["raw_result"] = raw_result

        # Preserve any additional fields (e.g., trust, warning from ECP)
        reserved_keys = {
            "sql", "db_name", "db_type", "dialect", "columns", "rows",
            "total_rows", "page", "total_pages", "page_size", "has_more",
            "csv_file", "csv_export_reason", "file_path", "file_size",
            "file_format", "file_mode", "file_export_error", "download_url",
            "preview_url", "raw_result"
        }
        for key, value in kwargs.items():
            if key not in reserved_keys and value is not None:
                result[key] = value

        return result

    async def generate_param(self, **kwargs) -> Optional[Dict[str, Any]]:
        """Async version of generate_param."""
        return self.sync_generate_param(**kwargs)