-- SQL Server 2017+ (Express / Developer)  |  Run ONCE in SSMS. Run each block (GO separates batches) or press Execute for the whole file.
IF DB_ID('spend_db') IS NULL CREATE DATABASE spend_db;
GO
USE spend_db;
GO
IF OBJECT_ID('dbo.spend', 'U') IS NOT NULL DROP TABLE dbo.spend;
GO
CREATE TABLE dbo.spend (
    invoice_id      VARCHAR(20)    NOT NULL PRIMARY KEY,
    invoice_date    DATE           NOT NULL,
    vendor_raw      NVARCHAR(150)  NULL,
    vendor_clean    NVARCHAR(150)  NULL,
    description     NVARCHAR(250)  NULL,
    amount_inr      DECIMAL(16,2)  NOT NULL,
    cost_center     VARCHAR(20)    NULL,
    po_number       VARCHAR(20)    NULL,
    has_po          CHAR(1)        NULL,
    payment_terms   VARCHAR(10)    NULL,
    erp_category    VARCHAR(40)    NULL,
    category        VARCHAR(40)    NULL,
    class_source    VARCHAR(20)    NULL,
    confidence      DECIMAL(5,3)   NULL,
    miscoding_flag  BIT            NULL
);
GO
CREATE INDEX idx_date     ON dbo.spend (invoice_date);
CREATE INDEX idx_category ON dbo.spend (category);
CREATE INDEX idx_vendor   ON dbo.spend (vendor_clean);
GO
SELECT COUNT(*) FROM spend;
SELECT COUNT(*) AS rows_loaded, SUM(amount_inr) AS total_spend FROM spend;