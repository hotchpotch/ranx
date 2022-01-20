import json
from collections import defaultdict
from typing import Dict, List

import numpy as np
import pandas as pd
from numba import types
from numba.typed import Dict as TypedDict
from numba.typed import List as TypedList

from .qrels_run_common import (
    add_and_sort,
    create_and_sort,
    sort_dict_by_key,
    sort_dict_of_dict_by_value,
    to_typed_list,
)


class Run(object):
    """`Run` stores the relevance scores estimated by the model under evaluation.\n
    The preferred way for creating a `Run` istance is converting a Python dictionary using [**from_dict**][ranx.Run.from_dict]:

    ```python
    run_dict = {
        "q_1": {
            "d_1": 1.5,
            "d_2": 2.6,
        },
        "q_2": {
            "d_3": 2.8,
            "d_2": 1.2,
            "d_5": 3.1,
        },
    }

    run = Run.from_dict(run_dict)
    ```
    """

    def __init__(self):
        self.run = TypedDict.empty(
            key_type=types.unicode_type,
            value_type=types.DictType(types.unicode_type, types.float64),
        )
        self.sorted = False
        self.name = None
        self.scores = defaultdict(dict)
        self.mean_scores = {}

    def keys(self):
        """Returns query ids. Used internally."""
        return self.run.keys()

    def add_score(self, q_id: str, doc_id: str, score: int):
        """Add a (doc_id, score) pair to a query (or, change its value if it already exists).

        Args:
            q_id (str): Query ID
            doc_id (str): Document ID
            score (int): Relevance score
        """
        if self.run.get(q_id) is None:
            self.run[q_id] = TypedDict.empty(
                key_type=types.unicode_type,
                value_type=types.float64,
            )
        self.run[q_id][doc_id] = float(score)
        self.sorted = False

    def add(self, q_id: str, doc_ids: List[str], scores: List[float]):
        """Add a query and its relevant documents with the associated relevance score.

        Args:
            q_id (str): Query ID
            doc_ids (List[str]): List of Document IDs
            scores (List[int]): List of relevance scores
        """
        self.add_multi([q_id], [doc_ids], [scores])

    def add_multi(
        self,
        q_ids: List[str],
        doc_ids: List[List[str]],
        scores: List[List[float]],
    ):
        """Add multiple queries at once.

        Args:
            q_ids (List[str]): List of Query IDs
            doc_ids (List[List[str]]): List of list of Document IDs
            scores (List[List[int]]): List of list of relevance scores
        """
        q_ids = TypedList(q_ids)
        doc_ids = TypedList([TypedList(x) for x in doc_ids])
        scores = TypedList([TypedList(map(float, x)) for x in scores])

        self.run = add_and_sort(self.run, q_ids, doc_ids, scores)
        self.sorted = True

    def get_query_ids(self):
        """Returns query ids."""
        return list(self.run.keys())

    def get_doc_ids_and_scores(self):
        """Returns doc ids and relevance scores."""
        return list(self.run.values())

    # Sort in place
    def sort(self):
        """Sort. Used internally."""
        self.run = sort_dict_by_key(self.run)
        self.run = sort_dict_of_dict_by_value(self.run)
        self.sorted = True

    def to_typed_list(self):
        """Convert Run to Numba Typed List. Used internally."""
        if self.sorted == False:
            self.sort()
        return to_typed_list(self.run)

    def to_dict(self):
        """Convert Run to Python dictionary.

        Returns:
            Dict[str, Dict[str, int]]: Run as Python dictionary
        """
        d = defaultdict(dict)
        for q_id in self.keys():
            d[q_id] = dict(self[q_id])
        return d

    def save(self, path: str = "run.txt"):
        """Write `run` to `path` in TREC run format or as JSON file.

        Args:
            path (str, optional): Saving path. Defaults to "run.txt".
            type (str, optional): Type of file to save, must be either "trec" or "json". Defaults to "trec".
        """
        assert type in {
            "trec",
            "json",
        }, "Error `type` must be 'trec' of 'json'"

        if self.sorted == False:
            self.sort()

        with open(path, "w") as f:
            if type == "trec":
                for i, q_id in enumerate(self.run.keys()):
                    for rank, doc_id in enumerate(self.run[q_id].keys()):
                        score = self.run[q_id][doc_id]
                        f.write(
                            f"{q_id} Q0 {doc_id} {rank+1} {score} {self.name}"
                        )

                        if (
                            i != len(self.run.keys()) - 1
                            or rank != len(self.run[q_id].keys()) - 1
                        ):
                            f.write("\n")
            else:
                f.write(json.dumps(self.to_dict(), indent=4))

    @staticmethod
    def from_dict(d: Dict[str, Dict[str, float]]):
        """Convert a Python dictionary in form of {q_id: {doc_id: score}} to ranx.Run.

        Args:
            d (Dict[str, Dict[str, int]]): Run as Python dictionary

        Returns:
            Run: ranx.Run
        """

        # Query IDs
        q_ids = list(d.keys())
        q_ids = TypedList(q_ids)

        # Doc IDs
        doc_ids = [list(doc.keys()) for doc in d.values()]
        max_len = max(len(y) for x in doc_ids for y in x)
        dtype = f"<U{max_len}"
        doc_ids = TypedList([np.array(x, dtype=dtype) for x in doc_ids])

        # Scores
        scores = [list(doc.values()) for doc in d.values()]
        scores = TypedList([np.array(x, dtype=float) for x in scores])

        run = Run()
        run.run = create_and_sort(q_ids, doc_ids, scores)
        run.sorted = True

        return run

    @staticmethod
    def from_file(path: str, type: str = "trec"):
        """Parse a run file into ranx.Run. Supported formats are TREC run format and JSON.

        Args:
            path (str): File path.
            type (str, optional): Type of file to load, must be either "trec" or "json". Defaults to "trec".

        Returns:
            Run: ranx.Run
        """
        assert type in {
            "trec",
            "json",
        }, "Error `type` must be 'trec' of 'json'"

        if type == "trec":
            run = defaultdict(dict)
            name = ""
            with open(path) as f:
                for line in f:
                    q_id, _, doc_id, _, rel, run_name = line.split()
                    run[q_id][doc_id] = float(rel)
                    if name == "":
                        name = run_name
        else:
            run = json.loads(open(path, "r").read())

        run = Run.from_dict(run)

        if type == "trec":
            run.name = name

        return run

    @staticmethod
    def from_df(
        df: pd.DataFrame,
        q_id_col: str = "q_id",
        doc_id_col: str = "doc_id",
        score_col: str = "score",
    ):
        """Convert a Pandas DataFrame to ranx.Run.

        Args:
            df (pd.DataFrame): Run as Pandas DataFrame
            q_id_col (str, optional): Query IDs column. Defaults to "q_id".
            doc_id_col (str, optional): Document IDs column. Defaults to "doc_id".
            score_col (str, optional): Relevance scores column. Defaults to "score".

        Returns:
            Run: ranx.Run
        """
        assert (
            df[q_id_col].dtype == "O"
        ), "DataFrame scores column dtype must be `object` (string)"
        assert (
            df[doc_id_col].dtype == "O"
        ), "DataFrame scores column dtype must be `object` (string)"
        assert (
            df[score_col].dtype == float
        ), "DataFrame scores column dtype must be `float`"

        run_py = (
            df.groupby(q_id_col)[[doc_id_col, score_col]]
            .apply(lambda g: {x[0]: x[1] for x in g.values.tolist()})
            .to_dict()
        )

        return Run.from_dict(run_py)

    @property
    def size(self):
        return len(self.run)

    def __getitem__(self, q_id):
        return dict(self.run[q_id])

    def __len__(self) -> int:
        return len(self.run)

    def __repr__(self):
        return self.run.__repr__()

    def __str__(self):
        return self.run.__str__()