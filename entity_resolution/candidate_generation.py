"""Candidate generation: blocking, so we never do O(N²) comparisons.

With ~90K operational property mentions and ~860K reference lots, the naive
cross product is ~7.7e10 comparisons. Blocking on (borough, house_number)
reduces that to comparing each mention only against lots that share its
house number in its borough — the only pairs that could plausibly be the
same building. Block-size caps guard against pathological keys, and every
skip is counted and logged, never silent (Phase 16/18).
"""

import logging
from collections import defaultdict
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class BlockingStats:
    total_left: int = 0
    total_right: int = 0
    comparisons: int = 0
    mentions_with_candidates: int = 0
    mentions_without_block_key: int = 0
    oversize_blocks_skipped: int = 0
    skipped_keys: list = field(default_factory=list)

    @property
    def naive_comparisons(self) -> int:
        return self.total_left * self.total_right

    @property
    def reduction_pct(self) -> float:
        if not self.naive_comparisons:
            return 0.0
        return 100.0 * (1 - self.comparisons / self.naive_comparisons)

    def summary(self) -> dict:
        return {
            "comparisons": self.comparisons,
            "naive_comparisons": self.naive_comparisons,
            "reduction_pct": round(self.reduction_pct, 4),
            "mentions_without_block_key": self.mentions_without_block_key,
            "oversize_blocks_skipped": self.oversize_blocks_skipped,
        }


def build_block_index(rows: list[dict], key_fields: tuple[str, ...]) -> dict[tuple, list[dict]]:
    """Index rows by blocking key; rows missing any key component are excluded."""
    index: dict[tuple, list[dict]] = defaultdict(list)
    for row in rows:
        key = tuple(row.get(f) for f in key_fields)
        if any(v is None or v == "" for v in key):
            continue
        index[key].append(row)
    return dict(index)


def iter_candidates(
    left_rows: list[dict],
    right_index: dict[tuple, list[dict]],
    key_fields: tuple[str, ...],
    max_block_size: int,
    stats: BlockingStats,
):
    """Yield (left_row, [candidate_rows]) for each left row with a usable block.

    ``right_index`` comes from build_block_index over the reference side.
    """
    oversize_seen: set[tuple] = set()
    for row in left_rows:
        key = tuple(row.get(f) for f in key_fields)
        if any(v is None or v == "" for v in key):
            stats.mentions_without_block_key += 1
            continue
        candidates = right_index.get(key, [])
        if not candidates:
            continue
        if len(candidates) > max_block_size:
            stats.oversize_blocks_skipped += 1
            if key not in oversize_seen:
                oversize_seen.add(key)
                stats.skipped_keys.append({"key": key, "size": len(candidates)})
                logger.warning(
                    "oversize_block_skipped",
                    extra={"block_key": str(key), "size": len(candidates), "cap": max_block_size},
                )
            continue
        stats.comparisons += len(candidates)
        stats.mentions_with_candidates += 1
        yield row, candidates
