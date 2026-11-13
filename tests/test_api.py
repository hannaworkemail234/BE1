import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from app import create_app


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temp_dir.name)
        self.client = create_app(self.data_dir).test_client()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_user_crud_and_compact_listing(self):
        created = self.client.post(
            "/api/users",
            json={"name": "Ada", "age": 31, "address": "Example address"},
        )
        self.assertEqual(created.status_code, 201)
        user = created.get_json()["data"]
        self.assertEqual(user["id"], 1)
        self.assertEqual(user["age"], 31)

        updated = self.client.put("/api/users/1", json={"age": 32})
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.get_json()["data"]["age"], 32)
        self.assertIn("updatedAt", updated.get_json()["data"])

        ids = self.client.get("/api/users/ids")
        self.assertEqual(ids.get_json()["data"], [
            {"id": 1, "name": "Ada", "age": 32, "address": "Example address"}
        ])

        deleted = self.client.delete("/api/users/1")
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(self.client.get("/api/users/1").status_code, 404)

    def test_product_validation_and_persistence(self):
        invalid = self.client.post(
            "/api/products",
            json={"name": "Keyboard", "price": 5, "quantity": 1.5},
        )
        self.assertEqual(invalid.status_code, 400)

        created = self.client.post(
            "/api/products",
            json={"name": " Keyboard ", "price": 49.99, "quantity": 20},
        )
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.get_json()["data"]["name"], "Keyboard")

        products = self.client.get("/api/products")
        self.assertEqual(products.get_json()["count"], 1)
        with closing(sqlite3.connect(self.data_dir / "app.db")) as connection:
            saved_quantity = connection.execute(
                "SELECT quantity FROM products"
            ).fetchone()[0]
        self.assertEqual(saved_quantity, 20)

    def test_imports_legacy_json_once_and_preserves_updates(self):
        legacy_dir = self.data_dir / "legacy"
        legacy_dir.mkdir()
        legacy_users = [
            {
                "id": 7,
                "name": "Legacy User",
                "age": 25,
                "address": "Old address",
                "createdAt": "2025-01-01T00:00:00.000Z",
            }
        ]
        legacy_products = [
            {
                "id": 4,
                "name": "Legacy Product",
                "price": 12.5,
                "quantity": 3,
                "createdAt": "2025-01-02T00:00:00.000Z",
            }
        ]
        (legacy_dir / "data.json").write_text(json.dumps(legacy_users))
        (legacy_dir / "products.json").write_text(json.dumps(legacy_products))

        client = create_app(legacy_dir).test_client()
        self.assertEqual(
            client.get("/api/users").get_json()["data"][0]["id"], 7
        )
        self.assertEqual(
            client.get("/api/products").get_json()["data"][0]["id"], 4
        )
        updated = client.put("/api/users/7", json={"name": "Updated User"})
        self.assertEqual(updated.status_code, 200)

        restarted_client = create_app(legacy_dir).test_client()
        self.assertEqual(
            restarted_client.get("/api/users").get_json()["data"][0]["name"],
            "Updated User",
        )
        self.assertEqual(
            json.loads((legacy_dir / "data.json").read_text())[0]["name"],
            "Legacy User",
        )

    def test_health_and_cors_preflight(self):
        health = self.client.get("/health")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.get_json(), {"status": "Server is running"})
        self.assertEqual(health.headers["Access-Control-Allow-Origin"], "*")

        preflight = self.client.options("/api/users")
        self.assertEqual(preflight.status_code, 200)
        self.assertIn("OPTIONS", preflight.headers["Access-Control-Allow-Methods"])


if __name__ == "__main__":
    unittest.main()
