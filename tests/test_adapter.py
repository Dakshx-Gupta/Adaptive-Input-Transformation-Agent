import json
from adapter.adapter import adapt
from adapter.contract import load_contract
from adapter.llm_client import FakeLLM
import json as _json
from datetime import date
from adapter.context import Context

def reply(payload, ambiguities=()):
    """Builds the JSON text a real LLM would send back."""
    return json.dumps({"payload": payload, "ambiguities": list(ambiguities)})


def test_email_agent(ctx):
    llm = FakeLLM([reply({
        "recipient": "rahul@awd.example.com",
        "subject": "Project Review Meeting",
        "body": "Hi Rahul, I would like to discuss the project review tomorrow at 3 PM.",
        "tone": "professional",
    })])
    result = adapt(
        "Send an email to Rahul at rahul@awd.example.com about the project review "
        "tomorrow at 3 PM. Keep it professional.",
        load_contract("email_agent"), ctx, llm)
    assert result["status"] == "ok"
    assert result["payload"]["recipient"] == "rahul@awd.example.com"
    assert result["dry_run"] is True


def test_task_agent(ctx):
    llm = FakeLLM([reply({
        "task_name": "Prepare report", "assigned_to": "Asha",
        "priority": "HIGH", "due_date": "2026-10-14",
    })])
    result = adapt(
        "Asha needs to prepare the report by tomorrow, it's high priority.",
        load_contract("task_agent"), ctx, llm)
    assert result["status"] == "ok"
    assert result["payload"]["priority"] == "high"      # normaliser lowercased it


def test_database_agent(ctx):
    llm = FakeLLM([reply({
        "operation": "insert", "table": "users",
        "data": {"name": "Meera", "email": "meera@awd.example.com"},
        "conditions": {},
    })])
    result = adapt(
        "Add a user named Meera with email meera@awd.example.com to the users table.",
        load_contract("database_agent"), ctx, llm)
    assert result["status"] == "ok"
    assert result["payload"]["table"] == "users"


def test_missing_due_date_asks_for_clarification(ctx):
    llm = FakeLLM([reply({
        "task_name": "Prepare report", "assigned_to": "Asha",
        "priority": "high", "due_date": None,
    })])
    result = adapt("Asha needs to prepare the report, high priority.",
                   load_contract("task_agent"), ctx, llm)
    assert result["status"] == "needs_clarification"
    assert result["missing_fields"] == ["due_date"]
    assert len(llm.prompts) == 1          # no retry for missing data


def test_invalid_value_is_retried(ctx):
    llm = FakeLLM([
        reply({"task_name": "Prepare report", "assigned_to": "Asha",
               "priority": "urgent", "due_date": "2026-10-14"}),   # bad enum
        reply({"task_name": "Prepare report", "assigned_to": "Asha",
               "priority": "high", "due_date": "2026-10-14"}),     # fixed
    ])
    result = adapt("Asha must prepare the report tomorrow, it's urgent.",
                   load_contract("task_agent"), ctx, llm)
    assert result["status"] == "ok"
    assert len(llm.prompts) == 2
    assert "priority" in llm.prompts[1]   # the retry prompt mentioned the error

def test_fourth_agent_calendar(ctx):
        """Calendar agent was added as a contract file only; no adapter code changed."""
        llm = FakeLLM([reply({
            "title": "Project Review",
            "attendees": ["rahul@awd.example.com"],
            "start_date": "2026-10-14",
            "start_time": "15:00",
            "duration_minutes": 60,
        })])
        result = adapt(
            "Schedule a project review with rahul@awd.example.com tomorrow at 3 PM for an hour.",
            load_contract("calendar_agent"), ctx, llm)
        assert result["status"] == "ok"
        assert result["payload"]["start_time"] == "15:00"


def test_brand_new_contract_written_at_test_time(ctx, tmp_path):
        """A contract that did not exist when the adapter was written still works."""
        contract_file = tmp_path / "ticket_agent.json"
        contract_file.write_text(_json.dumps({
            "name": "ticket_agent",
            "description": "Opens a support ticket.",
            "schema": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "severity": {"type": "string", "enum": ["low", "high"]},
                },
                "required": ["title", "severity"],
                "additionalProperties": False,
            },
        }))
        llm = FakeLLM([reply({"title": "Login broken", "severity": "high"})])
        result = adapt("Login is broken for everyone, very serious.",
                       load_contract(str(contract_file)), ctx, llm)
        assert result["status"] == "ok"


def test_delete_without_conditions_is_not_forwarded(ctx):
        llm = FakeLLM([reply({"operation": "delete", "table": "users",
                              "data": {}, "conditions": {}})])
        result = adapt("Delete all rows from the users table.",
                       load_contract("database_agent"), ctx, llm)
        assert result["status"] == "needs_clarification"
        assert "conditions" in result["missing_fields"]


def test_invented_recipient_is_rejected(ctx):
        bad = reply({"recipient": "rahul@company.com", "subject": "Review",
                     "body": "Hi Rahul", "tone": "professional"})
        llm = FakeLLM([bad, bad, bad])      # the model keeps inventing
        result = adapt("Email Rahul at rahul@awd.example.com about the review.",
                       load_contract("email_agent"), ctx, llm)
        assert result["status"] == "error"
        assert len(llm.prompts) == 3        # tried 3 times, then gave up


def test_relative_date_without_reference_date_asks_first():
        no_reference = Context(reference_date=None, timezone="Asia/Kolkata")
        llm = FakeLLM([])                   # must never be called
        result = adapt("Asha must finish the report tomorrow.",
                       load_contract("task_agent"), no_reference, llm)
        assert result["status"] == "needs_clarification"
        assert result["missing_fields"] == ["reference_date"]
        assert llm.prompts == []
