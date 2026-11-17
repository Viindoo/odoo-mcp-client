"""tools_expose.py - give a served lease a temporary public https address (instance_expose /
instance_unexpose).

Two reasons to want one: a third party must call the instance (an OAuth redirect, a payment or social
webhook needs a public https endpoint with a publicly trusted certificate), and a person following a
session from another device must open an instance that listens on localhost only. The address is a
Cloudflare Quick Tunnel run by the `cloudflared` binary - no account, no login, no domain
(scripts/lib/tunnel.py owns the process, the binary and the record of the tunnel).

While a lease is exposed its database holds `web.base.url` = the public address and
`web.base.url.freeze`, so every link, OAuth redirect and webhook URL a module builds carries the public
address and a later login of a system user from another address does not rewrite it. The values are
written through `odoo_db.py set-params` (SQL on ir_config_parameter plus Odoo's own cache-signalling
sequences, so the RUNNING server drops its cached parameters): no user of the database takes part and
no credential is read or changed. Unexposing puts `web.base.url` back to the lease's local URL and
removes the freeze.

The tunnel never outlives the server: a supervisor stops it when the server is gone, whoever stopped
the server (tunnel.py). lease_release and lease_park also unexpose first, so a kept database does not
keep a dead address; a lease whose tunnel died with its server (a gc, an older plugin version) has
its base URL restored by the next instance_serve of that lease (`heal_stale`).

The database manager of an exposed server: every server 50-instance-spinup.sh launches has Odoo's
database manager turned off (the checkout's own `--no-database-list` option), because anyone who
holds the public address could otherwise drop or dump every database of the workstation's cluster
with Odoo's default master password. instance_expose reports `database_manager_open` from the running
server itself, so a server that predates that protection is named, never silently exposed.
"""

import json
import urllib.error
import urllib.request

from . import cli, tools_lease
from .errors import ToolError
from .tools_lease import HANDLE_SCHEMA, LEASE_TOKEN_PROP, _obj

SET_PARAMS_TIMEOUT_S = 90
PROBE_TIMEOUT_S = 10

BASE_URL_KEY = "web.base.url"
FREEZE_KEY = "web.base.url.freeze"


def _tunnels():
    mod = cli.try_load_lib("tunnel")
    if mod is None:
        raise ToolError("TOOL_UNAVAILABLE", "scripts/lib/tunnel.py is missing or does not load")
    return mod


def _tunnel_error(exc):
    return ToolError(exc.code, exc.message, exc.diagnostics)


def _set_params(row, token, cwd, sets, unsets):
    """Write system parameters of the lease's database (odoo_db.py set-params). True when the
    write landed; the failure text otherwise."""
    argv = tools_lease.odoo_db_argv(
        row, "set-params",
        *([a for k, v in sets for a in ("--set", "%s=%s" % (k, v))] + [a for k in unsets for a in ("--unset", k)]))
    if argv is None:
        from .tools_instance import _lease_field
        _lease_field(tools_lease.lease_from_row(row), "venv_python", token)
        return "the lease names no database"
    try:
        rc, out, err = cli.run(argv, cwd, SET_PARAMS_TIMEOUT_S)
    except (cli.SubprocessTimeout, OSError) as exc:
        return "odoo_db.py set-params did not finish: %s" % exc
    if rc != 0:
        return "odoo_db.py set-params exited %s: %s" % (rc, cli.tail((err or out).strip(), 800))
    return True


def _local_base_url(row):
    ports = tools_lease._ports(row.get("ports"))
    return tools_lease.serve_url(ports[0]) if ports else None


def _database_manager_open(port):
    """Whether the server on `port` still answers Odoo's database-listing call: True = the database
    manager is on (anyone with the address could list, drop and dump databases with the master
    password), False = it refuses, None = the question got no usable answer."""
    body = json.dumps({"jsonrpc": "2.0", "method": "call", "id": 1,
                       "params": {"service": "db", "method": "list", "args": []}}).encode("utf-8")
    request = urllib.request.Request("http://127.0.0.1:%d/jsonrpc" % port, data=body,
                                     headers={"Content-Type": "application/json"})
    try:
        answer = json.loads(urllib.request.urlopen(request, timeout=PROBE_TIMEOUT_S).read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError):
        return None
    if not isinstance(answer, dict):
        return None
    if isinstance(answer.get("result"), list):
        return True
    return False if "error" in answer else None


# --------------------------------------------------------------------------- #
# instance_expose
# --------------------------------------------------------------------------- #
def _expose(args, ctx):
    token = args["lease_token"]
    cwd = tools_lease._cwd(args)
    with tools_lease.release_lock(token):
        return _expose_locked(token, cwd)


def _expose_locked(token, cwd):
    tunnels = _tunnels()
    home = tools_lease.state_home()
    row = tools_lease._require_row(token, cwd)
    pid = tools_lease._served_pid(row)
    lease = tools_lease.lease_from_row(row)
    if pid is None or not lease["ports"]:
        raise ToolError("LEASE_NOT_SERVED",
                        "lease %s has no running server to put an address in front of" % token[:8],
                        {"token_prefix": token[:8], "series": lease.get("series") or ""})
    port = lease["ports"][0]
    record = tunnels.live_record(home, token)
    already = bool(record and record.get("server_pid") == pid and record.get("http_port") == port)
    if not already:
        if record:  # a tunnel of an earlier server of this lease
            tunnels.stop(home, token)
        try:
            cloudflared = tunnels.obtain_cloudflared(home)
            record = tunnels.start(home, token, pid, port, lease.get("db_name") or "", cloudflared,
                                   env=cli.child_env())
        except tunnels.TunnelError as exc:
            raise _tunnel_error(exc)
        landed = _set_params(row, token, cwd, [(BASE_URL_KEY, record["public_url"]), (FREEZE_KEY, "True")], [])
        if landed is not True:
            tunnels.stop(home, token)
            raise ToolError("BASE_URL_NOT_SET",
                            "the tunnel opened but the database's web.base.url could not be set; "
                            "the tunnel was stopped", {"token_prefix": token[:8], "detail": landed,
                                                       "public_url": record["public_url"]})
    try:
        tunnels.sweep(home, [r.get("token") for r in tools_lease.list_rows([], cwd)])
    except Exception as exc:  # housekeeping never fails an expose
        cli.log.info("tunnel record sweep skipped: %s", exc)
    reachable = tunnels.wait_reachable(record["public_url"])
    manager_open = _database_manager_open(port)
    warnings = []
    if manager_open:
        warnings.append("this server was started with Odoo's database manager ON: anyone who holds the "
                        "public address can list, drop and dump every database of this machine's "
                        "PostgreSQL cluster with Odoo's default master password. Park the lease and "
                        "instance_serve it again to relaunch the server with the manager off.")
    handle = tools_lease.database_handle(row, lease=dict(lease, public_url=record["public_url"]),
                                         cwd=cwd, server_pid=pid, http_port=port)
    return {
        "public_url": record["public_url"],
        "already_exposed": already,
        "reachable": reachable,
        "http_port": port,
        "database_manager_open": manager_open,
        "warnings": warnings,
        "instance_handle": handle,
    }


# --------------------------------------------------------------------------- #
# instance_unexpose
# --------------------------------------------------------------------------- #
def _restore_base_url(row, token, cwd):
    """Put the lease's database back to its local base URL without the freeze. True, or the failure
    text; None when there is no row to restore (the lease is gone)."""
    if row is None:
        return None
    return _set_params(row, token, cwd, [(BASE_URL_KEY, _local_base_url(row) or "")], [FREEZE_KEY])


def unexpose_lease(token, row, cwd):
    """Stop the lease's tunnel (alive or not) and restore its database's base URL. Returns
    {was_exposed, public_url, base_url, base_url_restored, warnings}. Never raises for a restore
    that fails: the tunnel is stopped regardless."""
    tunnels = _tunnels()
    home = tools_lease.state_home()
    record = tunnels.stop(home, token)
    out = {"was_exposed": bool(record), "public_url": record["public_url"] if record else None,
           "base_url": None, "base_url_restored": False, "warnings": []}
    if not record:
        return out
    restored = _restore_base_url(row, token, cwd)
    if restored is True:
        out.update({"base_url": _local_base_url(row), "base_url_restored": True})
    elif restored is not None:
        out["warnings"].append("the tunnel was stopped but web.base.url could not be put back: %s" % restored)
    return out


def heal_stale(token, row, cwd):
    """A tunnel record whose supervisor is gone (the server stopped by a gc, an older plugin
    version, the owner's session ending) leaves the database frozen on an address that no longer
    answers: put its base URL back and drop the record. True when it restored one."""
    tunnels = _tunnels()
    home = tools_lease.state_home()
    record = tunnels.read_record(home, token)
    if record is None or tunnels.is_alive(record):
        return False
    restored = _restore_base_url(row, token, cwd)
    if restored is True or restored is None:
        tunnels.remove_record(home, token)
    return restored is True


def _unexpose(args, ctx):
    token = args["lease_token"]
    cwd = tools_lease._cwd(args)
    with tools_lease.release_lock(token):
        row = tools_lease.read_row(token, cwd)
        if row is None and _tunnels().read_record(tools_lease.state_home(), token) is None:
            tools_lease._require_row(token, cwd)  # raises LEASE_NOT_FOUND
        return unexpose_lease(token, row, cwd)


# --------------------------------------------------------------------------- #
# registration
# --------------------------------------------------------------------------- #
def register(registry, ctx):
    registry.add(
        "instance_expose",
        "Give your SERVED lease a temporary public https address (a Cloudflare Quick Tunnel: no "
        "account, no domain, a publicly trusted certificate) and return it as public_url. Use it when a "
        "third party must call the instance - an OAuth redirect, a payment or social-network "
        "webhook - or when a person on another device must open an instance that listens on "
        "localhost only. The lease's server must be running (instance_serve first; otherwise "
        "LEASE_NOT_SERVED). While exposed, the database's web.base.url is the public address and is "
        "frozen, so every link, redirect URI and webhook URL a module builds carries it, and the "
        "running server already uses it; no Odoo user or password is involved. Calling it again while "
        "exposed returns the same address (already_exposed true) without a second tunnel. The "
        "address changes every time a tunnel is created, so register it with the third party after "
        "this call, and keep the tunnel open for the whole scenario. reachable false = the name did "
        "not answer yet (a new tunnel can take a moment): retry the URL before relying on it. "
        "warnings non-empty = read it. The address is shown wherever the lease is read "
        "(instance_handle.public_url, lease.public_url of instance_status and lease_list). Quick "
        "Tunnel limits: no uptime guarantee, 200 requests in flight at most, no Server-Sent Events. "
        "The tunnel ends with the server: lease_release, lease_park and a gc all stop it; "
        "instance_unexpose stops it alone. The first call on a machine without cloudflared fetches "
        "the official release (a few seconds); CLOUDFLARED_UNAVAILABLE means it cannot be had. "
        "TUNNEL_FAILED = cloudflared did not come up (read diagnostics.log_tail; Quick Tunnels are "
        "rate limited, wait a minute).",
        _obj({"lease_token": LEASE_TOKEN_PROP,
              "cwd": {"type": "string", "minLength": 1,
                      "description": "Absolute path of your working tree; omit for the session's directory."}},
             ["lease_token"]),
        _obj({
            "public_url": {"type": "string", "description": "https://<words>.trycloudflare.com"},
            "already_exposed": {"type": "boolean",
                                "description": "true = a tunnel was already open for this server; nothing "
                                               "new was started."},
            "reachable": {"type": "boolean",
                          "description": "The public address answered an HTTP request from this machine "
                                         "(anything below 500) within the wait."},
            "http_port": {"type": "integer"},
            "database_manager_open": {"type": ["boolean", "null"],
                                      "description": "true = the running server still answers Odoo's "
                                                     "database-listing call (it was launched before the "
                                                     "protection existed; see warnings); false = refused; "
                                                     "null = no usable answer."},
            "warnings": {"type": "array", "items": {"type": "string"}},
            "instance_handle": HANDLE_SCHEMA,
        }, ["public_url", "already_exposed", "reachable", "http_port", "database_manager_open",
            "warnings", "instance_handle"]),
        _expose, title="Expose an Odoo instance at a public https address", long_running=True,
        destructive=False, idempotent=True,
    )
    registry.add(
        "instance_unexpose",
        "Close the public address instance_expose opened for your lease: stops the tunnel and puts "
        "the database's web.base.url back to the lease's local URL (http://localhost:<port>) and "
        "removes the freeze. Nothing to do (was_exposed false) when the lease is not exposed - "
        "calling it again is safe. You do not need it before lease_release or lease_park: both "
        "close the tunnel themselves; call it to end the exposure while the server keeps running. "
        "base_url_restored false with a warning = the tunnel is stopped but the database could not be "
        "reached to put the base URL back.",
        _obj({"lease_token": LEASE_TOKEN_PROP,
              "cwd": {"type": "string", "minLength": 1,
                      "description": "Absolute path of your working tree; omit for the session's directory."}},
             ["lease_token"]),
        _obj({
            "was_exposed": {"type": "boolean"},
            "public_url": {"type": ["string", "null"], "description": "The address that was closed."},
            "base_url": {"type": ["string", "null"], "description": "The base URL the database has "
                                                                    "now (the local URL); null when not "
                                                                    "restored."},
            "base_url_restored": {"type": "boolean"},
            "warnings": {"type": "array", "items": {"type": "string"}},
        }, ["was_exposed", "public_url", "base_url", "base_url_restored", "warnings"]),
        _unexpose, title="Close the public address of an Odoo instance", long_running=True,
        destructive=False, idempotent=True,
    )
