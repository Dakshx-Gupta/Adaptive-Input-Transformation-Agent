import argparse
import json
from datetime import date

from adapter.adapter import adapt
from adapter.context import Context
from adapter.contract import load_contract
from adapter.llm_client import FakeLLM


def reply(payload):
    return json.dumps({"payload": payload, "ambiguities": []})


# (title, contract name, input text, the reply a real LLM would plausibly give)
CASES = [
    ("Email agent", "email_agent",
     "Send an email to Rahul at rahul@awd.example.com about the project review "
     "tomorrow at 3 PM. Keep it professional.",
     reply({"recipient": "rahul@awd.example.com", "subject": "Project Review Meeting",
            "body": "Hi Rahul, I would like to discuss the project review tomorrow at 3 PM.",
            "tone": "professional"})),
    ("Task agent", "task_agent",
     "Asha needs to prepare the quarterly report by tomorrow. High priority.",
     reply({"task_name": "Prepare quarterly report", "assigned_to": "Asha",
            "priority": "high", "due_date": "2026-10-14"})),
    ("Database agent", "database_agent",
     "Add a user named Meera with email meera@awd.example.com to the users table.",
     reply({"operation": "insert", "table": "users",
            "data": {"name": "Meera", "email": "meera@awd.example.com"}, "conditions": {}})),
    ("Fourth agent (calendar), added as a file only", "calendar_agent",
     "Schedule a project review with rahul@awd.example.com tomorrow at 3 PM for an hour.",
     reply({"title": "Project Review", "attendees": ["rahul@awd.example.com"],
            "start_date": "2026-10-14", "start_time": "15:00", "duration_minutes": 60})),
    ("Missing data: no due date", "task_agent",
     "Asha needs to prepare the quarterly report. High priority.",
     reply({"task_name": "Prepare quarterly report", "assigned_to": "Asha",
            "priority": "high", "due_date": None})),
]


def main():
    parser = argparse.ArgumentParser(description="Adaptive Input Adapter demo")
    parser.add_argument("--live", action="store_true",
                        help="use a real LLM (needs an API key) instead of scripted replies")
    args = parser.parse_args()

    context = Context(reference_date=date(2026, 10, 13), timezone="Asia/Kolkata")

    live_llm = None
    if args.live:
        from adapter.llm_client import HuggingFaceLLM
        live_llm = HuggingFaceLLM()

    for title, contract_name, text, canned_reply in CASES:
        llm = live_llm or FakeLLM([canned_reply])
        result = adapt(text, load_contract(contract_name), context, llm)
        print("=" * 70)
        print(title)
        print("INPUT :", text)
        print("RESULT:", json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
