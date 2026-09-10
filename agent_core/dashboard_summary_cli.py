import argparse
import json

from .dashboard_summary import generate_dashboard_summary
from .events import emit, event


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args(argv)
    try:
        with open(args.input, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        print(json.dumps({"summary": generate_dashboard_summary(args.db, payload, args.timeout)}, ensure_ascii=False))
        return 0
    except Exception as exc:
        emit(event("dashboard_summary", "failed", "DASHBOARD_SUMMARY_FAILED", str(exc)))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
