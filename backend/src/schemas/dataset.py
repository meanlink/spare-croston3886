from pydantic import BaseModel, Field
class DatasetInput(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    source: str = Field(default='manual.json', max_length=200)
    records: list[dict] = Field(min_length=5, max_length=5000)
class MergePreviewInput(BaseModel):
    source: str = Field(default='redelivery.json', max_length=200)
    records: list[dict] = Field(min_length=1, max_length=5000)
class MergeResolution(BaseModel):
    part: str = Field(min_length=1, max_length=120)
    day: str = Field(min_length=4, max_length=40)
    demand: float | None = None
class MergeCommitInput(MergePreviewInput):
    name: str = Field(min_length=2, max_length=160)
    resolutions: list[MergeResolution] = Field(default_factory=list, max_length=5000)
