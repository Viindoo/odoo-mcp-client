# A public address for a leased instance

A leased instance listens on localhost. `instance_expose` (odoo-local) gives it a temporary
public HTTPS address through a Cloudflare Quick Tunnel - no account, no domain - and records it
on the lease as `public_url`; `instance_unexpose`, a release or a park closes it.

Open one when the human follows the session from somewhere else and has to look at the instance
(they say so, or the session is driven remotely), or when it is asked for: by the human, or by a
task whose third party must reach the instance (an OAuth redirect, a webhook). Otherwise the
instance stays local. Once open, the human gets that address, not `localhost`.

What to expect: the address is new each time a tunnel opens, so whatever was registered at a
third party is entered again; while it is open the database's `web.base.url` is the public
address; the tunnel carries ordinary requests (no Server-Sent Events, about 200 at once) and
promises no uptime.
