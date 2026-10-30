"""Service layer for Settlement transactions and queries."""

import hashlib
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.api.schemas.settlements import SettlementIn
from app.core.errors import (
    IdempotencyKeyReusedError,
    NotFoundError,
    OverpaymentError,
    ParticipantNotMemberError,
    ValidationError,
)
from app.core.pagination import decode_cursor, encode_cursor
from app.domain.balances import net_balances
from app.domain.money import MoneyError, format_paise, parse_rupees
from app.repositories import groups as groups_repo
from app.repositories import idempotency as idempotency_repo
from app.repositories import ledger as ledger_repo
from app.repositories import settlements as settlements_repo
from app.repositories import users as users_repo
from app.repositories.models import Expense, ExpenseShare, Settlement, User


def record_settlement(
    session: Session,
    group_public_id: str,
    payload: SettlementIn,
    idempotency_key: str | None = None,
    http_method: str = "POST",
    http_path: str = "/groups/{group_id}/settlements",
    canonical_body: str = "",
) -> tuple[dict[str, Any], int]:
    """Atomically record a settlement repayment with overpayment check and ledger entry.

    Transaction flow:
    1. with session.begin():
    2. Check idempotency record if key present.
    3. Lock group row FOR UPDATE.
    4. Validate from_user and to_user are distinct group members.
    5. Calculate current pairwise debt; assert amount <= debt (no overpayment).
    6. Insert settlement row with status CONFIRMED.
    7. Append ledger entry of type SETTLEMENT.
    8. Save idempotency record.
    9. Return 201 response.
    """
    fingerprint = ""
    with session.begin():
        if idempotency_key is not None:
            raw_fingerprint = f"{http_method.upper()}:{http_path}:{canonical_body}"
            fingerprint = hashlib.sha256(raw_fingerprint.encode("utf-8")).hexdigest()

            existing = idempotency_repo.get(
                session, scope=f"group:{group_public_id}", key=idempotency_key
            )
            if existing is not None:
                if existing.request_fingerprint != fingerprint:
                    raise IdempotencyKeyReusedError(
                        "Idempotency key reused with different request payload"
                    )
                if existing.response_body is not None:
                    return existing.response_body, existing.response_status or 201

        # 1. Lock group FOR UPDATE
        group = groups_repo.lock_for_update_by_public_id(session, group_public_id)
        if group is None:
            raise NotFoundError(f"Group '{group_public_id}' not found")

        # 2. Validate participants
        debtor = users_repo.get_by_public_id(session, payload.from_user)
        creditor = users_repo.get_by_public_id(session, payload.to_user)

        if debtor is None or not groups_repo.is_member(session, group.id, debtor.id):
            raise ParticipantNotMemberError(
                f"User '{payload.from_user}' is not a member of group '{group_public_id}'"
            )

        if creditor is None or not groups_repo.is_member(session, group.id, creditor.id):
            raise ParticipantNotMemberError(
                f"User '{payload.to_user}' is not a member of group '{group_public_id}'"
            )

        if debtor.id == creditor.id:
            raise ValidationError("Cannot settle balance with oneself")

        # 3. Parse amount
        try:
            amount_paise = parse_rupees(payload.amount)
        except MoneyError as exc:
            raise ValidationError(str(exc)) from exc

        # 4. Check overpayment against current pairwise debt
        expenses = list(session.scalars(select(Expense).where(Expense.group_id == group.id)).all())
        shares = list(
            session.scalars(
                select(ExpenseShare)
                .join(Expense, ExpenseShare.expense_id == Expense.id)
                .where(Expense.group_id == group.id)
            ).all()
        )
        settlements = list(
            session.scalars(select(Settlement).where(Settlement.group_id == group.id)).all()
        )

        net_map = net_balances(expenses, shares, settlements)
        debtor_net = net_map.get(debtor.id, 0)
        creditor_net = net_map.get(creditor.id, 0)

        # Maximum allowable settlement: debtor cannot repay more than their net debt,
        # and creditor cannot receive more than their net credit.
        max_allowed = min(max(0, -debtor_net), max(0, creditor_net))

        if amount_paise > max_allowed or max_allowed == 0:
            raise OverpaymentError(
                f"Settlement amount ({format_paise(amount_paise)}) exceeds current allowable debt "
                f"({format_paise(max_allowed)}) from {debtor.name} to {creditor.name}"
            )

        # 5. Insert settlement
        settlement = settlements_repo.create(
            session=session,
            group_id=group.id,
            from_user=debtor.id,
            to_user=creditor.id,
            amount_paise=amount_paise,
            status="CONFIRMED",
            method=payload.method,
        )

        # 6. Append ledger entry
        ledger_payload = {
            "settlement_id": settlement.id,
            "from_user": debtor.id,
            "to_user": creditor.id,
            "amount_paise": amount_paise,
            "method": settlement.method,
            "status": settlement.status,
        }
        ledger_repo.append(
            session=session,
            group_id=group.id,
            entry_type="SETTLEMENT",
            ref_id=settlement.id,
            payload=ledger_payload,
        )

        response_data: dict[str, Any] = {
            "id": settlement.public_id,
            "group_id": group.public_id,
            "from_user": {"id": debtor.public_id, "name": debtor.name},
            "to_user": {"id": creditor.public_id, "name": creditor.name},
            "amount": format_paise(settlement.amount_paise),
            "status": settlement.status,
            "method": settlement.method,
            "created_at": settlement.created_at.isoformat(),
        }

        # 7. Persist idempotency record
        if idempotency_key is not None:
            idempotency_repo.save(
                session=session,
                scope=f"group:{group.public_id}",
                key=idempotency_key,
                request_fingerprint=fingerprint,
                response_status=201,
                response_body=response_data,
            )

        return response_data, 201


def list_settlements(
    session: Session,
    group_public_id: str,
    limit: int = 20,
    cursor: str | None = None,
) -> tuple[list[dict[str, Any]], str | None]:
    """List settlements for a group using keyset pagination."""
    with session.begin():
        group = groups_repo.get_by_public_id(session, group_public_id)
        if group is None:
            raise NotFoundError(f"Group '{group_public_id}' not found")

        stmt = select(Settlement).where(Settlement.group_id == group.id)

        if cursor is not None:
            created_at_bound, id_bound = decode_cursor(cursor)
            stmt = stmt.where(
                or_(
                    Settlement.created_at < created_at_bound,
                    and_(
                        Settlement.created_at == created_at_bound,
                        Settlement.id < id_bound,
                    ),
                )
            )

        stmt = stmt.order_by(Settlement.created_at.desc(), Settlement.id.desc()).limit(limit + 1)
        results = list(session.scalars(stmt).all())

        if len(results) > limit:
            paginated = results[:limit]
            last_stl = paginated[-1]
            next_cursor = encode_cursor(last_stl.created_at, last_stl.id)
            items_to_render = paginated
        else:
            next_cursor = None
            items_to_render = results

        # Fetch users
        user_ids = set()
        for stl in items_to_render:
            user_ids.add(stl.from_user)
            user_ids.add(stl.to_user)

        user_map = {
            u.id: u for u in session.scalars(select(User).where(User.id.in_(user_ids))).all()
        }

        items = [
            {
                "id": stl.public_id,
                "group_id": group.public_id,
                "from_user": {
                    "id": user_map[stl.from_user].public_id,
                    "name": user_map[stl.from_user].name,
                },
                "to_user": {
                    "id": user_map[stl.to_user].public_id,
                    "name": user_map[stl.to_user].name,
                },
                "amount": format_paise(stl.amount_paise),
                "status": stl.status,
                "method": stl.method,
                "created_at": stl.created_at.isoformat(),
            }
            for stl in items_to_render
        ]

        return items, next_cursor
