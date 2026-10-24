class DomainError(Exception):
    """Base error untuk pelanggaran aturan domain; view menangkap dan menampilkan pesannya."""


class InvalidTransition(DomainError):
    """Transisi status tidak diizinkan oleh state machine."""


class BusinessRuleViolation(DomainError):
    """Pelanggaran aturan bisnis (BR-xx di SRS)."""
