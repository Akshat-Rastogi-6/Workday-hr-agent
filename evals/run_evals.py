import sys
import json
import asyncio

from pathlib import Path
from collections import defaultdict
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent import run_turn, to_gemini, server_params, Client, call_mcp_tool


HERE = Path(__file__).resolve().parent
CASES = json.loads((HERE / "cases.json").read_text(encoding="utf-8"))

def score(case: dict, result: dict) -> list[str]:
    reasons = []
    if result["stopped"]:
        return ["stopped: hit the step limit without answering"]

    answer = (result["answer"] or "").replace(",", "").lower()
    called = [c["name"] for c in result["calls"]]

    for text in case.get("must_contain", []):
        if text.lower() not in answer:
            reasons.append(f"missing '{text}'")

    for text in case.get("must_not_contain", []):
        if text.lower() in answer:
            reasons.append(f"should not contain '{text}'")

    for tool in case.get("expect_tools", []):
        if tool not in called:
            reasons.append(f"never called {tool}")

    limit = case.get("max_calls")
    if limit is not None and len(called) > limit:
        reasons.append(f"{len(called)} calls, max {limit}")

    return reasons

async def main():
    records = []
    totals = defaultdict(lambda: [0, 0])          # category -> [passed, total]

    for case in CASES:
        all_calls = []
        result = {"answer": None, "calls": [], "stopped": True}
        try:
            async with Client(server_params(case["as_user"])) as mcp_client:
                me = json.loads(await call_mcp_tool(mcp_client, "who_am_i", {}))
                if me.get("workerId") != case["as_user"]:
                    raise RuntimeError(f"signed in as {me.get('workerId')}, expected {case['as_user']}")

                tools = (await mcp_client.list_tools()).tools
                tool_declarations = [to_gemini(t) for t in tools]

                previous_id = None
                for message in [case["question"], *case.get("followups", [])]:
                    result = await run_turn(mcp_client, tool_declarations, message, previous_id, verbose=False)
                    all_calls += result["calls"]
                    if result["stopped"]:
                        break
                    previous_id = result["interaction_id"]
                result["calls"] = all_calls
                reasons = score(case, result)
        except Exception as e:
            result = {"answer": None, "calls": all_calls, "stopped": True}
            reasons = [f"crashed: {type(e).__name__}: {e}"]

        passed = not reasons
        totals[case["category"]][1] += 1
        if passed:
            totals[case["category"]][0] += 1

        status = "PASS" if passed else "FAIL"
        detail = "" if passed else "  -> " + "; ".join(reasons)
        print(f"{status}  [{case['as_user']}] {case['id']}{detail}")

        records.append({
            "id": case["id"],
            "category": case["category"],
            "as_user": case["as_user"],
            "question": case["question"],
            "passed": passed,
            "reasons": reasons,
            "followups": case.get("followups", []),
            "answer": result["answer"],
            "calls": result["calls"],
        })

    print("\nBy category:")
    for category, (ok, total) in totals.items():
        print(f"  {category:<12} {ok}/{total}")
    ok_all = sum(ok for ok, _ in totals.values())
    print(f"  {'TOTAL':<12} {ok_all}/{len(CASES)} ({ok_all / len(CASES):.0%})")

    out = HERE / "results_D1.json"
    out.write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nFull results saved to {out}")

if __name__ == "__main__":
    asyncio.run(main())