"""Pure business rules for the round lifecycle.

Depends on nothing: no database, no clock, no framework, not even `engine`.
Everything here is a function of its arguments, so it is exhaustively testable
without infrastructure.
"""
