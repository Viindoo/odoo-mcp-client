# A public address for a leased instance

A leased instance listens on localhost. `instance_expose` (odoo-local) gives it a temporary
public HTTPS address through a Cloudflare Quick Tunnel - no account, no domain - and records it
on the lease as `public_url`.

Open one when the human follows the session from somewhere else and has to look at the instance
(they say so, or the session is driven remotely), or when it is asked for: by the human, or by a
task whose third party must reach the instance (an OAuth redirect, a webhook). Otherwise the
instance stays local. Once open, the human gets that address, not `localhost`.

The address belongs to the lease: it stays the same through a park, an update build and the next
serve, so what was registered at a third party is registered once. A release, a reclaim of the
lease or `instance_unexpose` closes it, and a tunnel opened afterwards has a new address. Close it
with `instance_unexpose` as soon as nobody outside needs it: a parked lease that is still exposed
keeps its tunnel process running.

What to expect: while it is open the database's `web.base.url` is the public address; while the
server is down the address answers with an error; the tunnel carries ordinary requests (no
Server-Sent Events, about 200 at once) and promises no uptime.
