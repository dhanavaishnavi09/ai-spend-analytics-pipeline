-- SQL Server 2017+ (T-SQL)
USE spend_db;
GO

-- 1. spend by category
SELECT category, COUNT(*) AS invoices, ROUND(SUM(amount_inr),0) AS spend_inr,
       ROUND(100.0*SUM(amount_inr)/SUM(SUM(amount_inr)) OVER (),1) AS pct_of_total
FROM spend GROUP BY category ORDER BY spend_inr DESC;

-- 2. monthly trend, month-over-month %, 3-month rolling average
WITH m AS (SELECT CONVERT(CHAR(7), invoice_date, 120) AS month_key, SUM(amount_inr) AS spend FROM spend GROUP BY CONVERT(CHAR(7), invoice_date, 120))
SELECT month_key, ROUND(spend,0) AS spend_inr,
       ROUND(100.0*(spend - LAG(spend) OVER (ORDER BY month_key)) / LAG(spend) OVER (ORDER BY month_key),1) AS mom_pct,
       ROUND(AVG(spend) OVER (ORDER BY month_key ROWS BETWEEN 2 PRECEDING AND CURRENT ROW),0) AS rolling_3m_avg
FROM m ORDER BY month_key;

-- 3. vendor Pareto (cumulative % of spend)
WITH v AS (SELECT vendor_clean, SUM(amount_inr) AS spend FROM spend GROUP BY vendor_clean)
SELECT TOP 15 vendor_clean, ROUND(spend,0) AS spend_inr,
       ROUND(100.0*SUM(spend) OVER (ORDER BY spend DESC) / SUM(spend) OVER (),1) AS cumulative_pct
FROM v ORDER BY spend DESC;

-- 4. maverick (no-PO) spend by cost centre
SELECT COALESCE(cost_center,'UNKNOWN') AS cost_center,
       ROUND(SUM(CASE WHEN po_number IS NULL THEN amount_inr END),0) AS spend_without_po,
       ROUND(100.0*SUM(CASE WHEN po_number IS NULL THEN amount_inr END)/SUM(amount_inr),1) AS pct_without_po
FROM spend GROUP BY COALESCE(cost_center,'UNKNOWN') ORDER BY spend_without_po DESC;

-- 5. vendors that appear in more than one category (STRING_AGG has no DISTINCT, so de-duplicate first)
WITH vc AS (SELECT vendor_clean, category FROM spend GROUP BY vendor_clean, category)
SELECT vendor_clean, COUNT(*) AS n_categories, STRING_AGG(category, ', ') AS categories
FROM vc GROUP BY vendor_clean HAVING COUNT(*) > 1 ORDER BY n_categories DESC;

-- 6. possible duplicate payments: same vendor + amount within 30 days
SELECT a.invoice_id AS inv_a, b.invoice_id AS inv_b, a.vendor_clean, a.amount_inr, a.invoice_date AS date_a, b.invoice_date AS date_b
FROM spend a JOIN spend b ON a.vendor_clean = b.vendor_clean AND a.amount_inr = b.amount_inr
 AND a.invoice_id < b.invoice_id AND ABS(DATEDIFF(day, a.invoice_date, b.invoice_date)) <= 30;

-- 7. tail spend: vendors that make up the last 20% of spend
WITH v AS (SELECT vendor_clean, SUM(amount_inr) AS s FROM spend GROUP BY vendor_clean),
r AS (SELECT vendor_clean, s, SUM(s) OVER (ORDER BY s DESC) / SUM(s) OVER () AS cum FROM v)
SELECT COUNT(*) AS tail_vendors, ROUND(SUM(s),0) AS tail_spend_inr FROM r WHERE cum > 0.8;
