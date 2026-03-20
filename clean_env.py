import os
import shutil
from pathlib import Path

def clean_environment():
    root_dir = Path(__file__).resolve().parent
    
    # 1. Clean the Imports directory
    imports_dir = root_dir / "Imports"
    if imports_dir.exists() and imports_dir.is_dir():
        print(f"Cleaning imports directory: {imports_dir}")
        for item in imports_dir.iterdir():
            try:
                if item.is_file() or item.is_symlink():
                    item.unlink()
                    print(f"  Deleted file: {item.name}")
                elif item.is_dir():
                    shutil.rmtree(item)
                    print(f"  Deleted directory: {item.name}")
            except Exception as e:
                print(f"  Failed to delete {item.name}. Reason: {e}")
    else:
        print(f"Imports directory not found at {imports_dir}, skipping.")

    # 2. Delete the SQLite database
    db_file = root_dir / "gaze_analysis.db"
    if db_file.exists():
        try:
            db_file.unlink()
            print(f"Deleted database file: {db_file.name}")
        except Exception as e:
            print(f"Failed to delete database file. Reason: {e}")
    else:
        print("Database file gaze_analysis.db not found, skipping.")

    print("\nEnvironment successfully cleaned. Ready for a fresh debug session.")

if __name__ == "__main__":
    confirm = input("This will delete all imported files and the local database. Are you sure? (y/n): ")
    if confirm.lower() == 'y':
        clean_environment()
    else:
        print("Cleanup aborted.")
