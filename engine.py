"""Game Engine: owns the full puzzle, hidden statuses and face-down clues.

Owner: Engine & Puzzle.
Only this module may read Cell.status of unsolved cells and clues of face-down cards.
Input / output of every function: docs/INTERFACES.md.
"""
from agent import LogicAgent
from model import Puzzle

ACCEPTED = "ACCEPTED"
NOT_PROVABLE = "NOT_PROVABLE"
CONTRADICTED = "CONTRADICTED"


class GameEngine:
    def __init__(self, puzzle: Puzzle, agent: LogicAgent | None = None):
        self.puzzle = puzzle
        self.agent = agent or LogicAgent()
        self.restart()

    def restart(self) -> None:
        """Back to the initial state: only puzzle.revealed cards are face-up."""
        raise NotImplementedError

    def public_state(self) -> dict:
        """Everything the agent / GUI may see.

        {
          "rows": int, "cols": int,
          "cells": [{"cell", "name", "job"}],          # every cell, no status
          "revealed": {cell: clue},                     # face-up clues only
          "verdicts": {cell: "CRIMINAL" | "INNOCENT"},  # proved statuses only
        }
        """
        raise NotImplementedError

    def submit(self, cell: str, verdict: str) -> str:
        """A verdict from the player or the agent: ACCEPTED | NOT_PROVABLE | CONTRADICTED.

        Decide with LogicAgent.classify(public_state). On ACCEPTED, record the verdict
        and flip the card. On rejection, change nothing.
        """
        raise NotImplementedError

    def is_solved(self) -> bool:
        raise NotImplementedError
