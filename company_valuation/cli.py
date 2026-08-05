from __future__ import annotations

import argparse
import json
import sys

from company_valuation.tools import (
    TOOL_SCHEMAS,
    get_company_fundamentals,
    get_company_valuation,
    resolve_company,
)


def _dump(model: object) -> None:
    if hasattr(model, "model_dump"):
        print(json.dumps(model.model_dump(mode="json"), ensure_ascii=False, indent=2))
    elif isinstance(model, list):
        print(
            json.dumps(
                [m.model_dump(mode="json") if hasattr(m, "model_dump") else m for m in model],
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(json.dumps(model, ensure_ascii=False, indent=2))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="US/KR listed company valuation tools for agents"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_resolve = sub.add_parser("resolve", help="Resolve company name/ticker")
    p_resolve.add_argument("query")
    p_resolve.add_argument("--market", choices=["US", "KR"])

    p_val = sub.add_parser("valuation", help="Get valuation snapshot")
    p_val.add_argument("query")
    p_val.add_argument("--market", choices=["US", "KR"])

    p_fund = sub.add_parser("fundamentals", help="Get fundamentals")
    p_fund.add_argument("query")
    p_fund.add_argument("--market", choices=["US", "KR"])
    p_fund.add_argument("--year", type=int)

    sub.add_parser("schemas", help="Print agent tool schemas")

    args = parser.parse_args(argv)

    try:
        if args.command == "resolve":
            _dump(resolve_company(args.query, market=args.market))
        elif args.command == "valuation":
            _dump(get_company_valuation(query=args.query, market=args.market))
        elif args.command == "fundamentals":
            _dump(
                get_company_fundamentals(
                    query=args.query,
                    market=args.market,
                    year=args.year,
                )
            )
        elif args.command == "schemas":
            _dump(TOOL_SCHEMAS)
        return 0
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())