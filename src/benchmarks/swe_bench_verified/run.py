"""SWE-Bench-Verified runner - main entry point.

Example usage:

# Run a single instance
python src/benchmarks/swe_bench_verified/run.py \
    --instance-ids django__django-15280 \
    --model claude-opus-4-6 \
    --dashboard \
    --save-logs \
    --max-parallel 8 \
    --output-dir outputs/debug2

# Run a dataset subset in parallel
python src/benchmarks/swe_bench_verified/run.py \
    --dataset jerry128/SWE-bench_Verified_subset_0 \
    --model claude-opus-4-6 \
    --max-parallel 8 \
    --no-exclude \
    --dashboard \
    --save-logs \
    --output-dir outputs/swe_bench_results

# Submit predictions for evaluation
sb-cli submit swe-bench_verified test \
    --predictions_path outputs/swe_bench_results/predictions.jsonl \
    --run_id my-run-id

sb-cli list-runs swe-bench_verified test
sb-cli get-report swe-bench_verified test my-run-id -o ./reports
"""

import atexit
import signal
import socket
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List, Optional

from datasets import load_dataset

from benchmarks.swe_bench_verified.config import (InstanceResult,
                                                  load_excluded_instances,
                                                  parse_args)
from benchmarks.swe_bench_verified.docker_exec_client import DockerExecClient
from benchmarks.swe_bench_verified.instance import (run_instance,
                                                    save_patch_to_jsonl)
from harness.agent import AgentSPEX

# Global dashboard process for signal handler access
_dashboard_proc: Optional[subprocess.Popen] = None
_dashboard_keep: bool = False


UNSAFE_PORTS = {
    5060,  # SIP
    5061,  # SIP-TLS
    6000,  # X11
    6566,  # SANE
    6665,
    6666,
    6667,
    6668,
    6669,  # IRC
}


def find_available_port(start_port: int) -> int:
    """Find an available port starting from start_port.

    Mimics the logic in run_agent.sh that finds the next available port.
    Skips ports that browsers block for security reasons.
    """
    port = start_port
    while port < start_port + 100:  # Try up to 100 ports
        if port in UNSAFE_PORTS:
            port += 1
            continue
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                port += 1
    # Fall back to original port if all are in use
    return start_port


def cleanup_dashboard() -> None:
    """Clean up dashboard process gracefully.

    Mimics the cleanup() function in run_agent.sh:
    - Check if process is still running
    - Send SIGTERM
    - Wait for process to exit
    """
    global _dashboard_proc
    if _dashboard_proc is None:
        return
    if _dashboard_keep:
        return

    try:
        # Check if process is still running (like kill -0 in bash)
        if _dashboard_proc.poll() is None:
            _dashboard_proc.terminate()
            try:
                # Wait for process to exit (like wait in bash)
                _dashboard_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                # Force kill if it doesn't respond to SIGTERM
                _dashboard_proc.kill()
                _dashboard_proc.wait()
    except Exception:
        pass
    finally:
        _dashboard_proc = None


def _signal_handler(signum, frame):
    """Handle SIGINT/SIGTERM for graceful shutdown."""
    cleanup_dashboard()
    sys.exit(0)


def main():
    """Main entry point for the SWE-Bench runner."""
    global _dashboard_proc, _dashboard_keep

    args = parse_args()
    _dashboard_keep = args.dashboard_keep

    # Set up signal handlers for graceful shutdown (like trap in bash)
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    # Register cleanup on normal exit
    atexit.register(cleanup_dashboard)

    try:
        if args.dashboard:
            _dashboard_proc = start_dashboard(args)

        run_full_pipeline(args)
    finally:
        cleanup_dashboard()


def run_full_pipeline(args):
    """Run the full SWE-Bench pipeline: process instances and optionally evaluate."""
    print(f"Loading dataset {args.dataset} (split: {args.split})...")
    dataset = load_dataset(args.dataset, split=args.split)

    if args.instance_ids:
        print(f"Filtering dataset for instance IDs: {args.instance_ids}")
        filtered_indices = []
        for i, instance in enumerate(dataset):
            if instance["instance_id"] in args.instance_ids:
                filtered_indices.append(i)

        if not filtered_indices:
            print(f"Error: None of the specified instance IDs found in dataset")
            print(
                f"Available instances: {[inst['instance_id'] for inst in dataset[:5]]}..."
            )
            sys.exit(1)

        dataset = dataset.select(filtered_indices)
        print(f"Found {len(dataset)} matching task(s)")

    # Filter out excluded instances (unless --no-exclude is set)
    if not args.no_exclude:
        excluded = load_excluded_instances(args.exclude_file)
        if excluded:
            filtered_indices = []
            excluded_ids = []
            for i, instance in enumerate(dataset):
                if instance["instance_id"] not in excluded:
                    filtered_indices.append(i)
                else:
                    excluded_ids.append(instance["instance_id"])

            if filtered_indices:
                dataset = dataset.select(filtered_indices)
            if excluded_ids:
                print(
                    f"Excluded {len(excluded_ids)} instance(s) from {args.exclude_file}"
                )

    # Apply limit if specified
    if args.limit and args.limit < len(dataset):
        dataset = dataset.select(range(args.limit))
        print(f"Limited to first {args.limit} instance(s)")

    print(f"\n{len(dataset)} task(s) to process")
    if args.max_parallel > 1:
        print(f"Running with max {args.max_parallel} parallel instances")

    # Create output directory
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    def process_single_instance(instance_data: tuple) -> InstanceResult:
        """Process a single instance. Used by ThreadPoolExecutor."""
        idx, total, instance = instance_data
        instance_id = instance["instance_id"]

        print(f"\n{'='*80}")
        print(f"[{idx}/{total}] Starting: {instance_id}")
        print(f"{'='*80}")

        docker_client = None

        try:
            image = DockerExecClient.resolve_image_name(instance_id)
            print(f"[{instance_id}] Starting SWE-bench container: {image}")
            docker_client = DockerExecClient(image=image)
            agent = AgentSPEX(mcp_client=docker_client)

            result = run_instance(
                instance,
                agent,
                agent.mcp_client,
                args,
                output_dir,
                save_logs=args.save_logs,
            )
            print(f"[{instance_id}] Completed successfully")
            return result
        except Exception as e:
            print(f"[{instance_id}] Error: {e}")
            return InstanceResult(
                instance_id=instance_id,
                success=False,
                error=str(e),
            )
        finally:
            if docker_client is not None:
                docker_client.close()

    # Prepare instance data with index info
    instance_data_list = [
        (i + 1, len(dataset), instance) for i, instance in enumerate(dataset)
    ]

    # Process instances (parallel or sequential based on max_parallel)
    results: List[InstanceResult] = []
    if args.max_parallel > 1:
        # Parallel execution
        with ThreadPoolExecutor(max_workers=args.max_parallel) as executor:
            future_to_instance = {
                executor.submit(process_single_instance, data): data[2]["instance_id"]
                for data in instance_data_list
            }

            for future in as_completed(future_to_instance):
                instance_id = future_to_instance[future]
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    print(f"[{instance_id}] Unexpected error: {e}")
                    results.append(
                        InstanceResult(
                            instance_id=instance_id,
                            success=False,
                            error=str(e),
                        )
                    )
    else:
        # Sequential execution
        for data in instance_data_list:
            result = process_single_instance(data)
            results.append(result)

    # Save all patches to JSONL format
    predictions_file = output_dir / "predictions.jsonl"

    # Clear predictions file if it exists (avoid duplicates from reruns)
    if predictions_file.exists():
        predictions_file.unlink()

    print(f"\n{'='*80}")
    print(f"Saving predictions to {predictions_file}")
    print(f"{'='*80}\n")

    for result in results:
        if result.success:
            save_patch_to_jsonl(
                result.instance_id, result.patch, args.model, predictions_file
            )

    # Print summary
    successful = sum(1 for r in results if r.success)
    failed = len(results) - successful
    print(f"\n{'='*80}")
    print(
        f"Run complete: {successful}/{len(results)} patches generated successfully"
        + (f" ({failed} failed)" if failed else "")
    )
    print(f"Predictions: {predictions_file}")
    print(f"\nTo evaluate with sb-cli:")
    print(f"  sb-cli submit swe-bench_verified test \\")
    print(f"      --predictions_path {predictions_file.resolve()} \\")
    print(f"      --run_id <your-run-id>")
    print(f"  sb-cli get-report swe-bench_verified test <your-run-id> -o ./reports")
    print(f"{'='*80}\n")


def start_dashboard(args) -> subprocess.Popen:
    """Start dashboard pointing at output directory logs.

    Finds an available port starting from args.dashboard_port,
    similar to the logic in run_agent.sh.
    """
    repo_root = Path(__file__).resolve().parents[3]
    log_root = Path(args.output_dir).resolve()
    log_root.mkdir(parents=True, exist_ok=True)
    script_path = repo_root / "scripts" / "dashboard.py"

    requested_port = args.dashboard_port
    if requested_port in UNSAFE_PORTS:
        print(
            f"Warning: Port {requested_port} is blocked by browsers (ERR_UNSAFE_PORT)"
        )
    port = find_available_port(requested_port)
    if port != requested_port:
        print(f"Port {requested_port} unavailable, using port {port}")

    cmd = [
        sys.executable,
        str(script_path),
        "--log-root",
        str(log_root),
        "--port",
        str(port),
        "--no-auto-close",
    ]

    # For single-instance runs, pre-select the log file directly.
    # LogSession polls for the file even before it exists, so this works
    # even though the agent hasn't started yet when the dashboard launches.
    if args.instance_ids and len(args.instance_ids) == 1:
        log_file = log_root / f"{args.instance_ids[0]}_agent_events.log"
        cmd.append(str(log_file))

    if args.dashboard_no_browser:
        cmd.append("--no-browser")
    print(f"Starting dashboard: {' '.join(cmd)}")
    print(f"Dashboard: http://127.0.0.1:{port}")
    return subprocess.Popen(cmd)


if __name__ == "__main__":
    main()
