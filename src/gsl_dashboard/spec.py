"""Pure, frozen request data shared by codegen and the runner.

A :class:`RequestSpec` is one chosen dataset (product id + the active parameter values +
the variables selected for the panel layout). A :class:`RunRequest` bundles one or more
specs with a global time range. Both are plain data so codegen (what we *show*) and the
runner (what we *execute*) can never drift in intent — they consume the same object.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RequestSpec:
    dataset_id: str
    params: dict[str, Any] = field(default_factory=dict)
    variables: tuple[str, ...] = ()

    def with_variables(self, variables) -> "RequestSpec":
        return RequestSpec(self.dataset_id, dict(self.params), tuple(variables))


@dataclass(frozen=True)
class RunRequest:
    datasets: tuple[RequestSpec, ...]
    dt_fr: dt.datetime
    dt_to: dt.datetime
    title: str = ""

    @property
    def span_hours(self) -> float:
        return (self.dt_to - self.dt_fr).total_seconds() / 3600.0

    @property
    def is_single(self) -> bool:
        return len(self.datasets) == 1
