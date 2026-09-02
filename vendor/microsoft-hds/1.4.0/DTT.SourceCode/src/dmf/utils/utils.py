from collections.abc import Iterable
from concurrent.futures import Executor
from typing import Callable, Optional, Sequence, TypeVar, Union
from common.model.immutable_model import ImmutableModel

T = TypeVar('T')
R = TypeVar('R')
A = TypeVar('A')


def _is_iterable(obj):
    if isinstance(obj, ImmutableModel):
        return False
    return isinstance(obj, Iterable)


def parallel_process(executor: Executor,
                     func: Callable[[T], R],
                     inputs: Union[Sequence[T], Sequence[Sequence[T]]],
                     aggregator: Optional[Callable[[Sequence[R]], A]] = None) -> Union[Sequence[R], A]:
    """Parallel processing of a function with a list of inputs
    args:
    executor: concurrent.futures.Executor
    func: function to be executed
    inputs: list of inputs to be passed to func. can be a list of (tuples, lists), or single values
    aggregator: function to aggregate the results
    """
    results = []
    futures = []
    for args in inputs:
        if _is_iterable(args):
            future = executor.submit(func, *args)
        else:
            future = executor.submit(func, args)
        futures.append(future)
    for future in futures:
        results.append(future.result())
    if aggregator is not None:
        return aggregator(results)
    return results
