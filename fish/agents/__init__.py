from .base import Agent
from .random_agent import RandomAgent
from .heuristic import HeuristicAgent
from .memory import MemoryAgent
from .probabilistic import ProbabilisticAgent
from .search import SearchAgent
from .paired_search import PairedSearchAgent

AGENT_REGISTRY = {
    "random": RandomAgent,
    "heuristic": HeuristicAgent,
    "memory": MemoryAgent,
    "probabilistic": ProbabilisticAgent,
    "search": SearchAgent,
    "paired_search": PairedSearchAgent,
}

__all__ = ["Agent", "RandomAgent", "HeuristicAgent", "MemoryAgent",
           "ProbabilisticAgent", "SearchAgent", "PairedSearchAgent",
           "AGENT_REGISTRY"]
