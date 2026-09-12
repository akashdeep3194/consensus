"""Frozen version identifiers.

`ALGORITHM_VERSION` pins observable resolution behaviour. Any change to the
outcome rule, tier rule, mandate score, or canonical encoding MUST bump it —
the golden-vector test fails loudly otherwise.
"""

RULESET_VERSION = "1.1"
ALGORITHM_VERSION = "1.1.0"
