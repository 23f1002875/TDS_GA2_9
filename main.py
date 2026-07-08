from fastapi import FastAPI, Header, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import uuid
import time
import base64

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

TOTAL_ORDERS = 51
RATE_LIMIT = 17
WINDOW = 10

orders = []
idempotency_store = {}
rate_limits = {}


class OrderCreate(BaseModel):
    item: Optional[str] = None
    quantity: Optional[int] = 1


@app.post("/orders", status_code=201)
def create_order(
    body: OrderCreate,
    response: Response,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    client_id: str = Header("anonymous", alias="X-Client-Id"),
):
    now = time.time()

    bucket = rate_limits.setdefault(client_id, [])
    bucket[:] = [t for t in bucket if now - t < WINDOW]

    if len(bucket) >= RATE_LIMIT:
        retry = int(WINDOW - (now - bucket[0])) + 1
        response.headers["Retry-After"] = str(retry)
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    bucket.append(now)

    if idempotency_key in idempotency_store:
        return idempotency_store[idempotency_key]

    order = {
        "id": str(uuid.uuid4()),
        "item": body.item,
        "quantity": body.quantity,
    }

    idempotency_store[idempotency_key] = order
    orders.append(order)
    return order


@app.get("/orders")
def list_orders(
    limit: int = 10,
    cursor: Optional[str] = None,
    response: Response = None,
    client_id: str = Header("anonymous", alias="X-Client-Id"),
):
    now = time.time()

    bucket = rate_limits.setdefault(client_id, [])
    bucket[:] = [t for t in bucket if now - t < WINDOW]

    if len(bucket) >= RATE_LIMIT:
        retry = int(WINDOW - (now - bucket[0])) + 1
        response.headers["Retry-After"] = str(retry)
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    bucket.append(now)

    start = 1

    if cursor:
        start = int(base64.b64decode(cursor).decode())

    end = min(start + limit - 1, TOTAL_ORDERS)

    items = [{"id": i} for i in range(start, end + 1)]

    next_cursor = None
    if end < TOTAL_ORDERS:
        next_cursor = base64.b64encode(str(end + 1).encode()).decode()

    return {
        "items": items,
        "next_cursor": next_cursor,
    }
