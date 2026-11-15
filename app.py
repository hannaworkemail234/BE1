import json
import math
import os
import re
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flask import Flask, jsonify, request


def _read_legacy_records(path):
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as data_file:
        records = json.load(data_file)
    if not isinstance(records, list):
        raise ValueError(f"Legacy data in {path} must be a JSON array")
    return records


def _parse_integer_prefix(value):
    match = re.match(r"^\s*([+-]?\d+)", str(value))
    return int(match.group(1)) if match else None


def _parse_id(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or not number.is_integer():
        return None
    return int(number)


def _payload():
    body = request.get_json(silent=True)
    return body if isinstance(body, dict) else {}


def _timestamp():
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def _user_from_row(row):
    user = {
        "id": row["id"],
        "name": row["name"],
        "age": row["age"],
        "address": row["address"],
        "createdAt": row["created_at"],
    }
    if row["updated_at"] is not None:
        user["updatedAt"] = row["updated_at"]
    return user


def _product_from_row(row):
    product = {
        "id": row["id"],
        "name": row["name"],
        "price": row["price"],
        "quantity": row["quantity"],
        "createdAt": row["created_at"],
    }
    if row["updated_at"] is not None:
        product["updatedAt"] = row["updated_at"]
    return product


def _order_from_row(row):
    order = {
        "id": row["id"],
        "user_id": row["user_id"],
        "product_id": row["product_id"],
        "quantity": row["quantity"],
        "unit_price": row["unit_price"],
        "total_amount": row["total_amount"],
        "status": row["status"],
        "note": row["note"],
        "createdAt": row["created_at"],
    }
    if row["updated_at"] is not None:
        order["updatedAt"] = row["updated_at"]
    return order


class SQLiteStore:
    def __init__(self, database_path, legacy_dir):
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.user_file = Path(legacy_dir) / "data.json"
        self.product_file = Path(legacy_dir) / "products.json"
        self._initialize()

    def _connect(self):
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self):
        with closing(self._connect()) as connection:
            with connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS users (
                        id INTEGER PRIMARY KEY,
                        name TEXT NOT NULL,
                        age INTEGER,
                        address TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS products (
                        id INTEGER PRIMARY KEY,
                        name TEXT NOT NULL,
                        price REAL NOT NULL,
                        quantity INTEGER NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS orders (
                        id INTEGER PRIMARY KEY,
                        user_id INTEGER NOT NULL,
                        product_id INTEGER NOT NULL,
                        quantity INTEGER NOT NULL,
                        unit_price REAL NOT NULL,
                        total_amount REAL NOT NULL,
                        status TEXT NOT NULL,
                        note TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS app_metadata (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL
                    )
                    """
                )
                imported = connection.execute(
                    "SELECT 1 FROM app_metadata WHERE key = ?",
                    ("legacy_json_imported",),
                ).fetchone()
                if imported is None:
                    self._import_users(
                        connection, _read_legacy_records(self.user_file)
                    )
                    self._import_products(
                        connection, _read_legacy_records(self.product_file)
                    )
                    connection.execute(
                        "INSERT INTO app_metadata (key, value) VALUES (?, ?)",
                        ("legacy_json_imported", "1"),
                    )

    @staticmethod
    def _import_users(connection, users):
        connection.executemany(
            """
            INSERT INTO users (id, name, age, address, created_at, updated_at)
            VALUES (:id, :name, :age, :address, :createdAt, :updatedAt)
            """,
            [
                {
                    "id": user["id"],
                    "name": user["name"],
                    "age": user.get("age"),
                    "address": user["address"],
                    "createdAt": user["createdAt"],
                    "updatedAt": user.get("updatedAt"),
                }
                for user in users
            ],
        )

    @staticmethod
    def _import_products(connection, products):
        connection.executemany(
            """
            INSERT INTO products
                (id, name, price, quantity, created_at, updated_at)
            VALUES (:id, :name, :price, :quantity, :createdAt, :updatedAt)
            """,
            [
                {
                    "id": product["id"],
                    "name": product["name"],
                    "price": product["price"],
                    "quantity": product["quantity"],
                    "createdAt": product["createdAt"],
                    "updatedAt": product.get("updatedAt"),
                }
                for product in products
            ],
        )

    def list_users(self):
        with closing(self._connect()) as connection:
            rows = connection.execute("SELECT * FROM users ORDER BY id").fetchall()
            return [_user_from_row(row) for row in rows]

    def list_user_ids(self):
        return [
            {key: user[key] for key in ("id", "name", "age", "address")}
            for user in self.list_users()
        ]

    def get_user(self, user_id):
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT * FROM users WHERE id = ?", (user_id,)
            ).fetchone()
            return _user_from_row(row) if row is not None else None

    def create_user(self, name, age, address):
        created_at = _timestamp()
        with closing(self._connect()) as connection:
            with connection:
                cursor = connection.execute(
                    """
                    INSERT INTO users (name, age, address, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (name, age, address, created_at),
                )
                user_id = cursor.lastrowid
        return {
            "id": user_id,
            "name": name,
            "age": age,
            "address": address,
            "createdAt": created_at,
        }

    def update_user(self, user_id, changes):
        columns = {
            "name": "name",
            "age": "age",
            "address": "address",
        }
        updates = [(columns[key], value) for key, value in changes.items()]
        updates.append(("updated_at", _timestamp()))
        assignments = ", ".join(f"{column} = ?" for column, _ in updates)
        values = [value for _, value in updates]
        with closing(self._connect()) as connection:
            with connection:
                cursor = connection.execute(
                    f"UPDATE users SET {assignments} WHERE id = ?",
                    (*values, user_id),
                )
                if cursor.rowcount == 0:
                    return None
                row = connection.execute(
                    "SELECT * FROM users WHERE id = ?", (user_id,)
                ).fetchone()
                return _user_from_row(row)

    def delete_user(self, user_id):
        with closing(self._connect()) as connection:
            with connection:
                row = connection.execute(
                    "SELECT * FROM users WHERE id = ?", (user_id,)
                ).fetchone()
                if row is None:
                    return None
                connection.execute("DELETE FROM users WHERE id = ?", (user_id,))
                return _user_from_row(row)

    def list_products(self):
        with closing(self._connect()) as connection:
            rows = connection.execute("SELECT * FROM products ORDER BY id").fetchall()
            return [_product_from_row(row) for row in rows]

    def list_product_ids(self):
        return [
            {key: product[key] for key in ("id", "name", "price", "quantity")}
            for product in self.list_products()
        ]

    def get_product(self, product_id):
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT * FROM products WHERE id = ?", (product_id,)
            ).fetchone()
            return _product_from_row(row) if row is not None else None

    def create_product(self, name, price, quantity):
        created_at = _timestamp()
        with closing(self._connect()) as connection:
            with connection:
                cursor = connection.execute(
                    """
                    INSERT INTO products (name, price, quantity, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (name, price, quantity, created_at),
                )
                product_id = cursor.lastrowid
        return {
            "id": product_id,
            "name": name,
            "price": price,
            "quantity": quantity,
            "createdAt": created_at,
        }

    def update_product(self, product_id, changes):
        columns = {
            "name": "name",
            "price": "price",
            "quantity": "quantity",
        }
        updates = [(columns[key], value) for key, value in changes.items()]
        updates.append(("updated_at", _timestamp()))
        assignments = ", ".join(f"{column} = ?" for column, _ in updates)
        values = [value for _, value in updates]
        with closing(self._connect()) as connection:
            with connection:
                cursor = connection.execute(
                    f"UPDATE products SET {assignments} WHERE id = ?",
                    (*values, product_id),
                )
                if cursor.rowcount == 0:
                    return None
                row = connection.execute(
                    "SELECT * FROM products WHERE id = ?", (product_id,)
                ).fetchone()
                return _product_from_row(row)

    def delete_product(self, product_id):
        with closing(self._connect()) as connection:
            with connection:
                row = connection.execute(
                    "SELECT * FROM products WHERE id = ?", (product_id,)
                ).fetchone()
                if row is None:
                    return None
                connection.execute(
                    "DELETE FROM products WHERE id = ?", (product_id,)
                )
                return _product_from_row(row)

    def list_orders(
        self, filters={}, sort_by="id", direction="ASC", limit=None, offset=0
    ):
        query = "SELECT * FROM orders"
        if "status" in filters:
            query += f" WHERE status = '{filters['status']}'"
        query += f" ORDER BY {sort_by} {direction}"

        connection = self._connect()
        rows = connection.execute(query).fetchall()

        orders = []
        for row in rows:
            order = _order_from_row(row)
            user = self.get_user(order["user_id"])
            product = self.get_product(order["product_id"])
            order["user_name"] = user["name"] if user else None
            order["product_name"] = product["name"] if product else None
            orders.append(order)

        if limit is not None:
            orders = orders[offset : offset + limit]

        connection.close()
        return orders

    def count_orders(self):
        return len(self.list_orders())

    def list_order_ids(self):
        return [
            {key: order[key] for key in ("id", "user_id", "product_id", "status")}
            for order in self.list_orders()
        ]

    def get_order(self, order_id):
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT * FROM orders WHERE id = ?", (order_id,)
            ).fetchone()
            return _order_from_row(row) if row is not None else None

    def create_order(self, user_id, product_id, quantity, status, note):
        created_at = _timestamp()
        product = self.get_product(product_id)
        unit_price = product["price"]
        total_amount = unit_price * quantity

        with closing(self._connect()) as connection:
            with connection:
                cursor = connection.execute(
                    """
                    INSERT INTO orders
                        (user_id, product_id, quantity, unit_price,
                         total_amount, status, note, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        user_id,
                        product_id,
                        quantity,
                        unit_price,
                        total_amount,
                        status,
                        note,
                        created_at,
                    ),
                )
                order_id = cursor.lastrowid

        try:
            self.update_product(
                product_id, {"quantity": product["quantity"] - quantity}
            )
        except Exception:
            pass

        return {
            "id": order_id,
            "user_id": user_id,
            "product_id": product_id,
            "quantity": quantity,
            "unit_price": unit_price,
            "total_amount": total_amount,
            "status": status,
            "note": note,
            "createdAt": created_at,
        }

    def update_order(self, order_id, changes):
        columns = {
            "user_id": "user_id",
            "product_id": "product_id",
            "quantity": "quantity",
            "status": "status",
            "note": "note",
        }
        updates = [(columns[key], value) for key, value in changes.items()]
        updates.append(("updated_at", _timestamp()))
        assignments = ", ".join(f"{column} = ?" for column, _ in updates)
        values = [value for _, value in updates]
        with closing(self._connect()) as connection:
            with connection:
                cursor = connection.execute(
                    f"UPDATE orders SET {assignments} WHERE id = ?",
                    (*values, order_id),
                )
                if cursor.rowcount == 0:
                    return None
                row = connection.execute(
                    "SELECT * FROM orders WHERE id = ?", (order_id,)
                ).fetchone()
                return _order_from_row(row)

    def delete_order(self, order_id):
        connection = self._connect()
        row = connection.execute(
            "SELECT * FROM orders WHERE id = ?", (order_id,)
        ).fetchone()
        if row is None:
            connection.close()
            return None
        connection.execute("DELETE FROM orders WHERE id = ?", (order_id,))
        connection.commit()
        connection.close()
        return _order_from_row(row)


def create_app(data_dir=None):
    app = Flask(__name__)
    storage_dir = Path(data_dir) if data_dir else Path(__file__).resolve().parent
    storage_dir.mkdir(parents=True, exist_ok=True)
    store = SQLiteStore(storage_dir / "app.db", storage_dir)
    app.config["DATABASE"] = str(store.database_path)

    @app.after_request
    def add_cors_headers(response):
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Headers"] = (
            "Origin, X-Requested-With, Content-Type, Accept"
        )
        response.headers["Access-Control-Allow-Methods"] = (
            "GET, POST, PUT, DELETE, OPTIONS"
        )
        return response

    @app.before_request
    def handle_preflight():
        if request.method == "OPTIONS":
            return "", 200
        return None

    @app.post("/api/users")
    def add_user():
        body = _payload()
        name, age, address = (
            body.get("name"),
            body.get("age"),
            body.get("address"),
        )
        if not name or not age or not address:
            return jsonify(error="Missing required fields: name, age, address"), 400
        try:
            user = store.create_user(name, _parse_integer_prefix(age), address)
            return jsonify(message="User added successfully", data=user), 201
        except (sqlite3.Error, TypeError, ValueError):
            app.logger.exception("Failed to save user data")
            return jsonify(error="Failed to save user data"), 500

    @app.get("/api/users")
    def get_users():
        try:
            users = store.list_users()
            return jsonify(
                message="Users retrieved successfully", count=len(users), data=users
            )
        except sqlite3.Error:
            app.logger.exception("Failed to read user data")
            return jsonify(error="Failed to read user data"), 500

    @app.get("/api/users/ids")
    def get_user_ids():
        try:
            users = store.list_user_ids()
            return jsonify(
                message="User IDs retrieved successfully",
                count=len(users),
                data=users,
            )
        except sqlite3.Error:
            app.logger.exception("Failed to read user data")
            return jsonify(error="Failed to read user data"), 500

    @app.get("/api/users/<user_id>")
    def get_user(user_id):
        parsed_id = _parse_id(user_id)
        if parsed_id is None:
            return jsonify(error="ID must be an integer"), 400
        try:
            user = store.get_user(parsed_id)
            if user is None:
                return jsonify(error=f"User with ID {parsed_id} not found"), 404
            return jsonify(message="User retrieved successfully", data=user)
        except sqlite3.Error:
            app.logger.exception("Failed to read user data")
            return jsonify(error="Failed to read user data"), 500

    @app.put("/api/users/<user_id>")
    def update_user(user_id):
        parsed_id = _parse_id(user_id)
        if parsed_id is None:
            return jsonify(error="ID must be an integer"), 400

        body = _payload()
        if all(key not in body for key in ("name", "age", "address")):
            return jsonify(
                error="Provide at least one field to update: name, age, address"
            ), 400
        if "age" in body:
            try:
                numeric_age = float(body["age"])
            except (TypeError, ValueError):
                return jsonify(error="Age must be an integer"), 400
            if not math.isfinite(numeric_age) or not numeric_age.is_integer():
                return jsonify(error="Age must be an integer"), 400
        if ("name" in body and not body["name"]) or (
            "address" in body and not body["address"]
        ):
            return jsonify(error="Name and address cannot be empty"), 400

        changes = {}
        if "name" in body:
            changes["name"] = body["name"]
        if "age" in body:
            changes["age"] = _parse_integer_prefix(body["age"])
        if "address" in body:
            changes["address"] = body["address"]
        try:
            user = store.update_user(parsed_id, changes)
            if user is None:
                return jsonify(error=f"User with ID {parsed_id} not found"), 404
            return jsonify(message="User updated successfully", data=user)
        except (sqlite3.Error, TypeError, ValueError):
            app.logger.exception("Failed to update user data")
            return jsonify(error="Failed to update user data"), 500

    @app.delete("/api/users/<user_id>")
    def delete_user(user_id):
        parsed_id = _parse_id(user_id)
        if parsed_id is None:
            return jsonify(error="ID must be an integer"), 400
        try:
            user = store.delete_user(parsed_id)
            if user is None:
                return jsonify(error=f"User with ID {parsed_id} not found"), 404
            return jsonify(message="User deleted successfully", data=user)
        except sqlite3.Error:
            app.logger.exception("Failed to delete user data")
            return jsonify(error="Failed to delete user data"), 500

    @app.post("/api/products")
    def add_product():
        body = _payload()
        name, price, quantity = (
            body.get("name"),
            body.get("price"),
            body.get("quantity"),
        )
        if (
            not isinstance(name, str)
            or not name.strip()
            or "price" not in body
            or "quantity" not in body
        ):
            return jsonify(error="Missing required fields: name, price, quantity"), 400
        try:
            numeric_price = 0 if price is None else float(price)
            numeric_quantity = 0 if quantity is None else float(quantity)
        except (TypeError, ValueError):
            return jsonify(error="Price and quantity must be numeric"), 400
        if not math.isfinite(numeric_price) or numeric_price < 0:
            return jsonify(error="Price must be a non-negative number"), 400
        if not numeric_quantity.is_integer() or numeric_quantity < 0:
            return jsonify(error="Quantity must be a non-negative integer"), 400

        try:
            product = store.create_product(
                name.strip(), numeric_price, int(numeric_quantity)
            )
            return jsonify(message="Product added successfully", data=product), 201
        except (sqlite3.Error, TypeError, ValueError):
            app.logger.exception("Failed to save product data")
            return jsonify(error="Failed to save product data"), 500

    @app.get("/api/products")
    def get_products():
        try:
            products = store.list_products()
            return jsonify(
                message="Products retrieved successfully",
                count=len(products),
                data=products,
            )
        except sqlite3.Error:
            app.logger.exception("Failed to read product data")
            return jsonify(error="Failed to read product data"), 500

    @app.get("/api/products/ids")
    def get_product_ids():
        try:
            products = store.list_product_ids()
            return jsonify(
                message="Product IDs retrieved successfully",
                count=len(products),
                data=products,
            )
        except sqlite3.Error:
            app.logger.exception("Failed to read product data")
            return jsonify(error="Failed to read product data"), 500

    @app.get("/api/products/<product_id>")
    def get_product(product_id):
        parsed_id = _parse_id(product_id)
        if parsed_id is None:
            return jsonify(error="ID must be an integer"), 400
        try:
            product = store.get_product(parsed_id)
            if product is None:
                return jsonify(error=f"Product with ID {parsed_id} not found"), 404
            return jsonify(message="Product retrieved successfully", data=product)
        except sqlite3.Error:
            app.logger.exception("Failed to read product data")
            return jsonify(error="Failed to read product data"), 500

    @app.put("/api/products/<product_id>")
    def update_product(product_id):
        parsed_id = _parse_id(product_id)
        if parsed_id is None:
            return jsonify(error="ID must be an integer"), 400

        body = _payload()
        if all(key not in body for key in ("name", "price", "quantity")):
            return jsonify(
                error="Provide at least one field to update: name, price, quantity"
            ), 400
        if "name" in body and (
            not isinstance(body["name"], str) or not body["name"].strip()
        ):
            return jsonify(error="Name cannot be empty"), 400

        changes = {}
        if "name" in body:
            changes["name"] = body["name"].strip()
        if "price" in body:
            try:
                numeric_price = 0 if body["price"] is None else float(body["price"])
            except (TypeError, ValueError):
                return jsonify(error="Price must be a non-negative number"), 400
            if not math.isfinite(numeric_price) or numeric_price < 0:
                return jsonify(error="Price must be a non-negative number"), 400
            changes["price"] = numeric_price
        if "quantity" in body:
            try:
                numeric_quantity = (
                    0 if body["quantity"] is None else float(body["quantity"])
                )
            except (TypeError, ValueError):
                return jsonify(error="Quantity must be a non-negative integer"), 400
            if not numeric_quantity.is_integer() or numeric_quantity < 0:
                return jsonify(error="Quantity must be a non-negative integer"), 400
            changes["quantity"] = int(numeric_quantity)

        try:
            product = store.update_product(parsed_id, changes)
            if product is None:
                return jsonify(error=f"Product with ID {parsed_id} not found"), 404
            return jsonify(message="Product updated successfully", data=product)
        except (sqlite3.Error, TypeError, ValueError):
            app.logger.exception("Failed to update product data")
            return jsonify(error="Failed to update product data"), 500

    @app.delete("/api/products/<product_id>")
    def delete_product(product_id):
        parsed_id = _parse_id(product_id)
        if parsed_id is None:
            return jsonify(error="ID must be an integer"), 400
        try:
            product = store.delete_product(parsed_id)
            if product is None:
                return jsonify(error=f"Product with ID {parsed_id} not found"), 404
            return jsonify(message="Product deleted successfully", data=product)
        except sqlite3.Error:
            app.logger.exception("Failed to delete product data")
            return jsonify(error="Failed to delete product data"), 500

    @app.post("/api/orders")
    def add_order():
        body = _payload()
        user_id, product_id, quantity = (
            body.get("user_id"),
            body.get("product_id"),
            body.get("quantity"),
        )
        status = body.get("status", "pending")
        note = body.get("note")

        if not user_id or not product_id or not quantity:
            return jsonify(
                error="Missing required fields: user_id, product_id, quantity"
            ), 400
        if status not in ["pending", "paid", "shipped", "cancelled"]:
            return jsonify(
                error="Status must be one of: pending, paid, shipped, cancelled"
            ), 400

        try:
            order = store.create_order(
                user_id, product_id, int(quantity), status, note
            )
            return jsonify(message="Order added successfully", data=order), 200
        except sqlite3.Error:
            app.logger.exception("Failed to save order data")
            return jsonify(error="Failed to save order data"), 500

    @app.get("/api/orders")
    def get_orders():
        status = request.args.get("status")
        sort_by = request.args.get("sort", "id")
        direction = request.args.get("direction", "ASC")
        limit = request.args.get("limit")
        offset = request.args.get("offset", 0)

        filters = {}
        if status:
            filters["status"] = status

        try:
            orders = store.list_orders(
                filters,
                sort_by,
                direction,
                int(limit) if limit else None,
                int(offset),
            )
            return jsonify(
                message="Orders retrieved successfully",
                count=store.count_orders(),
                data=orders,
            )
        except sqlite3.Error:
            app.logger.exception("Failed to read order data")
            return jsonify(error="Failed to read order data"), 500

    @app.get("/api/orders/ids")
    def get_order_ids():
        try:
            orders = store.list_order_ids()
            return jsonify(
                message="Order IDs retrieved successfully",
                count=len(orders),
                data=orders,
            )
        except sqlite3.Error:
            app.logger.exception("Failed to read order data")
            return jsonify(error="Failed to read order data"), 500

    @app.get("/api/orders/<order_id>")
    def get_order(order_id):
        order_id = int(order_id)
        try:
            order = store.get_order(order_id)
            if order is None:
                return jsonify(error=f"Order with ID {order_id} not found"), 404
            return jsonify(message="Order retrieved successfully", data=order)
        except sqlite3.Error:
            app.logger.exception("Failed to read order data")
            return jsonify(error="Failed to read order data"), 500

    @app.put("/api/orders/<order_id>")
    def update_order(order_id):
        parsed_id = _parse_id(order_id)
        if parsed_id is None:
            return jsonify(error="ID must be an integer"), 400

        body = _payload()
        fields = ("user_id", "product_id", "quantity", "status", "note")
        if all(key not in body for key in fields):
            return jsonify(
                error=(
                    "Provide at least one field to update: "
                    "user_id, product_id, quantity, status, note"
                )
            ), 400
        if "status" in body and body["status"] not in [
            "pending",
            "paid",
            "shipped",
            "cancelled",
        ]:
            return jsonify(
                error="Status must be one of: pending, paid, shipped, cancelled"
            ), 400

        changes = {key: value for key, value in body.items() if key != "id"}

        try:
            order = store.update_order(parsed_id, changes)
            if order is None:
                return jsonify(error=f"Order with ID {parsed_id} not found"), 404
            return jsonify(message="Order updated successfully", data=order)
        except sqlite3.Error:
            app.logger.exception("Failed to update order data")
            return jsonify(error="Failed to update order data"), 500

    @app.delete("/api/orders/<order_id>")
    def delete_order(order_id):
        parsed_id = _parse_id(order_id)
        if parsed_id is None:
            return jsonify(error="ID must be an integer"), 400
        try:
            order = store.delete_order(parsed_id)
            if order is None:
                return jsonify(error=f"Order with ID {parsed_id} not found"), 404
            return jsonify(message="Order deleted successfully", data=order)
        except sqlite3.Error:
            app.logger.exception("Failed to delete order data")
            return jsonify(error="Failed to delete order data"), 500

    @app.get("/health")
    def health():
        return jsonify(status="Server is running")

    return app


def main():
    app = create_app()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "3000")))


if __name__ == "__main__":
    main()
