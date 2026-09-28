"""protocol.py - MCP over newline-delimited JSON-RPC 2.0 on stdio, plus the tool registry.

Wire rules:
  - one JSON object per line on stdin; one per line on stdout; stdout carries NOTHING else (the
    entry point re-points fd 1 at stderr and hands this module a private dup of the real stdout).
  - requests other than tools/call are answered inline on the reader thread; tools/call runs off the
    reader thread (one of the two lanes below) so a slow tool never blocks ping or a second call. One lock serializes writes.
  - TWO lanes, and a call never waits in a queue behind a call of the other lane:
      LONG  a tool registered with long_running=True - one that can block for minutes or wait on
            a slow probe (job_wait, instance_serve, instance_status, db_preflight, lease_find -
            whose parked lookup probes the database - gc, and the lease mutations acquire /
            release / park, which may stop a server or drop a database) - runs on a THREAD OF ITS
            OWN, started for that call. Nothing bounds the lane, so no long call ever queues: a lease_release answers at once while any number
            of job_waits block, and a fan-out of slow instance_status probes cannot hold up a
            release either. (A bounded long pool is exactly what starved lease mutations: 32
            job_waits filled it and a release queued behind them.)
      SHORT every other tool (lease_list, lease_adopt, catalog_read, server_info ...) - quick
            calls that never wait on a probe - runs on a small bounded pool. Since nothing slow
            is ever submitted to it, a free short worker is always moments away.
  - protocol errors: -32700 parse, -32600 invalid request (including a null id, which MCP forbids),
    -32601 unknown method, -32602 invalid params (including an unknown tool name, and any
    tools/list cursor - this server lists every tool in one page and never issues a cursor).
  - cancellation: notifications/cancelled for an in-flight tools/call sets that call's cancel
    event (cancel_event() inside the handler) and its response is never sent. A handler that WAITS
    (job_wait) polls the event and returns early; one that mutates (lease_release, a database
    drop) never looks at it and runs to completion - a half-done teardown is worse than a late one.
    stdin EOF cancels every in-flight call the same way, then drains them. A tool's own failure is NOT a protocol error: it is a
    tools/call result with isError=true and structuredContent {"error": {code, message, remedy,
    diagnostics}} (remedy from errors.py).

Tool registration API (tools_*.py each expose `register(registry, ctx)`):

    registry.add(name, description, input_schema, output_schema, handler,
                 title=None, read_only=False, long_running=False, destructive=None, idempotent=False)

Annotations: every tool is advertised openWorldHint=false (it touches only this machine). A tool
that is not read_only states `destructive` (True when it can stop a server or drop a database,
False when it only adds or re-labels state); a test holds every real tool to that.

    handler(args: dict, ctx: ServerContext) -> dict   # the structuredContent on success
    raise errors.ToolError(code, message, diagnostics) # the isError result on failure

`args` has been validated against input_schema (INVALID_ARGUMENTS names the bad field otherwise)
and top-level `default`s are filled in. The returned dict is checked against output_schema before
it is sent - a handler that drifts from its advertised schema returns INTERNAL rather than a result
the client would reject. The advertised outputSchema is `{"type":"object","anyOf":[<success>,
<error envelope>]}` so a strict client validating structuredContent accepts both result shapes.
"""

import concurrent.futures
import json
import logging
import re
import sys
import threading
import traceback

from . import SUPPORTED_PROTOCOL_VERSIONS  # newest first; defined in the package __init__
from . import errors
from .errors import ToolError

log = logging.getLogger("odoo-local")

SERVER_NAME = "odoo-local"
# What we answer when the client asks for a revision we lack.
LATEST_PROTOCOL_VERSION = SUPPORTED_PROTOCOL_VERSIONS[0]


def negotiate_protocol_version(requested):
    """The revision to answer initialize with: the client's when supported, else our latest."""
    return requested if requested in SUPPORTED_PROTOCOL_VERSIONS else LATEST_PROTOCOL_VERSION


INSTRUCTIONS = (
    "odoo-local drives LIVE local Odoo instances on this machine: lease a database and ports, "
    "build/test/serve an instance, and read the local instance catalog (instances.toml). "
    "It is NOT the Odoo source index - use Odoo Semantic for source/structure questions - "
    "and it holds no business records. Every failure returns error.code plus a one-line "
    "error.remedy: follow the remedy."
)

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603

# Tool names the plugin's browser-teardown hooks key on (prefix / suffix match on the bare tool
# name). A local tool matching one would be miscounted as a browser page or recording.
_RESERVED_PREFIXES = ("browser_",)
_RESERVED_SUFFIXES = ("new_page", "close_page", "record_page", "stop_recording")
_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


# --------------------------------------------------------------------------- #
# per-call cancellation
# --------------------------------------------------------------------------- #
_call_state = threading.local()
_NEVER_CANCELLED = threading.Event()  # never set: what cancel_event() returns outside a call


def cancel_event():
    """The cancellation Event of the tools/call running on this thread. It is set when the client
    sends notifications/cancelled for the call, or stdin closes. Outside a call it is never set."""
    return getattr(_call_state, "cancel", None) or _NEVER_CANCELLED


# --------------------------------------------------------------------------- #
# minimal JSON Schema validator (the subset the tool schemas use)
# --------------------------------------------------------------------------- #
_TYPE_CHECKS = {
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str),
    "boolean": lambda v: isinstance(v, bool),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "null": lambda v: v is None,
}


def _type_name(value):
    for name in ("null", "boolean", "integer", "number", "string", "array", "object"):
        if _TYPE_CHECKS[name](value):
            return name
    return type(value).__name__


def validate(value, schema, path="arguments"):
    """Return None when `value` satisfies `schema`, else a precise one-line message naming the path.

    Supports: type (string or list), enum, const, minimum, maximum, minLength, maxLength, minItems,
    maxItems, items, required, properties, additionalProperties (false or a schema), anyOf."""
    if not isinstance(schema, dict):
        return None
    if "anyOf" in schema:
        messages = []
        for sub in schema["anyOf"]:
            msg = validate(value, sub, path)
            if msg is None:
                break
            messages.append(msg)
        else:
            return "%s matches none of the allowed shapes (%s)" % (path, "; ".join(messages))
    expected = schema.get("type")
    if expected is not None:
        types = expected if isinstance(expected, list) else [expected]
        if not any(_TYPE_CHECKS.get(t, lambda v: False)(value) for t in types):
            return "%s: expected %s, got %s" % (path, " or ".join(types), _type_name(value))
    if "const" in schema and value != schema["const"]:
        return "%s: must be %s" % (path, json.dumps(schema["const"]))
    if "enum" in schema and value not in schema["enum"]:
        return "%s: %s is not one of %s" % (path, json.dumps(value), json.dumps(schema["enum"]))
    if _TYPE_CHECKS["number"](value):
        if "minimum" in schema and value < schema["minimum"]:
            return "%s: %s is below the minimum %s" % (path, value, schema["minimum"])
        if "maximum" in schema and value > schema["maximum"]:
            return "%s: %s is above the maximum %s" % (path, value, schema["maximum"])
    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            return "%s: must be at least %d characters" % (path, schema["minLength"])
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            return "%s: must be at most %d characters" % (path, schema["maxLength"])
    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            return "%s: must have at least %d items" % (path, schema["minItems"])
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            return "%s: must have at most %d items" % (path, schema["maxItems"])
        if isinstance(schema.get("items"), dict):
            for i, item in enumerate(value):
                msg = validate(item, schema["items"], "%s[%d]" % (path, i))
                if msg:
                    return msg
    if isinstance(value, dict):
        for key in schema.get("required", ()):
            if key not in value:
                return "%s.%s: required field is missing" % (path, key)
        props = schema.get("properties", {})
        extra = schema.get("additionalProperties", True)
        for key in sorted(value):
            sub_path = "%s.%s" % (path, key)
            if key in props:
                msg = validate(value[key], props[key], sub_path)
            elif extra is False:
                allowed = ", ".join(sorted(props)) or "none"
                msg = "%s: unknown field (allowed: %s)" % (sub_path, allowed)
            elif isinstance(extra, dict):
                msg = validate(value[key], extra, sub_path)
            else:
                msg = None
            if msg:
                return msg
    return None


def apply_defaults(args, schema):
    """Fill top-level `default`s the caller omitted (the schema is the one place a default lives)."""
    out = dict(args)
    for key, sub in (schema.get("properties") or {}).items():
        if key not in out and isinstance(sub, dict) and "default" in sub:
            out[key] = json.loads(json.dumps(sub["default"]))
    return out


# --------------------------------------------------------------------------- #
# registry
# --------------------------------------------------------------------------- #
class Tool(object):
    def __init__(self, name, description, input_schema, output_schema, handler, title=None, read_only=False,
                 long_running=False, destructive=None, idempotent=False):
        self.name = name
        self.destructive = destructive
        self.idempotent = bool(idempotent)
        self.long_running = bool(long_running)
        self.description = description
        self.input_schema = input_schema
        self.output_schema = output_schema
        self.handler = handler
        self.title = title
        self.read_only = read_only

    def advertised_output_schema(self):
        return {"type": "object", "anyOf": [self.output_schema, errors.ERROR_ENVELOPE_SCHEMA]}

    def listing(self):
        entry = {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
            "outputSchema": self.advertised_output_schema(),
        }
        if self.title:
            entry["title"] = self.title
        annotations = {"readOnlyHint": bool(self.read_only), "openWorldHint": False}
        if not self.read_only:
            # MCP defaults destructiveHint to true; say what the tool really does when it is known.
            if self.destructive is not None:
                annotations["destructiveHint"] = bool(self.destructive)
            annotations["idempotentHint"] = self.idempotent
        if self.title:
            annotations["title"] = self.title
        entry["annotations"] = annotations
        return entry


def check_tool_name(name):
    """Raise ValueError for a name that is malformed or collides with the browser-hook vocabulary."""
    if not isinstance(name, str) or not _NAME_RE.match(name):
        raise ValueError("tool name %r must match %s" % (name, _NAME_RE.pattern))
    for prefix in _RESERVED_PREFIXES:
        if name.startswith(prefix):
            raise ValueError("tool name %r starts with reserved browser prefix %r" % (name, prefix))
    for suffix in _RESERVED_SUFFIXES:
        if name.endswith(suffix):
            raise ValueError("tool name %r ends with reserved browser suffix %r" % (name, suffix))


class ToolRegistry(object):
    def __init__(self):
        self._tools = {}
        self._order = []

    def add(self, name, description, input_schema, output_schema, handler, title=None, read_only=False,
            long_running=False, destructive=None, idempotent=False):
        check_tool_name(name)
        if name in self._tools:
            raise ValueError("tool %r registered twice" % name)
        if not isinstance(description, str) or not description.strip():
            raise ValueError("tool %r needs a description" % name)
        for label, schema in (("input_schema", input_schema), ("output_schema", output_schema)):
            if not isinstance(schema, dict) or schema.get("type") != "object":
                raise ValueError("tool %r %s must be a JSON Schema with type object" % (name, label))
        if not callable(handler):
            raise ValueError("tool %r handler is not callable" % name)
        self._tools[name] = Tool(name, description, input_schema, output_schema, handler, title, read_only,
                                 long_running, destructive, idempotent)
        self._order.append(name)
        return self._tools[name]

    def get(self, name):
        return self._tools.get(name)

    def names(self):
        return list(self._order)

    def listing(self):
        return [self._tools[n].listing() for n in self._order]


class ServerContext(object):
    """What a handler may need besides its arguments. Built once at startup."""

    def __init__(self, version, anchor, plugin_root):
        self.version = version
        self.anchor = anchor
        self.plugin_root = plugin_root
        self.protocol_version = None
        self.client_info = None


def _compact(obj):
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False, sort_keys=False)


def call_tool(tool, arguments, ctx):
    """Validate, run, and shape one tool call into an MCP CallToolResult dict."""
    try:
        msg = validate(arguments, tool.input_schema)
        if msg:
            raise ToolError("INVALID_ARGUMENTS", msg, {"tool": tool.name})
        args = apply_defaults(arguments, tool.input_schema)
        result = tool.handler(args, ctx)
        if not isinstance(result, dict):
            raise ToolError("INTERNAL", "tool %s returned %s, not an object" % (tool.name, type(result).__name__))
        drift = validate(result, tool.output_schema, "result")
        if drift:
            raise ToolError("INTERNAL", "tool %s result violates its outputSchema: %s" % (tool.name, drift), {"tool": tool.name})
        return {"content": [{"type": "text", "text": _compact(result)}], "structuredContent": result, "isError": False}
    except ToolError as exc:
        payload = exc.payload()
        return {"content": [{"type": "text", "text": _compact(payload)}], "structuredContent": payload, "isError": True}
    except Exception as exc:
        log.error("tool %s crashed:\n%s", tool.name, traceback.format_exc())
        payload = ToolError("INTERNAL", "tool %s crashed: %s: %s" % (tool.name, type(exc).__name__, exc),
                            {"tool": tool.name, "exception": type(exc).__name__}).payload()
        return {"content": [{"type": "text", "text": _compact(payload)}], "structuredContent": payload, "isError": True}


# --------------------------------------------------------------------------- #
# server loop
# --------------------------------------------------------------------------- #
SHORT_WORKERS = 8


class Server(object):
    def __init__(self, registry, ctx, out_stream, max_workers=SHORT_WORKERS):
        self.registry = registry
        self.ctx = ctx
        self._out = out_stream  # binary stream owned exclusively by this server
        self._write_lock = threading.Lock()
        self._pool = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="odoo-local-tool")
        self._long_lock = threading.Lock()
        self._long_threads = set()  # the LONG lane: one live thread per in-flight long call
        self._inflight_lock = threading.Lock()
        self._inflight = {}  # request id -> cancel Event, for every tools/call not yet finished

    # -- output ------------------------------------------------------------
    def send(self, message):
        data = (_compact(message) + "\n").encode("utf-8")
        with self._write_lock:
            try:
                self._out.write(data)
                self._out.flush()
            except (BrokenPipeError, ValueError, OSError) as exc:
                log.warning("stdout closed, dropping message: %s", exc)

    def _result(self, req_id, result):
        self.send({"jsonrpc": "2.0", "id": req_id, "result": result})

    def _error(self, req_id, code, message, data=None):
        err = {"code": code, "message": message}
        if data is not None:
            err["data"] = data
        self.send({"jsonrpc": "2.0", "id": req_id, "error": err})

    # -- input -------------------------------------------------------------
    def handle_line(self, raw):
        """Handle one stdin line (bytes or str). Never raises."""
        if isinstance(raw, bytes):
            try:
                raw = raw.decode("utf-8")
            except UnicodeDecodeError as exc:
                self._error(None, PARSE_ERROR, "Parse error: input is not UTF-8 (%s)" % exc)
                return
        line = raw.strip()
        if not line:
            return
        try:
            msg = json.loads(line)
        except ValueError as exc:
            self._error(None, PARSE_ERROR, "Parse error: %s" % exc)
            return
        if isinstance(msg, list):
            self._error(None, INVALID_REQUEST, "Invalid Request: JSON-RPC batches are not supported; send one message per line")
            return
        if not isinstance(msg, dict):
            self._error(None, INVALID_REQUEST, "Invalid Request: a message must be a JSON object")
            return
        is_request = "id" in msg
        req_id = msg.get("id")
        if msg.get("jsonrpc") != "2.0" or not isinstance(msg.get("method"), str):
            if "method" not in msg and ("result" in msg or "error" in msg):
                return  # a response to a server->client request; this server sends none, so ignore
            if is_request:
                self._error(req_id, INVALID_REQUEST, "Invalid Request: need jsonrpc \"2.0\" and a string method")
            return
        if is_request and not (isinstance(req_id, (str, int)) and not isinstance(req_id, bool)):
            # MCP: a request id MUST be a string or integer and MUST NOT be null.
            self._error(None, INVALID_REQUEST, "Invalid Request: id must be a string or integer (not null)")
            return
        method = msg["method"]
        params = msg.get("params")
        if params is None:
            params = {}
        if not is_request:
            self._notification(method, params)
            return
        if not isinstance(params, dict):
            self._error(req_id, INVALID_PARAMS, "Invalid params: params must be an object")
            return
        try:
            self._request(req_id, method, params)
        except Exception as exc:  # never let one message kill the loop
            log.error("request %r (%s) crashed:\n%s", req_id, method, traceback.format_exc())
            self._error(req_id, INTERNAL_ERROR, "Internal error: %s: %s" % (type(exc).__name__, exc))

    def _notification(self, method, params):
        if method == "notifications/initialized":
            log.info("client initialized")
        elif method == "notifications/cancelled":
            req_id = params.get("requestId") if isinstance(params, dict) else None
            with self._inflight_lock:
                cancel = self._inflight.get(req_id) if isinstance(req_id, (str, int)) else None
            if cancel is not None:
                cancel.set()
            log.info("client cancelled request %r (%s)", req_id,
                     "its response is suppressed" if cancel is not None else "not in flight; ignored")
        # every other notification is ignored, as JSON-RPC requires (no reply to a notification)

    def _request(self, req_id, method, params):
        if method == "initialize":
            self._initialize(req_id, params)
        elif method == "ping":
            self._result(req_id, {})
        elif method == "tools/list":
            if params.get("cursor") is not None:
                # Every tool is listed in one page and no nextCursor is ever issued, so any cursor is
                # one this server did not issue (MCP pagination: invalid cursor -> -32602).
                self._error(req_id, INVALID_PARAMS, "Invalid params: unknown cursor (tools/list returns every tool in one page)")
                return
            self._result(req_id, {"tools": self.registry.listing()})
        elif method == "tools/call":
            self._tools_call(req_id, params)
        else:
            self._error(req_id, METHOD_NOT_FOUND, "Method not found: %s" % method)

    def _initialize(self, req_id, params):
        requested = params.get("protocolVersion")
        if requested is not None and not isinstance(requested, str):
            self._error(req_id, INVALID_PARAMS, "Invalid params: protocolVersion must be a string")
            return
        negotiated = negotiate_protocol_version(requested)
        self.ctx.protocol_version = negotiated
        self.ctx.client_info = params.get("clientInfo")
        self._result(req_id, {
            "protocolVersion": negotiated,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": SERVER_NAME, "version": self.ctx.version},
            "instructions": INSTRUCTIONS,
        })

    def _tools_call(self, req_id, params):
        name = params.get("name")
        if not isinstance(name, str) or not name:
            self._error(req_id, INVALID_PARAMS, "Invalid params: tools/call needs a string 'name'")
            return
        tool = self.registry.get(name)
        if tool is None:
            self._error(req_id, INVALID_PARAMS, "Invalid params: unknown tool %r" % name,
                        {"available": self.registry.names()})
            return
        arguments = params.get("arguments")
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, dict):
            self._error(req_id, INVALID_PARAMS, "Invalid params: 'arguments' must be an object")
            return

        cancel = threading.Event()
        with self._inflight_lock:
            self._inflight[req_id] = cancel

        def work():
            _call_state.cancel = cancel
            try:
                result = call_tool(tool, arguments, self.ctx)
            finally:
                _call_state.cancel = None
                with self._inflight_lock:
                    if self._inflight.get(req_id) is cancel:
                        del self._inflight[req_id]
            if cancel.is_set():
                log.info("tools/call %r (%s) was cancelled; response not sent", req_id, tool.name)
                return
            self._result(req_id, result)

        if tool.long_running:
            self._start_long(work)
        else:
            self._pool.submit(work)

    def _start_long(self, work):
        """Run `work` on a thread of its own (the LONG lane; see the module docstring)."""
        def run():
            try:
                work()
            finally:
                with self._long_lock:
                    self._long_threads.discard(threading.current_thread())

        thread = threading.Thread(target=run, name="odoo-local-long", daemon=True)
        with self._long_lock:
            self._long_threads.add(thread)
        thread.start()

    def _cancel_all(self):
        with self._inflight_lock:
            pending = list(self._inflight.values())
        for cancel in pending:
            cancel.set()

    def _drain_long(self):
        while True:
            with self._long_lock:
                pending = list(self._long_threads)
            if not pending:
                return
            for thread in pending:
                thread.join()

    # -- lifecycle ---------------------------------------------------------
    def serve(self, in_stream):
        """Read stdin until EOF, then drain in-flight tool calls and return."""
        try:
            for raw in iter(in_stream.readline, b""):
                self.handle_line(raw)
        except KeyboardInterrupt:
            pass
        finally:
            # No client is left to answer: stop every wait (a mutation ignores this and completes).
            self._cancel_all()
            self._pool.shutdown(wait=True)
            self._drain_long()
            log.info("stdin closed; server exiting")


def build_registry(ctx):
    """The registry with every tool group. Adding a group = one import + one register() call."""
    from . import tools_catalog, tools_instance, tools_lease

    registry = ToolRegistry()
    register_core_tools(registry, ctx)
    tools_catalog.register(registry, ctx)
    tools_lease.register(registry, ctx)
    tools_instance.register(registry, ctx)
    return registry


SERVER_INFO_OUTPUT = {
    "type": "object",
    "required": ["name", "version", "python", "plugin_root", "anchor", "tools"],
    "properties": {
        "name": {"type": "string"},
        "version": {"type": "string"},
        "protocol_version": {"type": ["string", "null"]},
        "python": {"type": "string"},
        "plugin_root": {"type": "string"},
        "anchor": {
            "type": "object",
            "required": ["pid", "fingerprint", "session_id", "source", "exported"],
            "properties": {
                "pid": {"type": "integer"},
                "fingerprint": {"type": "string"},
                "session_id": {"type": "string"},
                "source": {"type": "string"},
                "exported": {"type": "boolean"},
            },
        },
        "tools": {"type": "array", "items": {"type": "string"}},
    },
}


def register_core_tools(registry, ctx):
    def server_info(args, ctx):
        return {
            "name": SERVER_NAME,
            "version": ctx.version,
            "protocol_version": ctx.protocol_version,
            "python": "%d.%d.%d" % sys.version_info[:3],
            "plugin_root": str(ctx.plugin_root),
            "anchor": ctx.anchor.as_dict(),
            "tools": registry.names(),
        }

    registry.add(
        "server_info",
        "Report this odoo-local server's version, Python, plugin root, and the Claude Code session "
        "anchor (parent pid + fingerprint + session id) it stamps on every lease and job it creates. "
        "anchor.exported=false means the fingerprint could not be read, so leases are not "
        "session-anchored - say so to the user. Read-only; call it to diagnose the server itself.",
        {"type": "object", "properties": {}, "additionalProperties": False},
        SERVER_INFO_OUTPUT,
        server_info,
        title="odoo-local server info",
        read_only=True,
    )
