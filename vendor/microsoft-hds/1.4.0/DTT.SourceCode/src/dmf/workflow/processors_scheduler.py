from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from typing import List, Tuple

from common.utils.logging import Logger
from dmf.transformations.processor.target_processor import TargetProcessor


class TargetProcessorsGroup:
    def __init__(self) -> None:
        self.processors: List[TargetProcessor] = []

    def add(self, processor: TargetProcessor):
        self.processors.append(processor)

    def process(self) -> None:
        for processor in self.processors:
            processor.process()


class TargetProcessorScheduler:
    @staticmethod
    def schedule(processors: List[TargetProcessor]):
        if not processors:
            raise ValueError("No processors to schedule")
        storage_processors_and_tables = [(p, p.target_id) for p in processors]
        batches: List[TargetProcessorsGroup] = TargetProcessorScheduler._group_processors_by_target_id(storage_processors_and_tables)
        TargetProcessorScheduler._run_in_parallel(batches)

    @staticmethod
    def _group_processors_by_target_id(processors: List[Tuple[TargetProcessor, str]]) -> List[TargetProcessorsGroup]:
        batches_by_target_id = defaultdict(lambda: TargetProcessorsGroup())
        for processor, target_id in processors:
            batches_by_target_id[target_id].add(processor)
        return list(batches_by_target_id.values())

    @staticmethod
    def _run_in_parallel(processor_groups: List[TargetProcessorsGroup]):
        num_workers = TargetProcessorScheduler.compute_workers(processor_groups)
        Logger.info(f"Running {num_workers} batches of processors in parallel: {[len(pg.processors) for pg in processor_groups]}")
        futures = []
        with ThreadPoolExecutor(max_workers=num_workers, thread_name_prefix="processor") as executor:
            for processor_group in processor_groups:
                futures.append(executor.submit(processor_group.process))
        for future in futures:
            future.result()

    @staticmethod
    def compute_workers(processor_groups):
        return len(processor_groups)
