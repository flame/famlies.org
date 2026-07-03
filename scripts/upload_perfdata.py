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
import json
import sqlite3
import subprocess
import sys
import yaml
import re
from pathlib import Path
from datetime import datetime


# FTPS server configuration
FTPS_URL = "ftps://ftp.box.com/blis.famlies.org/perf.sqlite"
DOWNLOADED_DB = "perf.sqlite.downloaded"
MERGED_DB = "perf.sqlite.merged"
FINAL_DB = "perf.sqlite"
DB_COLUMNS = {
    "id": "INTEGER PRIMARY KEY AUTOINCREMENT",
    "tag": "TEXT",
    "git": "TEXT",
    "timestamp": "DATETIME DEFAULT CURRENT_TIMESTAMP",
    "machine": "TEXT",
    "threads": "INTEGER",
    "gflops": "REAL",
    "m": "INTEGER",
    "n": "INTEGER",
    "k": "INTEGER",
    "op": "TEXT",
    "dt": "TEXT",
    "config": "TEXT",
    "comment": "TEXT",
}


def parse_arguments():
    """Parse command line arguments."""
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
    parser.add_argument(
        "-n",
        "--dry-run",
        action="store_true",
        help="Skip download and upload steps, only merge local databases",
    )
    parser.add_argument(
        "-s",
        "--status",
        help="YAML file to save the status of each git reference (most recent commit) after processing",
    )

    args = parser.parse_args()
    if args.dry_run:
        args.keep_merged = True

    return args


def parse_testsuite(filepath: str | Path) -> dict:
    """Parse output.testsuite file and extract relevant data."""
    data = {"config": None, "threads": None, "operations": []}

    with open(filepath, "r") as f:
        lines = f.readlines()

    # Extract config (last word on "% active sub-configuration" line)
    for line in lines:
        if "% active sub-configuration" in line:
            parts = line.split()
            data["config"] = parts[-1].strip()
            break

    # Extract threads (first number in the "% environment" line after "% ways of parallelism")
    for i, line in enumerate(lines):
        if "% ways of parallelism" in line:
            # Look for the "% environment" line - it should be the next non-empty line or within next few lines
            for j in range(i + 1, min(i + 5, len(lines))):
                if "environment" in lines[j]:
                    # This line has the thread values, extract first number
                    numbers = re.findall(r"\d+", lines[j])
                    if numbers:
                        data["threads"] = int(numbers[0])
                    break
            break

    # Parse operation blocks
    i = 0
    while i < len(lines):
        line = lines[i]

        # Look for header lines starting with "% blis_"
        if line.startswith("% blis_<dt><op>"):
            # This is a header line, parse it to determine columns
            header = line.strip()

            # Parse column names from header
            # Format: % blis_<dt><op>_<params>_<stor>            m   gflops   resid      result
            # or:     % blis_<dt><op>_<params>_<stor>            m     n     k   gflops   resid      result

            columns = []
            parts = header.split()
            # Skip the first two parts (% and the template)
            for part in parts[2:]:
                if part in ["m", "n", "k", "gflops", "resid", "result"]:
                    columns.append(part)

            # Read data lines until we hit another header or comment
            i += 1
            while i < len(lines):
                data_line = lines[i]

                # Stop if we hit another header or empty comment section
                if data_line.startswith("%"):
                    break

                # Stop if line is empty
                if not data_line.strip():
                    i += 1
                    break

                # Parse the data line
                parts = data_line.split()
                if len(parts) >= 1 and parts[0].startswith("blis_"):
                    operation_name = parts[0]
                    values = parts[1:]

                    # Extract dt and op from operation_name
                    # Format: blis_s/d/c/z<op>_...
                    if len(operation_name) >= 7:
                        dt = operation_name[5]  # 6th character (0-indexed: 5)
                        op = operation_name[
                            6:
                        ]  # 7th character onwards, remove "blis_" and dt

                        # Create record
                        record = {
                            "op": op,
                            "dt": dt,
                            "m": -1,
                            "n": -1,
                            "k": -1,
                            "gflops": None,
                        }

                        # Map values to columns
                        for col_idx, col_name in enumerate(columns):
                            if col_idx < len(values):
                                try:
                                    if col_name in ["m", "n", "k"]:
                                        record[col_name] = int(values[col_idx])
                                    elif col_name == "gflops":
                                        record["gflops"] = float(values[col_idx])
                                except ValueError:
                                    pass

                        data["operations"].append(record)

                i += 1
        else:
            i += 1

    return data


def open_database(db_path: str | Path) -> sqlite3.Connection:
    """Create SQLite database with run table."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS run(
            {", ".join(f"{key} {value}" for key, value in DB_COLUMNS.items())}
        )
    """)

    conn.commit()
    return conn


def insert_data(
    conn: sqlite3.Connection,
    data: dict,
    git_commit: str,
    git_tag: str,
    machine: str | None = None,
    comment: str | None = None,
):
    """Insert parsed data into database."""
    cursor = conn.cursor()

    for operation in data["operations"]:
        cursor.execute(
            """
            INSERT INTO run (
                tag, git, timestamp, machine, threads, gflops, m, n, k, op, dt, config, comment
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                git_tag,
                git_commit,
                data["timestamp"]
                if "timestamp" in data
                else datetime.now().isoformat(),
                machine,
                data["threads"],
                operation["gflops"],
                operation["m"],
                operation["n"],
                operation["k"],
                operation["op"],
                operation["dt"],
                data["config"],
                comment,
            ),
        )

    conn.commit()


def import_testsuite(
    testsuite_file: str | Path,
    db_file: str | Path,
    git_commit: str,
    git_tag: str,
    machine: str | None = None,
    comment: str | None = None,
) -> bool:
    """
    Import test suite data into SQLite database.

    Arguments:
        testsuite_file (str or Path): Path to the output.testsuite file
        db_file (str or Path): Path to the SQLite database file
        git_commit (str): Git commit hash
        git_tag (str): Git tag/branch
        machine (str, optional): Machine name to store in the database
        comment (str, optional): Comment to store in the database

    Returns:
        bool: True if successful, False otherwise
    """
    # Check if testsuite file exists
    if not Path(testsuite_file).exists():
        print(f"Error: {testsuite_file} not found")
        return False

    print(f"Reading {testsuite_file}...")
    data = parse_testsuite(testsuite_file)

    print(f"Config: {data['config']}")
    print(f"Threads: {data['threads']}")
    print(f"Operations found: {len(data['operations'])}")

    print(f"Git commit: {git_commit}")
    print(f"Git tag/branch: {git_tag}")

    print(f"\nCreating/connecting to database {db_file}...")
    conn = open_database(db_file)

    print(f"Inserting {len(data['operations'])} rows...")
    insert_data(conn, data, git_commit, git_tag, machine, comment)

    conn.close()
    print("Done!")

    return True


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
        list: List of Path objects for commit directories containing output.testsuite
    """
    commit_dirs = []
    cwd = Path.cwd()

    for item in cwd.iterdir():
        if (
            item.is_dir()
            and is_git_hash_like(item.name)
            and (item / "runjob.sh").exists()
        ):
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
        conn_source = sqlite3.connect(str(source_db))
        cursor_source = conn_source.cursor()

        # Copy all rows from source.run to target.run
        # except the 'id' column, which is auto-incremented in the target
        cursor_source.execute(
            f"""SELECT
            {", ".join(DB_COLUMNS.keys() - {"id"})}
            FROM run
        """
        )
        data = cursor_source.fetchall()

        conn_source.close()

        conn_target = sqlite3.connect(str(target_db))
        cursor_target = conn_target.cursor()

        # Copy all rows from source.run to target.run
        # except the 'id' column, which is auto-incremented in the target
        cursor_target.executemany(
            f"""INSERT INTO run (
                {", ".join(DB_COLUMNS.keys() - {"id"})}
            ) VALUES ({", ".join(["?"] * (len(DB_COLUMNS) - 1))})
        """,
            data,
        )

        conn_target.commit()
        conn_target.close()

        return True
    except Exception as e:
        print(f"  Error merging databases: {e}")
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


def create_database(commit_dir: str | Path) -> bool:
    """
    Import the output.testsuite file from a commit directory into a new SQLite database.
    If the database already exists, it will not be recreated.

    Arguments:
        commit_dir (str or Path): Path to the commit directory containing output.testsuite

    Returns:
        bool: True if successful, False otherwise
    """
    commit_dir = Path(commit_dir)
    commit_hash = commit_dir.name

    db_path = commit_dir / FINAL_DB
    if db_path.exists():
        print(f"Database {db_path} already exists, recreating...")
        db_path.unlink()  # Remove existing database to create a fresh one

    config_path = commit_dir / "config.yaml"
    if not config_path.exists():
        print(f"Error: config.yaml not found in {commit_dir}")
        return False

    try:
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)
    except Exception as e:
        print(f"Error reading config.yaml: {e}")
        return False

    machine = config.pop("machine", None)
    git_tag = config.pop("tag", None)
    comment = json.dumps(config)

    if not machine:
        print("Error: 'machine' missing in config.yaml")
        return False

    outputs = list(commit_dir.glob("output.testsuite.*"))
    if not outputs:
        print(f"Error: No output.testsuite files found in {commit_dir}")
        return False

    for output_file in outputs:
        print(f"\nImporting {output_file} into database {db_path}...")
        if not import_testsuite(
            output_file, db_path, commit_hash, git_tag, machine, comment
        ):
            print(f"Error: Failed to import {output_file}")
            return False

    return True


def record_status(commit_dir: Path) -> dict:
    """
    Record the status of a git commit hash.

    Args:
        commit_dir (Path): Path to the commit directory

    Returns:
        dict: Status dictionary with commit hash and timestamp
    """
    commit_hash = commit_dir.name
    config_path = commit_dir / "config.yaml"
    if not config_path.exists():
        print(f"Error: config.yaml not found in {commit_dir}")
        return {}

    try:
        with open(config_path, "r") as f:
            tag = yaml.safe_load(f).get("tag", None)
            return {tag: commit_hash} if tag else {}
    except Exception as e:
        print(f"Error reading config.yaml: {e}")
        return {}


def main():
    """Main entry point."""

    args = parse_arguments()

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

    for commit_dir in commit_dirs:
        print(f"\nImporting data into {commit_dir / FINAL_DB}...")
        if not create_database(commit_dir):
            print(f"Error: Failed to create database for {commit_dir}")
            sys.exit(1)

    print(f"\nFound {len(commit_dirs)} database(s):")
    for commit_dir in commit_dirs:
        print(f"  - {commit_dir.name}")

    downloaded_path = Path.cwd() / DOWNLOADED_DB

    if not args.dry_run:
        # Download current database
        print(f"\n{'=' * 60}")
        print("Downloading current database")
        print(f"{'=' * 60}\n")

        download_result = download_database(FTPS_URL, str(downloaded_path))

        if download_result == "error":
            print("Error: Failed to download database (server error)")
            sys.exit(1)

    else:
        download_result = "skipped"

    status_data = {}
    if args.status:
        status_file = Path(args.status)
        if status_file.exists():
            try:
                with open(status_file, "r") as f:
                    status_data = yaml.safe_load(f) or {}
            except Exception as e:
                print(f"Error reading status file '{status_file}': {e}")
                sys.exit(1)

    # Merge databases
    print(f"\n{'=' * 60}")
    print("Merging databases")
    print(f"{'=' * 60}\n")

    merged_path = Path.cwd() / MERGED_DB
    import shutil

    first_to_merge = 0
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
        if download_result == "not_found":
            print(
                "Database doesn't exist on server, creating from local databases...\n"
            )
        else:
            print(
                "Download skipped, creating merged database from local databases...\n"
            )
        if not commit_dirs:
            print("Error: No local databases to merge")
            sys.exit(1)

        # Use first local database as base
        source_db = commit_dirs[0] / FINAL_DB
        status_data.update(record_status(commit_dirs[0]))
        try:
            shutil.copy(str(source_db), str(merged_path))
            print(f"Using first local database as base: {source_db}")
        except Exception as e:
            print(f"Error copying database: {e}")
            sys.exit(1)

        first_to_merge = 1  # Skip the first one since it's already copied

    # Merge each local database into the merged database
    for commit_dir in commit_dirs[first_to_merge:]:
        source_db = commit_dir / FINAL_DB
        status_data.update(record_status(commit_dir))
        print(f"\nMerging {source_db}...")
        if not merge_databases(merged_path, source_db):
            print(f"Error: Failed to merge {source_db}")
            sys.exit(1)
        print("  ✓ Merged successfully")

    if not args.dry_run:
        # Upload merged database
        print(f"\n{'=' * 60}")
        print("Uploading merged database")
        print(f"{'=' * 60}\n")

        if not upload_database(str(merged_path), FTPS_URL):
            print("Error: Failed to upload database")
            sys.exit(1)

    if args.status:
        status_file = Path(args.status)
        try:
            with open(status_file, "w") as f:
                yaml.safe_dump(status_data, f)
        except Exception as e:
            print(f"Error writing status file '{status_file}': {e}")
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
