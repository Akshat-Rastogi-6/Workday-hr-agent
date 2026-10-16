"""
Employee HR Agent
=================

Short description:
    Uses Gemini and MCP-provided HR tools to answer questions about employees.

Process:
    1. Connect to the MCP server and load its available tools.
    2. Send the user's question and tool definitions to Gemini.
    3. Execute any tools requested by Gemini through the MCP client.
    4. Return each tool result to Gemini until it produces an answer or the
       maximum number of steps is reached.
    5. Preserve the interaction ID so follow-up questions can continue the
       conversation.

Functions:
    clean_schema:
        Simplifies MCP JSON schemas for Gemini compatibility.
    to_gemini:
        Converts an MCP tool definition into a Gemini function declaration.
    call_mcp_tool:
        Calls an MCP tool and formats its result as text or an error payload.
    run_turn:
        Processes one user question, including Gemini responses and tool calls.
    main:
        Starts the MCP connection and runs the interactive question loop.
"""

import os
import sys
import asyncio
import json

from google import genai
from dotenv import load_dotenv
from pathlib import Path

from mcp import Client, StdioServerParameters
load_dotenv('.env')

MODEL = "gemini-3.5-flash-lite"  # or "gemini-3.5-turbo" for a larger model

# Gemini wants each declaration marked with "type": "function".
# The rest of the schema is what we wrote in tools.py


SYSTEM_INSTRUCTION = """You answer questions about employees using the HR tools provided.
Rules:
1. State only facts that appear in tool results. Never guess.
2. When a result gives a workerId or managerId, use that ID in later tool calls, not the name.
3. If a lookup returns several candidates, list them and ask the user which one they mean.
4. If a lookup finds no one, say that no matching employee was found. Do not try unrelated searches.
5. If no tool covers the question (for example salary), say you don't have access to that data and mention what you can look up.
6. Always include units with numbers, for example "7.0 days".
7. If a lookup finds no one, say which name was not found. Do not try unrelated searches. """

# question = sys.argv[1] if len(sys.argv) > 1 else "What does Carol Bahl do?"

HERE = Path(__file__).parent
SERVER = StdioServerParameters(
    command=sys.executable,              # the same Python as the agent, so your venv is used
    args=[str(HERE / "server.py")],
    cwd=str(HERE),                       # so tools.py finds data/
)
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY")) #reads GEMINI_API_KEY from environment

MAX_STEPS = 6

def clean_schema(schema):
    """Reduce an MCP (JSON Schema) definition to the plain subset Gemini accepted from our hand-written schemas."""
    if isinstance(schema, list):
        return [clean_schema(s) for s in schema]
    if not isinstance(schema, dict):
        return schema
    if "anyOf" in schema:                       # Optional[X] arrives as anyOf [X, null]
        options = [o for o in schema["anyOf"] if o.get("type") != "null"]
        if len(options) == 1:
            rest = {k: v for k, v in schema.items() if k != "anyOf"}
            schema = {**options[0], **rest}
    out = {}
    for key, value in schema.items():
        if key in ("title", "default"):
            continue
        if key == "properties":                 # keys here are parameter NAMES, never strip them
            out[key] = {name: clean_schema(prop) for name, prop in value.items()}
        else:
            out[key] = clean_schema(value)
    return out


def to_gemini(tool) -> dict:
    return {
        "type": "function",
        "name": tool.name,
        "description": tool.description,
        "parameters": clean_schema(tool.input_schema),
    }

async def call_mcp_tool(mcp_client, name: str, arguments: dict) -> str:
    result = await mcp_client.call_tool(name, arguments)
    text = "\n".join(c.text for c in result.content if c.type == "text")
    return json.dumps({"error": text}) if result.is_error else text

async def run_turn(mcp_client, tool_declarations, question: str, previous_interaction_id: str | None = None, verbose: bool = True):
    """
    Run a single turn of the conversation.
    Returns a dict with:
        answer: the final text answer, or None if the model stopped without answering
        calls: a list of all the function calls made during this turn
        stopped: True if the model stopped without answering, False otherwise
        interaction_id: the ID of the interaction for continuing the conversation
    """
    kwargs = {}
    if previous_interaction_id:
        kwargs["previous_interaction_id"] = previous_interaction_id

    interaction = client.interactions.create(
        model=MODEL,
        input=question,
        tools=tool_declarations,
        system_instruction=SYSTEM_INSTRUCTION,
        **kwargs,
    )
    all_calls = []
    for step in range(MAX_STEPS):
        if verbose: print("STEP TYPES RETURNED:", [s.type for s in interaction.steps])

        calls = [s for s in interaction.steps if s.type == "function_call"]
        if not calls:
            break                                   # the model has answered

        results = []
        for call in calls:
            result = await call_mcp_tool(mcp_client, call.name, call.arguments)
            if verbose: print(f"[{step + 1}] {call.name}({call.arguments}) -> {result[:150]}")
            all_calls.append({"name": call.name, "arguments": call.arguments})
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
            tools=tool_declarations,
            previous_interaction_id=interaction.id,
            system_instruction=SYSTEM_INSTRUCTION,
        )

    stopped = any(s.type == "function_call" for s in interaction.steps)
    if verbose:
        print("STOPPED..." if stopped else f"ANSWER: {interaction.output_text}")
    return {
        "answer": None if stopped else interaction.output_text,
        "calls": all_calls,
        "stopped": stopped,
        "interaction_id": interaction.id,
    }

async def main():
    async with Client(SERVER) as mcp_client:
        tools = (await mcp_client.list_tools()).tools
        tool_declarations = [to_gemini(t) for t in tools]
        print("Loaded tools:", [t.name for t in tools])

        previous_id = None
        while True:
            question = input("You: ")
            if question.strip().lower() in ("exit", "quit"):
                break
            result = await run_turn(mcp_client, tool_declarations, question, previous_id)
            previous_id = None if result["stopped"] else result["interaction_id"]
            # print("calls made:", result["calls"])


if __name__ == "__main__":
    asyncio.run(main())