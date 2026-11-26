# ADR-0005: Feature availability at decision time

Status: accepted (2026-11-25)

Context. FreshRetailNet-50K weather fields are same-day observations. Discounts and activity flags describe the sales day.

Decision. Weather enters only as trailing means ending at the forecast origin. Discount, activity and holiday flags for the target day are treated as known one day ahead (planned promotions and calendars). Target-day sales, stock flags and hourly data are never used.

Reasons. Promotions in grocery retail are typically planned in advance; same-day weather is not known when a next-day order is placed.

Trade-offs. If promotions are not actually known ahead, forecasts are optimistic. The ablation `no_promo_features` quantifies the dependence.

Validation. `tests/test_forecasting.py::test_no_future_leakage` perturbs every target-day and future value not on the allow-list and asserts identical features.
