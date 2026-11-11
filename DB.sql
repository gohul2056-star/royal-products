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
    ProductCode VARCHAR(50) UNIQUE NOT NULL,
    ProductName VARCHAR(150) NOT NULL,
    TamilName VARCHAR(150),
    CategoryID INT,
    CategorySlug VARCHAR(50),
    SupplierID INT,
    UnitPrice DECIMAL(10,2) NOT NULL,
    PrintedMRP DECIMAL(10,2),
    StockQuantity INT DEFAULT 50,
    ReorderLevel INT DEFAULT 10,
    PackSize VARCHAR(50) DEFAULT '250 g',
    ProductStatus VARCHAR(20) DEFAULT 'Active',
    ProductImage VARCHAR(255),
    Description TEXT,
    Details TEXT,
    Origin VARCHAR(100) DEFAULT 'Patemanagaram, Thoothukudi',
    CreatedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UpdatedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
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
INSERT INTO Categories (CategoryName) VALUES 
('Traditional Flours & Mixes'), 
('Traditional Sweets & Snacks'), 
('Restorative & Health Mixes'), 
('Active Health Malts'), 
('Traditional Idli Podi'),
('Traditional Masalas & Spices'),
('Organic Nature Soaps');

-- Insert Suppliers
INSERT INTO Suppliers (SupplierName, Phone, Email, Address) VALUES 
('Royal Products Manufacturing', '9566075664', 'royalproducts@gmail.com', '4/109, Middle Street, Patemanagaram, Thoothukudi – 628 620');

-- Insert Customers
INSERT INTO Customers (CustomerName, Phone, Email) VALUES 

('Ananya', '9876543213', 'ananya@example.com');

-- Insert All 15 Products from Official Catalogue
INSERT INTO Products (ProductCode, ProductName, TamilName, CategoryID, CategorySlug, SupplierID, UnitPrice, PrintedMRP, StockQuantity, ReorderLevel, PackSize, ProductStatus, ProductImage) VALUES 
('p1', 'Oottu Mavu (ஓட்டு மாவு)', 'ஓட்டு மாவு', 1, 'flours', 1, 100.00, 130.00, 60, 15, '250 g', 'Active', './assets/oottu-mavu.jpg'),
('p2', 'Muscoth Halwa', 'மஸ்கோத் அல்வா', 2, 'sweets', 1, 75.00, 85.00, 50, 10, '250 g', 'Active', './assets/muscoth-halwa.jpg'),
('p3', 'Kulal or Madaku Paniyaram (Sweet)', 'குழல் / மடக்கு பணியாரம்', 2, 'sweets', 1, 130.00, 140.00, 40, 10, 'Pack of 10 pieces', 'Active', './assets/kulal-madaku-paniyaram.jpg'),
('p4', 'Athirasam (Sweet)', 'அதிரசம்', 2, 'sweets', 1, 80.00, 100.00, 45, 10, 'Pack (Authentic Sweet)', 'Active', './assets/athirasam.jpg'),
('p5', 'Achi Muruku (Sweet)', 'அச்சு முறுக்கு', 2, 'sweets', 1, 80.00, 90.00, 50, 10, 'Pack of 10 big pieces', 'Active', './assets/achi-muruku.jpg'),
('p6', 'Karupatti Maskoth Halwa (Sweet)', 'கருப்பட்டி மஸ்கோத் அல்வா', 2, 'sweets', 1, 150.00, 160.00, 35, 10, '250 g', 'Active', './assets/karupatti-maskoth-halwa.jpg'),
('p7', 'Karuppu Kavuni Rice Kali, Kanji Mix', 'கருப்பு கவுனி அரிசி களி / கஞ்சி மிக்ஸ்', 3, 'restorative', 1, 180.00, 200.00, 55, 15, '200 g', 'Active', './assets/karuppu-kavuni-kali-kanji-mix.jpg'),
('p8', 'Karuppu Ulundhu Kali, Kanji Mix', 'கருப்பு உளுந்து களி / கஞ்சி மிக்ஸ்', 3, 'restorative', 1, 190.00, 210.00, 50, 15, '200 g', 'Active', './assets/karuppu-ulundhu-kali-kanji-mix.jpg'),
('p9', 'ABC+D Malt Powder', 'ஏபிசி+டி மால்ட் பவுடர்', 4, 'elixirs', 1, 240.00, 280.00, 40, 10, '200 g', 'Active', './assets/abc-malt.jpg'),
('p10', 'Health Mix (சத்துமாவு)', 'சத்துமாவு', 3, 'restorative', 1, 150.00, 180.00, 60, 15, 'Standard Pack', 'Active', './assets/health-mix.jpg'),
('p11', 'Murungai Keerai Idly Powder', 'முருங்கைக்கீரை இட்லி பொடி / சாதப்பொடி', 5, 'podis', 1, 75.00, 85.00, 70, 20, '100 g', 'Active', './assets/murungai-keerai-idly-powder.jpg'),
('p12', 'Karivaipillai Idly Powder', 'கறிவேப்பிலை இட்லி பொடி / சாதப்பொடி', 5, 'podis', 1, 75.00, 85.00, 70, 20, '100 g', 'Active', './assets/karivaipillai-idly-powder.jpg'),
('p13', 'Sesame Idli Podi (எள் இட்லி பொடி)', 'எள் இட்லி பொடி', 5, 'podis', 1, 75.00, 85.00, 65, 20, '100 g', 'Active', './assets/sesame-idli-podi.jpg'),
('p14', 'Puttu Maavu (புட்டு மாவு)', 'புட்டு மாவு', 1, 'flours', 1, 125.00, 145.00, 80, 20, '1 kg', 'Active', './assets/puttu-maavu.jpg'),
('p15', 'Idiyappan Maavu (இடியாப்பம் மாவு)', 'இடியாப்பம் மாவு', 1, 'flours', 1, 150.00, 160.00, 80, 20, '1 kg', 'Active', './assets/idiyappan-maavu.jpg'),
('p16', 'Kulambu Masala (குழம்பு மசாலா)', 'குழம்பு மசாலா', 6, 'masalas', 1, 170.00, 200.00, 50, 10, '250 g', 'Active', './assets/kulambu-masala.jpg'),
('p17', 'Garam Masala (கரம் மசாலா)', 'கரம் மசாலா', 6, 'masalas', 1, 80.00, 90.00, 50, 10, '100 g', 'Active', './assets/garam-masala.jpg'),
('p18', 'Biriyani Masala (பிரியாணி மசாலா)', 'பிரியாணி மசாலா', 6, 'masalas', 1, 80.00, 90.00, 50, 10, '100 g', 'Active', './assets/biriyani-masala.jpg'),
('p19', 'Manjistha Soap (மஞ்சிஸ்தா சோப்)', 'மஞ்சிஸ்தா சோப்', 7, 'soaps', 1, 199.00, 249.00, 40, 10, '100 g Bar', 'Active', './assets/manjistha-soap.jpg'),
('p20', 'Kuppai Meni Soap (குப்பைமேனி சோப்)', 'குப்பைமேனி சோப்', 7, 'soaps', 1, 199.00, 249.00, 40, 10, '100 g Bar', 'Active', './assets/kuppai-meni-soap.jpg'),
('p21', 'Multani Mitti Soap (முல்தானி மிட்டி சோப்)', 'முல்தானி மிட்டி சோப்', 7, 'soaps', 1, 199.00, 249.00, 40, 10, '100 g Bar', 'Active', './assets/multani-mitti-soap.jpg'),
('p22', 'Red Wine Soap (ரெட் ஒயின் சோப்)', 'ரெட் ஒயின் சோப்', 7, 'soaps', 1, 199.00, 249.00, 40, 10, '100 g Bar', 'Active', './assets/red-wine-soap.jpg');

-- Execute a sample Order process
CALL PlaceOrder(1, 200.00, @NewOrderID);
INSERT INTO OrderDetails (OrderID, ProductID, Quantity, UnitPrice) 
VALUES (@NewOrderID, 1, 2, 100.00); 
-- Note: Trigger 'trg_reduce_stock' will automatically drop Oottu Mavu stock from 60 to 58.
-- Note: Trigger 'trg_stock_audit' will automatically log the stock deduction.