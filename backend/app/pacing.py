from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
from typing import Any

CHECK_EVERY = 1024


class PacedSequence(Sequence):
    """Sequence view that consults a deadline callback while it is iterated.

    Helpers that loop over every record of a Workorder keep their code and gain
    time-budget enforcement, which matters when one Workorder owns most records.
    """

    def __init__(self, items: Sequence[Any], checkpoint: Callable[[], None]):
        self._items = items
        self._checkpoint = checkpoint

    def __len__(self) -> int:
        return len(self._items)

    def __getitem__(self, index):
        return self._items[index]

    def __iter__(self) -> Iterator[Any]:
        for position, item in enumerate(self._items):
            if position % CHECK_EVERY == 0:
                self._checkpoint()
            yield item


def paced(items: Sequence[Any], checkpoint: Callable[[], None] | None) -> Sequence[Any]:
    return items if checkpoint is None else PacedSequence(items, checkpoint)
