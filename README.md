# Simple Python Backend

A Flask REST API for managing users and products. Data is stored in the SQLite database `app.db` in the project directory.

## Requirements

- Python 3.10+
- [uv](https://docs.astral.sh/uv/)

## Setup and run

Install the project dependencies and create the lockfile:

```bash
uv sync
```

Start the server:

```bash
uv run python app.py
```

The server listens on `http://localhost:3000`. Set `PORT` to use another port:

```powershell
$env:PORT = "3001"
uv run python app.py
```

## API endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/users` | Add a user (`name`, `age`, `address`) |
| `GET` | `/api/users` | List users |
| `GET` | `/api/users/ids` | List user IDs and identifying details |
| `GET` | `/api/users/:id` | Get a user |
| `PUT` | `/api/users/:id` | Update a user's `name`, `age`, and/or `address` |
| `DELETE` | `/api/users/:id` | Delete a user |
| `POST` | `/api/products` | Add a product (`name`, `price`, `quantity`) |
| `GET` | `/api/products` | List products |
| `GET` | `/api/products/ids` | List product IDs and details |
| `GET` | `/api/products/:id` | Get a product |
| `PUT` | `/api/products/:id` | Update a product's `name`, `price`, and/or `quantity` |
| `DELETE` | `/api/products/:id` | Delete a product |
| `POST` | `/api/orders` | Add an order (`user_id`, `product_id`, `quantity`, optional `status`, `note`) |
| `GET` | `/api/orders` | List orders (`status`, `sort`, `direction`, `limit`, `offset` query params) |
| `GET` | `/api/orders/ids` | List order IDs and key fields |
| `GET` | `/api/orders/:id` | Get an order |
| `PUT` | `/api/orders/:id` | Update an order's `user_id`, `product_id`, `quantity`, `status`, and/or `note` |
| `DELETE` | `/api/orders/:id` | Delete an order |
| `GET` | `/health` | Check server health |

IDs must be integers. Missing records return `404`; invalid IDs or fields return `400`. Product prices must be non-negative numbers, and quantities must be non-negative integers.

An order references a user and a product. `unit_price` and `total_amount` are captured from the product at creation time, and placing an order reduces the product's stock. Order `status` must be one of `pending`, `paid`, `shipped`, or `cancelled`; it defaults to `pending`.

## Database and migration

The backend uses Python's built-in `sqlite3` module; no separate database server or extra dependency is required. On first startup, existing `data.json` and `products.json` records are imported into `app.db` once. If the JSON files are absent, the database starts empty. The original JSON files are left untouched as backups; all subsequent API changes are written to SQLite.

The database, its temporary files, and the legacy JSON files are ignored by Git because they may contain private data. Back them up separately if needed; they are not included when cloning the repository.

Example:

```bash
curl -X POST http://localhost:3000/api/products \
  -H "Content-Type: application/json" \
  -d '{"name":"Keyboard","price":49.99,"quantity":20}'

curl http://localhost:3000/api/products
```
