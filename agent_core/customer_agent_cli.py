import argparse
import json

from .customer_agent import (
    CustomerAgentError,
    ask_customer_agent,
    available_models,
    save_agent_model,
    selected_agent_model,
)
from .events import emit, event


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument("--question")
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--get-model", action="store_true")
    parser.add_argument("--set-model")
    parser.add_argument("--list-models", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.get_model:
            print(json.dumps({"model": selected_agent_model(args.db)}, ensure_ascii=False))
            return 0
        if args.set_model is not None:
            save_agent_model(args.db, args.set_model)
            print(json.dumps({"model": args.set_model.strip()}, ensure_ascii=False))
            return 0
        if args.list_models:
            print(json.dumps({"models": available_models(args.timeout)}, ensure_ascii=False))
            return 0
        if not args.question:
            raise CustomerAgentError("请输入想查找或导出的客户信息。")
        print(json.dumps(ask_customer_agent(args.db, args.question, args.timeout, progress=emit), ensure_ascii=False))
        return 0
    except Exception as exc:
        code = "CUSTOMER_AGENT_FAILED" if not isinstance(exc, CustomerAgentError) else "CUSTOMER_AGENT_REJECTED"
        emit(event("customer_agent", "failed", code, str(exc)))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
