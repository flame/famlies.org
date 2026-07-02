#!/usr/bin/env python3

import sqlite3
import subprocess
import re
from pathlib import Path
from datetime import datetime


def get_git_commit():
    """Get current git commit hash."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=Path.cwd(),
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def get_git_tag():
    """Get git tag for current commit, or branch name if no tag."""
    try:
        # Try to get tag
        result = subprocess.run(
            ["git", "describe", "--tags", "--exact-match"],
            cwd=Path.cwd(),
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return result.stdout.strip()

        # Fall back to branch name
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=Path.cwd(),
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def parse_testsuite(filepath):
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


def create_database(db_path):
    """Create SQLite database with run table."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS run(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tag TEXT,
            git TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            machine TEXT,
            threads INTEGER,
            gflops REAL,
            m INTEGER,
            n INTEGER,
            k INTEGER,
            op TEXT,
            dt TEXT,
            config TEXT,
            comment TEXT
        )
    """)

    conn.commit()
    return conn


def insert_data(conn, data, git_commit, git_tag, machine=None):
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
                None,  # comment is typically empty
            ),
        )

    conn.commit()


def main():
    import sys

    # Default paths
    testsuite_file = "output.testsuite"
    db_file = "perf.sqlite"
    machine = None

    # Parse command line arguments
    if len(sys.argv) == 2:
        machine = sys.argv[1]
    if len(sys.argv) > 2:
        testsuite_file = sys.argv[1]
        db_file = sys.argv[2]
    if len(sys.argv) > 3:
        machine = sys.argv[3]

    # Check if testsuite file exists
    if not Path(testsuite_file).exists():
        print(f"Error: {testsuite_file} not found")
        sys.exit(1)

    print(f"Reading {testsuite_file}...")
    data = parse_testsuite(testsuite_file)

    print(f"Config: {data['config']}")
    print(f"Threads: {data['threads']}")
    print(f"Operations found: {len(data['operations'])}")

    git_commit = get_git_commit()
    git_tag = get_git_tag()

    print(f"Git commit: {git_commit}")
    print(f"Git tag/branch: {git_tag}")

    print(f"\nCreating/connecting to database {db_file}...")
    conn = create_database(db_file)

    print(f"Inserting {len(data['operations'])} rows...")
    insert_data(conn, data, git_commit, git_tag, machine)

    conn.close()
    print("Done!")


if __name__ == "__main__":
    main()
