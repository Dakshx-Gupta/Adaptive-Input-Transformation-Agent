# Adaptive Input Transformation Agent

An intermediary "input adapter" for multi-agent workflows. It takes incoming content (free text or a dict) plus the **contract (JSON Schema) of a downstream agent**, and either:

- returns a **valid JSON payload** that matches that contract, or
- returns a **structured result** explaining what is missing, ambiguous or invalid.

The adapter is **schema-driven**: there is one `adapt()` function, and no per-agent transformation code. Supporting a new receiving agent means adding one JSON file to `contracts/`.

> **Nothing is ever executed.** The adapter only *prepares* payloads. It never sends an email, writes to a database or creates a task. Every result carries `"dry_run": true`.

---

## Honest status (please read first)

| Area | Status |
|---|---|
| Core pipeline (parse, normalise, validate, retry, structured errors) | Implemented, covered by 10 passing tests |
| Four receiving agents (email, database, task, calendar) | Implemented as contract files, all demonstrated |
| Tests and `demo.py` | Run **offline** using `FakeLLM` (scripted replies) |
| **Live LLM extraction from messy text** | **Not included and not verified.** The project ships with no real LLM client. I could not get free API access to a model during the assignment, so the prompt has never been run against a real model. |

What this means in practice: the tests prove that the **pipeline around the LLM** behaves correctly (it rejects bad output, refuses to guess, retries within limits, and reports missing data). They do **not** prove how well any particular model reads a messy sentence. The prompt in `adapter/prompts.py` is a reasoned design, not one tuned against real model output.

The LLM sits behind a one-method interface (`complete(prompt) -> str`), so a real model can be plugged in without changing the adapter (see "Plugging in a real LLM" below).

---

## How to run

Requires Python 3.10 or newer. No API key or internet connection is needed.

```bash
# 1. Create and activate a virtual environment
python -m venv .venv

# Windows (PowerShell):
.venv\Scripts\Activate.ps1
# Mac / Linux:
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run the tests (offline, no key needed)
pytest -v

# 4. Run the demo (offline, scripted LLM replies)
python demo.py
```

`tzdata` is in the requirements because Windows does not ship a timezone database, and the adapter validates timezone names such as `Asia/Kolkata`.

### Plugging in a real LLM

The adapter only needs an object with one method, `complete(prompt: str) -> str`, that returns the model's text reply. `FakeLLM` in `adapter/llm_client.py` is an example. To use a real model, write a small class like this (using your provider's SDK) and pass it to `adapt()`:

```python
class MyLLM:
    def complete(self, prompt: str) -> str:
        ...  # call your provider, return the reply text (use "" if there is none)
```

Keep API keys in environment variables, never in the code. This path is untested (see "Honest status").

---

## Architecture

```
raw_input (text or dict) ─┐
contract (JSON Schema)   ─┼─►  adapt()  ─►  result {status, payload, missing_fields, ...}
context (date, timezone) ─┘
```

Inside `adapt()`:

```
1. Pre-check     relative date in the input ("tomorrow") but no reference date given?
                 -> return needs_clarification without calling the LLM
2. Build prompt  one generic template + the contract + context + the input
3. Call LLM      (any object with complete(prompt); FakeLLM in tests and the demo)
4. Parse         find the JSON object in the reply, expect {"payload": {...}, "ambiguities": [...]}
5. Normalise     trim strings, fix enum casing, convert numeric strings, drop null/empty values
6. Validate      JSON Schema check + "grounding" check (see below)
7. Decide        no problems          -> status "ok"
                 only missing fields  -> status "needs_clarification" (no retry)
                 invalid values       -> retry with the errors fed back, up to 3 attempts,
                                         then status "error"
```

### Files

| File | Responsibility |
|---|---|
| `adapter/adapter.py` | The `adapt()` function and result building |
| `adapter/contract.py` | Loads and sanity-checks contract files |
| `adapter/context.py` | Reference date and timezone (explicit inputs, never read from the clock) |
| `adapter/prompts.py` | Generic prompt builder |
| `adapter/llm_client.py` | `FakeLLM`: scripted replies used by the tests and the demo |
| `adapter/parse.py` | Extracts the JSON object from an LLM reply |
| `adapter/normalize.py` | Schema-guided cleanup of values |
| `adapter/validate.py` | Schema validation and grounding checks |
| `contracts/*.json` | One file per receiving agent |
| `tests/` | pytest suite |
| `demo.py` | Runs example cases and prints results |

### Result format

Every call returns the same shape:

```json
{
  "status": "ok | needs_clarification | error",
  "payload": {},
  "missing_fields": [],
  "problems": [],
  "ambiguities": [],
  "message": "",
  "dry_run": true
}
```

---

## Contracts (receiving agents)

A contract file holds a `name`, a `description` and a JSON Schema under `schema`. The four included agents:

| File | Fields |
|---|---|
| `email_agent.json` | recipient, subject, body, tone |
| `database_agent.json` | operation (insert/update/delete), table, data, conditions |
| `task_agent.json` | task_name, assigned_to, priority (low/medium/high), due_date (YYYY-MM-DD) |
| `calendar_agent.json` | title, attendees, start_date, start_time, duration_minutes (fourth agent) |

Two custom annotations (JSON Schema ignores unknown `x-` keywords, so they don't break validation):

- `"x-verbatim": true`: the value is a critical fact (e.g. a recipient address) and **must literally appear in the input**.
- `"x-generated": true`: the LLM may write this text itself (e.g. an email subject or body). The prompt tells the model so.

Business rules live in the schema, not in code. For example, the database contract requires non-empty `conditions` for `update` and `delete`, so a "delete everything" payload cannot pass validation.

### Adding a new receiving agent

1. Create `contracts/your_agent.json` with `name`, `description` and `schema`.
2. Give every field a clear `description` (the model reads these to understand unfamiliar fields).
3. Call `adapt(text, load_contract("your_agent"), context, llm)`.

No code in `adapter/` changes. `calendar_agent.json` was added this way, and one test (`test_brand_new_contract_written_at_test_time`) writes a brand-new contract to a temporary file at test time and adapts to it.

---

## How LLM output is validated

The adapter treats LLM output as **untrusted** and checks it in layers:

1. **Parse check:** the reply must contain a JSON object with a `payload` object. Extra text around it is tolerated. Anything else is reported as a problem and retried.
2. **Normalisation:** deterministic cleanup, guided by the schema (`"HIGH "` becomes `"high"`, `"30"` becomes `30`, null and empty values are removed). It never invents values.
3. **Schema validation (`jsonschema`):** required fields, types, enums, patterns, formats (email, date), `additionalProperties: false` and conditional rules.
4. **Grounding check:** for fields marked `x-verbatim`, the value must appear in the original input (compared case-insensitively, ignoring extra whitespace). This is the guard against invented critical values.
5. **Missing versus invalid:** missing required values are **not retried**, because retrying only encourages the model to make something up. They are reported as `needs_clarification`. Invalid values are retried with the specific errors added to the prompt.
6. **Bounded retries:** at most 3 attempts, then a structured `error`.
7. **Ambiguity channel:** the prompt lets the model list ambiguities instead of guessing. Any reported ambiguity makes the result `needs_clarification`.
8. **Prompt-injection posture:** the input is passed as quoted data, and the prompt tells the model not to follow instructions inside it. Since nothing is executed, the worst outcome of a successful injection is a bad payload, which layers 3 to 5 can still catch. This has not been tested against a real model.

---

## Tests

`pytest -v` runs 10 tests, all using `FakeLLM`:

| Test | What it covers |
|---|---|
| `test_email_agent`, `test_task_agent`, `test_database_agent` | Three distinct receiving agents |
| `test_fourth_agent_calendar` | Fourth agent added as a contract file only |
| `test_brand_new_contract_written_at_test_time` | A contract that did not exist when the adapter was written |
| `test_missing_due_date_asks_for_clarification` | Missing data: asks for clarification, makes no retry |
| `test_invalid_value_is_retried` | Invalid enum value, corrected on retry |
| `test_delete_without_conditions_is_not_forwarded` | Safety rule expressed in the schema |
| `test_invented_recipient_is_rejected` | Grounding check; gives up after 3 attempts |
| `test_relative_date_without_reference_date_asks_first` | "tomorrow" without a reference date; the LLM is never called |

---

## Assumptions

- A reference date (and ideally a timezone) is supplied by the caller whenever the input contains relative dates.
- Input is mostly English.
- One contract per call. The caller decides which receiving agent the data is for. The adapter does not route.
- Contracts are valid JSON Schema (Draft 2020-12). Broken contract files fail early with a clear `ContractError`.
- The only output is the prepared payload. Forwarding it is outside this project.

## Limitations

- **No real LLM is integrated, and live model behaviour is unverified** (see "Honest status").
- **Relative-date detection is keyword-based** (`today`, `tomorrow`, weekday names, `next`, `last`, and so on). It can miss phrasings like "in three days", and can trigger on words like "last" when no date is meant.
- **The reference date and timezone are only given to the LLM.** The code does not independently recompute "tomorrow" or check that the returned date is consistent with the reference date, so a model that gets date arithmetic wrong would not be caught unless the format is invalid.
- **Grounding is an exact-text check.** It compares the whole value as a string, so it suits simple string fields like email addresses and names. It is not designed for list-valued fields, and a legitimate paraphrase of a name would be flagged.
- **Only fields marked `x-verbatim` are checked for invention.** Other fields (such as priority, which can be inferred) rely on the model and the schema.
- **Ambiguity detection depends on the model** reporting it. The adapter has no independent way to notice that "John" could mean two people.
- **Normalisation is conservative.** It does not map `"urgent"` to `"high"`. That is reported as invalid instead.
- **Nested and deeply structured schemas** are only lightly supported (objects are normalised recursively, arrays of objects are not).
- **Format checks** use `jsonschema`'s built-in checkers, so email validation is basic and does not confirm an address exists.
- The `x-generated` annotation currently only guides the prompt. It does not change validation.

## Safety

- The project makes no network calls, and contains no email, database or task-system code.
- Every result includes `"dry_run": true`.
- No credentials are stored in the repository. API tokens are read from environment variables only.

---

## Design decisions (and rejected alternatives)

| Alternative | Why not |
|---|---|
| One transformation function per agent | Explicitly disallowed and does not scale |
| Regex / keyword rules only | Cannot handle free-form language |
| Trust the LLM output as-is | LLMs produce wrong types and invented values |
| Have the LLM generate code to do the transformation | Executing generated code is a security risk and hard to validate |
| Write a custom validator | `jsonschema` is standard and well tested |
| LangChain / LangGraph / CrewAI | Disallowed by the assignment |

## Use of AI assistance

I had not built an agentic AI system before this assignment. I used an AI assistant (Claude) to explain the concepts and to help design and write the code, and I ran, tested and debugged it myself. Example data uses the `@awd.example.com` domain as the assignment's AI hallmark.
