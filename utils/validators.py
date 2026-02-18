import re

_NAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z\s\-''']+$")
_MIN_WORD_LENGTH = 2
_MIN_WORDS = 2
_MAX_WORDS = 5


def validate_passport_name(raw: str) -> str | None:
    raw = raw.strip()

    if not _NAME_PATTERN.match(raw):
        return None

    words = raw.split()
    if len(words) < _MIN_WORDS or len(words) > _MAX_WORDS:
        return None

    for word in words:
        clean = word.strip("-'''")
        if len(clean) < _MIN_WORD_LENGTH:
            return None

    return raw.title()


_MIN_PRICE = 10
_MAX_PRICE = 100_000


def validate_receipt_price(raw: str) -> int | None:
    cleaned = raw.strip().replace(" ", "").replace(",", "").replace(".", "")

    if not cleaned.isdigit():
        return None

    price = int(cleaned)
    if price < _MIN_PRICE or price > _MAX_PRICE:
        return None

    return price


_CARD_NUMBER_LENGTH = 16


def validate_card_input(raw: str) -> tuple[str, str] | None:
    parts = raw.strip().split()
    if not parts:
        return None

    digit_parts: list[str] = []
    name_parts: list[str] = []
    found_name = False

    for part in parts:
        if not found_name and part.isdigit():
            digit_parts.append(part)
        else:
            found_name = True
            name_parts.append(part)

    if not digit_parts or not name_parts:
        return None

    card_number = "".join(digit_parts)
    if len(card_number) != _CARD_NUMBER_LENGTH:
        return None

    formatted_number = " ".join(
        card_number[i : i + 4] for i in range(0, _CARD_NUMBER_LENGTH, 4)
    )

    name = validate_passport_name(" ".join(name_parts))
    if name is None:
        return None

    return formatted_number, name
