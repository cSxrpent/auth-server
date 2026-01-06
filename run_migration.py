from migrate_github_to_supabase import migrate_data, verify_migration
import os

if os.getenv("RUN_MIGRATION") != "true":
    print("⏭️ Migration skipped (RUN_MIGRATION != true)")
    exit(0)


if __name__ == '__main__':
    success = migrate_data()
    if success:
        verify_migration()
else:
    # Allow import without running
    pass
