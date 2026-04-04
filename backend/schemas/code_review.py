from pydantic import BaseModel


class CodeReviewStreamRequest(BaseModel):
    code: str = ""
    language: str = "diff"

