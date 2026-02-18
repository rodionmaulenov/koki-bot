from dataclasses import dataclass


class OCRServerError(Exception):
    """Raised when OCR fails due to API/server error (not photo quality)."""


@dataclass
class PassportResult:
    is_document: bool
    last_name: str | None
    first_name: str | None
    patronymic: str | None
    birth_date: str | None


@dataclass
class ReceiptResult:
    is_document: bool
    has_kok: bool
    price: int | None


@dataclass
class CardResult:
    is_document: bool
    card_number: str | None
    card_holder: str | None
