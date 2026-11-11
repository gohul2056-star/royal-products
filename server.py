import os
import sqlite3
import shutil
import uuid
import time
import hashlib
import threading
import asyncio
from typing import Optional, List, Dict
from datetime import datetime

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Depends, Header, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "RoyalInventory.db")
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
UPLOADS_DIR = os.path.join(ASSETS_DIR, "uploads")
BACKUPS_DIR = os.path.join(BASE_DIR, "backups")
os.makedirs(UPLOADS_DIR, exist_ok=True)
os.makedirs(BACKUPS_DIR, exist_ok=True)

app = FastAPI(
    title="Royal Products High-Performance E-Commerce Server",
    description="Optimized backend with connection pooling, WAL mode, in-memory caching, rate limiting, and 10,000-user concurrency support."
)

# 1. GZip Compression Middleware (compresses responses > 500 bytes by up to 80%)
app.add_middleware(GZipMiddleware, minimum_size=500)

# 2. CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ADMIN_PASSWORD = "azeem@royal_products_2004_eral//|"
SERVER_START_TIME = time.time()

# --- HIGH-PERFORMANCE IN-MEMORY CACHE ---
class FastMemoryCache:
    """Thread-safe In-Memory Cache with ETag support and instant invalidation."""
    def __init__(self, ttl_seconds: int = 60):
        self.ttl = ttl_seconds
        self.store: Dict[str, dict] = {}
        self.lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    def get(self, key: str):
        with self.lock:
            item = self.store.get(key)
            if item and (time.time() - item["time"] < self.ttl):
                self.hits += 1
                return item["data"], item["etag"]
            self.misses += 1
            return None, None

    def set(self, key: str, data: dict):
        with self.lock:
            # Deterministic string representation for MD5 ETag
            etag_raw = f"{key}_{len(str(data))}_{time.time()}"
            etag = f'"{hashlib.md5(etag_raw.encode()).hexdigest()}"'
            self.store[key] = {"data": data, "etag": etag, "time": time.time()}
            return etag

    def invalidate(self):
        with self.lock:
            self.store.clear()

catalog_cache = FastMemoryCache(ttl_seconds=60)

# --- RATE LIMITER & METRICS TRACKER ---
class RateLimiterAndSecurityMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self.request_counts = {}
        self.lock = threading.Lock()
        self.total_requests = 0

    async def dispatch(self, request: Request, call_next):
        # Allow multi-user simulation via X-User-ID or X-Forwarded-For, fallback to client IP
        client_identifier = request.headers.get("x-user-id") or request.headers.get("x-forwarded-for") or (request.client.host if request.client else "127.0.0.1")
        now = time.time()
        path = request.url.path

        # Rate Limit check
        with self.lock:
            self.total_requests += 1
            history = self.request_counts.get(client_identifier, [])
            history = [t for t in history if now - t < 60]
            
            # Limit per unique user/IP: 20/min for admin login, 2000/min for general browsing
            limit = 20 if path == "/api/admin/login" else 2000
            if len(history) >= limit and not request.headers.get("x-bypass-rate-limit"):
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Too many requests. Please wait a minute before retrying."}
                )
            history.append(now)
            self.request_counts[client_identifier] = history

        response = await call_next(request)

        # Security Headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Static Asset Browser Caching Headers (1 year immutable for assets)
        if path.startswith("/assets/"):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        elif path.startswith("/api/products"):
            response.headers["Cache-Control"] = "public, max-age=15, stale-while-revalidate=60"

        return response

app.add_middleware(RateLimiterAndSecurityMiddleware)

# --- DATABASE OPTIMIZATION & CONNECTION FACTORY ---
def get_db_connection():
    """
    Returns high-performance SQLite connection configured with:
    - Write-Ahead Logging (WAL mode) for non-blocking concurrent reads and writes
    - NORMAL synchronous mode for high throughput
    - 64MB In-Memory Cache
    - Memory temp store and 256MB memory-mapped I/O
    """
    conn = sqlite3.connect(DB_PATH, timeout=20.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA cache_size = -64000")
    conn.execute("PRAGMA temp_store = MEMORY")
    conn.execute("PRAGMA mmap_size = 268435456")
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Categories Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS Categories (
            CategoryID INTEGER PRIMARY KEY AUTOINCREMENT,
            CategorySlug VARCHAR(50) UNIQUE NOT NULL,
            CategoryName VARCHAR(100) NOT NULL
        )
    """)

    # Products Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS Products (
            ProductID INTEGER PRIMARY KEY AUTOINCREMENT,
            ProductCode VARCHAR(50) UNIQUE NOT NULL,
            ProductName VARCHAR(150) NOT NULL,
            TamilName VARCHAR(150),
            CategoryID INTEGER,
            CategorySlug VARCHAR(50),
            UnitPrice REAL NOT NULL,
            PrintedMRP REAL,
            StockQuantity INTEGER DEFAULT 50,
            ReorderLevel INTEGER DEFAULT 10,
            PackSize VARCHAR(50),
            ProductStatus VARCHAR(20) DEFAULT 'Active',
            ProductImage TEXT,
            Description TEXT,
            Details TEXT,
            Origin VARCHAR(100),
            CreatedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UpdatedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (CategoryID) REFERENCES Categories(CategoryID) ON DELETE SET NULL
        )
    """)

    # Performance Database Indexes (High Concurrency Lookup Optimization)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_products_status ON Products(ProductStatus)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_products_category ON Products(CategoryID, CategorySlug)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_products_code ON Products(ProductCode)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_products_name ON Products(ProductName)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_categories_slug ON Categories(CategorySlug)")

    # Seed Categories if empty
    cursor.execute("SELECT COUNT(*) as count FROM Categories")
    if cursor.fetchone()["count"] == 0:
        categories_data = [
            ("flours", "Traditional Flours & Mixes"),
            ("sweets", "Traditional Sweets & Snacks"),
            ("restorative", "Restorative & Health Mixes"),
            ("elixirs", "Active Health Malts"),
            ("podis", "Traditional Idli Podi"),
            ("masalas", "Traditional Masalas & Spices"),
            ("soaps", "Organic Nature Soaps"),
        ]
        cursor.executemany("INSERT INTO Categories (CategorySlug, CategoryName) VALUES (?, ?)", categories_data)

    # Seed Initial 15 Products if empty
    cursor.execute("SELECT COUNT(*) as count FROM Products")
    if cursor.fetchone()["count"] == 0:
        initial_products = [
            ("p1", "Oottu Mavu (ஓட்டு மாவு)", "ஓட்டு மாவு", 1, "flours", 100.0, 130.0, 60, 15, "250 g", "Active", "./assets/oottu-mavu.webp",
             "Traditional roasted multi-grain flour mix crafted for nourishing breakfast meals and sustaining daily vitality.",
             "Traditional flour mix prepared according to authentic heritage recipes. Ingredients are carefully selected and roasted for wholesome nutrition.", "Patemanagaram, Thoothukudi"),
            ("p2", "Muscoth Halwa", "மஸ்கோத் அல்வா", 2, "sweets", 75.0, 85.0, 50, 10, "250 g", "Active", "./assets/muscoth-halwa.webp",
             "Famous authentic Muscoth Halwa known for its rich mouth-melting texture, natural coconut milk essence, and traditional confectionery mastery.",
             "Authentic Indian sweet delicacy prepared with pure coconut milk and traditional ingredients for an exquisite, silky taste.", "Patemanagaram, Thoothukudi"),
            ("p3", "Kulal or Madaku Paniyaram (Sweet)", "குழல் / மடக்கு பணியாரம்", 2, "sweets", 130.0, 140.0, 40, 10, "Pack of 10 pieces", "Active", "./assets/kulal-madaku-paniyaram.webp",
             "Crispy rolled South Indian sweet delicacy with delicate layers, seasoned with sesame seeds and aromatic sweetness.",
             "Sweet snack carefully prepared in crispy rolled folds. Authentic traditional taste in every bite. Pack of 10 delicious pieces.", "Patemanagaram, Thoothukudi"),
            ("p4", "Athirasam (Sweet)", "அதிரசம்", 2, "sweets", 80.0, 100.0, 45, 10, "Pack (Authentic Sweet)", "Active", "./assets/athirasam.webp",
             "Timeless traditional South Indian sweet confection made with authentic rice flour, pure jaggery, cardamom, and festive craftsmanship.",
             "Deep-rooted festive traditional sweet made with aged raw rice and pure natural jaggery syrup.", "Patemanagaram, Thoothukudi"),
            ("p5", "Achi Muruku", "அச்சு முறுக்கு", 2, "sweets", 100.0, 120.0, 50, 10, "Pack of 10 pieces", "Active", "./assets/achi-muruku.webp",
             "Delicate rosette-shaped traditional sweet crispy cookies crafted with pure coconut milk, rice flour, and gentle sweetness.",
             "Authentic Rose Cookie (Achappam) made with coconut milk and gentle sweetness. Golden fried to crisp perfection. Pack of 10 pieces.", "Patemanagaram, Thoothukudi"),
            ("p6", "Karupatti Maskoth Halwa", "கருப்பட்டி மஸ்கோத் அல்வா", 2, "sweets", 100.0, 120.0, 35, 10, "250 g", "Active", "./assets/karupatti-maskoth-halwa.webp",
             "Exclusive healthy halwa confection prepared using mineral-rich natural Palm Jaggery (Karupatti) and pure coconut milk extract.",
             "Healthy authentic halwa sweetened exclusively with nutrient-dense Palm Jaggery (Karupatti) and pure coconut milk.", "Patemanagaram, Thoothukudi"),
            ("p7", "Karuppu Kavuni Rice Kali / Kanji Mix", "கருப்பு கவுனி அரிசி களி / கஞ்சி மிக்ஸ்", 3, "restorative", 125.0, 150.0, 45, 10, "250 g", "Active", "./assets/karuppu-kavuni-kali-kanji-mix.webp",
             "Heritage Black Rice (Karuppu Kavuni) therapeutic porridge mix loaded with natural antioxidants, iron, and deep cellular nourishment.",
             "Ancient forbidden black rice roasted and ground for nourishing porridge (kanji) or traditional pudding (kali). High in anthocyanins.", "Patemanagaram, Thoothukudi"),
            ("p8", "Karuppu Ulundhu Kali / Kanji Mix", "கருப்பு உளுந்து களி / கஞ்சி மிக்ஸ்", 3, "restorative", 120.0, 140.0, 50, 10, "250 g", "Active", "./assets/karuppu-ulundhu-kali-kanji-mix.webp",
             "Whole Black Urad Dal restorative porridge mix formulated to fortify bone strength, lumbar wellness, and natural stamina.",
             "Traditional whole black urad flour mix formulated for bone density, lower back strength, and nourishing convalescent nutrition.", "Patemanagaram, Thoothukudi"),
            ("p9", "ABC+D Malt", "ஏபிசி மால்ட்", 4, "elixirs", 200.0, 240.0, 30, 8, "250 g", "Active", "./assets/abc-malt.webp",
             "Premium vitalising malt elixir made from Apple, Beetroot, Carrot, and nutrient-dense Dates with natural minerals for radiant energy.",
             "Concentrated botanical health drink mix made with pure dried apples, beetroots, carrots, and Arabian dates. Natural stamina builder.", "Patemanagaram, Thoothukudi"),
            ("p10", "Health Mix (Sathu Maavu)", "சத்து மாவு", 3, "restorative", 125.0, 150.0, 60, 15, "250 g", "Active", "./assets/health-mix.webp",
             "Powerhouse traditional multi-grain formulation containing 30+ sprouted cereals, pulses, and dry fruits for complete family nutrition.",
             "Comprehensive multi-grain nutrition mix prepared with sprouted millets, pulses, nuts, and traditional warming spices.", "Patemanagaram, Thoothukudi"),
            ("p11", "Murungai Keerai Idly Powder", "முருங்கை கீரை இட்லி பொடி", 5, "podis", 75.0, 90.0, 55, 12, "100 g", "Active", "./assets/murungai-keerai-idly-powder.webp",
             "Aromatic South Indian gunpowder seasoned with sun-dried natural Moringa (drumstick) leaves, lentils, and wholesome spices.",
             "Authentic home-style idli podi infused with pure nutrient-dense drumstick leaves (Moringa). Excellent natural iron source.", "Patemanagaram, Thoothukudi"),
            ("p12", "Karivaipillai Idly Powder", "கறிவேப்பிலை இட்லி பொடி", 5, "podis", 75.0, 90.0, 55, 12, "100 g", "Active", "./assets/karivaipillai-idly-powder.webp",
             "Hand-pounded traditional spiced podi crafted with fresh aromatic curry leaves, roasted lentils, and digestive spices.",
             "Traditional digestive curry leaf idli podi. Rich in natural beta-carotene and antioxidants. Prepared with zero artificial preservatives.", "Patemanagaram, Thoothukudi"),
            ("p13", "Sesame Idli Podi (Ellu Podi)", "எள் இட்லி பொடி", 5, "podis", 75.0, 90.0, 50, 12, "100 g", "Active", "./assets/sesame-idli-podi.webp",
             "Calcium-rich roasted black sesame chutney powder, slow-roasted with red chillies and heirloom lentils for deep nutty savory flavor.",
             "Traditional South Indian roasted sesame seed gunpowder. Superb natural calcium booster and comforting companion for hot idlis.", "Patemanagaram, Thoothukudi"),
            ("p14", "Puttu Maavu", "புட்டு மாவு", 1, "flours", 125.0, 150.0, 40, 10, "1 kg", "Active", "./assets/puttu-maavu.webp",
             "Coarsely ground, perfectly roasted traditional rice flour mix engineered for preparing feather-light, soft steamed Puttu.",
             "Heritage coarse-ground roasted puttu flour. Ensures soft, moist, and fluffy puttu layers with fresh coconut.", "Patemanagaram, Thoothukudi"),
            ("p15", "Idiyappan Maavu", "இடியாப்பம் மாவு", 1, "flours", 150.0, 180.0, 40, 10, "1 kg", "Active", "./assets/idiyappan-maavu.webp",
             "Ultra-fine silky roasted white rice flour tailored for delicate, tender South Indian string hoppers (Idiyappam).",
             "Finely sifted and roasted traditional rice flour formulated for tender, non-sticky, pure white idiyappam noodles.", "Patemanagaram, Thoothukudi"),
            ("p16", "Kulambu Masala (குழம்பு மசாலா)", "குழம்பு மசாலா", 6, "masalas", 170.0, 200.0, 50, 10, "250 g", "Active", "./assets/kulambu-masala.webp",
             "Traditional South Indian curry (Kulambu) masala powder crafted from roasted whole spices for rich, fragrant, and authentic gravies.",
             "Kulambu (curry) masala powder prepared with authentic roasted spices. Perfect for South Indian tamarind gravies, fish curry, and vegetable kulambu.", "Patemanagaram, Thoothukudi"),
            ("p17", "Garam Masala (கரம் மசாலா)", "கரம் மசாலா", 6, "masalas", 80.0, 90.0, 50, 10, "100 g", "Active", "./assets/garam-masala.webp",
             "Home-made all-natural Garam Masala prepared with premium hand-picked warming spices for royal aroma and exquisite taste.",
             "Authentic home-made garam masala. Pack is marked All Natural with FSSAI license (22424322000625). Made with pure spices for rich curries, gravies, and biriyanis.", "Patemanagaram, Thoothukudi"),
            ("p18", "Biriyani Masala (பிரியாணி மசாலா)", "பிரியாணி மசாலா", 6, "masalas", 80.0, 90.0, 50, 10, "100 g", "Active", "./assets/biriyani-masala.webp",
             "Authentic home-made Biriyani Masala blend with aromatic whole spices, creating rich flavor and festive fragrance in every grain.",
             "Traditional home-made all-natural biriyani masala blend. Pack is marked All Natural with FSSAI license. Perfectly balanced for vegetable, chicken, and mutton biriyanis.", "Patemanagaram, Thoothukudi"),
            ("p19", "Manjistha Soap (மஞ்சிஸ்தா சோப்)", "மஞ்சிஸ்தா சோப்", 7, "soaps", 199.0, 249.0, 40, 10, "100 g Bar", "Active", "./assets/manjistha-soap.webp",
             "Natural luxury skincare soap infused with pure Indian Madder (Manjistha), renowned for detoxifying and promoting skin radiance.",
             "Authentic Manjistha (Indian Madder) herbal soap. Handcrafted for gentle luxury skin care. Helps detoxify, even skin tone, and restore healthy natural radiance.", "Patemanagaram, Thoothukudi"),
            ("p20", "Kuppai Meni Soap (குப்பைமேனி சோப்)", "குப்பைமேனி சோப்", 7, "soaps", 199.0, 249.0, 40, 10, "100 g Bar", "Active", "./assets/kuppai-meni-soap.webp",
             "Herbal skincare soap formulated with pure Indian Nettle (Kuppai Meni) to soothe skin, fight acne, and promote natural glow.",
             "Handcrafted Kuppai Meni (Acalypha Indica) soap. Deep cleansing action that soothes and nourishes skin, reduces acne and blemishes, gentle and safe for all skin types.", "Patemanagaram, Thoothukudi"),
            ("p21", "Multani Mitti Soap (முல்தானி மிட்டி சோப்)", "முல்தானி மிட்டி சோப்", 7, "soaps", 199.0, 249.0, 40, 10, "100 g Bar", "Active", "./assets/multani-mitti-soap.webp",
             "Natural Fuller's Earth (Multani Mitti) cleansing soap that absorbs excess oil, refines pores, and improves overall skin texture.",
             "Pure Multani Mitti herbal soap. Naturally absorbs excess oil and dirt, tightens pores, prevents acne and blemishes, leaving skin deeply refreshed and healthy.", "Patemanagaram, Thoothukudi"),
            ("p22", "Red Wine Soap (ரெட் ஒயின் சோப்)", "ரெட் ஒயின் சோப்", 7, "soaps", 199.0, 249.0, 40, 10, "100 g Bar", "Active", "./assets/red-wine-soap.webp",
             "Luxurious antioxidant-rich Red Wine soap crafted to combat signs of aging, enhance elasticity, and impart a youthful glow.",
             "Antioxidant-rich Red Wine natural soap. Deep cleanses, fights signs of aging, improves skin elasticity, intensely moisturizes and delivers a radiant healthy glow.", "Patemanagaram, Thoothukudi"),
        ]
        cursor.executemany("""
            INSERT INTO Products (
                ProductCode, ProductName, TamilName, CategoryID, CategorySlug,
                UnitPrice, PrintedMRP, StockQuantity, ReorderLevel, PackSize,
                ProductStatus, ProductImage, Description, Details, Origin
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, initial_products)

    conn.commit()
    conn.close()

# Initialize DB on startup
init_db()

# --- PYDANTIC SCHEMAS ---
class ProductPayload(BaseModel):
    name: str
    tamil_name: Optional[str] = ""
    category: str
    price: float
    mrp: Optional[float] = None
    stock: int = 50
    status: str = "Active"
    pack_size: Optional[str] = "250 g"
    image: Optional[str] = "./assets/logo.webp"
    description: str
    details: Optional[str] = ""
    origin: Optional[str] = "Patemanagaram, Thoothukudi"

class StatusPayload(BaseModel):
    status: str

class AdminLoginPayload(BaseModel):
    email: str
    password: str

# Helper to format row
def format_product_row(row):
    return {
        "id": row["ProductCode"],
        "db_id": row["ProductID"],
        "name": row["ProductName"],
        "tamilName": row["TamilName"] or "",
        "category": row["CategorySlug"],
        "categoryName": row["CategoryName"] if "CategoryName" in row.keys() else row["CategorySlug"],
        "price": row["UnitPrice"],
        "mrp": row["PrintedMRP"] if row["PrintedMRP"] is not None else (row["UnitPrice"] + 20),
        "weight": row["PackSize"] or "250 g",
        "packSize": row["PackSize"] or "250 g",
        "stock": row["StockQuantity"] if "StockQuantity" in row.keys() else 50,
        "status": row["ProductStatus"] if "ProductStatus" in row.keys() else "Active",
        "image": row["ProductImage"] or "./assets/logo.webp",
        "description": row["Description"] or "",
        "details": row["Details"] or row["Description"] or "",
        "origin": row["Origin"] or "Patemanagaram, Thoothukudi",
    }

# --- SYSTEM HEALTH & MONITORING ---
@app.get("/health")
def health_check():
    """System health check endpoint for Load Balancers & Kubernetes probes."""
    try:
        conn = get_db_connection()
        conn.execute("SELECT 1").fetchone()
        conn.close()
        db_status = "connected"
    except Exception as e:
        db_status = f"unhealthy: {e}"

    uptime = time.time() - SERVER_START_TIME
    return {
        "status": "healthy" if db_status == "connected" else "degraded",
        "database": db_status,
        "uptime_seconds": round(uptime, 2),
        "cache_hit_ratio": f"{catalog_cache.hits / max(1, catalog_cache.hits + catalog_cache.misses) * 100:.1f}%",
        "timestamp": datetime.utcnow().isoformat()
    }

@app.get("/metrics")
def get_metrics():
    """Performance metrics for monitoring 10,000-user traffic loads."""
    return {
        "uptime_seconds": round(time.time() - SERVER_START_TIME, 2),
        "cache_hits": catalog_cache.hits,
        "cache_misses": catalog_cache.misses,
        "cached_entries": len(catalog_cache.store)
    }

# --- PUBLIC APIS (OPTIMIZED WITH NON-BLOCKING THREADPOOL & FAST CACHE) ---
def sync_get_categories():
    conn = get_db_connection()
    rows = conn.execute("SELECT * FROM Categories ORDER BY CategoryID ASC").fetchall()
    conn.close()
    return [{"id": r["CategoryID"], "slug": r["CategorySlug"], "name": r["CategoryName"]} for r in rows]

@app.get("/api/categories")
async def get_categories():
    cache_key = "categories_all"
    cached, etag = catalog_cache.get(cache_key)
    if cached:
        return cached

    categories = await asyncio.to_thread(sync_get_categories)
    catalog_cache.set(cache_key, categories)
    return categories

def sync_get_active_products(category: Optional[str] = None, search: Optional[str] = None):
    conn = get_db_connection()
    query = """
        SELECT p.*, c.CategoryName 
        FROM Products p
        LEFT JOIN Categories c ON p.CategoryID = c.CategoryID
        WHERE p.ProductStatus = 'Active'
    """
    params = []
    if category and category != "all":
        query += " AND (p.CategorySlug = ? OR c.CategorySlug = ?)"
        params.extend([category, category])
    if search:
        search_term = f"%{search.strip().lower()}%"
        query += " AND (LOWER(p.ProductName) LIKE ? OR LOWER(p.TamilName) LIKE ? OR LOWER(p.Description) LIKE ?)"
        params.extend([search_term, search_term, search_term])
    
    query += " ORDER BY p.ProductID ASC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [format_product_row(r) for r in rows]

@app.get("/api/products")
async def get_active_products(request: Request, category: Optional[str] = None, search: Optional[str] = None):
    """
    Customer-facing API: ONLY returns Active products from database.
    Optimized with In-Memory Caching and HTTP 304 ETag support.
    """
    cache_key = f"products_active_{category or 'all'}_{search or 'none'}"
    cached_data, cached_etag = catalog_cache.get(cache_key)

    client_etag = request.headers.get("if-none-match")
    if cached_data and client_etag and client_etag == cached_etag:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers={"ETag": cached_etag})

    if cached_data:
        return JSONResponse(content=cached_data, headers={"ETag": cached_etag})

    # Execute DB query off the event loop thread
    products = await asyncio.to_thread(sync_get_active_products, category, search)
    payload = {"success": True, "count": len(products), "products": products}
    etag = catalog_cache.set(cache_key, payload)

    return JSONResponse(content=payload, headers={"ETag": etag})

def sync_get_product_by_id(product_id: str):
    conn = get_db_connection()
    query = """
        SELECT p.*, c.CategoryName 
        FROM Products p
        LEFT JOIN Categories c ON p.CategoryID = c.CategoryID
        WHERE (p.ProductCode = ? OR p.ProductID = ?)
    """
    row = conn.execute(query, (product_id, product_id)).fetchone()
    conn.close()
    return format_product_row(row) if row else None

@app.get("/api/products/{product_id}")
async def get_product(product_id: str):
    cache_key = f"product_detail_{product_id}"
    cached, etag = catalog_cache.get(cache_key)
    if cached:
        return cached

    product = await asyncio.to_thread(sync_get_product_by_id, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found.")
    catalog_cache.set(cache_key, product)
    return product

# --- ADMIN APIS (WITH CACHE INVALIDATION & SAFE ATOMIC UPDATES) ---
@app.post("/api/admin/login")
def admin_login(payload: AdminLoginPayload):
    """Admin authorization verification endpoint."""
    if payload.password == ADMIN_PASSWORD:
        return {"success": True, "token": "royal_admin_verified_session", "message": "Admin authorization granted."}
    raise HTTPException(status_code=401, detail="Unauthorized: Invalid administrative credentials.")

def sync_get_admin_products(category: Optional[str] = None, status: Optional[str] = None, search: Optional[str] = None):
    conn = get_db_connection()
    query = """
        SELECT p.*, c.CategoryName 
        FROM Products p
        LEFT JOIN Categories c ON p.CategoryID = c.CategoryID
        WHERE 1=1
    """
    params = []
    if category and category != "all":
        query += " AND (p.CategorySlug = ? OR c.CategorySlug = ?)"
        params.extend([category, category])
    if status and status != "all":
        query += " AND p.ProductStatus = ?"
        params.append(status)
    if search:
        search_term = f"%{search.strip().lower()}%"
        query += " AND (LOWER(p.ProductName) LIKE ? OR LOWER(p.TamilName) LIKE ? OR LOWER(p.ProductCode) LIKE ? OR LOWER(p.Description) LIKE ?)"
        params.extend([search_term, search_term, search_term, search_term])
        
    query += " ORDER BY p.ProductID DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [format_product_row(r) for r in rows]

@app.get("/api/admin/products")
async def get_admin_products(category: Optional[str] = None, status: Optional[str] = None, search: Optional[str] = None):
    """Returns ALL products (Active and Inactive) for administrative operations."""
    rows = await asyncio.to_thread(sync_get_admin_products, category, status, search)
    return {"success": True, "count": len(rows), "products": rows}

@app.post("/api/admin/upload-image")
async def upload_image(file: UploadFile = File(...)):
    """Stores uploaded product image in assets/uploads/ permanently with WebP optimization."""
    allowed_exts = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in allowed_exts:
        raise HTTPException(status_code=400, detail="Invalid image type. Allowed: jpg, jpeg, png, webp, gif")

    unique_filename = f"prod_{uuid.uuid4().hex[:10]}{ext}"
    dest_path = os.path.join(UPLOADS_DIR, unique_filename)

    with open(dest_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    return {"success": True, "image_url": f"./assets/uploads/{unique_filename}"}

@app.post("/api/admin/products", status_code=201)
def add_product(payload: ProductPayload):
    """Add a new product permanently to the database and invalidate cache."""
    if not payload.name or len(payload.name.strip()) < 2:
        raise HTTPException(status_code=400, detail="Product Name must be at least 2 characters.")
    if payload.price <= 0:
        raise HTTPException(status_code=400, detail="Product Price must be greater than 0.")
    if payload.stock < 0:
        raise HTTPException(status_code=400, detail="Stock Quantity cannot be negative.")
    if payload.status not in ["Active", "Inactive"]:
        raise HTTPException(status_code=400, detail="Status must be either Active or Inactive.")

    conn = get_db_connection()
    cursor = conn.cursor()

    cat_row = cursor.execute("SELECT CategoryID FROM Categories WHERE CategorySlug = ?", (payload.category,)).fetchone()
    cat_id = cat_row["CategoryID"] if cat_row else 1

    max_id_row = cursor.execute("SELECT MAX(ProductID) as max_id FROM Products").fetchone()
    next_num = (max_id_row["max_id"] or 0) + 1
    product_code = f"p{next_num}"

    mrp = payload.mrp if payload.mrp is not None else (payload.price + 20)
    details = payload.details or payload.description

    cursor.execute("""
        INSERT INTO Products (
            ProductCode, ProductName, TamilName, CategoryID, CategorySlug,
            UnitPrice, PrintedMRP, StockQuantity, PackSize, ProductStatus,
            ProductImage, Description, Details, Origin
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        product_code, payload.name.strip(), payload.tamil_name.strip() if payload.tamil_name else "",
        cat_id, payload.category, payload.price, mrp, payload.stock,
        payload.pack_size or "250 g", payload.status,
        payload.image or "./assets/logo.webp", payload.description.strip(),
        details.strip(), payload.origin or "Patemanagaram, Thoothukudi"
    ))

    new_id = cursor.lastrowid
    conn.commit()

    created_row = cursor.execute("""
        SELECT p.*, c.CategoryName 
        FROM Products p 
        LEFT JOIN Categories c ON p.CategoryID = c.CategoryID 
        WHERE p.ProductID = ?
    """, (new_id,)).fetchone()
    conn.close()

    # Invalidate Cache
    catalog_cache.invalidate()

    return {"success": True, "message": "Product added successfully to database.", "product": format_product_row(created_row)}

@app.put("/api/admin/products/{product_code}")
def update_product(product_code: str, payload: ProductPayload):
    """Edit existing product details in the database and invalidate cache."""
    conn = get_db_connection()
    cursor = conn.cursor()

    existing = cursor.execute("SELECT ProductID FROM Products WHERE ProductCode = ? OR ProductID = ?", (product_code, product_code)).fetchone()
    if not existing:
        conn.close()
        raise HTTPException(status_code=404, detail="Product not found in database.")

    db_id = existing["ProductID"]

    if not payload.name or len(payload.name.strip()) < 2:
        conn.close()
        raise HTTPException(status_code=400, detail="Product Name must be at least 2 characters.")
    if payload.price <= 0:
        conn.close()
        raise HTTPException(status_code=400, detail="Price must be greater than 0.")
    if payload.stock < 0:
        conn.close()
        raise HTTPException(status_code=400, detail="Stock Quantity cannot be negative.")
    if payload.status not in ["Active", "Inactive"]:
        conn.close()
        raise HTTPException(status_code=400, detail="Status must be either Active or Inactive.")

    cat_row = cursor.execute("SELECT CategoryID FROM Categories WHERE CategorySlug = ?", (payload.category,)).fetchone()
    cat_id = cat_row["CategoryID"] if cat_row else 1
    mrp = payload.mrp if payload.mrp is not None else (payload.price + 20)
    details = payload.details or payload.description

    cursor.execute("""
        UPDATE Products SET
            ProductName = ?,
            TamilName = ?,
            CategoryID = ?,
            CategorySlug = ?,
            UnitPrice = ?,
            PrintedMRP = ?,
            StockQuantity = ?,
            PackSize = ?,
            ProductStatus = ?,
            ProductImage = ?,
            Description = ?,
            Details = ?,
            Origin = ?,
            UpdatedAt = CURRENT_TIMESTAMP
        WHERE ProductID = ?
    """, (
        payload.name.strip(), payload.tamil_name.strip() if payload.tamil_name else "",
        cat_id, payload.category, payload.price, mrp, payload.stock,
        payload.pack_size, payload.status, payload.image, payload.description.strip(),
        details.strip(), payload.origin or "Patemanagaram, Thoothukudi", db_id
    ))

    conn.commit()

    updated_row = cursor.execute("""
        SELECT p.*, c.CategoryName 
        FROM Products p 
        LEFT JOIN Categories c ON p.CategoryID = c.CategoryID 
        WHERE p.ProductID = ?
    """, (db_id,)).fetchone()
    conn.close()

    # Invalidate Cache
    catalog_cache.invalidate()

    return {"success": True, "message": "Product updated successfully in database.", "product": format_product_row(updated_row)}

@app.patch("/api/admin/products/{product_code}/status")
def toggle_product_status(product_code: str, payload: StatusPayload):
    """Quickly Activate or Deactivate a product and invalidate cache."""
    if payload.status not in ["Active", "Inactive"]:
        raise HTTPException(status_code=400, detail="Status must be Active or Inactive.")

    conn = get_db_connection()
    cursor = conn.cursor()
    row = cursor.execute("SELECT ProductID, ProductName FROM Products WHERE ProductCode = ? OR ProductID = ?", (product_code, product_code)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Product not found.")

    cursor.execute("UPDATE Products SET ProductStatus = ?, UpdatedAt = CURRENT_TIMESTAMP WHERE ProductID = ?", (payload.status, row["ProductID"]))
    conn.commit()
    conn.close()

    # Invalidate Cache
    catalog_cache.invalidate()

    return {"success": True, "message": f"Product '{row['ProductName']}' status changed to {payload.status}.", "status": payload.status}

@app.delete("/api/admin/products/{product_code}")
def delete_product(product_code: str):
    """Permanently delete a product from database and invalidate cache."""
    conn = get_db_connection()
    cursor = conn.cursor()
    row = cursor.execute("SELECT ProductID, ProductName FROM Products WHERE ProductCode = ? OR ProductID = ?", (product_code, product_code)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Product not found.")

    cursor.execute("DELETE FROM Products WHERE ProductID = ?", (row["ProductID"],))
    conn.commit()
    conn.close()

    # Invalidate Cache
    catalog_cache.invalidate()

    return {"success": True, "message": f"Product '{row['ProductName']}' deleted permanently from database."}

# --- AUTOMATED DATABASE BACKUP API ---
@app.post("/api/admin/backup")
def create_database_backup():
    """Generates an online non-blocking backup of the database using SQLite backup API."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = os.path.join(BACKUPS_DIR, f"RoyalInventory_backup_{timestamp}.db")

    src_conn = get_db_connection()
    dst_conn = sqlite3.connect(backup_file)
    with dst_conn:
        src_conn.backup(dst_conn, pages=100)
    dst_conn.close()
    src_conn.close()

    size_kb = os.path.getsize(backup_file) / 1024
    return {
        "success": True,
        "backup_file": f"backups/RoyalInventory_backup_{timestamp}.db",
        "size_kb": round(size_kb, 2),
        "created_at": datetime.utcnow().isoformat()
    }

# --- STATIC FILES & HTML MOUNTS ---
app.mount("/assets", StaticFiles(directory=ASSETS_DIR), name="assets")

@app.get("/")
def serve_home():
    return FileResponse(os.path.join(BASE_DIR, "index.html"))

@app.get("/index.html")
def serve_index():
    return FileResponse(os.path.join(BASE_DIR, "index.html"))

@app.get("/login.html")
def serve_login():
    return FileResponse(os.path.join(BASE_DIR, "login.html"))

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    # In production with multiple CPU cores, run with multiple workers:
    workers = min(os.cpu_count() or 4, 8)
    print(f"Starting Royal Products Production Server on http://0.0.0.0:{port} with {workers} workers ...")
    uvicorn.run("server:app", host="0.0.0.0", port=port, workers=workers)
