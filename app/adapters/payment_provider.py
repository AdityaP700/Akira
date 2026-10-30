"""Payment provider adapter interface and mock implementation."""

from dataclasses import dataclass, field
from typing import Any, Protocol

from app.domain.money import format_paise


@dataclass(frozen=True)
class ProviderIntent:
    reference: str
    amount_paise: int
    upi_link: str
    status: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProviderStatus:
    reference: str
    status: str  # "PENDING", "SUCCESS", "FAILED"
    amount_paise: int


class PaymentProvider(Protocol):
    """Protocol defining payment collection and status verification interface."""

    def create_collect(
        self, reference: str, amount_paise: int, payee_vpa: str | None = None
    ) -> ProviderIntent:
        """Create a payment collection request with UPI deep link."""
        ...

    def get_status(self, reference: str) -> ProviderStatus:
        """Query terminal or in-flight payment status from provider."""
        ...


class MockPaymentProvider:
    """Mock implementation of PaymentProvider simulating UPI payments and callbacks."""

    def __init__(self) -> None:
        self._intents: dict[str, ProviderStatus] = {}

    def create_collect(
        self, reference: str, amount_paise: int, payee_vpa: str | None = None
    ) -> ProviderIntent:
        vpa = payee_vpa or "merchant@upi"
        rupees = format_paise(amount_paise)
        upi_link = f"upi://pay?pa={vpa}&am={rupees}&tr={reference}&tn=Settlement"
        status_obj = ProviderStatus(
            reference=reference,
            status="PENDING",
            amount_paise=amount_paise,
        )
        self._intents[reference] = status_obj
        return ProviderIntent(
            reference=reference,
            amount_paise=amount_paise,
            upi_link=upi_link,
            status="PENDING",
            metadata={"payee_vpa": vpa, "gateway": "mock_upi"},
        )

    def get_status(self, reference: str) -> ProviderStatus:
        if reference in self._intents:
            return self._intents[reference]
        return ProviderStatus(reference=reference, status="PENDING", amount_paise=0)

    def set_status(self, reference: str, status: str) -> None:
        """Helper to mutate provider state in tests or dev simulation."""
        current = self._intents.get(reference)
        amount = current.amount_paise if current else 0
        self._intents[reference] = ProviderStatus(
            reference=reference,
            status=status,
            amount_paise=amount,
        )
