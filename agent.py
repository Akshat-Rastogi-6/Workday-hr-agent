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

from tools import GET_DIRECT_REPORTS_SCHEMA, GET_WORKER_SCHEMA, GET_TIME_OFF_BALANCE_SCHEMA, GET_SEARCH_WORKERS_SCHEMA, run_tool
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
] 

question = sys.argv[1] if len(sys.argv) > 1 else "What does Carol Bahl do?"

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY")) #reads GEMINI_API_KEY from environment

MAX_STEPS = 6

# Round 0: the question and tool descriptions go in.
interaction = client.interactions.create(
    model=MODEL,
    input=question,
    tools=TOOL_DECLARATIONS,
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
    )

# Whichever way the loop ended, look at the latest reply before deciding.
pending = [s for s in interaction.steps if s.type == "function_call"]
if pending:
    print(f"STOPPED: still asking for tools after {MAX_STEPS} rounds")
else:
    print("ANSWER:", interaction.output_text)