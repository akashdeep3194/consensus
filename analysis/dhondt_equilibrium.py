"""
Project Consensus 3D - outcome-shape analysis for finding F1.

Question: how concentrated must the vote be before the three-digit outcome
collapses to a repdigit (AAA), making it trivially predictable?

Result: the transition is a sharp threshold in the leading digit's vote share,
with a closed form under a uniform tail. Verified against exact rational
arithmetic below.
"""
from fractions import Fraction

def allocate(counts, divisor, slots=3):
    """Highest-quotient allocation. Ties resolve permanently to the lower digit."""
    won = [0] * 10
    result = []
    for _ in range(slots):
        best = None
        for d in range(10):
            q = Fraction(counts[d], divisor(won[d]))
            if best is None or q > best[0]:   # strict > keeps the LOWER digit on ties
                best = (q, d)
        won[best[1]] += 1
        result.append(best[1])
    return result

DHONDT       = lambda w: w + 1      # divisors 1, 2, 3
SAINTE_LAGUE = lambda w: 2 * w + 1  # divisors 1, 3, 5

def shape(result):
    return {1: "AAA", 2: "AAB", 3: "ABC"}[len(set(result))]

def profile(share, n=900_000):
    """Leading digit holds `share`; the other nine split the remainder evenly."""
    top = round(n * share)
    return [top] + [round((n - top) / 9)] * 9


def thresholds():
    print("Actual leading-digit vote share -> outcome shape (uniform tail)\n")
    print(f"{'share':>7}  {'D Hondt':>8}  {'Sainte-Lague':>13}")
    prev = None
    for i in range(100, 460, 5):
        s = i / 1000
        row = (shape(allocate(profile(s), DHONDT)),
               shape(allocate(profile(s), SAINTE_LAGUE)))
        mark = "  <- transition" if row != prev else ""
        if row != prev:
            print(f"{s:>6.1%}  {row[0]:>8}  {row[1]:>13}{mark}")
        prev = row

    print("\nClosed form, nine-digit uniform tail:")
    print(f"  D'Hondt        two slots at s > 2/11 = {2/11:.1%}"
          f"   full sweep at s > 1/4  = {1/4:.1%}")
    print(f"  Sainte-Lague   two slots at s > 1/4  = {1/4:.1%}"
          f"   full sweep at s > 5/14 = {5/14:.1%}")
    print("\nUncoordinated voting sits at 10.0% per digit -> ABC, always.")
    print("A single bloc holding 25% of the vote sweeps all three positions"
          " under D'Hondt.")


if __name__ == "__main__":
    thresholds()
