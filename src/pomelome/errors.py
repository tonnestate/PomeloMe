class PomeloError(Exception):
    """Base PomeloMe error."""


class AdmissionError(PomeloError):
    """A plan cannot be admitted safely."""


class AuthorizationError(PomeloError):
    """A concrete action is not authorized."""


class BudgetExceeded(PomeloError):
    """A hierarchical execution budget would be exceeded."""


class InvalidTransition(PomeloError):
    """A finite-state-machine transition is invalid."""


class ReplanRequired(PomeloError):
    """Deterministic execution reached a semantic decision boundary."""


class SimulatedCrash(PomeloError):
    """Used only by fault-injection tests to emulate process loss."""
