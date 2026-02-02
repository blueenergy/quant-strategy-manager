#!/usr/bin/env python3
"""
Database migration: Remove deprecated engine_class field.

This script removes the `engine_class` field from watchlist_strategies
since it's now automatically resolved from strategy_key via strategy_registry.

Usage:
    python scripts/migrate_remove_engine_class.py
    python scripts/migrate_remove_engine_class.py --dry-run
"""

import argparse
import sys
from pymongo import MongoClient
import os


def get_db_connection():
    """Get MongoDB connection from environment."""
    mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    mongo_db = os.getenv("MONGO_DB", "finance")
    
    client = MongoClient(mongo_uri)
    return client[mongo_db]


def migrate_remove_engine_class(dry_run=False):
    """
    Remove engine_class field from watchlist_strategies.
    
    Args:
        dry_run: If True, only show what would be changed
    """
    db = get_db_connection()
    collection = db["watchlist_strategies"]
    
    # Find documents with engine_class field
    query = {"engine_class": {"$exists": True}}
    docs = list(collection.find(query))
    
    if not docs:
        print("✓ No documents found with engine_class field")
        print("  Database is already clean!")
        return 0
    
    print(f"Found {len(docs)} documents with engine_class field:")
    print()
    
    for doc in docs:
        symbol = doc.get("symbol", "N/A")
        strategy_key = doc.get("strategy_key", "N/A")
        engine_class = doc.get("engine_class", "N/A")
        
        print(f"  • {symbol} ({strategy_key})")
        print(f"    Current engine_class: {engine_class}")
        
        if dry_run:
            print(f"    [DRY RUN] Would remove engine_class field")
        else:
            result = collection.update_one(
                {"_id": doc["_id"]},
                {"$unset": {"engine_class": ""}}
            )
            if result.modified_count > 0:
                print(f"    ✓ Removed engine_class field")
            else:
                print(f"    ⚠️  Failed to remove field")
        
        print()
    
    if dry_run:
        print(f"[DRY RUN] Would update {len(docs)} documents")
        print()
        print("Run without --dry-run to apply changes:")
        print("  python scripts/migrate_remove_engine_class.py")
    else:
        print(f"✓ Migration complete: Updated {len(docs)} documents")
        print()
        print("Next steps:")
        print("  1. Verify strategies still work correctly")
        print("  2. UI should now only save: engine + strategy_key")
        print("  3. System auto-resolves engine_class from strategy_registry")
    
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Remove deprecated engine_class field from database"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be changed without modifying database"
    )
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("Database Migration: Remove engine_class Field")
    print("=" * 60)
    print()
    
    try:
        return migrate_remove_engine_class(dry_run=args.dry_run)
    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
