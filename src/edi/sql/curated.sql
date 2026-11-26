-- Curated layer. Executed by edi.pipeline with integer parameters substituted:
--   {n_days} number of days in the panel, {lo} and {hi} 1-based inclusive list bounds of the
--   stock-count hour window (hours 6..21 -> 7..22).

CREATE OR REPLACE TABLE series_dim AS
SELECT
  series_id,
  any_value(store_id)            AS store_id,
  any_value(product_id)          AS product_id,
  any_value(city_id)             AS city_id,
  any_value(management_group_id) AS management_group_id,
  any_value(first_category_id)   AS first_category_id,
  any_value(second_category_id)  AS second_category_id,
  any_value(third_category_id)   AS third_category_id,
  count(*)                       AS n_rows,
  avg(sale_amount)               AS mean_sales,
  avg(CASE WHEN stock_hour6_22_cnt > 0 THEN 1.0 ELSE 0.0 END) AS stockout_day_share
FROM staged
GROUP BY series_id;

CREATE OR REPLACE TABLE calendar AS
SELECT day_index, any_value(dt) AS dt, max(holiday_flag) AS holiday_flag
FROM staged
GROUP BY day_index;

CREATE OR REPLACE TABLE series_day AS
WITH grid AS (
  SELECT s.series_id, CAST(r.range AS INTEGER) AS day_index
  FROM series_dim s CROSS JOIN range(1, {n_days} + 1) r
)
SELECT
  g.series_id,
  g.day_index,
  c.dt,
  CAST(st.series_id IS NULL AS INTEGER)                        AS is_missing,
  st.sale_amount,
  st.hours_sale,
  st.hours_stock_status,
  list_sum(list_slice(st.hours_stock_status, {lo}, {hi}))      AS stockout_hours,
  coalesce(st.discount, 1.0)                                   AS discount,
  coalesce(st.discount_imputed, 0)                             AS discount_imputed,
  coalesce(st.activity_flag, 0)                                AS activity_flag,
  coalesce(c.holiday_flag, 0)                                  AS holiday_flag,
  st.precpt,
  st.avg_temperature,
  st.avg_humidity,
  st.avg_wind_level,
  st.split
FROM grid g
LEFT JOIN staged st USING (series_id, day_index)
LEFT JOIN calendar c USING (day_index)
ORDER BY g.series_id, g.day_index;

-- Summary view used by the data-reliability page.
CREATE OR REPLACE VIEW dq_daily_summary AS
SELECT
  day_index,
  any_value(dt)                                         AS dt,
  count(*)                                              AS series,
  sum(is_missing)                                       AS missing_rows,
  avg(CASE WHEN stockout_hours > 0 THEN 1.0 ELSE 0.0 END) AS stockout_share,
  sum(sale_amount)                                      AS total_sales
FROM series_day
GROUP BY day_index
ORDER BY day_index;
