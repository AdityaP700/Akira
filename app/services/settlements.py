"""Service layer for Settlement transactions, payment lifecycle, and webhook callbacks."""

import hashlib
import json
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.keys import KeyProvider
from app.adapters.notifier import DbNotifier, Notifier
from app.adapters.payment_provider import MockPaymentProvider, PaymentProvider
from app.api.schemas.settlements import ProviderWebhookIn, SettlementIn
from app.core.errors import (
    IdempotencyKeyReusedError,
    InvalidTransitionError,
    NotFoundError,
    OverpaymentError,
    ParticipantNotMemberError,
    ValidationError,
)
from app.core.ids import new_reference_id
from app.core.pagination import decode_cursor, encode_cursor
from app.domain.balances import net_balances
from app.domain.money import MoneyError, format_paise, parse_rupees
from app.domain.settlement_state import (
    METHOD_UPI,
    STATUS_CLAIMED,
    STATUS_CONFIRMED,
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_REJECTED,
    STATUS_SUCCESS,
    can_transition,
    is_terminal_status,
)
from app.repositories import groups as groups_repo
from app.repositories import idempotency as idempotency_repo
from app.repositories import ledger as ledger_repo
from app.repositories import settlements as settlements_repo
from app.repositories import users as users_repo
from app.repositories.models import Expense, ExpenseShare, Settlement, User
from app.security.guards import require_member, require_member_and_lock
from app.security.signatures import verify_webhook_signature

logger = logging.getLogger("app.services.settlements")


def record_settlement(
    session: Session,
    group_public_id: str,
    payload: SettlementIn,
    actor: User | None = None,
    idempotency_key: str | None = None,
    http_method: str = "POST",
    http_path: str = "/groups/{group_id}/settlements",
    canonical_body: str = "",
    payment_provider: PaymentProvider | None = None,
    notifier: Notifier | None = None,
    key_provider: KeyProvider | None = None,
) -> tuple[dict[str, Any], int]:
    """Record a settlement payment following two-phase foreign call pattern and state machine.

    State logic:
    - UPI: Starts PENDING. Provider intent created outside DB transaction.
    - Manual/Direct:
      - If creator is to_user (receiver recording payment received): immediately CONFIRMED.
      - If creator is from_user (payer claiming payment): CLAIMED (awaits receiver confirmation).
      - Third-party: CLAIMED.
    """
    if payment_provider is None:
        payment_provider = MockPaymentProvider()
    if notifier is None:
        notifier = DbNotifier()

    fingerprint = ""
    # Idempotency check before work
    if idempotency_key is not None:
        raw_fingerprint = f"{http_method.upper()}:{http_path}:{canonical_body}"
        fingerprint = hashlib.sha256(raw_fingerprint.encode("utf-8")).hexdigest()

        with session.begin():
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

    reference = new_reference_id()
    method = payload.method.upper()
    amount_paise = 0
    settlement_id = 0
    creditor_id = 0
    debtor_public_id = ""
    creditor_public_id = ""
    debtor_name = ""
    creditor_name = ""
    settlement_public_id = ""
    settlement_status = ""
    created_at_iso = ""

    # Phase 1: Local DB transaction holding group lock
    with session.begin():
        if actor is not None:
            group = require_member_and_lock(session, group_public_id, actor)
        else:
            raw_group = groups_repo.lock_for_update_by_public_id(session, group_public_id)
            if raw_group is None:
                raise NotFoundError(f"Group '{group_public_id}' not found")
            group = raw_group

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

        try:
            amount_paise = parse_rupees(payload.amount)
        except MoneyError as exc:
            raise ValidationError(str(exc)) from exc

        # Calculate allowable debt bounds including in-flight PENDING/CLAIMED reservations
        expenses = list(session.scalars(select(Expense).where(Expense.group_id == group.id)).all())
        shares = list(
            session.scalars(
                select(ExpenseShare)
                .join(Expense, ExpenseShare.expense_id == Expense.id)
                .where(Expense.group_id == group.id)
            ).all()
        )
        all_settlements = list(
            session.scalars(select(Settlement).where(Settlement.group_id == group.id)).all()
        )

        net_map = net_balances(expenses, shares, all_settlements)
        debtor_net = net_map.get(debtor.id, 0)
        creditor_net = net_map.get(creditor.id, 0)

        max_allowed = min(max(0, -debtor_net), max(0, creditor_net))

        # In-flight reservation: settlements already PENDING or CLAIMED between this pair
        in_flight_paise = sum(
            s.amount_paise
            for s in all_settlements
            if s.from_user == debtor.id
            and s.to_user == creditor.id
            and s.status in (STATUS_PENDING, STATUS_CLAIMED)
        )
        available_debt = max(0, max_allowed - in_flight_paise)

        if amount_paise > available_debt or available_debt == 0:
            raise OverpaymentError(
                f"Settlement amount ({format_paise(amount_paise)}) exceeds current available debt "
                f"({format_paise(available_debt)}) from {debtor.name} to {creditor.name}"
            )

        # Determine initial status
        if method == METHOD_UPI:
            settlement_status = STATUS_PENDING
        elif method == "CASH":
            if actor is not None and actor.id == creditor.id:
                settlement_status = STATUS_CONFIRMED
            else:
                settlement_status = STATUS_CLAIMED
        else:
            settlement_status = STATUS_CONFIRMED

        creator_id = actor.id if actor else None
        settlement = settlements_repo.create(
            session=session,
            group_id=group.id,
            from_user=debtor.id,
            to_user=creditor.id,
            amount_paise=amount_paise,
            status=settlement_status,
            method=method,
            created_by=creator_id,
            reference=reference,
        )

        settlement_id = settlement.id
        settlement_public_id = settlement.public_id
        creditor_id = creditor.id
        debtor_public_id = debtor.public_id
        debtor_name = debtor.name
        creditor_public_id = creditor.public_id
        creditor_name = creditor.name
        created_at_iso = settlement.created_at.isoformat()

        # If immediately confirmed, append to ledger
        if settlement_status == STATUS_CONFIRMED:
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
            notifier.notify(
                session=session,
                user_id=debtor.id,
                event_type="SETTLEMENT_CONFIRMED",
                title="Settlement Confirmed",
                message=(
                    f"{creditor.name} confirmed receiving payment of ₹{format_paise(amount_paise)}."
                ),
                group_id=group.id,
                data={"settlement_id": settlement.public_id, "amount_paise": amount_paise},
            )
        elif settlement_status == STATUS_CLAIMED:
            notifier.notify(
                session=session,
                user_id=creditor.id,
                event_type="SETTLEMENT_CLAIMED",
                title="Settlement Claimed",
                message=(
                    f"{debtor.name} claimed a payment of ₹{format_paise(amount_paise)} to you."
                    " Please confirm or reject."
                ),
                group_id=group.id,
                data={"settlement_id": settlement.public_id, "amount_paise": amount_paise},
            )

    # Phase 2: Call provider outside DB transaction if method == UPI
    upi_link: str | None = None
    if method == METHOD_UPI:
        payee_vpa = payload.payee_vpa
        if not payee_vpa and key_provider is not None:
            from app.services.users import get_decrypted_user_vpa

            with session.begin():
                payee_vpa = get_decrypted_user_vpa(
                    session, creditor_id, creditor_public_id, key_provider
                )

        intent = payment_provider.create_collect(
            reference=reference,
            amount_paise=amount_paise,
            payee_vpa=payee_vpa,
        )
        upi_link = intent.upi_link

        # Phase 3: Short transaction to store intent info
        with session.begin():
            st = settlements_repo.get_by_id(session, settlement_id)
            if st is not None:
                st.provider_intent = {
                    "upi_link": intent.upi_link,
                    "status": intent.status,
                    "metadata": intent.metadata,
                }

    response_data: dict[str, Any] = {
        "id": settlement_public_id,
        "group_id": group_public_id,
        "from_user": {"id": debtor_public_id, "name": debtor_name},
        "to_user": {"id": creditor_public_id, "name": creditor_name},
        "amount": format_paise(amount_paise),
        "status": settlement_status,
        "method": method,
        "reference": reference,
        "upi_link": upi_link,
        "created_at": created_at_iso,
        "updated_at": created_at_iso,
    }

    # Save idempotency record
    if idempotency_key is not None:
        with session.begin():
            idempotency_repo.save(
                session=session,
                scope=f"group:{group_public_id}",
                key=idempotency_key,
                request_fingerprint=fingerprint,
                response_status=201,
                response_body=response_data,
            )

    return response_data, 201


def confirm_settlement(
    session: Session,
    group_public_id: str,
    settlement_public_id: str,
    actor: User,
    notifier: Notifier | None = None,
) -> dict[str, Any]:
    """Receiver confirms a claimed manual settlement."""
    if notifier is None:
        notifier = DbNotifier()

    with session.begin():
        group = require_member_and_lock(session, group_public_id, actor)

        settlement = settlements_repo.get_by_public_id(session, settlement_public_id)
        if settlement is None or settlement.group_id != group.id:
            raise NotFoundError(f"Settlement '{settlement_public_id}' not found")

        # Authorization: only the receiver (to_user) can confirm
        if settlement.to_user != actor.id:
            raise NotFoundError(f"Settlement '{settlement_public_id}' not found")

        if not can_transition(settlement.status, STATUS_CONFIRMED):
            raise InvalidTransitionError(
                f"Cannot confirm settlement currently in '{settlement.status}' status"
            )

        settlement.status = STATUS_CONFIRMED

        # Append ledger entry
        ledger_payload = {
            "settlement_id": settlement.id,
            "from_user": settlement.from_user,
            "to_user": settlement.to_user,
            "amount_paise": settlement.amount_paise,
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

        debtor = users_repo.get_by_id(session, settlement.from_user)
        debtor_name = debtor.name if debtor else ""
        debtor_public_id = debtor.public_id if debtor else ""

        notifier.notify(
            session=session,
            user_id=settlement.from_user,
            event_type="SETTLEMENT_CONFIRMED",
            title="Settlement Confirmed",
            message=(
                f"{actor.name} confirmed your payment of ₹{format_paise(settlement.amount_paise)}."
            ),
            group_id=group.id,
            data={"settlement_id": settlement.public_id, "amount_paise": settlement.amount_paise},
        )

        upi_link = None
        if settlement.provider_intent:
            upi_link = settlement.provider_intent.get("upi_link")

        return {
            "id": settlement.public_id,
            "group_id": group.public_id,
            "from_user": {"id": debtor_public_id, "name": debtor_name},
            "to_user": {"id": actor.public_id, "name": actor.name},
            "amount": format_paise(settlement.amount_paise),
            "status": settlement.status,
            "method": settlement.method,
            "reference": settlement.reference,
            "upi_link": upi_link,
            "created_at": settlement.created_at,
            "updated_at": settlement.updated_at,
        }


def reject_settlement(
    session: Session,
    group_public_id: str,
    settlement_public_id: str,
    actor: User,
    notifier: Notifier | None = None,
) -> dict[str, Any]:
    """Receiver rejects a claimed manual settlement."""
    if notifier is None:
        notifier = DbNotifier()

    with session.begin():
        group = require_member_and_lock(session, group_public_id, actor)

        settlement = settlements_repo.get_by_public_id(session, settlement_public_id)
        if settlement is None or settlement.group_id != group.id:
            raise NotFoundError(f"Settlement '{settlement_public_id}' not found")

        # Authorization: only the receiver (to_user) can reject
        if settlement.to_user != actor.id:
            raise NotFoundError(f"Settlement '{settlement_public_id}' not found")

        if not can_transition(settlement.status, STATUS_REJECTED):
            raise InvalidTransitionError(
                f"Cannot reject settlement currently in '{settlement.status}' status"
            )

        settlement.status = STATUS_REJECTED

        debtor = users_repo.get_by_id(session, settlement.from_user)
        debtor_name = debtor.name if debtor else ""
        debtor_public_id = debtor.public_id if debtor else ""

        notifier.notify(
            session=session,
            user_id=settlement.from_user,
            event_type="SETTLEMENT_REJECTED",
            title="Settlement Rejected",
            message=(
                f"{actor.name} rejected your settlement claim of"
                f" ₹{format_paise(settlement.amount_paise)}."
            ),
            group_id=group.id,
            data={"settlement_id": settlement.public_id, "amount_paise": settlement.amount_paise},
        )

        upi_link = None
        if settlement.provider_intent:
            upi_link = settlement.provider_intent.get("upi_link")

        return {
            "id": settlement.public_id,
            "group_id": group.public_id,
            "from_user": {"id": debtor_public_id, "name": debtor_name},
            "to_user": {"id": actor.public_id, "name": actor.name},
            "amount": format_paise(settlement.amount_paise),
            "status": settlement.status,
            "method": settlement.method,
            "reference": settlement.reference,
            "upi_link": upi_link,
            "created_at": settlement.created_at,
            "updated_at": settlement.updated_at,
        }


def refresh_settlement_status(
    session: Session,
    group_public_id: str,
    settlement_public_id: str,
    actor: User,
    payment_provider: PaymentProvider | None = None,
    notifier: Notifier | None = None,
) -> dict[str, Any]:
    """Query provider status and apply state transition for in-flight settlement."""
    if payment_provider is None:
        payment_provider = MockPaymentProvider()
    if notifier is None:
        notifier = DbNotifier()

    # Read settlement
    with session.begin():
        group = require_member(session, group_public_id, actor)
        settlement = settlements_repo.get_by_public_id(session, settlement_public_id)
        if settlement is None or settlement.group_id != group.id:
            raise NotFoundError(f"Settlement '{settlement_public_id}' not found")

        ref = settlement.reference
        current_status = settlement.status

    if is_terminal_status(current_status) or ref is None:
        return _format_settlement_response(session, settlement_public_id)

    # Provider call outside transaction
    provider_status = payment_provider.get_status(ref)

    if provider_status.status != current_status and can_transition(
        current_status, provider_status.status
    ):
        with session.begin():
            # Lock group row
            groups_repo.lock_for_update_by_public_id(session, group_public_id)
            st = settlements_repo.get_by_reference(session, ref)
            if st and can_transition(st.status, provider_status.status):
                st.status = provider_status.status

                if st.status == STATUS_SUCCESS:
                    ledger_payload = {
                        "settlement_id": st.id,
                        "from_user": st.from_user,
                        "to_user": st.to_user,
                        "amount_paise": st.amount_paise,
                        "method": st.method,
                        "status": st.status,
                    }
                    ledger_repo.append(
                        session=session,
                        group_id=st.group_id,
                        entry_type="SETTLEMENT",
                        ref_id=st.id,
                        payload=ledger_payload,
                    )
                    notifier.notify(
                        session=session,
                        user_id=st.from_user,
                        event_type="SETTLEMENT_SUCCESS",
                        title="Payment Succeeded",
                        message=f"Payment of ₹{format_paise(st.amount_paise)} was confirmed.",
                        group_id=st.group_id,
                    )
                    notifier.notify(
                        session=session,
                        user_id=st.to_user,
                        event_type="SETTLEMENT_SUCCESS",
                        title="Payment Received",
                        message=f"Received payment of ₹{format_paise(st.amount_paise)}.",
                        group_id=st.group_id,
                    )
                elif st.status == STATUS_FAILED:
                    notifier.notify(
                        session=session,
                        user_id=st.from_user,
                        event_type="SETTLEMENT_FAILED",
                        title="Payment Failed",
                        message=f"Payment of ₹{format_paise(st.amount_paise)} failed.",
                        group_id=st.group_id,
                    )

    return _format_settlement_response(session, settlement_public_id)


def process_provider_webhook(
    session: Session,
    raw_body: bytes,
    signature_header: str | None,
    key_provider: KeyProvider,
    notifier: Notifier | None = None,
) -> tuple[dict[str, Any], int]:
    """Process signed webhook from payment provider with deduplication and state machine."""
    if notifier is None:
        notifier = DbNotifier()

    # 1. Raw body HMAC-SHA256 signature verification
    verify_webhook_signature(
        raw_body=raw_body,
        signature_header=signature_header,
        key_provider=key_provider,
    )

    # 2. Parse payload
    try:
        body_dict = json.loads(raw_body.decode("utf-8"))
        payload = ProviderWebhookIn.model_validate(body_dict)
    except Exception as exc:
        raise ValidationError(f"Invalid webhook payload: {exc}") from exc

    try:
        amount_paise = parse_rupees(payload.amount)
    except MoneyError as exc:
        raise ValidationError(str(exc)) from exc

    with session.begin():
        # 3. Deduplicate via provider_events table (UNIQUE event_id)
        existing_event = settlements_repo.get_provider_event(session, payload.event_id)
        if existing_event is not None:
            return {"status": "ok", "message": "Duplicate event ignored"}, 200

        # Record event first
        settlements_repo.record_provider_event(
            session=session,
            event_id=payload.event_id,
            reference=payload.reference,
            status=payload.status,
            amount_paise=amount_paise,
        )

        # 4. Find settlement by reference
        settlement = settlements_repo.get_by_reference(session, payload.reference)
        if settlement is None:
            logger.warning("Webhook received for unknown reference: %s", payload.reference)
            return {"status": "ok", "message": "Unknown reference"}, 200

        # Lock group row
        groups_repo.lock_for_update(session, settlement.group_id)

        # Verify amount matches settlement
        if settlement.amount_paise != amount_paise:
            raise ValidationError(
                f"Webhook amount ({format_paise(amount_paise)}) does not match "
                f"settlement amount ({format_paise(settlement.amount_paise)})"
            )

        # 5. Check transition validity
        target_status = payload.status
        if not can_transition(settlement.status, target_status):
            # Out-of-order or late event: ignore without error per spec
            logger.warning(
                "Ignoring out-of-order webhook transition from %s to %s for reference %s",
                settlement.status,
                target_status,
                settlement.reference,
            )
            return {"status": "ok", "message": "Transition ignored (out of order)"}, 200

        # Apply state transition
        settlement.status = target_status

        if target_status == STATUS_SUCCESS:
            ledger_payload = {
                "settlement_id": settlement.id,
                "from_user": settlement.from_user,
                "to_user": settlement.to_user,
                "amount_paise": settlement.amount_paise,
                "method": settlement.method,
                "status": settlement.status,
            }
            ledger_repo.append(
                session=session,
                group_id=settlement.group_id,
                entry_type="SETTLEMENT",
                ref_id=settlement.id,
                payload=ledger_payload,
            )
            notifier.notify(
                session=session,
                user_id=settlement.from_user,
                event_type="SETTLEMENT_SUCCESS",
                title="Payment Succeeded",
                message=f"UPI payment of ₹{format_paise(settlement.amount_paise)} was confirmed.",
                group_id=settlement.group_id,
                data={"settlement_id": settlement.public_id, "reference": settlement.reference},
            )
            notifier.notify(
                session=session,
                user_id=settlement.to_user,
                event_type="SETTLEMENT_SUCCESS",
                title="Payment Received",
                message=f"Received UPI payment of ₹{format_paise(settlement.amount_paise)}.",
                group_id=settlement.group_id,
                data={"settlement_id": settlement.public_id, "reference": settlement.reference},
            )
        elif target_status == STATUS_FAILED:
            notifier.notify(
                session=session,
                user_id=settlement.from_user,
                event_type="SETTLEMENT_FAILED",
                title="Payment Failed",
                message=f"UPI payment of ₹{format_paise(settlement.amount_paise)} failed.",
                group_id=settlement.group_id,
                data={"settlement_id": settlement.public_id, "reference": settlement.reference},
            )

        return {
            "status": "ok",
            "reference": settlement.reference,
            "new_status": settlement.status,
        }, 200


def list_settlements(
    session: Session,
    group_public_id: str,
    actor: User,
    cursor: str | None = None,
    limit: int = 20,
) -> tuple[list[dict[str, Any]], str | None]:
    """List settlements in a group ordered newest first with keyset pagination."""
    cursor_id: int | None = None
    if cursor is not None:
        _, cursor_id = decode_cursor(cursor)

    with session.begin():
        group = require_member(session, group_public_id, actor)

        raw_settlements = settlements_repo.list_by_group(
            session=session,
            group_id=group.id,
            cursor=cursor_id,
            limit=limit + 1,
        )

        has_more = len(raw_settlements) > limit
        items = raw_settlements[:limit]

        user_ids = {s.from_user for s in items} | {s.to_user for s in items}
        users = list(session.scalars(select(User).where(User.id.in_(user_ids))).all())
        user_map = {u.id: u for u in users}

        result = []
        for s in items:
            debtor = user_map.get(s.from_user)
            creditor = user_map.get(s.to_user)
            upi_link = None
            if s.provider_intent:
                upi_link = s.provider_intent.get("upi_link")

            result.append(
                {
                    "id": s.public_id,
                    "group_id": group.public_id,
                    "from_user": {
                        "id": debtor.public_id if debtor else "",
                        "name": debtor.name if debtor else "",
                    },
                    "to_user": {
                        "id": creditor.public_id if creditor else "",
                        "name": creditor.name if creditor else "",
                    },
                    "amount": format_paise(s.amount_paise),
                    "status": s.status,
                    "method": s.method,
                    "reference": s.reference,
                    "upi_link": upi_link,
                    "created_at": s.created_at,
                    "updated_at": s.updated_at,
                }
            )

        next_cursor = None
        if has_more and items:
            last = items[-1]
            next_cursor = encode_cursor(last.created_at, last.id)

        return result, next_cursor


def _format_settlement_response(session: Session, settlement_public_id: str) -> dict[str, Any]:
    with session.begin():
        st = settlements_repo.get_by_public_id(session, settlement_public_id)
        if st is None:
            raise NotFoundError(f"Settlement '{settlement_public_id}' not found")

        group = groups_repo.get_by_id(session, st.group_id)
        debtor = users_repo.get_by_id(session, st.from_user)
        creditor = users_repo.get_by_id(session, st.to_user)

        upi_link = None
        if st.provider_intent:
            upi_link = st.provider_intent.get("upi_link")

        return {
            "id": st.public_id,
            "group_id": group.public_id if group else "",
            "from_user": {
                "id": debtor.public_id if debtor else "",
                "name": debtor.name if debtor else "",
            },
            "to_user": {
                "id": creditor.public_id if creditor else "",
                "name": creditor.name if creditor else "",
            },
            "amount": format_paise(st.amount_paise),
            "status": st.status,
            "method": st.method,
            "reference": st.reference,
            "upi_link": upi_link,
            "created_at": st.created_at,
            "updated_at": st.updated_at,
        }
