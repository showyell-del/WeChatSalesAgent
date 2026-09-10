from typing import List, Literal, Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)


IntentBand = Literal["高意向", "待激活", "长期培育", "排除"]


class LeadJudgment(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    customer_id: StrictStr = Field(min_length=1)
    intent_score: StrictInt = Field(ge=0, le=100)
    intent_band: IntentBand
    recent_contact_ts: StrictInt = Field(gt=0)
    evidence_ids: List[StrictStr] = Field(min_length=1, max_length=12)
    obstacles: List[StrictStr] = Field(max_length=5)
    suggested_action: StrictStr = Field(min_length=1, max_length=400)
    draft_text: Optional[StrictStr] = Field(default=None, max_length=1000)
    draft_evidence_ids: List[StrictStr] = Field(default_factory=list, max_length=8)

    @field_validator("evidence_ids", "draft_evidence_ids")
    @classmethod
    def unique_ids(cls, value):
        if len(value) != len(set(value)):
            raise ValueError("evidence IDs must be unique")
        return value

    @model_validator(mode="after")
    def score_matches_band(self):
        if self.intent_score >= 80:
            expected = "高意向"
        elif self.intent_score >= 55:
            expected = "待激活"
        elif self.intent_score >= 30:
            expected = "长期培育"
        else:
            expected = "排除"
        if self.intent_band != expected:
            raise ValueError("intent band does not match score thresholds")
        return self


class ProviderLeadJudgment(BaseModel):
    """DeepSeek may judge evidence, but it may not author outbound copy."""

    model_config = ConfigDict(extra="forbid", strict=True)

    customer_id: StrictStr = Field(min_length=1)
    intent_score: StrictInt = Field(ge=0, le=100)
    intent_band: IntentBand
    recent_contact_ts: StrictInt = Field(gt=0)
    evidence_ids: List[StrictStr] = Field(min_length=1, max_length=12)
    obstacles: List[StrictStr] = Field(max_length=5)
    suggested_action: StrictStr = Field(min_length=1, max_length=400)

    @field_validator("evidence_ids")
    @classmethod
    def unique_ids(cls, value):
        if len(value) != len(set(value)):
            raise ValueError("evidence IDs must be unique")
        return value

    @model_validator(mode="after")
    def score_matches_band(self):
        expected = (
            "高意向"
            if self.intent_score >= 80
            else "待激活"
            if self.intent_score >= 55
            else "长期培育"
            if self.intent_score >= 30
            else "排除"
        )
        if self.intent_band != expected:
            raise ValueError("intent band does not match score thresholds")
        return self


class ProviderUsage(BaseModel):
    model_config = ConfigDict(extra="allow", strict=True)

    prompt_tokens: StrictInt = Field(ge=0)
    prompt_cache_hit_tokens: StrictInt = Field(ge=0)
    prompt_cache_miss_tokens: StrictInt = Field(ge=0)
    completion_tokens: StrictInt = Field(ge=0)
    total_tokens: StrictInt = Field(ge=0)

    @model_validator(mode="after")
    def totals_match(self):
        if (
            self.prompt_tokens
            != self.prompt_cache_hit_tokens + self.prompt_cache_miss_tokens
        ):
            raise ValueError("prompt token breakdown mismatch")
        if self.total_tokens != self.prompt_tokens + self.completion_tokens:
            raise ValueError("total token mismatch")
        return self


class BusinessProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    business_name: StrictStr = Field(min_length=1, max_length=120)
    products: List[StrictStr] = Field(min_length=1, max_length=50)
    prices: List[StrictStr] = Field(default_factory=list, max_length=50)
    offers: List[StrictStr] = Field(default_factory=list, max_length=50)
    address: StrictStr = Field(default="", max_length=300)
    business_hours: StrictStr = Field(default="", max_length=300)
    allowed_claims: List[StrictStr] = Field(default_factory=list, max_length=100)
    forbidden_claims: List[StrictStr] = Field(default_factory=list, max_length=100)
    lead_keywords: List[StrictStr] = Field(min_length=1, max_length=100)
    minor_data_approved: StrictBool = False
    external_api_data_transfer_approved: StrictBool = False

    @field_validator(
        "products",
        "prices",
        "offers",
        "allowed_claims",
        "forbidden_claims",
        "lead_keywords",
    )
    @classmethod
    def normalized_nonempty_unique_values(cls, value):
        normalized = [item.strip() for item in value]
        if any(not item for item in normalized):
            raise ValueError("business truth list values must not be blank")
        if len(normalized) != len(set(normalized)):
            raise ValueError("business truth list values must be unique")
        return normalized
