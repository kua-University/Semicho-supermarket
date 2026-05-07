from __future__ import annotations

import os
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, render_template, request


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DB_DIR = Path(tempfile.gettempdir()) / "Semicho"
DB_PATH = Path(os.environ.get("SEMICHO_DB_PATH", DEFAULT_DB_DIR / "supermarket.db"))

app = Flask(__name__)


def get_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_db() -> None:
    with get_db() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                category TEXT NOT NULL,
                price REAL NOT NULL,
                stock INTEGER NOT NULL,
                description TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_name TEXT NOT NULL,
                total REAL NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS order_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                quantity INTEGER NOT NULL,
                unit_price REAL NOT NULL,
                FOREIGN KEY(order_id) REFERENCES orders(id),
                FOREIGN KEY(product_id) REFERENCES products(id)
            );
            """
        )

        product_count = connection.execute("SELECT COUNT(*) FROM products").fetchone()[0]
        if product_count == 0:
            connection.executemany(
                """
                INSERT INTO products (name, category, price, stock, description)
                VALUES (?, ?, ?, ?, ?)
                """,
                [
                    ("Fresh Milk", "Dairy", 2.50, 24, "1-litre fresh whole milk"),
                    ("Brown Bread", "Bakery", 1.20, 30, "High-fiber loaf baked daily"),
                    ("Bananas", "Produce", 0.30, 80, "Locally sourced ripe bananas"),
                    ("Rice 2kg", "Pantry", 4.75, 18, "Long-grain rice for family meals"),
                    ("Laundry Soap", "Household", 3.10, 16, "Multipurpose soap bar pack"),
                    ("Eggs Tray", "Dairy", 5.40, 12, "Tray of 30 eggs"),
                ],
            )


def product_to_dict(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "category": row["category"],
        "price": row["price"],
        "stock": row["stock"],
        "description": row["description"],
    }


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/products")
def list_products():
    with get_db() as connection:
        rows = connection.execute(
            "SELECT id, name, category, price, stock, description FROM products ORDER BY category, name"
        ).fetchall()
    return jsonify([product_to_dict(row) for row in rows])


@app.get("/api/orders")
def list_orders():
    with get_db() as connection:
        rows = connection.execute(
            """
            SELECT o.id, o.customer_name, o.total, o.created_at,
                   COUNT(oi.id) AS item_lines
            FROM orders o
            LEFT JOIN order_items oi ON oi.order_id = o.id
            GROUP BY o.id
            ORDER BY o.id DESC
            """
        ).fetchall()
    return jsonify(
        [
            {
                "id": row["id"],
                "customer_name": row["customer_name"],
                "total": row["total"],
                "created_at": row["created_at"],
                "item_lines": row["item_lines"],
            }
            for row in rows
        ]
    )


@app.get("/api/dashboard")
def dashboard():
    with get_db() as connection:
        total_products = connection.execute("SELECT COUNT(*) FROM products").fetchone()[0]
        low_stock = connection.execute("SELECT COUNT(*) FROM products WHERE stock <= 10").fetchone()[0]
        total_orders = connection.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
        revenue = connection.execute("SELECT COALESCE(SUM(total), 0) FROM orders").fetchone()[0]

    return jsonify(
        {
            "total_products": total_products,
            "low_stock": low_stock,
            "total_orders": total_orders,
            "revenue": round(revenue, 2),
        }
    )


@app.post("/api/orders")
def create_order():
    payload = request.get_json(silent=True) or {}
    customer_name = (payload.get("customer_name") or "").strip()
    items = payload.get("items") or []

    if not customer_name:
        return jsonify({"error": "Customer name is required."}), 400
    if not items:
        return jsonify({"error": "At least one product must be selected."}), 400

    with get_db() as connection:
        requested_ids = [item.get("product_id") for item in items]
        placeholders = ",".join("?" for _ in requested_ids)
        rows = connection.execute(
            f"SELECT id, name, price, stock FROM products WHERE id IN ({placeholders})",
            requested_ids,
        ).fetchall()
        products = {row["id"]: row for row in rows}

        order_total = 0.0
        normalized_items: list[dict] = []

        for item in items:
            product_id = item.get("product_id")
            quantity = int(item.get("quantity", 0))
            if quantity <= 0 or product_id not in products:
                return jsonify({"error": "Invalid order item provided."}), 400

            product = products[product_id]
            if quantity > product["stock"]:
                return jsonify({"error": f"Insufficient stock for {product['name']}."}), 400

            line_total = float(product["price"]) * quantity
            order_total += line_total
            normalized_items.append(
                {
                    "product_id": product_id,
                    "quantity": quantity,
                    "unit_price": float(product["price"]),
                }
            )

        cursor = connection.execute(
            "INSERT INTO orders (customer_name, total, created_at) VALUES (?, ?, ?)",
            (customer_name, round(order_total, 2), datetime.utcnow().isoformat(timespec="seconds")),
        )
        order_id = cursor.lastrowid

        for item in normalized_items:
            connection.execute(
                """
                INSERT INTO order_items (order_id, product_id, quantity, unit_price)
                VALUES (?, ?, ?, ?)
                """,
                (order_id, item["product_id"], item["quantity"], item["unit_price"]),
            )
            connection.execute(
                "UPDATE products SET stock = stock - ? WHERE id = ?",
                (item["quantity"], item["product_id"]),
            )

    return jsonify(
        {
            "message": "Order placed successfully.",
            "order_id": order_id,
            "total": round(order_total, 2),
        }
    )


@app.post("/api/restock")
def restock_product():
    payload = request.get_json(silent=True) or {}
    product_id = payload.get("product_id")
    quantity = int(payload.get("quantity", 0))

    if not product_id or quantity <= 0:
        return jsonify({"error": "A valid product and positive quantity are required."}), 400

    with get_db() as connection:
        result = connection.execute(
            "UPDATE products SET stock = stock + ? WHERE id = ?",
            (quantity, product_id),
        )
        if result.rowcount == 0:
            return jsonify({"error": "Product not found."}), 404

    return jsonify({"message": "Stock updated successfully."})


init_db()


if __name__ == "__main__":
    app.run(debug=True)
