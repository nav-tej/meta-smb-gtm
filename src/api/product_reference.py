"""Public product-reference import for the daily creator desk."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.services.product_reference import (
    ProductReference,
    ProductReferenceError,
    ProductReferenceService,
)

router = APIRouter(tags=["products"])


class ProductReferenceRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2000)


def get_product_reference_service() -> ProductReferenceService:
    return ProductReferenceService()


@router.post("/product-reference", response_model=ProductReference)
async def product_reference(
    request: ProductReferenceRequest,
    service: Annotated[ProductReferenceService, Depends(get_product_reference_service)],
) -> ProductReference:
    """Read one public item without generating content or connecting an account."""
    try:
        return await service.read(request.url)
    except ProductReferenceError as err:
        raise HTTPException(status_code=422, detail=str(err)) from err
