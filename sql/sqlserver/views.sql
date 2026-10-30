-- Views for Power BI. Run once after schema.sql. (CREATE OR ALTER needs SQL Server 2016 SP1+)
USE spend_db;
GO
CREATE OR ALTER VIEW dbo.vw_spend_by_category AS
SELECT category, COUNT(*) AS invoices, SUM(amount_inr) AS spend_inr FROM dbo.spend GROUP BY category;
GO
CREATE OR ALTER VIEW dbo.vw_monthly_spend AS
SELECT CONVERT(CHAR(7), invoice_date, 120) AS month_key, MIN(invoice_date) AS month_start, SUM(amount_inr) AS spend_inr, COUNT(*) AS invoices
FROM dbo.spend GROUP BY CONVERT(CHAR(7), invoice_date, 120);
GO
CREATE OR ALTER VIEW dbo.vw_vendor_summary AS
SELECT vendor_clean, SUM(amount_inr) AS spend_inr, COUNT(*) AS invoices,
       RANK() OVER (ORDER BY SUM(amount_inr) DESC) AS spend_rank
FROM dbo.spend GROUP BY vendor_clean;
GO
CREATE OR ALTER VIEW dbo.vw_maverick_spend AS
SELECT COALESCE(cost_center,'UNKNOWN') AS cost_center, SUM(amount_inr) AS total_spend,
       SUM(CASE WHEN po_number IS NULL THEN amount_inr ELSE 0 END) AS spend_without_po
FROM dbo.spend GROUP BY COALESCE(cost_center,'UNKNOWN');
GO
