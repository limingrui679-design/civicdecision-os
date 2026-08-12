"""Typed project errors."""


class CivicDecisionError(Exception):
    """Base error for expected CivicDecision failures."""


class ProtocolError(CivicDecisionError):
    """A protocol document could not be parsed or validated."""


class EvidenceGateError(ProtocolError):
    """An output attempted to claim a stronger evidence type than supported."""


class ConnectorError(CivicDecisionError):
    """A public-data connector failed safely."""


class IntegrityError(CivicDecisionError):
    """A content hash, count, or other integrity invariant failed."""


class AnalysisError(CivicDecisionError):
    """An analytical run failed a declared input or execution invariant."""
