from __future__ import annotations

import json
from pathlib import Path
from typing import Union

from .schemas import PRReviewEvaluationDataset


def load_pr_review_dataset(dataset_path: Union[str, Path]) -> PRReviewEvaluationDataset:
    path = Path(dataset_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    return PRReviewEvaluationDataset.model_validate(data)

