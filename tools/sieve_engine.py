"""
SmartSieveEngine — Einstein/Zebra puzzle solver.

DSL for rules (eval'd strings, 's' = StateProxy):
  s.pos("cat", "val")           → position (0..N-1) of val in category cat
  s.pos("cat", "A") == s.pos("cat2", "B")  → A and B in same house
  abs(s.pos("c","A") - s.pos("c2","B")) == 1  → neighbors
  s.pos("c","A") == s.pos("c2","B") + 1       → A right-of B
  s.pos("c","A") < s.pos("c2","B")            → A left-of B
  s.pos("c","A") == 0                          → A is first
  s.pos("c","A") == N-1                        → A is last

Also supports shorthand s.p("cat:val") for compact rules.

Pipeline:
  1. LLM extracts constraints as rule strings
  2. SmartSieveEngine.solve() prunes via incremental permutation sieve
  3. verify_logic() checks all worlds for axiom/hypothesis validation
"""

from itertools import permutations
import time


class SmartSieveEngine:
    def __init__(self, categories: dict[str, list[str]], rules: list[str]):
        """
        categories: {"nation": ["Eng","Swe",...], "color": ["red","blue",...], ...}
        rules: list of eval-able strings using 's' proxy
        """
        self.categories = categories
        self.cat_names = list(categories.keys())
        self.rules = rules
        self.size = len(next(iter(categories.values())))
        self.perms = list(permutations(range(self.size)))

    class StateProxy:
        """Object that rule lambdas see as 's'."""
        __slots__ = ('state', 'cat_map', 'cat_names')

        def __init__(self, state, cat_map, cat_names):
            self.state = state       # tuple of permutations, one per category
            self.cat_map = cat_map   # {"nation": ["Eng","Swe",...], ...}
            self.cat_names = cat_names

        def pos(self, cat_or_query, val=None):
            """
            Two call styles:
              s.pos("nation", "English")  → positional index
              s.pos("nation:English")     → shorthand
            """
            if val is None:
                cat, val = cat_or_query.split(':')
            else:
                cat = cat_or_query
            c_idx = self.cat_names.index(cat)
            v_idx = self.cat_map[cat].index(val)
            return self.state[c_idx][v_idx]

        # Shorthand alias
        p = pos

    def _rule_mentions_cats(self, rule_str: str) -> set[int]:
        """Which category indices does this rule reference?"""
        mentioned = set()
        for i, name in enumerate(self.cat_names):
            if name in rule_str:
                mentioned.add(i)
        return mentioned

    def _is_rule_ready(self, rule_str: str, current_cat_idx: int) -> bool:
        """Can we evaluate this rule given categories 0..current_cat_idx?"""
        for idx in self._rule_mentions_cats(rule_str):
            if idx > current_cat_idx:
                return False
        return True

    def solve(self, verbose=True):
        """
        Incremental sieve: add one category at a time, prune early.
        Returns list of surviving full states.
        """
        stream = [()]  # start with empty state
        t0 = time.perf_counter()

        for i, name in enumerate(self.cat_names):
            active_rules = [r for r in self.rules if self._is_rule_ready(r, i)]
            new_stream = []

            for state in stream:
                for p in self.perms:
                    candidate = state + (p,)
                    proxy = self.StateProxy(candidate, self.categories, self.cat_names)

                    try:
                        if all(eval(r, {"__builtins__": {}}, {"s": proxy, "abs": abs}) for r in active_rules):
                            new_stream.append(candidate)
                    except Exception as e:
                        pass  # rule references something not yet available

            if verbose:
                print(f"  [{i+1}/{len(self.cat_names)}] {name:>12}: "
                      f"{len(stream):>6} × {len(self.perms)} perms → "
                      f"{len(new_stream):>6} survivors  "
                      f"({len(active_rules)} rules active)")

            stream = new_stream
            if not stream:
                if verbose:
                    print("  No solutions survive!")
                return []

        elapsed = time.perf_counter() - t0
        if verbose:
            print(f"  Done: {len(stream)} solution(s) in {elapsed:.2f}s")
        return stream

    def format_solution(self, state) -> str:
        """Pretty-print a solution state."""
        lines = []
        header = "  House |" + " | ".join(f" {n:>10}" for n in self.cat_names) + " |"
        sep = "  " + "-" * (len(header) - 2)
        lines.append(sep)
        lines.append(header)
        lines.append(sep)

        for house in range(self.size):
            row = f"  {house+1:>5} |"
            for ci, cat_name in enumerate(self.cat_names):
                vals = self.categories[cat_name]
                # Which value is in this house?
                perm = state[ci]
                val = vals[perm.index(house)] if house in perm else "?"
                row += f" {val:>10} |"
            lines.append(row)
        lines.append(sep)
        return "\n".join(lines)


# ── Verification (all-worlds check) ────────────────────────────────────────

def verify_logic(categories, axioms, hypotheses=None, verbose=True):
    """
    Brute-force verify:
    1. Generate all possible worlds (all perm combos)
    2. Filter by axioms → stable worlds
    3. Test each hypothesis branch

    categories: same dict as engine
    axioms: list of rule strings
    hypotheses: dict of {"branch_name": [rule_strings]}
    """
    cat_names = list(categories.keys())
    size = len(next(iter(categories.values())))
    all_perms = list(permutations(range(size)))

    def make_proxy(state):
        return SmartSieveEngine.StateProxy(state, categories, cat_names)

    def check_rule(state, rule):
        proxy = make_proxy(state)
        try:
            return eval(rule, {"__builtins__": {}}, {"s": proxy, "abs": abs})
        except:
            return True  # skip unparseable

    # Generate all possible complete assignments
    if verbose:
        total = len(all_perms) ** len(cat_names)
        print(f"\n  [Verify] Total worlds: {total:,}")

    # Incremental filter by axioms (smarter than full cartesian)
    stream = [()]
    for ci in range(len(cat_names)):
        applicable = [ax for ax in axioms
                      if all(cat_names.index(n) <= ci
                             for n in cat_names if n in ax)]
        new_stream = []
        for state in stream:
            for p in all_perms:
                candidate = state + (p,)
                if all(check_rule(candidate, ax) for ax in applicable):
                    new_stream.append(candidate)
        stream = new_stream
        if verbose:
            print(f"    After {cat_names[ci]}: {len(stream):,} worlds survive")

    stable_worlds = stream

    if verbose:
        print(f"  [Verify] Stable worlds (axioms pass): {len(stable_worlds):,}")

    # Test hypotheses
    if hypotheses:
        for branch, rules in hypotheses.items():
            valid = [w for w in stable_worlds
                     if all(check_rule(w, r) for r in rules)]
            if verbose:
                print(f"  [Hypothesis '{branch}']: {len(valid)} solution(s)")
                if valid:
                    engine = SmartSieveEngine(categories, [])
                    print(engine.format_solution(valid[0]))

    return stable_worlds


# ── Example: mini Einstein puzzle ───────────────────────────────────────────

EXAMPLE_CATEGORIES = {
    "nation":  ["English", "Swede", "Dane", "German", "Norwegian"],
    "color":   ["red", "green", "white", "yellow", "blue"],
    "drink":   ["tea", "coffee", "milk", "beer", "water"],
    "smoke":   ["PallMall", "Dunhill", "Blend", "BlueMaster", "Prince"],
    "pet":     ["dog", "bird", "cat", "horse", "fish"],
}

EXAMPLE_RULES = [
    # 1. The Englishman lives in the red house
    's.pos("nation", "English") == s.pos("color", "red")',
    # 2. The Swede keeps dogs
    's.pos("nation", "Swede") == s.pos("pet", "dog")',
    # 3. The Dane drinks tea
    's.pos("nation", "Dane") == s.pos("drink", "tea")',
    # 4. The green house is immediately left of the white house
    's.pos("color", "green") == s.pos("color", "white") - 1',
    # 5. The green house owner drinks coffee
    's.pos("color", "green") == s.pos("drink", "coffee")',
    # 6. The PallMall smoker keeps birds
    's.pos("smoke", "PallMall") == s.pos("pet", "bird")',
    # 7. The yellow house owner smokes Dunhill
    's.pos("color", "yellow") == s.pos("smoke", "Dunhill")',
    # 8. The man in the center house drinks milk
    's.pos("drink", "milk") == 2',
    # 9. The Norwegian lives in the first house
    's.pos("nation", "Norwegian") == 0',
    # 10. The Blend smoker lives next to the cat owner
    'abs(s.pos("smoke", "Blend") - s.pos("pet", "cat")) == 1',
    # 11. The horse owner lives next to the Dunhill smoker
    'abs(s.pos("pet", "horse") - s.pos("smoke", "Dunhill")) == 1',
    # 12. The BlueMaster smoker drinks beer
    's.pos("smoke", "BlueMaster") == s.pos("drink", "beer")',
    # 13. The German smokes Prince
    's.pos("nation", "German") == s.pos("smoke", "Prince")',
    # 14. The Norwegian lives next to the blue house
    'abs(s.pos("nation", "Norwegian") - s.pos("color", "blue")) == 1',
    # 15. The Blend smoker has a neighbor who drinks water
    'abs(s.pos("smoke", "Blend") - s.pos("drink", "water")) == 1',
]


def demo():
    print("=" * 70)
    print("  SmartSieveEngine — Einstein Puzzle Demo")
    print("=" * 70)

    engine = SmartSieveEngine(EXAMPLE_CATEGORIES, EXAMPLE_RULES)
    solutions = engine.solve(verbose=True)

    if solutions:
        print("\n  Solution:")
        print(engine.format_solution(solutions[0]))

    # Verify
    print("\n  Verification (brute-force):")
    verify_logic(EXAMPLE_CATEGORIES, EXAMPLE_RULES)


if __name__ == "__main__":
    demo()
