"""Progress reporting for the loops that make one API request per item."""

from __future__ import annotations

import sys
from collections.abc import Iterable

from tqdm import tqdm


def with_progress[T](items: Iterable[T], description: str, unit: str) -> Iterable[T]:
    """Wrap an iterable in a progress bar, silent whenever stderr is not a terminal."""
    return tqdm(items, desc=description, unit=unit, disable=not sys.stderr.isatty())
