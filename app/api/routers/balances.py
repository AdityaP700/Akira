"""Router for Balances and Settle-up endpoints."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_actor, get_db
from app.api.schemas.balances import AllGroupsBalancesOut, GroupBalancesOut, SettleUpOut
from app.services import balances as balances_service

router = APIRouter(tags=["balances"])


@router.get(
    "/groups/{group_id}/balances",
    response_model=GroupBalancesOut,
    status_code=status.HTTP_200_OK,
    summary="Get group balances",
    description="Calculate pairwise debts and net balances for all members in a group.",
)
def get_group_balances(
    group_id: str,
    db: Annotated[Session, Depends(get_db)],
    actor: Annotated[Any, Depends(get_actor)] = None,
) -> Any:
    return balances_service.get_group_balances(db, group_public_id=group_id)


@router.get(
    "/balances",
    response_model=AllGroupsBalancesOut,
    status_code=status.HTTP_200_OK,
    summary="Get balances across all groups",
    description="Brief-compatible endpoint returning derived balances for all groups.",
)
def get_all_balances(
    db: Annotated[Session, Depends(get_db)],
    actor: Annotated[Any, Depends(get_actor)] = None,
) -> Any:
    groups_data = balances_service.get_all_group_balances(db)
    return {"groups": groups_data}


@router.get(
    "/groups/{group_id}/settle-up",
    response_model=SettleUpOut,
    status_code=status.HTTP_200_OK,
    summary="Get settle-up transfer suggestions",
    description="Greedy debt simplification suggesting at most n - 1 transfers to settle balances.",
)
def get_settle_up(
    group_id: str,
    db: Annotated[Session, Depends(get_db)],
    actor: Annotated[Any, Depends(get_actor)] = None,
) -> Any:
    return balances_service.get_settle_up_suggestions(db, group_public_id=group_id)
