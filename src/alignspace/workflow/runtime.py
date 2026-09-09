import sqlite3

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver

from alignspace.agents.contracts import AgentBundle
from alignspace.workflow.graph import build_graph


def memory_graph(agents: AgentBundle):
    return build_graph(agents, InMemorySaver())


def sqlite_graph(agents: AgentBundle, path: str):
    connection = sqlite3.connect(path, check_same_thread=False)
    return build_graph(agents, SqliteSaver(connection))
