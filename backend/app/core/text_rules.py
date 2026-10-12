import re

CARD_NUMBER_PATTERN = re.compile(r"(?:\d[ -]?){13,19}")


def contains_card_number(text: str | None) -> bool:
    """True if the text holds something that looks like a full card number (13–19 digits)."""
    if not text:
        return False
    for match in CARD_NUMBER_PATTERN.finditer(text):
        digits = re.sub(r"\D", "", match.group())
        if 13 <= len(digits) <= 19:
            return True
    return False
