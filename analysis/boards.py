import itertools, random, math

PREDS = [p for p in itertools.permutations(range(10), 3)]   # 720 ordered distinct
SETS  = list(itertools.combinations(range(10), 3))           # 120 unordered
print(f"prediction space: {len(PREDS)} ordered / {len(SETS)} unordered sets\n")

def outcome(c): return tuple(sorted(range(10), key=lambda d:(-c[d], d))[:3])
def dist(p,w):  return sum(abs(a-b) for a,b in zip(p,w))
def raw(p,c):   return c[p[0]]+c[p[1]]+c[p[2]]                # user's idea 2
def wtd(p,c):   return 3*c[p[0]]+2*c[p[1]]+1*c[p[2]]          # position-weighted variant

# ── how many distinct ranks does each board actually produce? ──
def tiers(c):
    return (len(set(raw(p,c) for p in PREDS)), len(set(wtd(p,c) for p in PREDS)))

def counts(blocs, n=500_000):
    rest=(1-sum(blocs.values()))/10
    probs=[blocs.get(d,0)+rest for d in range(10)]
    out=[]; rem=n; rp=1.0
    for p in probs[:-1]:
        q=p/rp if rp>0 else 0
        k=int(round(random.gauss(rem*q, math.sqrt(max(rem*q*(1-q),0)))))
        k=min(max(k,0),rem); out.append(k); rem-=k; rp-=p
    out.append(rem); return out

print("Distinct leaderboard tiers (of 720 possible predictions)")
print(f"  {'scenario':<26}{'raw vote-sum':>14}{'weighted 3/2/1':>16}")
for label,b in [("uniform voting",{}),("one bloc 30%",{7:.30}),("two blocs 30/20",{7:.30,3:.20})]:
    c=counts(b); r,w=tiers(c)
    print(f"  {label:<26}{r:>10} tiers{w:>11} tiers")

# ── the key fairness property of the weighted board ──
print("\nCost of misordering two adjacent positions = the vote margin you misread")
c=counts({7:.30, 3:.20}); w=outcome(c)
print(f"  winner {''.join(map(str,w))}   counts: "
      + "  ".join(f"{d}:{c[d]:,}" for d in w))
swap23=(w[0],w[2],w[1]); swap12=(w[1],w[0],w[2])
print(f"  perfect          weighted {wtd(w,c):,}")
print(f"  swap pos 2 and 3 weighted {wtd(swap23,c):,}  cost {wtd(w,c)-wtd(swap23,c):,}"
      f"  (= margin between digits {w[1]} and {w[2]} = {c[w[1]]-c[w[2]]:,})")
print(f"  swap pos 1 and 2 weighted {wtd(swap12,c):,}  cost {wtd(w,c)-wtd(swap12,c):,}"
      f"  (= margin between digits {w[0]} and {w[1]} = {c[w[0]]-c[w[1]]:,})")
print("  -> misordering two near-tied digits barely hurts. Distance cannot do this.")

# ── contrast with digit distance on the same round ──
print(f"\nSame round, digit distance:")
for name,p in [("perfect",w),("swap pos 2/3",swap23),("swap pos 1/2",swap12)]:
    print(f"  {name:<14} distance {dist(p,w):>2}")
worst=max(itertools.permutations(w), key=lambda p: dist(p,w))
print(f"  worst permutation {''.join(map(str,worst))} distance {dist(worst,w)} "
      f"vs mean {sum(dist(p,w) for p in PREDS)/720:.1f} over all 720")

# ── tier sizes at 500k players, uniform guessing ──
print("\nTier population at N=500,000 (uniform guessing over 720)")
for name,frac in [("TRIFECTA  exact order",1/720),("BOXED     right 3, any order",5/720),
                  ("distance 1",6/720),("distance 2",15/720)]:
    print(f"  {name:<30} ~{int(500_000*frac):>6,} players")
import itertools, random, math, statistics
PREDS=[p for p in itertools.permutations(range(10),3)]
def outcome(c): return tuple(sorted(range(10),key=lambda d:(-c[d],d))[:3])
def wtd(p,c):   return 3*c[p[0]]+2*c[p[1]]+1*c[p[2]]
def counts(blocs,n=500_000):
    rest=(1-sum(blocs.values()))/10
    probs=[blocs.get(d,0)+rest for d in range(10)]
    out=[];rem=n;rp=1.0
    for p in probs[:-1]:
        q=p/rp if rp>0 else 0
        k=int(round(random.gauss(rem*q,math.sqrt(max(rem*q*(1-q),0)))))
        k=min(max(k,0),rem);out.append(k);rem-=k;rp-=p
    out.append(rem);return out

print("Normalised mandate score = weighted sum as % of the trifecta's score")
print("Distribution over all 720 predictions:\n")
print(f"  {'scenario':<20}{'max':>7}{'p90':>8}{'median':>8}{'min':>8}{'spread':>9}")
for label,b in [("uniform voting",{}),("one bloc 30%",{7:.30}),
                ("two blocs 30/20",{7:.30,3:.20}),("three blocs",{7:.30,3:.20,1:.12})]:
    c=counts(b); w=outcome(c); top=wtd(w,c)
    s=sorted(100*wtd(p,c)/top for p in PREDS)
    print(f"  {label:<20}{s[-1]:>6.1f}%{s[int(.9*720)]:>7.1f}%"
          f"{statistics.median(s):>7.1f}%{s[0]:>7.1f}%{s[-1]-s[0]:>8.1f}pt")

print("\nHow much does copying the visible top-3 actually win you?")
print("A copier picks the standings' top 3 in order; blackout then shifts the counts.")
for label,b in [("uniform voting",{}),("one bloc 30%",{7:.30})]:
    gaps=[]; beaten=[]
    for _ in range(400):
        pre=counts(b, 480_000)                      # visible at T+23
        late=counts(b, 20_000)                      # the dark hour
        final=[pre[d]+late[d] for d in range(10)]
        copier=outcome(pre)                          # copy what was visible
        true=outcome(final)
        top=wtd(true,final)
        gaps.append(100*wtd(copier,final)/top)
        beaten.append(sum(1 for p in PREDS if wtd(p,final)>wtd(copier,final)))
    print(f"  {label:<20}copier scores {statistics.mean(gaps):.2f}% of max, "
          f"beaten by {statistics.mean(beaten):.1f} of 720 predictions")
