import time
import random
import functools
import sys

PANGLOSS_QUOTES = [
    "Private misfortunes make the general good.",
    "All is for the best in the best of all possible worlds.",
    "Everything is made for a purpose.",
    "Observe that noses were made to wear spectacles; and so we have spectacles.",
    "It is demonstrable that things cannot be otherwise than as they are.",
    "Warning ignored. All is for the best in the best of all possible worlds."
]

def log_pangloss(message: str, quote: bool = True):
    if quote:
        q = random.choice(PANGLOSS_QUOTES)
        print(f"[Pangloss] {message} \"{q}\"", file=sys.stderr)
    else:
        print(f"[Pangloss] {message}", file=sys.stderr)

def retry_with_pangloss(max_retries=3, initial_delay=2):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            delay = initial_delay
            last_exception = None
            for i in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if i < max_retries - 1:
                        log_pangloss(f"API Rate Limit Hit or Error. Retrying in {delay}s...")
                        time.sleep(delay)
                        delay *= 2
                    else:
                        log_pangloss(f"Final failure after {max_retries} attempts.")
            raise last_exception
        return wrapper
    return decorator
