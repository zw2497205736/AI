from pydantic import BaseModel, Field


class GitHubRepositoryCreatePayload(BaseModel):
    repo_owner: str = Field(min_length=1, max_length=100)
    repo_name: str = Field(min_length=1, max_length=100)
    display_name: str = Field(min_length=1, max_length=255)
    github_token: str = Field(min_length=1, max_length=255)
    webhook_secret: str = Field(min_length=8, max_length=255)

