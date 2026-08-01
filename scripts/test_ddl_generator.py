#!/usr/bin/env python3
"""
Test script for DDL Generator

This script validates the DDL generator by:
1. Discovering ORM models
2. Generating DDL for MySQL and PostgreSQL
3. Validating the generated SQL syntax
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "packages" / "derisk-core" / "src"))

from ddl_generator.core import (
    DDLGenerator,
    discover_metadata,
    get_project_version,
)


def test_basic_reflection():
    """Test basic schema reflection."""
    print("=" * 80)
    print("Test 1: Basic Schema Reflection")
    print("=" * 80)

    # Discover metadata
    metadata = discover_metadata()

    print(f"Tables found: {len(metadata.tables)}")
    if metadata.tables:
        print(f"Sample tables: {list(metadata.tables.keys())[:5]}")

        # Show first table details
        first_table = list(metadata.tables.values())[0]
        print(f"\nFirst table: {first_table.name}")
        print(f"  Columns: {len(first_table.columns)}")
        print(f"  Indexes: {len(first_table.indexes)}")

        return True
    else:
        print("WARNING: No tables found. Database might not be initialized.")
        return False


def test_mysql_ddl_generation():
    """Test MySQL DDL generation."""
    print("\n" + "=" * 80)
    print("Test 2: MySQL DDL Generation")
    print("=" * 80)

    metadata = discover_metadata()
    version = get_project_version(project_root)

    generator = DDLGenerator(metadata, version)

    try:
        ddl_content = generator.generate_full_ddl("mysql")

        # Basic validation
        assert "CREATE TABLE" in ddl_content, "Missing CREATE TABLE statement"
        assert "ENGINE=InnoDB" in ddl_content, "Missing MySQL-specific syntax"
        assert f"Version: {version}" in ddl_content, "Missing version header"

        print("✓ MySQL DDL generation successful")
        print(f"  Generated {len(ddl_content.splitlines())} lines")

        # Show sample output
        lines = ddl_content.splitlines()
        print("\nSample output (first 20 lines):")
        print("\n".join(lines[:20]))

        return True
    except Exception as e:
        print(f"✗ MySQL DDL generation failed: {e}")
        return False


def test_postgresql_ddl_generation():
    """Test PostgreSQL DDL generation."""
    print("\n" + "=" * 80)
    print("Test 3: PostgreSQL DDL Generation")
    print("=" * 80)

    metadata = discover_metadata()
    version = get_project_version(project_root)

    generator = DDLGenerator(metadata, version)

    try:
        ddl_content = generator.generate_full_ddl("postgresql")

        # Basic validation
        assert "CREATE TABLE" in ddl_content, "Missing CREATE TABLE statement"
        assert "ENGINE=InnoDB" not in ddl_content, "Should not have MySQL syntax"
        assert f"Version: {version}" in ddl_content, "Missing version header"

        # PostgreSQL-specific checks
        if "BOOLEAN" in ddl_content:
            assert "true" in ddl_content.lower() or "false" in ddl_content.lower(), \
                "PostgreSQL should use lowercase true/false"

        print("✓ PostgreSQL DDL generation successful")
        print(f"  Generated {len(ddl_content.splitlines())} lines")

        # Show sample output
        lines = ddl_content.splitlines()
        print("\nSample output (first 20 lines):")
        print("\n".join(lines[:20]))

        return True
    except Exception as e:
        print(f"✗ PostgreSQL DDL generation failed: {e}")
        return False


def test_file_output():
    """Test writing DDL to files."""
    print("\n" + "=" * 80)
    print("Test 4: File Output")
    print("=" * 80)

    import tempfile
    import shutil

    # Create temporary directory
    temp_dir = Path(tempfile.mkdtemp(prefix="ddl_test_"))

    try:
        metadata = discover_metadata()
        version = get_project_version(project_root)

        generator = DDLGenerator(metadata, version)

        # Generate for all dialects
        output_files = generator.generate_all_dialects(temp_dir)

        # Validate output
        for dialect, output_file in output_files.items():
            if not output_file.exists():
                print(f"✗ Output file not created: {output_file}")
                return False

            content = output_file.read_text(encoding="utf-8")
            if len(content) < 100:
                print(f"✗ Output file too small: {output_file} ({len(content)} bytes)")
                return False

            print(f"✓ {dialect.upper()} DDL written to: {output_file}")
            print(f"  File size: {len(content)} bytes")

        return True
    except Exception as e:
        print(f"✗ File output test failed: {e}")
        return False
    finally:
        # Cleanup
        shutil.rmtree(temp_dir, ignore_errors=True)


def main():
    """Run all tests."""
    print("DDL Generator Test Suite")
    print("=" * 80)

    tests = [
        ("Basic Reflection", test_basic_reflection),
        ("MySQL DDL", test_mysql_ddl_generation),
        ("PostgreSQL DDL", test_postgresql_ddl_generation),
        ("File Output", test_file_output),
    ]

    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"✗ Test '{name}' crashed: {e}")
            results.append((name, False))

    # Summary
    print("\n" + "=" * 80)
    print("Test Summary")
    print("=" * 80)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "PASS" if result else "FAIL"
        print(f"  {status}: {name}")

    print(f"\nTotal: {passed}/{total} tests passed")

    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())