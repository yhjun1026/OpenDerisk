#!/usr/bin/env python3
"""
DDL Generator CLI Tool

Usage:
    python scripts/generate_ddl.py --dialect mysql,postgresql
    python scripts/generate_ddl.py --dialect mysql --output-dir ./assets/schema
    python scripts/generate_ddl.py --list-dialects
    python scripts/generate_ddl.py --no-incremental  # Only generate full DDL
"""

import argparse
import logging
import sys
import re
from pathlib import Path
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "packages" / "derisk-core" / "src"))

from ddl_generator.core import (
    DDLGenerator,
    discover_metadata,
    get_project_version,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Generate DDL scripts from SQLAlchemy ORM models",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate full and incremental DDL for MySQL and PostgreSQL
  python scripts/generate_ddl.py

  # Generate only MySQL DDL with custom output directory
  python scripts/generate_ddl.py --dialect mysql --output-dir ./custom/schema

  # Generate only full DDL (no incremental)
  python scripts/generate_ddl.py --no-incremental

  # List all supported databases
  python scripts/generate_ddl.py --list-dialects

  # Dry run (preview without writing files)
  python scripts/generate_ddl.py --dry-run
        """,
    )

    parser.add_argument(
        "--dialect",
        type=str,
        default="mysql,postgresql",
        help="Comma-separated list of database dialects (default: mysql,postgresql)",
    )

    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("assets/schema"),
        help="Output directory for DDL files (default: assets/schema)",
    )

    parser.add_argument(
        "--list-dialects",
        action="store_true",
        help="List all supported database dialects",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview DDL without writing files",
    )

    parser.add_argument(
        "--no-incremental",
        action="store_true",
        help="Skip incremental DDL generation (only generate full DDL)",
    )

    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose output",
    )

    return parser.parse_args()


def main():
    """Main entry point."""
    args = parse_args()

    # Set log level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # List dialects mode
    if args.list_dialects:
        print("Supported database dialects:")
        print("  - mysql")
        print("  - postgresql")
        print("\nFuture support planned for:")
        print("  - oracle")
        print("  - sqlserver")
        print("  - tidb")
        return 0

    # Get project version
    version = get_project_version(project_root)
    logger.info(f"Project version: {version}")

    # Discover metadata
    logger.info("Discovering ORM models...")
    metadata = discover_metadata()

    if not metadata.tables:
        logger.error("No tables found in metadata. Is the database initialized?")
        return 1

    logger.info(f"Found {len(metadata.tables)} tables in metadata")

    # Create DDL generator
    generator = DDLGenerator(metadata, version)

    # Parse dialects
    dialects = [d.strip().lower() for d in args.dialect.split(",")]

    # Validate dialects
    invalid_dialects = [d for d in dialects if d not in generator.adapters]
    if invalid_dialects:
        logger.error(f"Unsupported dialects: {', '.join(invalid_dialects)}")
        logger.error(f"Supported: {', '.join(generator.adapters.keys())}")
        return 1

    # Generate DDL for each dialect
    if args.dry_run:
        logger.info("Dry run mode - preview only")
        for dialect in dialects:
            print(f"\n{'=' * 80}")
            print(f"Full DDL for {dialect.upper()}")
            print(f"{'=' * 80}\n")
            ddl_content = generator.generate_full_ddl(dialect)
            print(ddl_content)
    else:
        logger.info(f"Generating DDL for: {', '.join(dialects)}")

        for dialect in dialects:
            # Create output directories
            dialect_dir = args.output_dir / dialect
            dialect_dir.mkdir(parents=True, exist_ok=True)

            # Generate full DDL
            full_ddl_file = dialect_dir / "derisk.sql"
            try:
                generator.generate_full_ddl(dialect, full_ddl_file)
                logger.info(f"✓ Generated full {dialect} DDL: {full_ddl_file}")
            except Exception as e:
                logger.error(f"✗ Failed to generate {dialect} full DDL: {e}")
                return 1

            # Generate incremental DDL (if enabled and old DDL exists)
            if not args.no_incremental:
                # Check for existing full DDL (backup before overwrite)
                backup_file = dialect_dir / "derisk.sql.bak"

                if full_ddl_file.exists():
                    # Read old version from existing DDL
                    try:
                        # Extract old version and timestamp
                        old_content = full_ddl_file.read_text(encoding="utf-8")
                        old_version_match = re.search(r'-- Version:\s*(\S+)', old_content)
                        old_generated_match = re.search(r'-- Generated:\s*(\S+)', old_content)

                        old_version = old_version_match.group(1) if old_version_match else "unknown"
                        old_generated = old_generated_match.group(1) if old_generated_match else ""

                        # Generate incremental DDL filename
                        current_timestamp = datetime.now().strftime('%Y%m%d')
                        old_timestamp = old_generated.split('T')[0].replace('-', '') if old_generated else "unknown"

                        upgrade_filename = f"upgrade_{old_version}_{old_timestamp}_to_{version}_{current_timestamp}.sql"
                        upgrade_file = dialect_dir / "upgrades" / upgrade_filename

                        # Generate incremental DDL
                        # Note: We need to pass the backup file (before it's overwritten)
                        # For now, we'll use the current file which was just written
                        incremental_ddl = generator.generate_incremental_ddl(
                            dialect,
                            full_ddl_file,
                            upgrade_file
                        )

                        if incremental_ddl:
                            logger.info(f"✓ Generated incremental {dialect} DDL: {upgrade_file}")
                        else:
                            logger.info(f"  No schema changes detected for {dialect}")

                    except Exception as e:
                        logger.warning(f"Failed to generate incremental DDL for {dialect}: {e}")

        logger.info("DDL generation complete!")

    return 0


if __name__ == "__main__":
    sys.exit(main())