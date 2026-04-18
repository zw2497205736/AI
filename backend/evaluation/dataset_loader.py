from __future__ import annotations

import json
from pathlib import Path
from typing import Union

from .schemas import EvaluationDataset


def load_dataset(dataset_path: Union[str, Path]) -> EvaluationDataset:
    path = Path(dataset_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    return EvaluationDataset.model_validate(data)
