"""Schema definitions for literature corpus."""

from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Literal


class PaperEntry(BaseModel):
    """A single paper in the literature corpus."""

    doi: Optional[str] = Field(default=None, description="Digital Object Identifier")
    arxiv_id: Optional[str] = Field(default=None, description="arXiv identifier")
    pubmed_id: Optional[str] = Field(default=None, description="PubMed identifier")
    title: str = Field(..., min_length=5, description="Paper title")
    authors: List[str] = Field(..., min_length=1, description="List of author names")
    year: int = Field(..., ge=1900, le=2030, description="Publication year")
    journal: Optional[str] = Field(default=None, description="Journal name")
    abstract: Optional[str] = Field(default=None, description="Paper abstract")
    citations: Optional[int] = Field(default=None, ge=0, description="Citation count")
    relevance_score: Optional[float] = Field(default=None, ge=0, le=1, description="Relevance to project (0-1)")
    verification_status: Literal["verified", "unverified", "retracted", "expression_of_concern"] = Field(
        default="unverified", description="Citation verification status"
    )

    @field_validator("title")
    @classmethod
    def title_must_be_substantive(cls, v: str) -> str:
        if len(v.strip()) < 5:
            raise ValueError("Paper title must be at least 5 characters")
        return v.strip()


class LiteratureCorpus(BaseModel):
    """Complete literature corpus for a project."""

    schema_version: str = Field(..., pattern=r"^\d+\.\d+\.\d+$")
    papers: List[PaperEntry] = Field(..., min_length=1)
    search_queries: List[str] = Field(default=[], description="Search queries used to build corpus")
    last_updated: str = Field(..., description="ISO 8601 timestamp of last update")

    @field_validator("papers")
    @classmethod
    def at_least_one_paper(cls, v: List[PaperEntry]) -> List[PaperEntry]:
        if len(v) < 1:
            raise ValueError("Corpus must contain at least one paper")
        return v
