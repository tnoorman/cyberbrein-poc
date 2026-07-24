from dataclasses import dataclass


class PipelineRuntimeError(RuntimeError):
    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(category)


@dataclass(frozen=True, slots=True)
class PipelineResult:
    measurement_round_id: str
    ingestion_accepted_count: int
    ingestion_rejected_count: int
    ingestion_rejection_reasons: dict[str, int]
    processing_accepted_count: int
    processing_rejected_count: int
    processing_rejection_reasons: dict[str, int]
    finding_count: int
