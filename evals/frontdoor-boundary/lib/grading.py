#!/usr/bin/env python3
"""Deterministic grader for the FRONT-DOOR DISPATCH BOUNDARY: did the orchestrating context do a
specialist's work itself instead of dispatching it?

WHAT THIS PROTECTS. A front-door skill exists to ROUTE: it scopes the request, dispatches the
specialist that owns the work, and records what came back. The recurring defect - eight instances
of it were corrected in one pass - is a front door whose own body tells the orchestrator to perform
the specialist step INLINE: `odoo-forward-port` P6/P7 ran a conflict scan, raw OSM
`model_inspect`/`entity_lookup` grounding and a `python -m pytest --collect-only` collection gate in
the main context; `odoo-solution-design` had the orchestrator decide contested symbols itself
instead of dispatching the reconcile pass. Prose alone has already failed once here, so the prose
correction needs a mechanism behind it. This module is that mechanism's grading half.

WHICH HALF COVERS WHICH GAP - the two halves are complementary, neither is redundant:
  - `plugins/odoo-ai-agents/hooks/block-coordinator-code-write.sh` (PREVENTIVE, runtime) refuses a
    write when the CALLER is a dispatched AGENT whose declared role forbids authoring. It needs a
    populated `agent_type` to resolve a role, so it can only ever act on a dispatched subagent.
  - THIS GRADER (DETECTIVE, post-hoc) covers the gap that hook structurally cannot reach: a
    FRONT-DOOR SKILL running in the MAIN context, where there is no `agent_type` at all and
    therefore no coordinator role for a PreToolUse hook to key on. It also covers a dispatched
    COORDINATOR's own inline breach, which a sidechain filter would miss (see "Why not
    isSidechain" below).

HOW A TURN'S ACTOR IS RESOLVED (the whole design rests on this). Keying on `isSidechain` was
measured and REJECTED: main-context turns are all `isSidechain:false` and a dispatched subagent's
turns are all `true`, but a subagent COORDINATOR's forbidden call is itself a sidechain turn - so a
sidechain filter misses exactly the case that matters. This grader keys on the turn's AGENT
IDENTITY resolved through `agents.<name>.role` in `plugins/odoo-ai-agents/generator/
skill_tool_deps.json` - the same agent-role SSOT lookup already live at
`hooks/remind-delegate.sh` (leaf advisory) and `hooks/block-coordinator-code-write.sh` (role gate),
with the same `${AGENT_TYPE##*:}` bare-name normalization, so adding an agent to the SSOT arms this
grader for it with no edit here.

    no agent identity on the turn   -> MAIN-CONTEXT ORCHESTRATOR   -> in scope (the front-door gap)
    role: coordinator | spawner     -> DISPATCHED ORCHESTRATOR     -> in scope (the sidechain gap)
    role: leaf                      -> SPECIALIST doing its own job -> out of scope, never flagged
    identity present, role unknown  -> UNKNOWN ACTOR                -> out of scope (see residuals)

The identity field spellings are OBSERVED, not guessed. A real subagent transcript line carries
`attributionAgent` (e.g. `"odoo-ai-agents:odoo-backend-coder"`, `"git-toolkit:github-operator"`)
alongside `agentId` and `isSidechain:true`; a real MAIN-context transcript line carries
`attributionSkill` (e.g. `"odoo-ai-agents:odoo-forward-port"`) and NEVER `attributionAgent`. The
hook-shaped spellings (`agent_type`/`agentType`/`subagent_type`) are accepted too so a transcript
captured from a hook payload grades identically.

WHY THIS IS ITS OWN MODULE, not an addition to `evals/resource-teardown/lib/grading.py`. That file
is scoped - by its own docstring and by its directory - to the resource-teardown contract's T0-T4
evals, and the repo's layout is one `lib/grading.py` per eval directory. A front-door boundary
grader is a DIFFERENT contract with its own eval directory, so hosting it under a directory named
after an unrelated contract would make that directory name a lie and pile every future guard into
it. The parsing overlap is deliberate and bounded: `_iter_turns_with_envelope()` below is not a copy
of that module's `_iter_turns()` - it yields a third element that one discards by contract - and
that function is left byte-identical because its own CI tests pin its behavior and a cross-eval
import would couple two independent eval directories.

FORBIDDEN CLASSES ARE DATA, NOT CODE. `grade_frontdoor_boundary()` takes the classes as an
argument; each eval definition (`../<skill>.evals.json` -> `forbidden_tool_classes`) is the SSOT for
what ITS front door may not do inline, so the eval definition and the CI fixture test cannot drift
apart. A class is matched on tool name AND/OR flattened input shape, with whitespace normalized -
never on line adjacency, and never on a single phrasing.

No LLM judgment is used: every assertion is mechanical (name suffix / regex over the flattened tool
input), so a deterministic grader is more reliable here (ETHOS #8: assert on observable results).

RESIDUAL FALSE NEGATIVES - stated, not papered over. A guard that claimed completeness it lacks is
worse than one that names its limit:
  R1. An orchestrator that REASONS FROM MEMORY and calls no tool leaves no transcript evidence at
      all. The `odoo-solution-design` breach in its purest form - reading the contested-symbols file
      and picking a winner in its own head - is invisible here unless the decision is written out.
  R2. An actor whose name resolves to no `agents.<name>.role` entry (`general-purpose`, `Explore`, a
      third-party plugin agent) is treated as delegated and never flagged. This is deliberate and
      mirrors `block-coordinator-code-write.sh`: the gate acts on a POSITIVE role claim only, so an
      actor this repo declares nothing about is never accused. It is also load-bearing - the
      corrected `odoo-forward-port` P6 dispatches `Explore` to do exactly the grounding calls that
      would be a violation if the orchestrator issued them.
  R3. Shape-keyed, not semantics-keyed. An inline specialist step spelled through a wrapper the
      class's `input_pattern` does not name (`make test`, `./gate.sh`, a command assembled from
      shell variables, an MCP tool outside the declared suffixes) is not matched.
  R4. `satisfied_by_prior_dispatch` proves a DISPATCH HAPPENED before the write, not that what was
      written is what the dispatch returned. An orchestrator that dispatches the reconcile pass and
      then writes its own verdict anyway is exonerated by this grader.
  R5. Turn ORDER within the transcript is the only ordering signal. A dispatch whose result had not
      returned yet (fire-and-forget, then write) reads the same as one that was awaited.
  R6. The inverse risk, for completeness: a transcript export carrying NO attribution keys at all
      makes every assistant turn look like the main-context orchestrator, which produces false
      POSITIVES on a leaf's legitimate calls - not false negatives. `actors` in the result names
      what was resolved, so this is visible rather than silent.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Iterable

# Repo root: evals/frontdoor-boundary/lib/grading.py -> parents[3]. Portable (no absolute path).
_REPO_ROOT = Path(__file__).resolve().parents[3]
_AGENT_ROLE_SSOT = _REPO_ROOT / "plugins" / "odoo-ai-agents" / "generator" / "skill_tool_deps.json"

# Roles that mean "this actor routes work"; anything it does inline that a specialist owns is the
# defect. SSOT for the vocabulary itself is skill_tool_deps.json's own `agents.<name>.role` values.
ORCHESTRATING_ROLES = frozenset({"coordinator", "spawner"})

# Envelope keys that name a DISPATCHED AGENT. `attributionAgent` is what real Claude Code subagent
# transcripts carry; the rest are the hook-payload spellings (remind-delegate.sh / V-52) so a
# transcript captured from a hook stream grades the same way.
_AGENT_NAME_KEYS = ("attributionAgent", "agent_type", "agentType", "subagent_type", "subagentType")
# Presence of an opaque id alone still proves "this turn ran inside a subagent" even when no name
# is carried - same signal block-coordinator-code-write.sh condition (a) uses.
_AGENT_ID_KEYS = ("agent_id", "agentId")
# Envelope keys that name the ACTIVE SKILL. Real main-context transcripts carry `attributionSkill`.
_SKILL_NAME_KEYS = ("attributionSkill", "skill_name", "skillName")

_WS_RE = re.compile(r"\s+")


# --------------------------------------------------------------------------------------------- #
# Transcript parsing - envelope-PRESERVING sibling of resource-teardown/lib/grading.py::_iter_turns
# --------------------------------------------------------------------------------------------- #


def _iter_turns_with_envelope(transcript_path) -> Iterable[tuple[str, list, dict]]:
    """Yield (role, content_blocks, envelope) for every line of a transcript.jsonl.

    This is the deliberate sibling of `evals/resource-teardown/lib/grading.py::_iter_turns`, which
    yields `(role, content)` and DISCARDS the envelope - so the identity fields this grader keys on
    (`attributionAgent`, `attributionSkill`, `agentId`) are invisible to it. That function's
    contract is pinned by its own graders and their CI tests and is left untouched; this one adds
    the third element instead of widening it.

    Tolerates both the raw `{"role": ..., "content": [...]}` shape the fixture builders use and the
    `{"message": {"role": ..., "content": [...]}, ...}` envelope real Claude Code transcripts wrap
    turns in - the same tolerance `hooks/enforce-teardown.sh` applies (`(.message // .)`). The
    envelope returned is the OUTER object, because that is where the attribution keys live.
    """
    text = Path(transcript_path).read_text(encoding="utf-8")
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        msg = obj.get("message", obj)
        if not isinstance(msg, dict):
            msg = {}
        role = msg.get("role") or obj.get("type") or ""
        content = msg.get("content") or []
        if isinstance(content, list):
            yield role, content, obj


def _lookup(envelope: dict, keys: tuple[str, ...]) -> str:
    """First non-empty value among `keys`, checked on the envelope and on its nested message."""
    nested = envelope.get("message")
    scopes = [envelope, nested if isinstance(nested, dict) else {}]
    for scope in scopes:
        for key in keys:
            value = scope.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ""


def _bare(name: str) -> str:
    """`odoo-ai-agents:odoo-coder` -> `odoo-coder`. Same normalization the hooks use (`${V##*:}`)."""
    return name.rsplit(":", 1)[-1].strip()


def load_agent_roles(roles_path=None) -> dict[str, str]:
    """Read `agents.<name>.role` from the agent-role SSOT (generator/skill_tool_deps.json).

    A missing/unreadable SSOT degrades to an EMPTY map rather than raising: every named actor then
    resolves to `unknown` and only the main-context orchestrator is graded. That is the same
    fail-open posture the hooks take on a missing SSOT - never guess a role.
    """
    path = Path(roles_path) if roles_path else _AGENT_ROLE_SSOT
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    agents = data.get("agents", {})
    if not isinstance(agents, dict):
        return {}
    return {
        name: str(spec.get("role", "")).strip()
        for name, spec in agents.items()
        if isinstance(spec, dict)
    }


def resolve_turn_actor(envelope: dict, roles: dict[str, str]) -> dict:
    """Classify WHO issued this turn: orchestrator, specialist leaf, or unknown actor.

    Returns {agent, skill, role, kind, orchestrating}. `kind` is one of:
      `main-context`   - no agent identity at all: the front-door skill running as the orchestrator.
      `coordinator`    - a dispatched agent whose declared role routes work (coordinator/spawner).
      `leaf`           - a dispatched specialist; its own tool calls are its job, never a breach.
      `unknown-actor`  - inside a subagent this repo declares no role for (see residual R2).
    """
    agent = _bare(_lookup(envelope, _AGENT_NAME_KEYS))
    skill = _bare(_lookup(envelope, _SKILL_NAME_KEYS))
    has_agent_id = bool(_lookup(envelope, _AGENT_ID_KEYS))

    if not agent and not has_agent_id:
        return {"agent": "", "skill": skill, "role": "", "kind": "main-context", "orchestrating": True}
    role = roles.get(agent, "")
    if role in ORCHESTRATING_ROLES:
        return {"agent": agent, "skill": skill, "role": role, "kind": "coordinator", "orchestrating": True}
    if role == "leaf":
        return {"agent": agent, "skill": skill, "role": role, "kind": "leaf", "orchestrating": False}
    return {"agent": agent, "skill": skill, "role": role, "kind": "unknown-actor", "orchestrating": False}


# --------------------------------------------------------------------------------------------- #
# Forbidden-class matching
# --------------------------------------------------------------------------------------------- #


def _flatten(value) -> Iterable[str]:
    """Every scalar inside a nested tool input, as plain strings."""
    if isinstance(value, dict):
        for item in value.values():
            yield from _flatten(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _flatten(item)
    elif value is not None:
        yield str(value)


def tool_use_haystack(block: dict) -> str:
    r"""Flatten a tool_use block's name + input into one greppable, WHITESPACE-NORMALIZED string.

    Two deliberate choices, each with a defect it exists to catch:
      - NOT `json.dumps()`-ed. A JSON encoding backslash-escapes embedded quotes, which defeats a
        pattern written against the text as it appears on the wire (same reasoning as
        resource-teardown/lib/grading.py::_tool_use_haystack).
      - Runs of whitespace - INCLUDING newlines - collapse to one space, so a command broken across
        lines with a backslash continuation, a heredoc, or a wrapped multi-line prompt matches the
        same pattern as its single-line spelling. Matching must never depend on line adjacency.
    """
    name = str(block.get("name", ""))
    values = " ".join(_flatten(block.get("input", {})))
    return _WS_RE.sub(" ", f"{name} {values}").strip()


def _compile_class(spec: dict) -> dict:
    """Validate + compile one forbidden class. A class that could match ANYTHING is refused."""
    if not isinstance(spec, dict):
        raise ValueError(f"forbidden class must be an object, got {type(spec).__name__}")
    cid = str(spec.get("id", "")).strip()
    if not cid:
        raise ValueError("each forbidden class needs an `id`")
    suffixes = tuple(spec.get("tool_name_suffixes") or ())
    name_pat = spec.get("tool_name_pattern") or ""
    input_pat = spec.get("input_pattern") or ""
    if not suffixes and not name_pat and not input_pat:
        # A class with no selector matches every tool call ever made - a landmine, not a guard.
        raise ValueError(
            f"forbidden class {cid!r} declares no selector "
            "(need at least one of tool_name_suffixes / tool_name_pattern / input_pattern)"
        )
    prior = spec.get("satisfied_by_prior_dispatch") or None
    if prior is not None and not (prior.get("tool_name_pattern") or prior.get("input_pattern")):
        raise ValueError(f"forbidden class {cid!r}: satisfied_by_prior_dispatch declares no selector")
    return {
        "id": cid,
        "rule": str(spec.get("rule", "")).strip(),
        "suffixes": suffixes,
        "name_re": re.compile(name_pat) if name_pat else None,
        "input_re": re.compile(input_pat) if input_pat else None,
        "exempt_re": re.compile(spec["exempt_input_pattern"]) if spec.get("exempt_input_pattern") else None,
        "prior_name_re": re.compile(prior["tool_name_pattern"]) if prior and prior.get("tool_name_pattern") else None,
        "prior_input_re": re.compile(prior["input_pattern"]) if prior and prior.get("input_pattern") else None,
        "prior_label": (prior or {}).get("label", ""),
    }


def _class_matches(cls: dict, name: str, hay: str) -> bool:
    selectors_declared = bool(cls["suffixes"]) or cls["name_re"] is not None
    if selectors_declared:
        name_ok = any(name.endswith(s) for s in cls["suffixes"])
        if not name_ok and cls["name_re"] is not None:
            name_ok = bool(cls["name_re"].search(name))
        if not name_ok:
            return False
    if cls["input_re"] is not None and not cls["input_re"].search(hay):
        return False
    if cls["exempt_re"] is not None and cls["exempt_re"].search(hay):
        return False
    return True


def _prior_dispatch_matches(cls: dict, name: str, hay: str) -> bool:
    if cls["prior_name_re"] is None and cls["prior_input_re"] is None:
        return False
    if cls["prior_name_re"] is not None and not cls["prior_name_re"].search(name):
        return False
    if cls["prior_input_re"] is not None and not cls["prior_input_re"].search(hay):
        return False
    return True


# --------------------------------------------------------------------------------------------- #
# The grader
# --------------------------------------------------------------------------------------------- #


def grade_frontdoor_boundary(transcript_path, forbidden_tool_classes, skill_name=None,
                             roles_path=None) -> dict:
    """Return the assistant `tool_use` blocks issued WHILE ACTING AS THE ORCHESTRATOR that match a
    forbidden class for that context.

    PASS iff (a) at least one orchestrating turn exists - a transcript with no orchestrator in it
    can never fail, so grading it PASS would be vacuous - and (b) no orchestrating tool_use matches
    a forbidden class without being exonerated.

    `forbidden_tool_classes` is a list of objects (SSOT: each eval definition's
    `forbidden_tool_classes`):
        id                          required, names the class in the verdict
        rule                        human-readable statement of what the front door must dispatch
        tool_name_suffixes          [..]  suffix-keyed name match (MCP-prefix agnostic, so a new
                                          namespace - headed/plugin_* - is covered for free)
        tool_name_pattern           regex over the full tool name
        input_pattern               regex over the whitespace-normalized name + flattened input
        exempt_input_pattern        regex that, when it matches, makes the call legitimate
        satisfied_by_prior_dispatch {tool_name_pattern, input_pattern, label} - an EARLIER assistant
                                    tool_use matching this exonerates the hit (the specialist WAS
                                    dispatched; see residual R4 for what that does and does not
                                    prove)
    At least one of the three selectors is required; a class with none raises ValueError rather than
    silently matching every call.

    `skill_name`, when given, drops turns POSITIVELY attributed to a DIFFERENT skill. Turns carrying
    no skill attribution stay in scope: the subject of this guard is the orchestrator, and an
    unattributed orchestrating turn is exactly the shape being hunted.

    Residual false negatives: see this module's docstring, R1-R6. The one that matters most - an
    orchestrator that reasons from memory and calls no tool leaves no transcript evidence (R1).
    """
    classes = [_compile_class(c) for c in (forbidden_tool_classes or [])]
    if not classes:
        raise ValueError("grade_frontdoor_boundary needs at least one forbidden class")

    roles = load_agent_roles(roles_path)
    want_skill = _bare(skill_name) if skill_name else ""

    violations: list[dict] = []
    exonerated: list[dict] = []
    actors: dict[str, int] = {}
    orchestrating_turns = 0
    delegated_turns = 0
    seen_dispatches: list[tuple[str, str]] = []  # (name, haystack) of every EARLIER assistant call

    for turn_index, (role, content, envelope) in enumerate(_iter_turns_with_envelope(transcript_path)):
        if role != "assistant":
            continue
        actor = resolve_turn_actor(envelope, roles)
        label = actor["kind"] if not actor["agent"] else f"{actor['kind']}:{actor['agent']}"
        actors[label] = actors.get(label, 0) + 1
        in_scope = actor["orchestrating"]
        if in_scope and want_skill and actor["skill"] and actor["skill"] != want_skill:
            in_scope = False  # positively attributed to another front door - not this eval's subject
        if in_scope:
            orchestrating_turns += 1
        else:
            delegated_turns += 1

        for block_index, block in enumerate(content):
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            name = str(block.get("name", ""))
            hay = tool_use_haystack(block)
            if in_scope:
                for cls in classes:
                    if not _class_matches(cls, name, hay):
                        continue
                    hit = {
                        "class_id": cls["id"],
                        "rule": cls["rule"],
                        "tool_name": name,
                        "turn_index": turn_index,
                        "block_index": block_index,
                        "actor": label,
                        "evidence": hay[:240],
                        "block": block,
                    }
                    prior = next(
                        (d for d in seen_dispatches if _prior_dispatch_matches(cls, d[0], d[1])),
                        None,
                    )
                    if prior is not None:
                        hit["exonerated_by"] = cls["prior_label"] or prior[0]
                        exonerated.append(hit)
                    else:
                        violations.append(hit)
            # Every assistant call - orchestrating or delegated - can serve as a prior dispatch.
            seen_dispatches.append((name, hay))

    expectations = [
        {
            "text": "The transcript contains at least one turn issued by the orchestrator "
                    "(main context, or a dispatched coordinator/spawner) - otherwise nothing here "
                    "could ever fail.",
            "passed": orchestrating_turns > 0,
            "evidence": f"orchestrating_turns={orchestrating_turns} delegated_turns={delegated_turns} "
                        f"actors={actors}",
        }
    ]
    for cls in classes:
        hits = [v for v in violations if v["class_id"] == cls["id"]]
        expectations.append(
            {
                "text": f"The orchestrating context issues no `{cls['id']}` call: "
                        f"{cls['rule'] or 'this step belongs to a dispatched specialist.'}",
                "passed": not hits,
                "evidence": (
                    "no orchestrating tool_use matched this class"
                    if not hits
                    else "; ".join(
                        f"turn {h['turn_index']} ({h['actor']}) {h['tool_name']}: {h['evidence'][:120]}"
                        for h in hits
                    )
                ),
            }
        )

    return {
        "pass": orchestrating_turns > 0 and not violations,
        "violations": violations,
        "exonerated": exonerated,
        "orchestrating_turns": orchestrating_turns,
        "delegated_turns": delegated_turns,
        "actors": actors,
        "expectations": expectations,
    }


# --------------------------------------------------------------------------------------------- #
# CLI - for grading a REAL transcript captured from a live front-door session
# --------------------------------------------------------------------------------------------- #


def _main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: grading.py <eval-definition.evals.json> <transcript.jsonl>", file=sys.stderr)
        return 2
    eval_path, transcript_path = argv
    spec = json.loads(Path(eval_path).read_text(encoding="utf-8"))
    result = grade_frontdoor_boundary(
        transcript_path,
        spec.get("forbidden_tool_classes", []),
        skill_name=spec.get("skill_name") or spec.get("agent_name"),
    )
    printable = {
        key: value for key, value in result.items() if key not in ("violations", "exonerated")
    }
    printable["violations"] = [
        {k: v for k, v in hit.items() if k != "block"} for hit in result["violations"]
    ]
    printable["exonerated"] = [
        {k: v for k, v in hit.items() if k != "block"} for hit in result["exonerated"]
    ]
    printable["summary"] = {
        "passed": sum(1 for e in result["expectations"] if e["passed"]),
        "total": len(result["expectations"]),
    }
    print(json.dumps(printable, indent=2))
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
