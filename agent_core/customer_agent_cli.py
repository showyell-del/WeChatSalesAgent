import argparse
import json

from .customer_agent import (
    CustomerAgentError,
    ask_customer_agent,
    available_models,
    delete_saved_analysis,
    list_saved_analyses,
    load_saved_analysis,
    refresh_saved_analysis,
    save_analysis,
    save_agent_model,
    selected_agent_model,
)
from .events import emit, event


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument("--question")
    parser.add_argument("--session-id", default="")
    parser.add_argument("--mode", default="")
    parser.add_argument("--save-session")
    parser.add_argument("--refresh-saved")
    parser.add_argument("--load-saved")
    parser.add_argument("--delete-saved")
    parser.add_argument("--list-saved", action="store_true")
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
        if args.list_saved:
            print(json.dumps({"saved_analyses": list_saved_analyses(args.db)}, ensure_ascii=False))
            return 0
        if args.load_saved:
            print(json.dumps(load_saved_analysis(args.db, args.load_saved), ensure_ascii=False))
            return 0
        if args.delete_saved:
            delete_saved_analysis(args.db, args.delete_saved)
            print(json.dumps({"deleted_saved_id": args.delete_saved}, ensure_ascii=False))
            return 0
        if args.save_session:
            print(json.dumps(save_analysis(args.db, args.save_session), ensure_ascii=False))
            return 0
        if args.refresh_saved:
            print(json.dumps(refresh_saved_analysis(args.db, args.refresh_saved, args.timeout, progress=emit), ensure_ascii=False))
            return 0
        if not args.question:
            raise CustomerAgentError("请输入想查找或导出的客户信息。")
        print(json.dumps(ask_customer_agent(
            args.db,
            args.question,
            args.timeout,
            progress=emit,
            session_id=args.session_id,
            forced_task_type=args.mode,
        ), ensure_ascii=False))
        return 0
    except Exception as exc:
        code = "CUSTOMER_AGENT_FAILED" if not isinstance(exc, CustomerAgentError) else "CUSTOMER_AGENT_REJECTED"
        emit(event("customer_agent", "failed", code, str(exc)))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
