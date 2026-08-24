from datetime import date, datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class SortOrder(str, Enum):
    ASC = "asc"
    DESC = "desc"


class GroupBy(str, Enum):
    CATEGORY = "category"
    DAY = "day"
    WEEK = "week"
    MONTH = "month"


class ExpenseBase(BaseModel):
    amount: float = Field(..., gt=0, description="Valor gasto, em reais")
    description: str = Field(..., min_length=1, max_length=200)
    date: date
    category: str = Field(..., min_length=1, max_length=50)
    tags: List[str] = Field(default_factory=list)


class ExpenseCreate(ExpenseBase):
    pass


class ExpenseUpdate(BaseModel):
    amount: Optional[float] = Field(None, gt=0)
    description: Optional[str] = Field(None, min_length=1, max_length=200)
    date: Optional[date] = None
    category: Optional[str] = Field(None, min_length=1, max_length=50)
    tags: Optional[List[str]] = None


class ExpenseOut(ExpenseBase):
    id: str
    created_at: datetime
    updated_at: datetime


class PaginatedExpenses(BaseModel):
    items: List[ExpenseOut]
    total: int
    page: int
    limit: int


class SummaryBucket(BaseModel):
    key: str
    total: float
    count: int


class ExpenseSummary(BaseModel):
    group_by: GroupBy
    buckets: List[SummaryBucket]
    total: float


class ParsedTransaction(BaseModel):
    date: date
    description: str
    amount: float
    category: str = ""
    is_credit: bool = False
    include: bool = True


class BulkExpenseCreate(BaseModel):
    items: List[ExpenseCreate] = Field(..., min_length=1)


class BulkExpenseResult(BaseModel):
    created: int
