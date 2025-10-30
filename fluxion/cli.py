# fluxion/cli.py
from __future__ import annotations
import argparse, json, sys
from fluxion.runtime.runner_v2 import RunnerV2

def _json_default(o):
    # JSON'a uygun olmayan her şeyi okunabilir stringe çevir
    # (ör. function, Path, set, custom objeler vs.)
    name = getattr(o, "__name__", None)
    if name:
        return name
    try:
        return str(o)
    except Exception:
        return f"<non-serializable {type(o).__name__}>"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-s", "--script", required=True, help="Fluxion script path (.flx)")
    ap.add_argument("-D", "--define", action="append", default=[],
                    help="Predefine variables (key=value or flag)")
    args = ap.parse_args()

    vars_dict: dict[str, object] = {}
    for item in args.define:
        if "=" in item:
            k, v = item.split("=", 1)
            vars_dict[k] = v
        else:
            vars_dict[item] = True

    runner = RunnerV2()
    res = runner.run_file(args.script, variables=vars_dict)

    json.dump(res, sys.stdout, ensure_ascii=False, indent=2, default=_json_default)
    sys.stdout.write("\n")

if __name__ == "__main__":
    main()
