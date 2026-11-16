import tempfile
import unittest
from pathlib import Path

from app import create_app


class OrderApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temp_dir.name)
        self.client = create_app(self.data_dir).test_client()
        self.client.post(
            "/api/users",
            json={"name": "Ada", "age": 31, "address": "Example address"},
        )
        self.client.post(
            "/api/products",
            json={"name": "Keyboard", "price": 10.0, "quantity": 20},
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def _create_order(self, **overrides):
        payload = {"user_id": 1, "product_id": 1, "quantity": 2}
        payload.update(overrides)
        return self.client.post("/api/orders", json=payload)

    def test_create_order_returns_totals_and_reduces_stock(self):
        created = self._create_order(note="Rush delivery")
        self.assertEqual(created.status_code, 200)

        order = created.get_json()["data"]
        self.assertEqual(order["id"], 1)
        self.assertEqual(order["quantity"], 2)
        self.assertEqual(order["unit_price"], 10.0)
        self.assertEqual(order["total_amount"], 20.0)
        self.assertEqual(order["status"], "pending")
        self.assertEqual(order["note"], "Rush delivery")

        product = self.client.get("/api/products/1").get_json()["data"]
        self.assertEqual(product["quantity"], 18)

    def test_create_order_rejects_missing_fields_and_bad_status(self):
        missing = self.client.post("/api/orders", json={"user_id": 1})
        self.assertEqual(missing.status_code, 400)

        bad_status = self._create_order(status="refunded")
        self.assertEqual(bad_status.status_code, 400)

    def test_list_orders_includes_related_names(self):
        self._create_order()
        self._create_order(quantity=3, status="paid")

        listed = self.client.get("/api/orders")
        self.assertEqual(listed.status_code, 200)
        body = listed.get_json()
        self.assertEqual(body["count"], 2)
        self.assertEqual(body["data"][0]["user_name"], "Ada")
        self.assertEqual(body["data"][0]["product_name"], "Keyboard")

        paid_only = self.client.get("/api/orders?status=paid")
        self.assertEqual(len(paid_only.get_json()["data"]), 1)

        page = self.client.get("/api/orders?limit=1&offset=1")
        self.assertEqual(len(page.get_json()["data"]), 1)
        self.assertEqual(page.get_json()["data"][0]["id"], 2)

    def test_list_orders_validates_query_inputs(self):
        self._create_order()
        self._create_order(status="paid")

        injected_status = self.client.get(
            "/api/orders?status=%27%20OR%201%3D1%20--"
        )
        self.assertEqual(injected_status.get_json()["data"], [])

        invalid_sort = self.client.get(
            "/api/orders?sort=id%20DESC&direction=DESC%2C%20id"
        )
        self.assertEqual(
            [order["id"] for order in invalid_sort.get_json()["data"]],
            [1, 2],
        )

    def test_order_ids_listing(self):
        self._create_order()
        ids = self.client.get("/api/orders/ids")
        self.assertEqual(
            ids.get_json()["data"],
            [{"id": 1, "user_id": 1, "product_id": 1, "status": "pending"}],
        )

    def test_get_update_and_delete_order(self):
        self._create_order()

        fetched = self.client.get("/api/orders/1")
        self.assertEqual(fetched.status_code, 200)
        self.assertEqual(fetched.get_json()["data"]["id"], 1)

        updated = self.client.put("/api/orders/1", json={"status": "shipped"})
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.get_json()["data"]["status"], "shipped")
        self.assertIn("updatedAt", updated.get_json()["data"])

        deleted = self.client.delete("/api/orders/1")
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(self.client.get("/api/orders/1").status_code, 404)

    def test_update_requires_known_field(self):
        self._create_order()
        empty = self.client.put("/api/orders/1", json={})
        self.assertEqual(empty.status_code, 400)

    def test_missing_order_returns_404(self):
        self.assertEqual(self.client.get("/api/orders/99").status_code, 404)
        self.assertEqual(self.client.delete("/api/orders/99").status_code, 404)


if __name__ == "__main__":
    unittest.main()
