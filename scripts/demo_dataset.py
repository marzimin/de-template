"""The demo dataset this template ships with. Replace this file with your own.

Everything here is specific to the worked example: fake orders, customers,
product categories, regions, and monthly sales — matching the four extractor
classes in ``extractors/files/local_excel.py`` (``LocalSeedExtractor``,
``LocalLatestOrdersExtractor``, ``LocalCustomersExtractor``,
``LocalMonthlySalesExtractor``) and the ``local_*`` sources in
``cfg/config.yaml`` that read them back.

None of the *mechanics* live here — ``scripts/seed_toolkit.py`` has those,
and stays as-is when you swap this file out. To replace the demo data with
your own:

1. Decide what your fake entities are, and which of the four kinds each one
   is — seed / overwritten snapshot / appended snapshot / incremental
   partition series. See ``extractors/files/local_excel.py``'s module
   docstring for what each kind means and which ``load_mode`` it needs.
2. Write one ``write_*`` call per entity in :func:`seed_all` below, using
   ``scripts/seed_toolkit.py``'s primitives — the four below are the
   worked pattern for each kind.
3. Add a matching extractor class to ``extractors/files/local_excel.py``
   (copy one of the four there — they're a few lines each) and a matching
   ``local_*`` source to ``cfg/config.yaml``.
4. Add the new raw table to ``dbt/models/staging/sources.yml`` and write its
   staging model.

``scripts/seed_local_dummy_data.py`` just calls :func:`seed_all` below —
nothing there needs to change when you replace this file's contents.
"""

import random
import re
import time
from datetime import date
from typing import Any

from core.local_files import LocalFolderClient
from scripts.seed_toolkit import (
    write_appended_snapshot,
    write_incremental_partitions,
    write_overwritten_snapshot,
    write_static_workbook,
)

CATEGORIES = ["hardware", "software", "services", "supplies"]
REGIONS = ["north", "south", "east", "west"]

SEED_WORKBOOKS = {
    "seed_categories.xlsx": (
        ["category_id", "category_name"],
        [[i + 1, name] for i, name in enumerate(CATEGORIES)],
    ),
    "seed_regions.xlsx": (
        ["region_id", "region_name"],
        [[i + 1, name] for i, name in enumerate(REGIONS)],
    ),
}

ORDERS_HEADER = ["order_id", "customer_name", "category", "amount", "order_date"]
CUSTOMERS_HEADER = ["customer_id", "customer_name", "region", "signup_date"]
CUSTOMER_ID_PATTERN = re.compile(r"CUST-(\d+)")
MONTHLY_SALES_HEADER = ["sale_id", "category", "amount", "sale_date"]


def _latest_orders_row_builder() -> Any:
    """Build order rows against one RNG shared across the whole snapshot."""
    rng = random.Random()

    def build(i: int) -> list[Any]:
        return [
            f"ORD-{int(time.time())}-{i:04d}",
            f"Customer {rng.randint(1, 200)}",
            rng.choice(CATEGORIES),
            round(rng.uniform(10, 5000), 2),
            date.today().isoformat(),
        ]

    return build


def _next_customer_id(existing_rows: list[list[Any]]) -> int:
    """Continue the ``CUST-NNNNN`` sequence from whatever's already in the file."""
    existing_ids = [
        int(match.group(1))
        for row in existing_rows
        if row and (match := CUSTOMER_ID_PATTERN.fullmatch(str(row[0])))
    ]
    return max(existing_ids, default=0) + 1


def _customer_row_builder() -> Any:
    """Build customer rows against one RNG shared across the batch being appended."""
    rng = random.Random()

    def build(customer_id: int) -> list[Any]:
        return [
            f"CUST-{customer_id:05d}",
            f"Customer {customer_id}",
            rng.choice(REGIONS),
            date.today().isoformat(),
        ]

    return build


def _monthly_sales_row_builder(period: date) -> Any:
    """Build sale rows for one month, deterministic per month but varying per row."""
    rng = random.Random(f"{period:%Y-%m}")

    def build(i: int) -> list[Any]:
        return [
            f"SALE-{period:%Y%m}-{i:04d}",
            rng.choice(CATEGORIES),
            round(rng.uniform(10, 5000), 2),
            period.isoformat(),
        ]

    return build


def seed_all(
    client: LocalFolderClient,
    folder_path: str,
    *,
    latest_orders_rows: int = 30,
    customers_new_rows: int = 10,
    monthly_sales_rows: int = 50,
    backfill_months: int = 1,
    skip_static: bool = False,
) -> list[str]:
    """Write one example of each of the four demo file kinds.

    The single entry point ``scripts/seed_local_dummy_data.py`` calls — see
    its ``main()`` for the argument parsing this wraps.

    Args:
        client: Where to write the workbooks.
        folder_path: Destination folder, relative to the store root.
        latest_orders_rows: Order rows in this run's ``latest_orders.xlsx``.
        customers_new_rows: New customer rows to append this run.
        monthly_sales_rows: Sales rows per ``monthly_sales_*.xlsx`` file.
        backfill_months: How many months of ``monthly_sales_*.xlsx`` history
            to ensure exist, counting the current month.
        skip_static: Skip the ``seed_*.xlsx`` reference files.

    Returns:
        Every file name written this run.
    """
    uploaded: list[str] = []

    if not skip_static:
        for file_name, (header, rows) in SEED_WORKBOOKS.items():
            uploaded.append(
                write_static_workbook(client, folder_path, file_name, header, rows)
            )

    uploaded.append(
        write_overwritten_snapshot(
            client,
            folder_path,
            "latest_orders.xlsx",
            ORDERS_HEADER,
            row_builder=_latest_orders_row_builder(),
            count=latest_orders_rows,
        )
    )

    uploaded.append(
        write_appended_snapshot(
            client,
            folder_path,
            "customers.xlsx",
            CUSTOMERS_HEADER,
            next_id=_next_customer_id,
            row_builder=_customer_row_builder(),
            new_count=customers_new_rows,
        )
    )

    uploaded += write_incremental_partitions(
        client,
        folder_path,
        MONTHLY_SALES_HEADER,
        file_name_for=lambda period: f"monthly_sales_{period.isoformat()}.xlsx",
        row_builder_for=_monthly_sales_row_builder,
        rows_per_partition=monthly_sales_rows,
        backfill_months=backfill_months,
    )

    return uploaded
