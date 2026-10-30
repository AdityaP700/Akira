"""Repository for Expense and ExpenseShare persistence."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.repositories.models import Expense, ExpenseShare


def create(
    session: Session,
    group_id: int,
    paid_by: int,
    amount_paise: int,
    description: str,
    split_type: str,
    shares: dict[int, int],
) -> Expense:
    """Create an expense and its associated shares in a single operation.

    Note: session commits are owned by the service layer.
    """
    expense = Expense(
        group_id=group_id,
        paid_by=paid_by,
        amount_paise=amount_paise,
        description=description,
        split_type=split_type,
    )
    session.add(expense)
    session.flush()

    for user_id, owed_paise in shares.items():
        share = ExpenseShare(
            expense_id=expense.id,
            user_id=user_id,
            owed_paise=owed_paise,
        )
        session.add(share)

    session.flush()
    return expense


def list_by_group(
    session: Session,
    group_id: int,
    limit: int = 50,
    cursor: int | None = None,
) -> list[Expense]:
    """List expenses for a group ordered newest first, with cursor pagination."""
    stmt = select(Expense).where(Expense.group_id == group_id)
    if cursor is not None:
        stmt = stmt.where(Expense.id < cursor)
    stmt = stmt.order_by(Expense.created_at.desc(), Expense.id.desc()).limit(limit)
    return list(session.scalars(stmt).all())


def get_shares_by_group(session: Session, group_id: int) -> list[ExpenseShare]:
    """Retrieve all expense shares for a group."""
    stmt = (
        select(ExpenseShare)
        .join(Expense, ExpenseShare.expense_id == Expense.id)
        .where(Expense.group_id == group_id)
    )
    return list(session.scalars(stmt).all())
