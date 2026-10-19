"""Request bodies for the TCP Lab API (pydantic checks the ranges)."""

from pydantic import BaseModel, Field


class SimulateRequest(BaseModel):
    scenario: str = Field(..., examples=["S2"])
    variant: str = Field(..., examples=["3_losses"])
    algorithms: list[str] = Field(default=["tahoe", "reno", "newreno"], min_length=1, max_length=3)
    seed: int = Field(default=1, ge=1, le=1000)
    # 1 = one simulated second per real second
    speed: float = Field(default=1.0, ge=0.25, le=50.0)


class ReplayRequest(BaseModel):
    scenario: str = Field(..., examples=["S3"])
    variant: str = Field(..., examples=["loss_1pct"])
    run: int = Field(default=1, ge=1, le=100)
    speed: float = Field(default=1.0, ge=0.25, le=50.0)
