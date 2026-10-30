"""Service layer for Expense operations."""

import hashlib
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.adapters.keys import KeyProvider
from app.adapters.notifier import DbNotifier, Notifier
from app.api.schemas.expenses import ExpenseIn
from app.core.errors import (
    IdempotencyKeyReusedError,
    NotFoundError,
    ParticipantNotMemberError,
    PayerNotMemberError,
    ValidationError,
)
from app.core.pagination import decode_cursor, encode_cursor
from app.domain.money import MoneyError, format_paise, parse_rupees
from app.domain.splits import EqualSplit, ExactSplit, SharesSplit, SplitError
from app.repositories import expenses as expenses_repo
from app.repositories import groups as groups_repo
from app.repositories import idempotency as idempotency_repo
from app.repositories import ledger as ledger_repo
from app.repositories import users as users_repo
from app.repositories.models import Expense, User
from app.security.guards import require_member, require_member_and_lock


def create_expense(
    session: Session,
    group_public_id: str,
    payload: ExpenseIn,
    actor: User | None = None,
    idempotency_key: str | None = None,
    http_method: str = "POST",
    http_path: str = "/groups/{group_id}/expenses",
    canonical_body: str = "",
    notifier: Notifier | None = None,
    key_provider: KeyProvider | None = None,
) -> tuple[dict[str, Any], int]:
    """Atomically create an expense, shares, and ledger entry with idempotency.

    Transaction flow:
    1. Check idempotency record if key is present.
    2. Open transaction: lock group row (SELECT ... FOR UPDATE).
    3. Validate actor is member (OWASP API1).
    4. Validate payer is a member of the group.
    5. Validate split strategy and compute participant shares.
    6. Assert sum of shares equals total amount.
    7. Insert expense and expense_shares.
    8. Append ledger entry (payload contains ids and amounts only).
    9. Save idempotency record.
    10. Commit and return response data.
    """
    fingerprint = ""
    with session.begin():
        if idempotency_key is not None:
            raw_fingerprint = f"{http_method.upper()}:{http_path}:{canonical_body}"
            fingerprint = hashlib.sha256(raw_fingerprint.encode("utf-8")).hexdigest()

            # Check existing idempotency record
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

        # 1. Lock group row FOR UPDATE and check actor membership
        if actor is not None:
            group = require_member_and_lock(session, group_public_id, actor)
        else:
            raw_group = groups_repo.lock_for_update_by_public_id(session, group_public_id)
            if raw_group is None:
                raise NotFoundError(f"Group '{group_public_id}' not found")
            group = raw_group

        # 2. Validate payer
        payer = users_repo.get_by_public_id(session, payload.paid_by)
        if payer is None or not groups_repo.is_member(session, group.id, payer.id):
            raise PayerNotMemberError(
                f"Payer '{payload.paid_by}' is not a member of group '{group_public_id}'"
            )

        # 3. Parse and validate amount
        try:
            amount_paise = parse_rupees(payload.amount)
        except MoneyError as exc:
            raise ValidationError(str(exc)) from exc

        # 4. Fetch group members
        members = groups_repo.get_members(session, group.id)
        member_user_ids = {m.user_id for m in members}

        # 5. Compute split shares
        shares_dict: dict[int, int] = {}
        if payload.split_type == "EQUAL":
            participant_ids = sorted(list(member_user_ids))
            equal_strategy = EqualSplit()
            try:
                shares_dict = equal_strategy.compute(amount_paise, participant_ids)
            except SplitError as exc:
                raise ValidationError(str(exc)) from exc
        elif payload.split_type == "EXACT":
            if not payload.splits:
                raise ValidationError("EXACT split requires 'splits' list")

            spec: dict[int, int] = {}
            for s in payload.splits:
                part_user = users_repo.get_by_public_id(session, s.user_id)
                if part_user is None or part_user.id not in member_user_ids:
                    raise ParticipantNotMemberError(
                        f"Participant '{s.user_id}' is not a member of group '{group_public_id}'"
                    )
                try:
                    s_paise = parse_rupees(s.amount)
                except MoneyError as exc:
                    raise ValidationError(str(exc)) from exc
                spec[part_user.id] = s_paise

            exact_strategy = ExactSplit()
            try:
                shares_dict = exact_strategy.compute(amount_paise, list(spec.keys()), spec=spec)
            except SplitError as exc:
                raise ValidationError(str(exc)) from exc
        elif payload.split_type == "SHARES":
            if not payload.shares:
                raise ValidationError("SHARES split requires 'shares' list")

            shares_spec: dict[int, int] = {}
            for item in payload.shares:
                part_user = users_repo.get_by_public_id(session, item.user_id)
                if part_user is None or part_user.id not in member_user_ids:
                    raise ParticipantNotMemberError(
                        f"Participant '{item.user_id}' is not a member of group '{group_public_id}'"
                    )
                shares_spec[part_user.id] = item.weight

            shares_strategy = SharesSplit()
            try:
                shares_dict = shares_strategy.compute(
                    amount_paise, list(shares_spec.keys()), spec=shares_spec
                )
            except SplitError as exc:
                raise ValidationError(str(exc)) from exc
        else:
            raise ValidationError(f"Unsupported split type '{payload.split_type}'")

        # Invariant check: sum of shares must equal total amount
        if sum(shares_dict.values()) != amount_paise:
            raise ValidationError("Sum of shares does not equal amount")

        # 6. Insert expense and shares
        expense = expenses_repo.create(
            session=session,
            group_id=group.id,
            paid_by=payer.id,
            amount_paise=amount_paise,
            description=payload.description,
            split_type=payload.split_type,
            shares=shares_dict,
        )

        # 7. Insert append-only ledger entry (payload contains only IDs and amounts, no PII/names)
        ledger_payload = {
            "expense_id": expense.id,
            "paid_by": payer.id,
            "amount_paise": amount_paise,
            "split_type": payload.split_type,
            "shares": [{"user_id": uid, "amount_paise": owed} for uid, owed in shares_dict.items()],
        }
        ledger_repo.append(
            session=session,
            group_id=group.id,
            entry_type="EXPENSE",
            ref_id=expense.id,
            payload=ledger_payload,
            key_provider=key_provider,
        )

        if notifier is None:
            notifier = DbNotifier()

        for uid, owed in shares_dict.items():
            if uid != payer.id and owed > 0:
                notifier.notify(
                    session=session,
                    user_id=uid,
                    event_type="EXPENSE_CREATED",
                    title="New Expense Added",
                    message=(
                        f"{payer.name} added expense '{expense.description}' in '{group.name}'."
                        f" Your share is ₹{format_paise(owed)}."
                    ),
                    group_id=group.id,
                    data={
                        "expense_id": expense.public_id,
                        "amount_paise": amount_paise,
                        "owed_paise": owed,
                    },
                )

        # 8. Build response
        all_participant_users = list(
            session.scalars(select(User).where(User.id.in_(shares_dict.keys()))).all()
        )
        user_map = {u.id: u for u in all_participant_users}

        shares_out = [
            {
                "user_id": user_map[uid].public_id,
                "name": user_map[uid].name,
                "amount": format_paise(owed),
            }
            for uid, owed in sorted(shares_dict.items(), key=lambda x: user_map[x[0]].public_id)
        ]

        warning = None
        if len(member_user_ids) == 1 and payer.id in member_user_ids:
            warning = "NO_OTHER_PARTICIPANTS"

        response_data: dict[str, Any] = {
            "id": expense.public_id,
            "group_id": group.public_id,
            "description": expense.description,
            "amount": format_paise(expense.amount_paise),
            "paid_by": {
                "id": payer.public_id,
                "name": payer.name,
            },
            "split_type": expense.split_type,
            "created_at": expense.created_at.isoformat(),
            "shares": shares_out,
            "warning": warning,
        }

        # 9. Save idempotency record
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


def list_expenses(
    session: Session,
    group_public_id: str,
    actor: User | None = None,
    limit: int = 20,
    cursor: str | None = None,
) -> tuple[list[dict[str, Any]], str | None]:
    """List expenses for a group using keyset pagination."""
    with session.begin():
        if actor is not None:
            group = require_member(session, group_public_id, actor)
        else:
            raw_group = groups_repo.get_by_public_id(session, group_public_id)
            if raw_group is None:
                raise NotFoundError(f"Group '{group_public_id}' not found")
            group = raw_group

        stmt = (
            select(Expense, User)
            .join(User, Expense.paid_by == User.id)
            .where(Expense.group_id == group.id)
        )

        if cursor is not None:
            created_at_bound, id_bound = decode_cursor(cursor)
            stmt = stmt.where(
                or_(
                    Expense.created_at < created_at_bound,
                    and_(
                        Expense.created_at == created_at_bound,
                        Expense.id < id_bound,
                    ),
                )
            )

        stmt = stmt.order_by(Expense.created_at.desc(), Expense.id.desc()).limit(limit + 1)
        results = list(session.execute(stmt).all())

        if len(results) > limit:
            paginated = results[:limit]
            last_exp = paginated[-1][0]
            next_cursor = encode_cursor(last_exp.created_at, last_exp.id)
            items_to_render = paginated
        else:
            next_cursor = None
            items_to_render = results

        items = [
            {
                "id": exp.public_id,
                "description": exp.description,
                "amount": format_paise(exp.amount_paise),
                "paid_by": {
                    "id": payer.public_id,
                    "name": payer.name,
                },
                "split_type": exp.split_type,
                "created_at": exp.created_at.isoformat(),
            }
            for exp, payer in items_to_render
        ]

        return items, next_cursor
