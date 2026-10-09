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

from tools import GET_DIRECT_REPORTS_SCHEMA, GET_WORKER_SCHEMA, run_tool
from dotenv import load_dotenv
load_dotenv('.env')

MODEL = "gemini-3.5-flash-lite"  # or "gemini-3.5-turbo" for a larger model

# Gemini wants each declaration marked with "type": "function".
# The rest of the schema is what we wrote in tools.py

TOOL_DECLARATIONS = [
    {"type": "function", **GET_WORKER_SCHEMA},
    {"type": "function", **GET_DIRECT_REPORTS_SCHEMA},
] 

question = sys.argv[1] if len(sys.argv) > 1 else "What does Carol Bahl do?"

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY")) #reads GEMINI_API_KEY from environment

# ---- Round trip 1: question + tool descriptions go in ----------------------
first = client.interactions.create(
    model=MODEL,
    input=question,
    tools=TOOL_DECLARATIONS,
)

print("STEP TYPES RETURNED:", [s.type for s in first.steps])

call = next((s for s in first.steps if s.type == "function_call"), None)

if call is None:
     # The model decided no tool was needed and answered directly.
    print("NO TOOL CALLED")
    print("ANSWER:", first.output_text)
    sys.exit()

# ---- Your code runs the tool. The model is not involved here. --------------
result = run_tool(call.name, call.arguments)   # returns a JSON string
print("TOOL RETURNED:", result[:300])

# ---- Round trip 2: the result goes back, the model writes the answer -------
final = client.interactions.create(
    model=MODEL,
    input=[
        {
            "type": "function_result",
            "name": call.name,
            "call_id": call.id,          # ties this result to that request
            "result": [{"type": "text", "text": result}],
        }
    ],
    tools=TOOL_DECLARATIONS,
    previous_interaction_id=first.id,    # tells the server which conversation this continues
)
 
print("ANSWER:", final.output_text)