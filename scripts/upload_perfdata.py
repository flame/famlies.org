#!/usr/bin/env python3

"""
Upload performance data to the central database.

This script performs Stage 3 of the data collection process:
1. Downloads the current perf.sqlite database from the FTPS server
2. Merges it with any local perf.sqlite databases found in directories
   named after git commit hashes
3. Uploads the merged database back to the server

Usage:
    python3 upload_perfdata.py

The script assumes:
- A .netrc file is configured for FTPS authentication
- Local perf.sqlite databases exist in subdirectories matching git commit hashes
- Write permissions exist in the current directory
"""

import argparse
import sqlite3
import subprocess
import sys
from pathlib import Path
from datetime import datetime


# FTPS server configuration
FTPS_URL = "ftps://ftp.box.com/blis.famlies.org/perf.sqlite"
DOWNLOADED_DB = "perf.sqlite.downloaded"
MERGED_DB = "perf.sqlite.merged"
FINAL_DB = "perf.sqlite"


def is_git_hash_like(name):
    """
    Check if a string looks like a git commit hash.

    Git short hashes are typically 7-40 hex characters.
    """
    if not isinstance(name, str):
        return False
    # Accept 7-40 hex characters (short or full commit hash)
    if len(name) < 7 or len(name) > 40:
        return False
    try:
        int(name, 16)
        return True
    except ValueError:
        return False


def find_commit_directories():
    """
    Find all subdirectories in the current directory that look like git commit hashes.

    Returns:
        list: List of Path objects for commit directories containing perf.sqlite
    """
    commit_dirs = []
    cwd = Path.cwd()

    for item in cwd.iterdir():
        if item.is_dir() and is_git_hash_like(item.name):
            db_file = item / FINAL_DB
            if db_file.exists():
                commit_dirs.append(item)

    return sorted(commit_dirs)


def download_database(url, output_file):
    """
    Download the database from the FTPS server using curl.

    Args:
        url (str): FTPS URL to download from
        output_file (str): Local file path to save to

    Returns:
        "success": Download successful
        "not_found": File not found on server (404)
        "error": Other error occurred
    """
    print(f"Downloading database from {url}...")
    try:
        result = subprocess.run(
            ["curl", "-n", "--ssl-reqd", "-o", output_file, "-w", "%{http_code}", url],
            capture_output=True,
            text=True,
            check=False,
        )
        # Extract HTTP status code from stdout (last part)
        http_code = result.stdout.strip().split()[-1] if result.stdout.strip() else ""

        if http_code == "200" or result.returncode == 0:
            print(f"  ✓ Database downloaded: {output_file}")
            return "success"
        elif http_code == "404":
            print("  Database not found on server (404)")
            return "not_found"
        else:
            print(f"  Error downloading database (HTTP {http_code}): {result.stderr}")
            return "error"
    except FileNotFoundError:
        print("  Error: curl command not found")
        return "error"
    except Exception as e:
        print(f"  Error during download: {e}")
        return "error"


def merge_databases(target_db, source_db):
    """
    Merge a source database into a target database.

    Copies all rows from the 'run' table in source_db to target_db.

    Args:
        target_db (Path or str): Path to target database
        source_db (Path or str): Path to source database

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        conn_target = sqlite3.connect(str(target_db))
        cursor_target = conn_target.cursor()

        # Attach source database
        cursor_target.execute(f'ATTACH DATABASE "{source_db}" AS source')

        # Copy all rows from source.run to target.run
        cursor_target.execute(
            """
            INSERT INTO run
            SELECT * FROM source.run
        """
        )

        # Detach source database
        cursor_target.execute("DETACH DATABASE source")
        conn_target.commit()
        conn_target.close()

        return True
    except sqlite3.Error as e:
        print(f"  Error merging databases: {e}")
        return False
    except Exception as e:
        print(f"  Error during merge: {e}")
        return False


def upload_database(file_path, url):
    """
    Upload the merged database to the FTPS server using curl.

    Args:
        file_path (str): Local file path to upload
        url (str): FTPS URL to upload to

    Returns:
        bool: True if successful, False otherwise
    """
    print(f"Uploading database to {url}...")
    try:
        result = subprocess.run(
            ["curl", "-n", "-f", "--ssl-reqd", "-T", file_path, url],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            print("  ✓ Database uploaded successfully")
            return True
        else:
            print(f"  Error uploading database: {result.stderr}")
            return False
    except FileNotFoundError:
        print("  Error: curl command not found")
        return False
    except Exception as e:
        print(f"  Error during upload: {e}")
        return False


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Upload merged performance data to central database"
    )
    parser.add_argument(
        "--keep-downloaded",
        action="store_true",
        help="Keep downloaded database after merging",
    )
    parser.add_argument(
        "--keep-merged",
        action="store_true",
        help="Keep merged database after uploading",
    )

    args = parser.parse_args()

    print(f"\n{'=' * 60}")
    print("BLIS Performance Data Upload")
    print(f"{'=' * 60}\n")

    # Find local commit directories with databases
    print("Looking for local databases in commit hash directories...")
    commit_dirs = find_commit_directories()
    if not commit_dirs:
        print("  No local databases found in commit hash directories")
        print("  Nothing to merge and upload")
        return

    print(f"  Found {len(commit_dirs)} database(s):")
    for commit_dir in commit_dirs:
        print(f"    - {commit_dir.name}")

    # Download current database
    print(f"\n{'=' * 60}")
    print("Downloading current database")
    print(f"{'=' * 60}\n")

    downloaded_path = Path.cwd() / DOWNLOADED_DB
    download_result = download_database(FTPS_URL, str(downloaded_path))

    if download_result == "error":
        print("Error: Failed to download database (server error)")
        sys.exit(1)

    # Merge databases
    print(f"\n{'=' * 60}")
    print("Merging databases")
    print(f"{'=' * 60}\n")

    merged_path = Path.cwd() / MERGED_DB
    import shutil

    if download_result == "success":
        # Downloaded successfully, copy it as base for merging
        try:
            shutil.copy(str(downloaded_path), str(merged_path))
            print(f"Copied downloaded database to {merged_path}")
        except Exception as e:
            print(f"Error copying database: {e}")
            sys.exit(1)
    else:
        # Database doesn't exist on server (404), use local databases as base
        print("Database doesn't exist on server, creating from local databases...\n")
        if not commit_dirs:
            print("Error: No local databases to merge")
            sys.exit(1)

        # Use first local database as base
        source_db = commit_dirs[0] / FINAL_DB
        try:
            shutil.copy(str(source_db), str(merged_path))
            print(f"Using first local database as base: {source_db}")
        except Exception as e:
            print(f"Error copying database: {e}")
            sys.exit(1)

        commit_dirs = commit_dirs[1:]  # Remaining directories to merge

    # Merge each local database into the merged database
    for commit_dir in commit_dirs:
        source_db = commit_dir / FINAL_DB
        print(f"\nMerging {source_db}...")
        if not merge_databases(merged_path, source_db):
            print(f"Error: Failed to merge {source_db}")
            sys.exit(1)
        print("  ✓ Merged successfully")

    # Upload merged database
    print(f"\n{'=' * 60}")
    print("Uploading merged database")
    print(f"{'=' * 60}\n")

    if not upload_database(str(merged_path), FTPS_URL):
        print("Error: Failed to upload database")
        sys.exit(1)

    # Cleanup
    print(f"\n{'=' * 60}")
    print("Cleanup")
    print(f"{'=' * 60}\n")

    try:
        if download_result == "success":
            if not args.keep_downloaded:
                downloaded_path.unlink()
                print(f"Removed {DOWNLOADED_DB}")
            else:
                print(f"Keeping {DOWNLOADED_DB} (use --keep-downloaded to control)")

        if not args.keep_merged:
            merged_path.unlink()
            print(f"Removed {MERGED_DB}")
        else:
            print(f"Keeping {MERGED_DB} (use --keep-merged to control)")
    except Exception as e:
        print(f"Warning: Error during cleanup: {e}")

    print(f"\n{'=' * 60}")
    print("Upload Complete")
    print(f"{'=' * 60}")
    print(f"  Timestamp: {datetime.now().isoformat()}")
    print(f"  Databases merged: {len(commit_dirs)}")
    print()


if __name__ == "__main__":
    main()
