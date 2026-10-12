from typing import Annotated

from pydantic import AfterValidator, BaseModel, BeforeValidator, ConfigDict, StringConstraints

from app.core.text_rules import contains_card_number


def _no_card_number(value: str | None) -> str | None:
    if contains_card_number(value):
        raise ValueError("Do not enter card numbers — only the last 4 digits are stored, on the card record")
    return value


Email = Annotated[str, StringConstraints(strip_whitespace=True, max_length=150, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")]
SafeText = Annotated[str, AfterValidator(_no_card_number)]
Currency = Annotated[
    str,
    BeforeValidator(lambda v: v.strip().upper() if isinstance(v, str) else v),
    StringConstraints(pattern=r"^[A-Z]{3}$"),
]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Message(BaseModel):
    detail: str
