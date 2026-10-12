"""
Lesson 2: a real model asks for your tool.
 
One question, two round trips, no loop yet:
  1. send the question + tool descriptions
  2. the model replies with a function call (a request, not an answer)
  3. YOUR code runs the function
  4. send the result back; the model writes the final answer
 
Setup:
  pip install -U google-genai
  set GEMINI_API_KEY in your environment (key from Google AI Studio)
 
Run:  python lesson2.py "What does Carol Bahl do?"
"""

import os
import sys

from google import genai

from tools import GET_DIRECT_REPORTS_SCHEMA, GET_WORKER_SCHEMA, GET_TIME_OFF_BALANCE_SCHEMA, GET_SEARCH_WORKERS_SCHEMA, GET_TEAM_TIME_OFF_SCHEMA, run_tool
from dotenv import load_dotenv
load_dotenv('.env')

MODEL = "gemini-3.5-flash-lite"  # or "gemini-3.5-turbo" for a larger model

# Gemini wants each declaration marked with "type": "function".
# The rest of the schema is what we wrote in tools.py

TOOL_DECLARATIONS = [
    {"type": "function", **GET_WORKER_SCHEMA},
    {"type": "function", **GET_DIRECT_REPORTS_SCHEMA},
    {"type": "function", **GET_TIME_OFF_BALANCE_SCHEMA},
    {"type": "function", **GET_SEARCH_WORKERS_SCHEMA},
    {"type": "function", **GET_TEAM_TIME_OFF_SCHEMA},
] 

SYSTEM_INSTRUCTION = """You answer questions about employees using the HR tools provided.
Rules:
1. State only facts that appear in tool results. Never guess.
2. When a result gives a workerId or managerId, use that ID in later tool calls, not the name.
3. If a lookup returns several candidates, list them and ask the user which one they mean.
4. If a lookup finds no one, say that no matching employee was found. Do not try unrelated searches.
5. If no tool covers the question (for example salary), say you don't have access to that data and mention what you can look up.
6. Always include units with numbers, for example "7.0 days"."""

question = sys.argv[1] if len(sys.argv) > 1 else "What does Carol Bahl do?"

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY")) #reads GEMINI_API_KEY from environment

MAX_STEPS = 6

def run_turn(question: str, previous_interaction_id: str | None = None):
    """"Handle one user message: call tools until the model answers or MAX_STEPS is reached. Returns the interaction ID to continue from, or None to start fresh."""
    kwargs = {}
    if previous_interaction_id:
        kwargs["previous_interaction_id"] = previous_interaction_id

    interaction = client.interactions.create(
        model=MODEL,
        input=question,
        tools=TOOL_DECLARATIONS,
        system_instruction=SYSTEM_INSTRUCTION,
        **kwargs,
    )

    for step in range(MAX_STEPS):
        print("STEP TYPES RETURNED:", [s.type for s in interaction.steps])

        calls = [s for s in interaction.steps if s.type == "function_call"]
        if not calls:
            break                                   # the model has answered

        results = []
        for call in calls:
            result = run_tool(call.name, call.arguments)
            print(f"[{step + 1}] {call.name}({call.arguments}) -> {result[:150]}")
            results.append(
                {
                    "type": "function_result",
                    "name": call.name,
                    "call_id": call.id,
                    "result": [{"type": "text", "text": result}],
                }
            )

        interaction = client.interactions.create(
            model=MODEL,
            input=results,
            tools=TOOL_DECLARATIONS,
            previous_interaction_id=interaction.id,
            system_instruction=SYSTEM_INSTRUCTION,
        )

    pending = [s for s in interaction.steps if s.type == "function_call"]
    if pending:
        print(f"STOPPED: still asking for tools after {MAX_STEPS} rounds. Starting a fresh conversation.")
        return None
    print("ANSWER:", interaction.output_text)
    return interaction.id

previous_id = None
while True:
    question = input("You: ")
    if question.strip().lower() in ("exit", "quit"):
        break
    previous_id = run_turn(question, previous_id)