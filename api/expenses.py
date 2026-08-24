from datetime import date, datetime, time, timezone
from typing import List, Optional

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, HTTPException, Query, status
from pymongo import ReturnDocument

from database import get_expenses_collection
from models import (
    BulkExpenseCreate,
    BulkExpenseResult,
    ExpenseCreate,
    ExpenseOut,
    ExpenseSummary,
    ExpenseUpdate,
    GroupBy,
    PaginatedExpenses,
    SortOrder,
    SummaryBucket,
)

router = APIRouter(tags=["expenses"])


def _object_id(expense_id: str) -> ObjectId:
    try:
        return ObjectId(expense_id)
    except InvalidId as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="ID inválido") from exc


def _start_of_day(d: date) -> datetime:
    return datetime.combine(d, time.min, tzinfo=timezone.utc)


def _end_of_day(d: date) -> datetime:
    return datetime.combine(d, time.max, tzinfo=timezone.utc)


def _date_range_filter(start_date: Optional[date], end_date: Optional[date]) -> dict:
    if not start_date and not end_date:
        return {}
    date_filter = {}
    if start_date:
        date_filter["$gte"] = _start_of_day(start_date)
    if end_date:
        date_filter["$lte"] = _end_of_day(end_date)
    return {"date": date_filter}


def _serialize(doc: dict) -> dict:
    return {
        "id": str(doc["_id"]),
        "amount": doc["amount"],
        "description": doc["description"],
        "date": doc["date"].date(),
        "category": doc["category"],
        "tags": doc.get("tags", []),
        "created_at": doc["created_at"],
        "updated_at": doc["updated_at"],
    }


@router.post("/expenses", response_model=ExpenseOut, status_code=status.HTTP_201_CREATED)
async def create_expense(payload: ExpenseCreate):
    collection = get_expenses_collection()
    now = datetime.now(timezone.utc)
    doc = {
        **payload.model_dump(exclude={"date"}),
        "date": _start_of_day(payload.date),
        "created_at": now,
        "updated_at": now,
    }
    result = await collection.insert_one(doc)
    doc["_id"] = result.inserted_id
    return _serialize(doc)


@router.post("/expenses/bulk", response_model=BulkExpenseResult, status_code=status.HTTP_201_CREATED)
async def bulk_create_expenses(payload: BulkExpenseCreate):
    collection = get_expenses_collection()
    now = datetime.now(timezone.utc)
    docs = [
        {
            **item.model_dump(exclude={"date"}),
            "date": _start_of_day(item.date),
            "created_at": now,
            "updated_at": now,
        }
        for item in payload.items
    ]
    result = await collection.insert_many(docs)
    return BulkExpenseResult(created=len(result.inserted_ids))


@router.get("/expenses", response_model=PaginatedExpenses)
async def list_expenses(
    category: Optional[str] = None,
    tag: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    search: Optional[str] = Query(None, description="Busca por texto na descrição"),
    sort_by: str = Query("date", pattern="^(date|amount|category)$"),
    order: SortOrder = SortOrder.DESC,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=200),
):
    collection = get_expenses_collection()
    query: dict = {}
    if category:
        query["category"] = category
    if tag:
        query["tags"] = tag
    if search:
        query["description"] = {"$regex": search, "$options": "i"}
    query.update(_date_range_filter(start_date, end_date))

    total = await collection.count_documents(query)
    sort_direction = 1 if order == SortOrder.ASC else -1
    cursor = (
        collection.find(query)
        .sort(sort_by, sort_direction)
        .skip((page - 1) * limit)
        .limit(limit)
    )
    items = [_serialize(doc) async for doc in cursor]
    return PaginatedExpenses(items=items, total=total, page=page, limit=limit)


@router.get("/expenses/summary", response_model=ExpenseSummary)
async def get_summary(
    group_by: GroupBy = GroupBy.CATEGORY,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    category: Optional[str] = None,
):
    collection = get_expenses_collection()
    match: dict = {}
    if category:
        match["category"] = category
    match.update(_date_range_filter(start_date, end_date))

    group_id_by_field = {
        GroupBy.CATEGORY: "$category",
        GroupBy.DAY: {"$dateToString": {"format": "%Y-%m-%d", "date": "$date"}},
        GroupBy.WEEK: {"$dateToString": {"format": "%G-W%V", "date": "$date"}},
        GroupBy.MONTH: {"$dateToString": {"format": "%Y-%m", "date": "$date"}},
    }

    pipeline = [
        {"$match": match},
        {
            "$group": {
                "_id": group_id_by_field[group_by],
                "total": {"$sum": "$amount"},
                "count": {"$sum": 1},
            }
        },
        {"$sort": {"_id": 1}},
    ]

    buckets: List[SummaryBucket] = []
    total = 0.0
    async for row in collection.aggregate(pipeline):
        buckets.append(SummaryBucket(key=str(row["_id"]), total=row["total"], count=row["count"]))
        total += row["total"]

    return ExpenseSummary(group_by=group_by, buckets=buckets, total=total)


@router.get("/categories", response_model=List[str])
async def list_categories():
    collection = get_expenses_collection()
    categories = await collection.distinct("category")
    return sorted(categories)


@router.get("/expenses/{expense_id}", response_model=ExpenseOut)
async def get_expense(expense_id: str):
    collection = get_expenses_collection()
    doc = await collection.find_one({"_id": _object_id(expense_id)})
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gasto não encontrado")
    return _serialize(doc)


@router.put("/expenses/{expense_id}", response_model=ExpenseOut)
async def update_expense(expense_id: str, payload: ExpenseUpdate):
    collection = get_expenses_collection()
    oid = _object_id(expense_id)

    update_data = payload.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nenhum campo para atualizar")
    if "date" in update_data:
        update_data["date"] = _start_of_day(update_data["date"])
    update_data["updated_at"] = datetime.now(timezone.utc)

    doc = await collection.find_one_and_update(
        {"_id": oid}, {"$set": update_data}, return_document=ReturnDocument.AFTER
    )
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gasto não encontrado")
    return _serialize(doc)


@router.delete("/expenses/{expense_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_expense(expense_id: str):
    collection = get_expenses_collection()
    result = await collection.delete_one({"_id": _object_id(expense_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gasto não encontrado")
