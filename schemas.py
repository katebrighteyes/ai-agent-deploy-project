# -*- coding: utf-8 -*-
"""
schemas.py
-----------
API 입력/출력 데이터 모델 (Pydantic)
"""

from pydantic import BaseModel, Field


class ReceiptRequest(BaseModel):
    """POST /receipt/check 요청 바디"""

    item_name: str = Field(..., description="지출 항목 (예: 택시비, 식대, KTX)", examples=["택시비"])
    amount: int = Field(..., description="청구 금액(원)", examples=[35000])
    is_night: bool = Field(False, description="야간 여부 (택시비 판단용)", examples=[True])

    class Config:
        json_schema_extra = {
            "example": {
                "item_name": "택시비",
                "amount": 35000,
                "is_night": True,
            }
        }


class ReceiptResponse(BaseModel):
    """POST /receipt/check 응답 바디"""

    item_name: str
    amount: int
    approved_amount: int
    status: str
    reason: str

    class Config:
        json_schema_extra = {
            "example": {
                "item_name": "택시비",
                "amount": 35000,
                "approved_amount": 30000,
                "status": "부분 승인 (한도 초과)",
                "reason": "야간 택시비 한도 30,000원 적용",
            }
        }
