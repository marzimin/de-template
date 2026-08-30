"""One-time (and re-runnable) generator for the demo Excel data on local disk.

Produces one example of each file kind that
``extractors/files/local_excel.py`` knows how to tell apart — static seed
workbooks, an overwritten ``latest_orders.xlsx`` snapshot, an appended-to
``customers.xlsx``, and one ``monthly_sales_YYYY-MM-DD.xlsx`` per month (see
that module's docstring for what each means). The actual generation is in
``scripts/demo_dataset.py`` — **that's the file to replace with your own fake
data**; this one is just the CLI wrapper and does not need to change when you
do. See ``scripts/demo_dataset.py``'s docstring for the checklist.

Nothing in ``.env`` is required to run this: the destination is a
project-relative path from ``cfg/config.yaml``'s ``local_dummy_data`` section,
not a secret. Use this to exercise the pipeline end to end
(extract → load → dbt → export) with no external service involved — local
development, tests, or CI. See ``docs/pipelines.md#local-dummy-data`` for the
full picture, including what this demo data does and does not prove.

    python -m scripts.seed_local_dummy_data
"""

import argparse
import sys

import structlog

from core.config import resolve_project_path
from core.local_files import DEFAULT_FOLDER_PATH, LocalFolderClient, default_folder_path
from scripts.demo_dataset import seed_all

log = structlog.get_logger()


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns the process exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--destination",
        default=None,
        help="Directory to write into, relative to the repository root. "
        "Defaults to local_dummy_data.destination in cfg/config.yaml.",
    )
    parser.add_argument(
        "--folder-path",
        default=None,
        help="Subfolder within the destination. Defaults to "
        f"local_dummy_data.folder_path (usually {DEFAULT_FOLDER_PATH!r}).",
    )
    parser.add_argument(
        "--latest-orders-rows",
        type=int,
        default=30,
        help="Order rows in this run's latest_orders.xlsx snapshot.",
    )
    parser.add_argument(
        "--customers-new-rows",
        type=int,
        default=10,
        help="New customer rows to append to customers.xlsx this run.",
    )
    parser.add_argument(
        "--monthly-sales-rows",
        type=int,
        default=50,
        help="Sales rows per monthly_sales_*.xlsx file.",
    )
    parser.add_argument(
        "--backfill-months",
        type=int,
        default=1,
        help="How many months of monthly_sales_*.xlsx history to ensure exist, "
        "counting the current month.",
    )
    parser.add_argument(
        "--skip-static",
        action="store_true",
        help="Skip the seed_*.xlsx reference files (they rarely need rewriting).",
    )
    args = parser.parse_args(argv)

    client = (
        LocalFolderClient(base_dir=resolve_project_path(args.destination))
        if args.destination
        else LocalFolderClient.from_config()
    )
    folder_path = args.folder_path or default_folder_path()

    uploaded = seed_all(
        client,
        folder_path,
        latest_orders_rows=args.latest_orders_rows,
        customers_new_rows=args.customers_new_rows,
        monthly_sales_rows=args.monthly_sales_rows,
        backfill_months=args.backfill_months,
        skip_static=args.skip_static,
    )

    log.info("seed_complete", folder_path=folder_path, files=len(uploaded))
    return 0


if __name__ == "__main__":
    sys.exit(main())
