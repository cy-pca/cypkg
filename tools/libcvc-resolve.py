"""Resolve the merge conflicts between open libcvc PRs that cypkg's CI knows, and no others.

Run by tools/libcvc.sh in a libcvc checkout mid-merge. Each conflicted file must be in RULES, and
each conflict block in it must match one of the file's rules, or nothing is written and it exits
1. Temporary: delete a rule once the PRs it reconciles have merged or been rebased onto each
other.

Known today (2026-10-30):
  src/ari/main.cpp, transfix/libcvc#896 (ari test, quit codes) vs #887 (the browser pages). Both
  sides of both hunks are wanted:
    1. #896 adds "--tap" to the host flags; #887 makes the options mutable and adds the browser
       build's backend and component-path defaults.
    2. #896 returns the exit code a (quit code) set; #887 reports "running" to the browser page.
"""

import re
import subprocess
import sys

BLOCK = re.compile(r"^<<<<<<< [^\n]*\n(.*?)^=======\n(.*?)^>>>>>>> [^\n]*\n", re.S | re.M)


def ari_main_flags(ours, theirs):
    if '"--tap"' in ours and "CVC_ARI_WASM_BACKEND" in theirs:
        return theirs.replace('{"--json", "--functions"}', '{"--json", "--functions", "--tap"}')
    return None


def ari_main_check(ours, theirs):
    if "return rt.exit_code();" in ours and "ari::report_running();" in theirs:
        running = [l for l in theirs.splitlines(True) if "report_running" in l]
        return ours + "".join(running)
    return None


RULES = {"src/ari/main.cpp": [ari_main_flags, ari_main_check]}


def main():
    files = subprocess.run(["git", "diff", "--name-only", "--diff-filter=U"],
                           capture_output=True, text=True, check=True).stdout.split()
    if not files:
        return 1
    out = {}
    for f in files:
        rules = RULES.get(f)
        if not rules:
            print(f"libcvc-resolve: no rule for {f}", file=sys.stderr)
            return 1
        text = open(f).read()

        def fix(m):
            for rule in rules:
                r = rule(m.group(1), m.group(2))
                if r is not None:
                    return r
            raise LookupError(m.group(0)[:200])

        try:
            out[f] = BLOCK.sub(fix, text)
        except LookupError as e:
            print(f"libcvc-resolve: an unknown conflict in {f}:\n{e}", file=sys.stderr)
            return 1
        if "<<<<<<<" in out[f] or ">>>>>>>" in out[f]:
            return 1
    for f, text in out.items():
        open(f, "w").write(text)
        subprocess.run(["git", "add", f], check=True)
        print(f"libcvc-resolve: resolved {f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
