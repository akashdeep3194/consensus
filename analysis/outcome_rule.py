"""
Project Consensus 3D - V1.1 outcome rule.

    The winning number is the three most-voted digits, ranked by vote count,
    always distinct. Ties resolve to the lower digit.

Replaces the v2.1 D'Hondt allocation. See analysis/dhondt_equilibrium.py for the
measurement that motivated the change.
"""
import collections, math, random


def outcome(counts):
    """counts[0..9] -> [d1, d2, d3]. Sort by count descending, digit ascending."""
    return sorted(range(10), key=lambda d: (-counts[d], d))[:3]


def distance(prediction, winner):
    """Sum of absolute per-position digit distance."""
    return sum(abs(p - w) for p, w in zip(prediction, winner))


# ── rule verification ────────────────────────────────────────────────
def checks():
    print("Rule checks")
    print("  all zero votes     ->", outcome([0] * 10), " every count ties; lower digits win")
    c = [0] * 10; c[5] = 100; c[2] = 100; c[7] = 50
    print("  5:100 2:100 7:50   ->", outcome(c), " equal counts: lower digit ranks higher")
    c = [0] * 10; c[9] = 500; c[0] = 400; c[3] = 300
    print("  9:500 0:400 3:300  ->", outcome(c))
    print("  outcome space      =", 10 * 9 * 8, "ordered distinct triples")

    assert outcome([0] * 10) == [0, 1, 2]
    assert len(set(outcome([random.randrange(99) for _ in range(10)]))) == 3
    print("  determinism        : outcome is a pure function of the count vector")


# ── what coordination buys ───────────────────────────────────────────
def draw(probs, n):
    """Multinomial counts by normal approximation - fast and accurate at large n."""
    counts = []; remaining = n; rp = 1.0
    for p in probs[:-1]:
        q = p / rp if rp > 0 else 0
        k = int(round(random.gauss(remaining * q, math.sqrt(max(remaining * q * (1 - q), 0)))))
        k = min(max(k, 0), remaining)
        counts.append(k); remaining -= k; rp -= p
    counts.append(remaining)
    return counts


def mix(blocs):
    rest = (1 - sum(blocs.values())) / 10
    return [blocs.get(d, 0) + rest for d in range(10)]


def coordination(trials=6000, n=50_000):
    print("\nWhat coordination buys (50,000 voters, 6,000 rounds)\n")
    print(f"  {'scenario':<34}{'outcomes':>10}{'best guess':>12}")
    for label, blocs in [
        ("no coordination",              {}),
        ("one bloc, 30%",                {7: 0.30}),
        ("two blocs, 30% + 20%",         {7: 0.30, 3: 0.20}),
        ("three blocs, 30/20/12%",       {7: 0.30, 3: 0.20, 1: 0.12}),
    ]:
        seen = collections.Counter()
        for _ in range(trials):
            seen[tuple(outcome(draw(mix(blocs), n)))] += 1
        best = seen.most_common(1)[0][1] / trials
        print(f"  {label:<34}{len(seen):>6} /720{100*best:>11.1f}%")
    print("\n  One bandwagon locks position 1 and leaves 72 outcomes live - the")
    print("  interesting case. Fully solving the number needs three separately")
    print("  organised blocs holding deliberately different sizes.")


# ── the order penalty ────────────────────────────────────────────────
def order_penalty(w=(5, 2, 7)):
    import itertools
    distinct = [tuple(map(int, f"{i:03d}")) for i in range(1000) if len(set(f"{i:03d}")) == 3]
    mean = sum(distance(p, w) for p in distinct) / len(distinct)
    perms = [p for p in itertools.permutations(w) if p != w]
    print(f"\nOrder penalty, winner {''.join(map(str,w))}")
    print(f"  mean distance over all 720 distinct predictions: {mean:.1f}")
    for p in sorted(perms, key=lambda p: distance(p, w)):
        d = distance(p, w)
        flag = "  <- worse than a random guess" if d > mean else ""
        print(f"  {''.join(map(str,p))}  right digits, wrong order  distance {d:>2}{flag}")
    print(f"  427  one digit off by one            distance {distance((4,2,7), w):>2}")
    print("\n  Identifying all three winning digits but misordering them scores worse")
    print("  than guessing unrelated digits. See open question Q2.")


if __name__ == "__main__":
    checks(); coordination(); order_penalty()
