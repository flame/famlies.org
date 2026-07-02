#!/usr/bin/env python3

"""
Collect performance data from a BLIS build and save to database.

Usage:
    python3 collect_perfdata.py <config.yaml> <git_ref> [<git_ref> ...] [-j N]

The script reads a YAML configuration file that specifies machine details,
thread configurations, and optional metadata. It then clones, builds, and
prepares the test environment for one or more git references, creating a
runjob.sh batch script for each commit.
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import yaml


substitution_vars = {
    "dt": "sdcz",
    "mstorage": "rc",
    "vstorage": "c",
    "repeat": 3,
    "1m": 1,
    "native": 1,
    "level2": 0,
    "level3": 1,
}


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Collect BLIS performance data from one or more git commits/tags/branches"
    )
    parser.add_argument(
        "config_file", help="YAML configuration file with machine specs and metadata"
    )
    parser.add_argument(
        "git_refs",
        nargs="+",
        help="One or more git commit hashes, tags, or branch names to collect data for",
    )
    parser.add_argument(
        "-j",
        "--jobs",
        type=int,
        default=1,
        help="Number of concurrent jobs to pass to make (default: 1)",
    )

    return parser.parse_args()


def read_config_file(config_path):
    """
    Read and parse the YAML configuration file.

    Expected structure:
    machine: <machine_name>
    threads: [<thread_counts>]
    hi: [<high_matrix_sizes>]
    lo: [<low_matrix_sizes>]
    step: [<step_sizes>]
    config: <config_name>
    <other_user_defined_keys>: <values>

    Returns:
        dict: Configuration data with required and optional keys
    """
    config_path = Path(config_path)
    if not config_path.exists():
        print(f"Error: Configuration file '{config_path}' not found")
        sys.exit(1)

    try:
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)
    except yaml.YAMLError as e:
        print(f"Error parsing YAML file: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error reading configuration file: {e}")
        sys.exit(1)

    # Validate required fields
    required_fields = ["machine", "threads", "hi", "lo", "step", "config"]
    missing_fields = [field for field in required_fields if field not in config]

    if missing_fields:
        print(f"Error: Missing required config fields: {', '.join(missing_fields)}")
        sys.exit(1)

    # Validate threads, hi, lo, and step arrays
    array_fields = ["threads", "hi", "lo", "step"]

    # Check that all array fields are lists
    for field in array_fields:
        if not isinstance(config[field], (list, tuple)):
            print(
                f"Error: '{field}' must be a list/array, got {type(config[field]).__name__}"
            )
            sys.exit(1)

    # Check that all arrays are non-empty
    for field in array_fields:
        if len(config[field]) == 0:
            print(f"Error: '{field}' array must not be empty")
            sys.exit(1)

    # Check that all arrays have the same length
    lengths = {field: len(config[field]) for field in array_fields}
    if len(set(lengths.values())) > 1:
        print("Error: 'threads', 'hi', 'lo', and 'step' must all have the same length")
        print(f"  threads: {lengths['threads']}")
        print(f"  hi: {lengths['hi']}")
        print(f"  lo: {lengths['lo']}")
        print(f"  step: {lengths['step']}")
        sys.exit(1)

    # Check that all elements in each array are positive integers
    for field in array_fields:
        for i, value in enumerate(config[field]):
            if not isinstance(value, int) or value <= 0:
                print(
                    f"Error: '{field}[{i}]' must be a positive integer, got {value} ({type(value).__name__})"
                )
                sys.exit(1)

    for var, default in substitution_vars.items():
        if var not in config:
            config[var] = default

    return config


def extract_user_defined_keys(config):
    """
    Extract user-defined keys (non-standard fields) from config.

    Standard fields are: machine, threads, hi, lo, step, config
    All other keys are collected into a JSON-formatted comment.

    Args:
        config (dict): Configuration dictionary

    Returns:
        str: JSON-formatted string of user-defined keys, or empty string
    """
    standard_fields = {"machine", "threads", "hi", "lo", "step", "config"}
    user_keys = {k: v for k, v in config.items() if k not in standard_fields}

    if user_keys:
        return json.dumps(user_keys)
    return ""


def validate_git_ref(git_ref):
    """
    Validate that the git reference exists in the repository.

    Args:
        git_ref (str): Git commit hash, tag, or branch name

    Returns:
        str: Short commit hash if valid, None otherwise
    """
    try:
        # Try to resolve the reference to a short commit hash
        result = subprocess.run(
            ["git", "rev-parse", "--short", git_ref],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        else:
            print(f"Error: Git reference '{git_ref}' not found")
            return None
    except FileNotFoundError:
        print("Error: git command not found")
        return None


def get_git_tag_for_commit(commit_hash):
    """
    Get the tag or branch name for a given commit hash.

    Args:
        commit_hash (str): Full commit hash

    Returns:
        str: Tag name if commit is tagged, otherwise branch name or commit hash
    """
    try:
        # Try to get tag for this commit
        result = subprocess.run(
            ["git", "describe", "--tags", "--exact-match", commit_hash],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass

    # Fall back to using the input reference or commit hash
    return commit_hash


def clone_blis_repository(build_dir):
    """
    Clone the BLIS repository into the specified directory.

    Args:
        build_dir (Path): Directory where BLIS will be cloned

    Returns:
        Path: Path to cloned BLIS directory, or None on failure
    """
    blis_dir = build_dir / "blis"

    # Remove directory if it already exists
    if blis_dir.exists():
        print(f"  Removing existing BLIS directory: {blis_dir}")
        subprocess.run(["rm", "-rf", str(blis_dir)], check=True)

    print(f"  Cloning BLIS repository to {blis_dir}...")
    try:
        result = subprocess.run(
            ["git", "clone", "https://github.com/flame/blis", str(blis_dir)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            print(f"  Error cloning repository: {result.stderr}")
            return None
        print("  Repository cloned successfully")
        return blis_dir
    except Exception as e:
        print(f"  Error during clone: {e}")
        return None


def checkout_git_ref(repo_dir, git_ref):
    """
    Checkout the specified git reference (commit/tag/branch).

    Args:
        repo_dir (Path): Repository directory
        git_ref (str): Git reference to check out

    Returns:
        bool: True if successful, False otherwise
    """
    print(f"  Checking out {git_ref}...")
    try:
        result = subprocess.run(
            ["git", "checkout", git_ref],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            print(f"  Error checking out {git_ref}: {result.stderr}")
            return False
        print("  Checked out successfully")
        return True
    except Exception as e:
        print(f"  Error during checkout: {e}")
        return False


def configure_blis(blis_dir, config_name):
    """
    Run BLIS configure script with the specified configuration.

    Args:
        blis_dir (Path): BLIS directory
        config_name (str): Configuration name for -tomp

    Returns:
        bool: True if successful, False otherwise
    """
    print(f"  Running configure with config: {config_name}...")
    configure_script = blis_dir / "configure"

    if not configure_script.exists():
        print(f"  Error: configure script not found at {configure_script}")
        return False

    try:
        result = subprocess.run(
            ["./configure", "-tomp", config_name],
            cwd=blis_dir,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            print(f"  Error running configure: {result.stderr}")
            return False
        print("  Configuration successful")
        return True
    except Exception as e:
        print(f"  Error during configure: {e}")
        return False


def build_blis(blis_dir, jobs=1):
    """
    Build BLIS and run make check to generate test executable and verify library.

    Args:
        blis_dir (Path): BLIS directory
        jobs (int): Number of concurrent jobs to pass to make

    Returns:
        Path: Path to test executable if successful, None otherwise
    """
    print(f"  Running make check with -j {jobs}...")
    try:
        result = subprocess.run(
            ["make", "-j", str(jobs), "check"],
            cwd=blis_dir,
            capture_output=True,
            text=True,
            check=False,
            timeout=3600,  # 1 hour timeout for build
        )
        if result.returncode != 0:
            print(f"  Error running make check: {result.stderr}")
            return None

        # Verify test executable exists
        test_exec = blis_dir / "test_libblis.x"
        if not test_exec.exists():
            print(f"  Error: test executable not found at {test_exec}")
            return None

        print("  Build successful, test executable created")
        return test_exec

    except subprocess.TimeoutExpired:
        print("  Error: make check timed out (exceeded 1 hour)")
        return None
    except Exception as e:
        print(f"  Error during build: {e}")
        return None


def create_job_directory(commit_hash, config, blis_dir):
    """
    Create a job directory named after the commit hash and generate runjob.sh.

    Args:
        commit_hash (str): Short git commit hash
        config (dict): Configuration dictionary
        blis_dir (Path): Path to BLIS repository

    Returns:
        Path: Path to job directory if successful, None otherwise
    """
    # Create directory in original working directory
    job_dir = Path.cwd() / commit_hash
    print(f"  Creating job directory: {job_dir}")

    try:
        job_dir.mkdir(exist_ok=True)
    except Exception as e:
        print(f"  Error creating directory: {e}")
        return None

    # Read runjob.sh.in template
    template_file = Path(__file__).parent / "runjob.sh.in"
    if not template_file.exists():
        print(f"  Error: Template file not found: {template_file}")
        return None

    try:
        with open(template_file, "r") as f:
            template_content = f.read()
    except Exception as e:
        print(f"  Error reading template: {e}")
        return None

    # Build substitution values
    threads_array = " ".join(str(t) for t in config["threads"])
    lo_array = " ".join(str(l) for l in config["lo"])
    hi_array = " ".join(str(h) for h in config["hi"])
    step_array = " ".join(str(s) for s in config["step"])

    scripts_dir = Path(__file__).parent
    db_file = Path.cwd() / "perf.sqlite"

    # Perform substitutions
    script_content = template_content.replace("@BLIS_DIR@", str(blis_dir))
    script_content = script_content.replace("@THREADS_ARRAY@", threads_array)
    script_content = script_content.replace("@LO_ARRAY@", lo_array)
    script_content = script_content.replace("@HI_ARRAY@", hi_array)
    script_content = script_content.replace("@STEP_ARRAY@", step_array)
    script_content = script_content.replace("@MACHINE@", config["machine"])
    script_content = script_content.replace("@CONFIG@", config["config"])
    script_content = script_content.replace("@DB_FILE@", str(db_file))
    script_content = script_content.replace("@GIT_COMMIT@", commit_hash)
    script_content = script_content.replace("@SCRIPTS_DIR@", str(scripts_dir))

    # Substitute optional variables
    for var in substitution_vars.keys():
        script_content = script_content.replace(f"@{var.upper()}@", str(config[var]))

    # Write runjob.sh
    runjob_file = job_dir / "runjob.sh"
    try:
        with open(runjob_file, "w") as f:
            f.write(script_content)
        # Make executable
        runjob_file.chmod(0o755)
        print(f"  ✓ Generated batch script: {runjob_file}")
        return job_dir
    except Exception as e:
        print(f"  Error writing batch script: {e}")
        return None


def process_git_ref(git_ref, config, args, build_dir, user_comment):
    """
    Process a single git reference: clone, build, and generate batch script.

    Args:
        git_ref (str): Git reference to process
        config (dict): Configuration dictionary
        args (argparse.Namespace): Command line arguments
        build_dir (Path): Build directory to use
        user_comment (str): User-defined metadata comment

    Returns:
        bool: True if successful, False otherwise
    """
    print(f"\n{'=' * 60}")
    print(f"Processing: {git_ref}")
    print(f"{'=' * 60}\n")

    # Validate and resolve git reference
    print(f"Validating git reference: {git_ref}")
    commit_hash = validate_git_ref(git_ref)
    if not commit_hash:
        return False

    git_tag = get_git_tag_for_commit(commit_hash)
    print(f"  Commit hash: {commit_hash}")
    print(f"  Tag/Branch: {git_tag}")

    print("\nBuilding BLIS and preparing test environment")
    print(f"{'=' * 40}\n")

    # Clone BLIS repository into commit-specific build directory
    commit_build_dir = build_dir / commit_hash

    print(f"  Build directory: {commit_build_dir}\n")

    blis_repo_dir = clone_blis_repository(commit_build_dir)
    if not blis_repo_dir:
        print("Error: Failed to clone BLIS repository")
        return False

    # Checkout requested git reference
    print()
    if not checkout_git_ref(blis_repo_dir, git_ref):
        print("Error: Failed to checkout git reference")
        return False

    # Configure BLIS
    print()
    if not configure_blis(blis_repo_dir, config["config"]):
        print("Error: BLIS configuration failed")
        return False

    # Build BLIS and generate test executable
    print()
    test_exec = build_blis(blis_repo_dir, jobs=args.jobs)
    if not test_exec:
        print("Error: BLIS build failed or test executable not created")
        return False

    # Create job directory and generate batch script
    print()
    job_dir = create_job_directory(commit_hash, config, blis_repo_dir)
    if not job_dir:
        print("Error: Failed to create job directory or generate batch script")
        return False

    print("\nConfiguration Summary")
    print(f"{'=' * 40}")
    print(f"  Git reference: {git_ref}")
    print(f"  Resolved commit: {commit_hash}")
    print(f"  Machine: {config['machine']}")
    print(f"  Config name: {config['config']}")
    if user_comment:
        print(f"  User metadata: {user_comment}")

    print("\nNext Steps")
    print(f"{'=' * 40}")
    print(f"  Batch script created: {job_dir}/runjob.sh")
    print()
    print("  To run the performance collection:")
    print(f"    cd {job_dir}")
    print("    ./runjob.sh")
    print()
    print("  Or submit to SLURM:")
    print(f"    sbatch {job_dir}/runjob.sh")

    return True


def main():
    """Main entry point."""
    args = parse_arguments()

    print(f"\n{'=' * 60}")
    print("BLIS Performance Data Collector")
    print(f"{'=' * 60}\n")

    # Read and parse configuration
    print("Reading configuration...")
    config = read_config_file(args.config_file)
    print(f"  Machine: {config['machine']}")
    print(f"  Config: {config['config']}")
    print(f"  Thread counts: {config['threads']}")
    print(
        f"  Matrix size range (lo-hi-step): {config['lo']}-{config['hi']}-{config['step']}"
    )

    # Extract user-defined keys
    user_comment = extract_user_defined_keys(config)
    if user_comment:
        print(f"  User-defined metadata: {user_comment}")

    # Create a temporary build directory
    build_dir = Path.cwd() / "blis_build"

    # Process each git reference
    print(f"\n{'=' * 60}")
    print(f"Processing {len(args.git_refs)} git reference(s)")
    print(f"{'=' * 60}")

    failed_refs = []
    successful_refs = []

    for git_ref in args.git_refs:
        if process_git_ref(git_ref, config, args, build_dir, user_comment):
            successful_refs.append(git_ref)
        else:
            failed_refs.append(git_ref)

    # Print summary
    print(f"\n{'=' * 60}")
    print("Summary")
    print(f"{'=' * 60}")
    print(f"  Successful: {len(successful_refs)}")
    for ref in successful_refs:
        print(f"    ✓ {ref}")
    if failed_refs:
        print(f"  Failed: {len(failed_refs)}")
        for ref in failed_refs:
            print(f"    ✗ {ref}")
        sys.exit(1)

    print(f"\n  Timestamp: {datetime.now().isoformat()}")
    print()


if __name__ == "__main__":
    main()
