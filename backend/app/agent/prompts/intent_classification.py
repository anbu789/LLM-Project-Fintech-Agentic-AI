"""
FinTech Agent — Intent Classification Prompts (Phase 4, Node 2)
System prompt, user prompt builder, and JSON schema for structured LLM output.
Covers all RequestMode categories with banking-domain examples.
"""

from typing import Any, Dict, List

# ---------------------------------------------------------------------------
# System prompt — sets the LLM's classification context and constraints
# ---------------------------------------------------------------------------

INTENT_CLASSIFICATION_SYSTEM_PROMPT = """\
You are the Intent Router for FinTech Agent, a banking intelligence system that processes
natural language queries from bank analysts, risk officers, compliance teams, and operations staff.

Your ONLY task is to classify the user's request into exactly one of the following modes and
return a valid JSON object — nothing else.

## Classification Modes

### QUERY_ONLY
The user is asking for information, data, analytics, or reports from the banking database.
Examples:
- "Show me all active loans above ₹10 lakhs"
- "How many customers have high credit risk scores?"
- "List transactions flagged for AML review in the last 30 days"
- "What is the total outstanding amount across all loan accounts?"
- "Show fraud alerts for high-risk customers"
- "Which branches have the highest NPA ratio?"
- "Give me a summary of KYC compliance status"

### QUERY_AND_SCHEDULE
The user wants to run a data query AND also schedule it to run on a recurring basis.
Examples:
- "Show me overdue loans and email me this report every Monday"
- "Get the daily transaction summary and schedule it to run at 9am every weekday"
- "Run the fraud alert report now and also schedule it weekly"

### SCHEDULE_ONLY
The user wants to set up a recurring report or scheduled job without asking for immediate results.
Examples:
- "Schedule a weekly NPA report every Friday at 6pm"
- "Set up a daily email with loan disbursement summary at 8am"
- "Create a monthly compliance report scheduled for the 1st of each month"

### CLARIFICATION_REQUIRED
The user's request is ambiguous, incomplete, or needs more information before it can be processed.
Examples:
- "Show me the loans" (Which loans? What criteria? Time range?)
- "Tell me about the customers" (What about them? Which segment?)
- "Get the report" (Which report? What parameters?)
- "What happened yesterday?" (What type of event? Which system?)

### OUT_OF_SCOPE
The user's request is not related to banking data analytics, general banking glossary questions,
or is a greeting/chitchat/personal question that this system cannot or should not answer.
Examples:
- "Hello" / "Hi there" / "How are you?"
- "What's the weather like?"
- "Write me a poem"
- "What is the capital of France?"
- "Tell me a joke"

## Rules
1. NEVER classify a request as QUERY_ONLY or QUERY_AND_SCHEDULE based on vague or missing criteria.
2. NEVER grant authorization to execute destructive operations — that is not your role.
3. If the query is a general banking terminology question (e.g., "What is NPA?"), classify as OUT_OF_SCOPE
   because this system handles data queries, not definitional Q&A.
4. Always populate `intent_reason` with a clear, brief explanation.
5. For CLARIFICATION_REQUIRED, always populate `clarification_question` with a specific question.
6. For QUERY_ONLY, QUERY_AND_SCHEDULE, and SCHEDULE_ONLY, always populate `query_description`.

## Output Format
Return ONLY valid JSON — no markdown, no code fences, no explanation:
{
  "request_mode": "<one of the five modes above>",
  "intent_reason": "<brief explanation of why this mode was chosen>",
  "query_description": "<null or concise restatement of what data the user wants>",
  "clarification_question": "<null or specific question to ask the user>"
}
"""

# ---------------------------------------------------------------------------
# JSON schema for structured output validation (Pydantic IntentClassification)
# ---------------------------------------------------------------------------

INTENT_JSON_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "request_mode": {
            "type": "string",
            "enum": [
                "QUERY_ONLY",
                "QUERY_AND_SCHEDULE",
                "SCHEDULE_ONLY",
                "CLARIFICATION_REQUIRED",
                "OUT_OF_SCOPE",
            ],
        },
        "intent_reason": {"type": "string"},
        "query_description": {"type": ["string", "null"]},
        "clarification_question": {"type": ["string", "null"]},
    },
    "required": ["request_mode", "intent_reason"],
}


# ---------------------------------------------------------------------------
# User prompt builder — injects query and optional conversation context
# ---------------------------------------------------------------------------

def build_intent_classification_prompt(
    query: str,
    conversation_history: List[Dict[str, Any]] | None = None,
) -> str:
    """Build the user-turn prompt for intent classification.

    Includes the last two conversation turns as context (if present) to help
    resolve pronouns and follow-up references, then states the current query.

    Args:
        query: The current user message to classify.
        conversation_history: Optional list of prior {role, content} dicts.

    Returns:
        A string forming the user message payload for the LLM.
    """
    context_lines: List[str] = []

    if conversation_history:
        # Include the last 2 turns (4 messages = 2 user + 2 assistant)
        recent = conversation_history[-4:]
        for msg in recent:
            role = msg.get("role", "user")
            content = (msg.get("content") or "").strip()
            if role == "user" and content:
                context_lines.append(f"Previous user: {content}")
            elif role == "assistant" and content:
                context_lines.append(f"Previous assistant: {content[:200]}")

    parts: List[str] = []
    if context_lines:
        parts.append("## Conversation Context (last 2 turns)")
        parts.extend(context_lines)
        parts.append("")

    parts.append("## Current User Query to Classify")
    parts.append(query)
    parts.append("")
    parts.append("Classify the current query and return ONLY the JSON object as specified.")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Mock-provider deterministic classification rules
# Used when LLM_PROVIDER == "mock" to ensure reproducible unit tests
# ---------------------------------------------------------------------------

_SCHEDULE_KEYWORDS = [
    "schedule", "every monday", "every friday", "every day", "daily",
    "weekly", "monthly", "recurring", "set up a report", "cron",
    "send me every", "email me every", "remind me every",
]

_SCHEDULE_ONLY_KEYWORDS = [
    "schedule only", "just schedule", "set up a schedule",
    "create a schedule", "recurring report without",
]

_BANKING_DATA_KEYWORDS = [
    "loan", "loans", "account", "accounts", "customer", "customers",
    "transaction", "transactions", "fraud", "alert", "risk", "credit",
    "npa", "overdue", "outstanding", "branch", "branches", "kyc",
    "aml", "portfolio", "disbursement", "repayment", "balance",
    "collateral", "delinquent", "default", "interest", "emi",
    "deposit", "withdrawal", "transfer", "payment", "investment",
    "insurance", "compliance", "regulatory", "audit", "report",
    "total", "count", "average", "summary", "list", "show", "get",
    "find", "filter", "how many", "which", "what are",
]

_GREETINGS = [
    "hello", "hi", "hey", "good morning", "good afternoon",
    "good evening", "how are you", "what's up", "howdy",
]

_OUT_OF_SCOPE_INDICATORS = [
    "weather", "poem", "joke", "capital of", "who is", "what is a",
    "what is an", "explain what", "define ", "definition of",
    "stock price", "news", "sports", "movie", "recipe", "translate",
    "what does .* mean", "meaning of",
]

_AMBIGUOUS_PATTERNS = [
    "show me the loans",   # too vague
    "tell me about",       # too vague
    "get the report",      # unspecified
    "what happened",       # unspecified
    "give me data",        # unspecified
    "run a query",         # no subject
]


_FOLLOW_UP_PATTERNS = [
    "what about", "how about", "only show", "sort them by", "sort by",
    "filter by", "only failed", "failed ones", "active ones", "closed ones",
    "which of those", "how many of them", "and also", "show failed ones",
    "what of", "and for", "only for", "show them",
]


def mock_classify_intent(
    query: str,
    conversation_history: List[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    """Deterministic keyword-based intent classification for mock provider.

    This is used ONLY when LLM_PROVIDER is 'mock'. It provides stable, reproducible
    test behavior and context resolution across multi-turn sessions without requiring API credentials.

    Args:
        query: The current user message.
        conversation_history: Optional prior conversation turns used for context resolution.

    Returns:
        A dict matching IntentClassification fields.
    """
    q = query.lower().strip()

    # 1. Greeting / trivial chitchat
    if any(q == g or q.startswith(g) for g in _GREETINGS) and len(q) < 60:
        return {
            "request_mode": "OUT_OF_SCOPE",
            "intent_reason": "Greeting or chitchat - not a banking data query.",
            "query_description": None,
            "clarification_question": None,
        }

    # 2. Explicit out-of-scope indicators
    for indicator in _OUT_OF_SCOPE_INDICATORS:
        if indicator in q:
            return {
                "request_mode": "OUT_OF_SCOPE",
                "intent_reason": f"Non-banking topic detected ('{indicator}').",
                "query_description": None,
                "clarification_question": None,
            }

    # 3. Schedule-only (wants recurring job, no immediate data)
    if any(kw in q for kw in _SCHEDULE_ONLY_KEYWORDS):
        return {
            "request_mode": "SCHEDULE_ONLY",
            "intent_reason": "User wants to set up a recurring scheduled job without immediate results.",
            "query_description": query,
            "clarification_question": None,
        }

    # 4. Multi-turn conversation context resolution
    # Check if this query is a follow-up referencing prior banking context
    prior_banking_query = None
    if conversation_history:
        for msg in reversed(conversation_history):
            if msg.get("role") == "user" and msg.get("content"):
                c = msg["content"].lower()
                if any(kw in c for kw in _BANKING_DATA_KEYWORDS) and not any(ind in c for ind in _OUT_OF_SCOPE_INDICATORS):
                    prior_banking_query = msg["content"]
                    break

    has_banking = any(kw in q for kw in _BANKING_DATA_KEYWORDS)
    has_schedule = any(kw in q for kw in _SCHEDULE_KEYWORDS)

    # If query lacks explicit banking keywords but is a conversational follow-up to prior banking query
    is_follow_up = False
    if prior_banking_query:
        if any(pat in q for pat in _FOLLOW_UP_PATTERNS):
            is_follow_up = True
        elif len(q.split()) <= 6 and not any(q == g or q.startswith(g) for g in _GREETINGS):
            # Short elliptical query with prior banking context (e.g. "What about Coimbatore?", "In Mumbai?")
            is_follow_up = True

    if is_follow_up and prior_banking_query:
        has_banking = True
        composite_desc = f"{prior_banking_query} (follow-up: {query})"
    else:
        composite_desc = query

    # 5. Banking query + scheduling together -> QUERY_AND_SCHEDULE
    if has_banking and has_schedule:
        return {
            "request_mode": "QUERY_AND_SCHEDULE",
            "intent_reason": "User wants to retrieve banking data AND schedule recurring delivery.",
            "query_description": composite_desc,
            "clarification_question": None,
        }

    # 6. Pure banking data query (standalone or contextual follow-up)
    if has_banking:
        # Check for excessive vagueness (only for standalone queries, not follow-ups)
        if not is_follow_up and any(pat in q for pat in _AMBIGUOUS_PATTERNS) and len(q) < 50:
            return {
                "request_mode": "CLARIFICATION_REQUIRED",
                "intent_reason": "Banking topic detected but query is too vague to generate a pipeline.",
                "query_description": None,
                "clarification_question": "Could you provide more details? For example: which loan status, time range, branch, or customer segment are you interested in?",
            }
        reason = "Contextual follow-up banking query identified." if is_follow_up else "Clear banking data query identified."
        return {
            "request_mode": "QUERY_ONLY",
            "intent_reason": reason,
            "query_description": composite_desc,
            "clarification_question": None,
        }

    # 7. Has scheduling keywords but no clear banking subject -> clarify
    if has_schedule:
        return {
            "request_mode": "CLARIFICATION_REQUIRED",
            "intent_reason": "Scheduling intent detected but no banking data subject specified.",
            "query_description": None,
            "clarification_question": "What data or report would you like to schedule? Please specify the banking metric or collection you're interested in.",
        }

    # 8. Very short or unclear input without prior context
    if len(q) < 10:
        return {
            "request_mode": "CLARIFICATION_REQUIRED",
            "intent_reason": "Query is too short to determine intent.",
            "query_description": None,
            "clarification_question": "Could you describe what banking data or analysis you need in more detail?",
        }

    # 9. Default - out of scope for unrecognised content
    return {
        "request_mode": "OUT_OF_SCOPE",
        "intent_reason": "No banking data keywords or scheduling intent detected in the query.",
        "query_description": None,
        "clarification_question": None,
    }
