import functools
import random
import time


def SyntheticId(original_class):
    orig_init = original_class.__init__
    # Make copy of original __init__, so we can call it without recursion

    def __init__(self, *args, **kws):
        self.id = random.randint(0, 1000000)
        orig_init(self, *args, **kws)  # Call the original __init__

    original_class.__init__ = __init__  # Set the class' __init__ to the new one
    return original_class


class Timed():
    def __init__(self, logger):
        self.logger = logger

    def __call__(self, func):

        @functools.wraps(func)
        def wrapper(wrapped_self, *args, **kwargs):
            try:
                _id: int = wrapped_self.id
            except AttributeError:
                raise ValueError(f"{wrapped_self} has no `id` attribute. Please use SyntheticId")
            t: float = time.time()
            result = func(wrapped_self, *args, **kwargs)
            elapsed_time = time.time() - t
            self.logger.info(f"{wrapped_self}[{_id}].{func.__name__} elapsed {elapsed_time:.2f} sec")
            return result
        return wrapper
