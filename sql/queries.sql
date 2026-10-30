-- name: spend_by_category
SELECT category, COUNT(*) AS invoices, ROUND(SUM(amount_inr),0) AS spend_inr,
       ROUND(100.0*SUM(amount_inr)/SUM(SUM(amount_inr)) OVER (),1) AS pct_of_total
FROM spend GROUP BY category ORDER BY spend_inr DESC;

-- name: monthly_trend_mom
WITH m AS (SELECT strftime('%Y-%m', invoice_date) AS month, SUM(amount_inr) AS spend FROM spend GROUP BY 1)
SELECT month, ROUND(spend,0) AS spend_inr,
       ROUND(100.0*(spend - LAG(spend) OVER (ORDER BY month)) / LAG(spend) OVER (ORDER BY month),1) AS mom_pct,
       ROUND(AVG(spend) OVER (ORDER BY month ROWS BETWEEN 2 PRECEDING AND CURRENT ROW),0) AS rolling_3m_avg
FROM m ORDER BY month;

-- name: vendor_pareto
WITH v AS (SELECT vendor_clean, SUM(amount_inr) AS spend FROM spend GROUP BY 1)
SELECT vendor_clean, ROUND(spend,0) AS spend_inr,
       ROUND(100.0*SUM(spend) OVER (ORDER BY spend DESC) / SUM(spend) OVER (),1) AS cumulative_pct
FROM v ORDER BY spend DESC LIMIT 15;

-- name: maverick_spend_by_cost_center
SELECT COALESCE(cost_center,'UNKNOWN') AS cost_center,
       ROUND(SUM(CASE WHEN po_number IS NULL THEN amount_inr END),0) AS spend_without_po,
       ROUND(100.0*SUM(CASE WHEN po_number IS NULL THEN amount_inr END)/SUM(amount_inr),1) AS pct_without_po
FROM spend GROUP BY 1 ORDER BY spend_without_po DESC;

-- name: vendors_in_multiple_categories
SELECT vendor_clean, COUNT(DISTINCT category) AS n_categories, GROUP_CONCAT(DISTINCT category) AS categories
FROM spend GROUP BY 1 HAVING COUNT(DISTINCT category) > 1 ORDER BY n_categories DESC;

-- name: possible_duplicate_payments_same_vendor_amount_30d
SELECT a.invoice_id AS inv_a, b.invoice_id AS inv_b, a.vendor_clean, a.amount_inr, a.invoice_date AS date_a, b.invoice_date AS date_b
FROM spend a JOIN spend b ON a.vendor_clean=b.vendor_clean AND a.amount_inr=b.amount_inr
 AND a.invoice_id < b.invoice_id AND ABS(julianday(a.invoice_date)-julianday(b.invoice_date)) <= 30;

-- name: tail_spend
WITH v AS (SELECT vendor_clean, SUM(amount_inr) s FROM spend GROUP BY 1),
r AS (SELECT vendor_clean, s, SUM(s) OVER (ORDER BY s DESC) / SUM(s) OVER () AS cum FROM v)
SELECT COUNT(*) AS tail_vendors, ROUND(SUM(s),0) AS tail_spend_inr FROM r WHERE cum > 0.8;
