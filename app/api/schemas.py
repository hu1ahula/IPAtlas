from pydantic import BaseModel, Field


class BatchLookupRequest(BaseModel):
    ips: list[str] = Field(min_length=1)
    include_sources: bool = False


class RangeLookupRequest(BaseModel):
    start_ip: str
    end_ip: str


class BatchLookupResponse(BaseModel):
    count: int
    results: list[dict]

