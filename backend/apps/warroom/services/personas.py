"""Persona advocates for the War Room debate.

The live debate path (services/debate.py) runs each persona as a real streaming
run via run_ai_on_message and imports _FRAMING + _user_prompt from here. (The
earlier run_structured-based ``run_persona`` / ``PersonaArgument`` were superseded
by that path and removed.)"""

from __future__ import annotations

_FRAMING = {
    "bull": "You are the BULL. Argue the strongest evidence-based case FOR the position. Be concrete.",
    "bear": "You are the BEAR. Argue the strongest evidence-based case AGAINST the position. Be concrete.",
    "skeptic": "You are the SKEPTIC. Attack the assumptions on BOTH sides; name what's unknowable and what would falsify each case.",
}


def _user_prompt(subject_context: str, prior_args: list[dict]) -> str:
    parts = [f"SUBJECT:\n{subject_context}"]
    if prior_args:
        prior = "\n".join(f"- [{a.get('persona')}] {a.get('argument')}" for a in prior_args)
        parts.append(f"\nARGUMENTS SO FAR (rebut where you disagree):\n{prior}")
    parts.append("\nMake your case. Strictly observational; no buy/sell directive.")
    return "\n".join(parts)
