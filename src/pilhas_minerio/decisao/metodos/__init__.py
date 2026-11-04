"""Métodos de apoio à decisão; cada um é um módulo que se registra em ``METHODS``."""
from .base import METHODS, DecisionMethod, MethodResult, ranking_from_scores, register_method

__all__ = ["METHODS", "DecisionMethod", "MethodResult", "ranking_from_scores", "register_method"]
