from typing import Any

from pydantic import BaseModel, Field, field_validator


class KeywordItem(BaseModel):
    word: str
    weight: float


class CoLoanBook(BaseModel):
    bookname: str
    isbn13: str
    authors: str


class TranslationSignals(BaseModel):
    detected: bool
    hints: list[str] = Field(default_factory=list)


class EvidenceAvailability(BaseModel):
    keywords: bool
    description: bool
    co_loan_books: bool
    translation_signals: bool


class BiblioSchema(BaseModel):
    found: bool
    isbn_ea: str = ""
    isbn_add_code: str = ""
    set_isbn: str = ""
    set_add_code: str = ""
    set_expression: str = ""
    price: str = ""
    title: str = ""
    author: str = ""
    volume: str = ""
    pub_place: str = ""
    publisher: str = ""
    publish_year: str = ""
    publish_predate: str = ""
    kdc: str = ""
    kdc_edition: str = ""
    kdc_name: str = ""
    ddc: str = ""
    ddc_edition: str = ""
    subject: str = ""
    edition_stmt: str = ""
    series_title: str = ""
    series_no: str = ""
    page: str = ""
    book_size: str = ""
    form: str = ""
    ebook_yn: str = ""
    description: str = ""
    control_no: str = ""
    cover_url: str = ""
    toc_url: str = ""
    intro_url: str = ""
    field_sources: dict[str, str] = Field(default_factory=dict)


class EvidenceSchema(BaseModel):
    keywords: list[KeywordItem] = Field(default_factory=list)
    description: str = ""
    co_loan_books: list[CoLoanBook] = Field(default_factory=list)
    title: str = ""
    author: str = ""
    kdc_from_api: str = ""
    ddc_from_api: str = ""
    translation_signals: TranslationSignals
    available: EvidenceAvailability


class LookupResponseSchema(BaseModel):
    isbn: str
    biblio: BiblioSchema
    evidence: EvidenceSchema
    raw: dict[str, Any] = Field(default_factory=dict)


class BulkIsbnRequest(BaseModel):
    isbns: list[str]

    @field_validator("isbns")
    @classmethod
    def check_limit(cls, value: list[str]) -> list[str]:
        if len(value) == 0:
            raise ValueError("ISBN 목록이 비어 있습니다.")
        if len(value) > 10:
            raise ValueError("한 번에 최대 10개까지 조회할 수 있습니다.")
        return value
