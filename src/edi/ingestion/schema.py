"""FreshRetailNet-50K schema as published on the dataset card (19 fields)."""

from __future__ import annotations

HOURS = 24
# Hours counted by `stock_hour6_22_cnt`. The card does not define the boundary; 06:00 to 22:00
# is read as hour slots 6..21. data_quality checks both conventions on real data.
STOCK_COUNT_HOURS = range(6, 22)

ID_COLUMNS = [
    "city_id",
    "store_id",
    "management_group_id",
    "first_category_id",
    "second_category_id",
    "third_category_id",
    "product_id",
]

FRN_COLUMNS: dict[str, str] = {
    "city_id": "int64",
    "store_id": "int64",
    "management_group_id": "int64",
    "first_category_id": "int64",
    "second_category_id": "int64",
    "third_category_id": "int64",
    "product_id": "int64",
    "dt": "string",
    "sale_amount": "float64",
    "hours_sale": "list<float64>[24]",
    "stock_hour6_22_cnt": "int32",
    "hours_stock_status": "list<int32>[24]",
    "discount": "float64",
    "holiday_flag": "int32",
    "activity_flag": "int32",
    "precpt": "float64",
    "avg_temperature": "float64",
    "avg_humidity": "float64",
    "avg_wind_level": "float64",
}

PRIMARY_KEY = ["store_id", "product_id", "dt"]

# Columns added during standardization.
STANDARD_EXTRA = ["series_id", "day_index", "split", "ingested_at", "data_source"]

CATEGORY_PROFILES = ["leafy", "fruit", "dairy", "protein"]


def profile_for_category(first_category_id: int, ordered_ids: list[int]) -> str:
    """Deterministic mapping from a category id to an assumed economics profile.

    For the synthetic fixture ids 1..4 map directly. For real data the sorted distinct ids are
    assigned round-robin, which is an explicit assumption (real category semantics are encoded).
    """
    if first_category_id in (1, 2, 3, 4) and ordered_ids == [1, 2, 3, 4]:
        return CATEGORY_PROFILES[first_category_id - 1]
    idx = ordered_ids.index(first_category_id) if first_category_id in ordered_ids else 0
    return CATEGORY_PROFILES[idx % len(CATEGORY_PROFILES)]
