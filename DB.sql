-- =====================================================================================
-- ROYAL PRODUCTS: INVENTORY 
-- =====================================================================================

-- 1. DATABASE INITIALIZATION
CREATE DATABASE IF NOT EXISTS RoyalInventory;
USE RoyalInventory;


SET FOREIGN_KEY_CHECKS = 0;

-- Drop existing tables/routines if they exist 
DROP TABLE IF EXISTS OrderDetails, StockTransactions, Orders, Products, Customers, Suppliers, Categories;
DROP VIEW IF EXISTS AvailableProducts, LowStockProducts, SalesSummary;
DROP FUNCTION IF EXISTS GetStock;
DROP FUNCTION IF EXISTS TotalSales;
DROP PROCEDURE IF EXISTS AddProduct;
DROP PROCEDURE IF EXISTS UpdateStock;
DROP PROCEDURE IF EXISTS PlaceOrder;

SET FOREIGN_KEY_CHECKS = 1;

-- =====================================================================================
-- 2. TABLE CREATION (Ordered by Dependencies)
-- =====================================================================================

CREATE TABLE Categories (
    CategoryID INT AUTO_INCREMENT PRIMARY KEY,
    CategoryName VARCHAR(100) NOT NULL
);

CREATE TABLE Suppliers (
    SupplierID INT AUTO_INCREMENT PRIMARY KEY,
    SupplierName VARCHAR(100) NOT NULL,
    Phone VARCHAR(15),
    Email VARCHAR(100),
    Address VARCHAR(255)
);

CREATE TABLE Customers (
    CustomerID INT AUTO_INCREMENT PRIMARY KEY,
    CustomerName VARCHAR(100),
    Phone VARCHAR(15),
    Email VARCHAR(100)
);

CREATE TABLE Products (
    ProductID INT AUTO_INCREMENT PRIMARY KEY,
    ProductName VARCHAR(150) NOT NULL,
    CategoryID INT,
    SupplierID INT,
    UnitPrice DECIMAL(10,2),
    StockQuantity INT,
    ReorderLevel INT,
    FOREIGN KEY (CategoryID) REFERENCES Categories(CategoryID) ON DELETE SET NULL,
    FOREIGN KEY (SupplierID) REFERENCES Suppliers(SupplierID) ON DELETE SET NULL
);

CREATE TABLE Orders (
    OrderID INT AUTO_INCREMENT PRIMARY KEY,
    CustomerID INT,
    OrderDate DATE,
    TotalAmount DECIMAL(12,2),
    FOREIGN KEY (CustomerID) REFERENCES Customers(CustomerID) ON DELETE CASCADE
);

CREATE TABLE OrderDetails (
    OrderDetailID INT AUTO_INCREMENT PRIMARY KEY,
    OrderID INT,
    ProductID INT,
    Quantity INT,
    UnitPrice DECIMAL(10,2),
    FOREIGN KEY (OrderID) REFERENCES Orders(OrderID) ON DELETE CASCADE,
    FOREIGN KEY (ProductID) REFERENCES Products(ProductID) ON DELETE RESTRICT
);

CREATE TABLE StockTransactions (
    TransactionID INT AUTO_INCREMENT PRIMARY KEY,
    ProductID INT,
    TransactionType VARCHAR(20),
    Quantity INT,
    TransactionDate TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (ProductID) REFERENCES Products(ProductID) ON DELETE CASCADE
);

-- =====================================================================================
-- 3. PRODUCTION INDEXES (For Query Performance)
-- =====================================================================================

CREATE INDEX idx_products_category ON Products(CategoryID, UnitPrice);
CREATE INDEX idx_products_stock ON Products(StockQuantity, ReorderLevel);
CREATE INDEX idx_orders_customer_date ON Orders(CustomerID, OrderDate);
CREATE INDEX idx_transactions_product_date ON StockTransactions(ProductID, TransactionDate);

-- =====================================================================================
-- 4. VIEWS (Reporting & Monitoring)
-- =====================================================================================

CREATE VIEW AvailableProducts AS
SELECT ProductID, ProductName, StockQuantity, UnitPrice
FROM Products
WHERE StockQuantity > 0;

CREATE VIEW LowStockProducts AS
SELECT ProductID, ProductName, StockQuantity, ReorderLevel
FROM Products
WHERE StockQuantity <= ReorderLevel;

CREATE VIEW SalesSummary AS
SELECT O.OrderID, C.CustomerName, O.OrderDate, O.TotalAmount
FROM Orders O
JOIN Customers C ON O.CustomerID = C.CustomerID;

-- =====================================================================================
-- 5. TRIGGERS (Automated Data Integrity & Auditing)
-- =====================================================================================
DELIMITER $$

-- Prevent negative stock & automatically deduct inventory upon sale
CREATE TRIGGER trg_reduce_stock
BEFORE INSERT ON OrderDetails
FOR EACH ROW
BEGIN
    DECLARE v_current_stock INT;
    
    SELECT StockQuantity INTO v_current_stock 
    FROM Products 
    WHERE ProductID = NEW.ProductID;
    
    IF v_current_stock < NEW.Quantity THEN
        SIGNAL SQLSTATE '45000' 
        SET MESSAGE_TEXT = 'Operation Denied: Insufficient warehouse assets available.';
    ELSE
        UPDATE Products
        SET StockQuantity = StockQuantity - NEW.Quantity
        WHERE ProductID = NEW.ProductID;
    END IF;
END$$

-- Record an audit log only when stock values actually change
CREATE TRIGGER trg_stock_audit
AFTER UPDATE ON Products
FOR EACH ROW
BEGIN
    IF OLD.StockQuantity <> NEW.StockQuantity THEN
        INSERT INTO StockTransactions (ProductID, TransactionType, Quantity)
        VALUES (
            NEW.ProductID,
            IF(NEW.StockQuantity > OLD.StockQuantity, 'RESTOCK', 'DISPATCH'),
            ABS(NEW.StockQuantity - OLD.StockQuantity)
        );
    END IF;
END$$

-- =====================================================================================
-- 6. STORED PROCEDURES & FUNCTIONS (Business Logic)
-- =====================================================================================

CREATE FUNCTION GetStock(p_product_id INT)
RETURNS INT
READS SQL DATA
BEGIN
    DECLARE v_stock INT;
    SELECT StockQuantity INTO v_stock
    FROM Products
    WHERE ProductID = p_product_id;
    RETURN IFNULL(v_stock, 0);
END$$

CREATE FUNCTION TotalSales()
RETURNS DECIMAL(12,2)
READS SQL DATA
BEGIN
    DECLARE v_total DECIMAL(12,2);
    SELECT SUM(TotalAmount) INTO v_total
    FROM Orders;
    RETURN IFNULL(v_total, 0.00);
END$$

CREATE PROCEDURE AddProduct(
    IN p_name VARCHAR(150),
    IN p_category INT,
    IN p_supplier INT,
    IN p_price DECIMAL(10,2),
    IN p_stock INT
)
BEGIN
    INSERT INTO Products (ProductName, CategoryID, SupplierID, UnitPrice, StockQuantity, ReorderLevel)
    VALUES (p_name, p_category, p_supplier, p_price, p_stock, 10); -- Defaulting reorder level to 10
END$$

CREATE PROCEDURE UpdateStock(
    IN p_product INT,
    IN p_quantity INT
)
BEGIN
    UPDATE Products
    SET StockQuantity = StockQuantity + p_quantity
    WHERE ProductID = p_product;
END$$

--  order placement with transaction rollback safety
CREATE PROCEDURE PlaceOrder(
    IN p_customer INT,
    IN p_total DECIMAL(12,2),
    OUT p_new_order_id INT
)
BEGIN
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Order processing failure: Transaction aborted.';
    END;

    START TRANSACTION;
        INSERT INTO Orders (CustomerID, OrderDate, TotalAmount)
        VALUES (p_customer, CURDATE(), p_total);
        
        SET p_new_order_id = LAST_INSERT_ID();
    COMMIT;
END$$

DELIMITER ;

-- =====================================================================================
-- 7. SEED DATA (Run this to populate the database for testing)
-- =====================================================================================

-- Insert Categories
INSERT INTO Categories (CategoryName) VALUES ('Heritage Grains'), ('Restorative Mixes'), ('Active Elixirs');

-- Insert Suppliers
INSERT INTO Suppliers (SupplierName, Phone, Email) VALUES 
('Thanjavur Organic Farms', '9876543210', 'sales@thanjavurfarms.in'),
('Nilgiri Botanicals', '9876543211', 'contact@nilgiribot.in');

-- Insert Customers
INSERT INTO Customers (CustomerName, Phone, Email) VALUES 
('Gohul', '9876543212', 'gohul@example.com'),
('Girthanaa', '9876543213', 'girthanaa@example.com');

-- Insert Products
INSERT INTO Products (ProductName, CategoryID, SupplierID, UnitPrice, StockQuantity, ReorderLevel) VALUES 
('Karuppu Kavuni Rice', 1, 1, 240.00, 50, 10),
('ABC Malt Powder', 3, 2, 450.00, 25, 5),
('Oottu Mavu', 2, 1, 320.00, 40, 15);

-- Execute a sample Order process
CALL PlaceOrder(1, 480.00, @NewOrderID);
INSERT INTO OrderDetails (OrderID, ProductID, Quantity, UnitPrice) 
VALUES (@NewOrderID, 1, 2, 240.00); 
-- Note: Trigger 'trg_reduce_stock' will automatically drop Karuppu Kavuni stock from 50 to 48.
-- Note: Trigger 'trg_stock_audit' will automatically log the stock deduction.