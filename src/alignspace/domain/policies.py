class DomainRuleError(ValueError):
    """Raised when a change violates a domain invariant."""


class StaleStateError(ValueError):
    """Raised when a patch was generated from an older state version."""
