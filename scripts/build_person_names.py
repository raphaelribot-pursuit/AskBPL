"""Patch 0064. Build packages/orchestrator/config/person_names.txt (see config/person_names_SOURCE.md): SSA names given to >=100 babies, minus ordinary words, calendar words and policy words."""
import collections, glob, sys
MIN_BIRTHS, POPULAR = 100, 50000
tot = collections.Counter()
for f in glob.glob("ssa/yob*.txt"):
    for line in open(f):
        n, _, c = line.strip().split(","); tot[n.lower()] += int(c)
words = {w.strip() for w in open("/usr/share/dict/words") if w.strip() and w[0].islower()}
CALENDAR = set("january february march april may june july august september october november december monday tuesday wednesday thursday friday saturday sunday easter christmas juneteenth thanksgiving".split())
# Capitalised words in the BPL policy texts that are names in the SSA data but are not people there (John, Melanie, Don are).
POLICY_WORDS = set("media brooklyn any general key see york loan branch manual special child page purpose chief other oral law case edit job add carry justice read press sincere english daily day author".split())
keep = {n for n, c in tot.items() if c >= MIN_BIRTHS and (n not in words or c >= POPULAR) and n not in POLICY_WORDS}
keep -= CALENDAR - {"may", "june", "august", "april"}  # month names that are also names stay, but only as AMBIGUOUS
out = sorted(keep)
open(sys.argv[1], "w").write("\n".join(out) + "\n")
print(len(out), "names written")
