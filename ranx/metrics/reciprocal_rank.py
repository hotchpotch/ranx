from typing import Union

import numba
import numpy as np
from numba import config, njit, prange

config.THREADING_LAYER = "workqueue"

from .common import _clean_qrels, fix_k


# LOW LEVEL FUNCTIONS ==========================================================
@njit(cache=True)
def _reciprocal_rank(qrels, run, k):
    qrels = _clean_qrels(qrels.copy())
    if len(qrels) == 0:
        return 0.0

    k = fix_k(k, run)

    for i in range(k):
        if run[i, 0] in qrels[:, 0]:
            return 1 / (i + 1)
    return 0.0


@njit(cache=True, parallel=True)
def _reciprocal_rank_parallel(qrels, run, k):
    scores = np.zeros((len(qrels)), dtype=np.float64)
    for i in prange(len(qrels)):
        scores[i] = _reciprocal_rank(qrels[i], run[i], k)
    return scores


# HIGH LEVEL FUNCTIONS =========================================================
def reciprocal_rank(
    qrels: Union[np.ndarray, numba.typed.List],
    run: Union[np.ndarray, numba.typed.List],
    k: int = 0,
) -> np.ndarray:
    r"""Compute Reciprocal Rank (at k).

    The Reciprocal Rank is the multiplicative inverse of the rank of the first retrieved relevant document: 1 for first place, 1/2 for second place, 1/3 for third place, and so on.<br />
    If k > 0, only the top-k retrieved documents are considered.

    $$
    Reciprocal Rank = \frac{1}{rank}
    $$

    where,

    - $rank$ is the position of the first retrieved relevant document.

    Args:
        qrels (Union[np.ndarray, numba.typed.List]): IDs and relevance scores of _relevant_ documents.

        run (Union[np.ndarray, numba.typed.List]): IDs and relevance scores of _retrieved_ documents.

        k (int, optional): This argument is ignored. It was added to standardize metrics' input. Defaults to 0.

    Returns:
        Reciprocal Rank (at k) scores.

    """

    assert k >= 0, "k must be grater or equal to 0"

    return _reciprocal_rank_parallel(qrels, run, k)