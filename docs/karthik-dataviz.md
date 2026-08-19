# Karthik data-visualization integration

Hermes owns its client-specific adapter for the external
`karthik-data-visualization-skill` repository. The external repository remains
limited to portable skills, the repair case state machine, and the MCP server.

## Components

- `plugins/dataviz-release-guard/` detects chart-repair turns, injects the
  active-profile skill and case paths, requires a fresh `delegate_task`
  reviewer, and only permits a `MEDIA:` attachment whose hash has an
  independent `Send` verdict.
- `scripts/sync_karthik_dataviz.py` validates the external checkout and
  installs its Claude-compatible skill trees into the active profile's
  `skills/data-science` directory.
- The MCP server continues to run from the external checkout's isolated
  environment and is registered under `mcp_servers.karthik_dataviz`.

## Karthik's host deployment

Run directly on the host; do not SSH back into it through an alias.

```bash
cd /home/karthik/apps/karthik-data-visualization-skill
git pull --ff-only
./sync.sh --no-pull --validate-only
.venv/bin/python -m pip install -e ".[test]"

cd /home/karthik/apps/hermes
python scripts/sync_karthik_dataviz.py \
  --source /home/karthik/apps/karthik-data-visualization-skill
hermes plugins enable dataviz-release-guard
systemctl --user restart hermes-gateway.service
```

The configured MCP command is:

```yaml
mcp_servers:
  karthik_dataviz:
    command: /home/karthik/apps/karthik-data-visualization-skill/.venv/bin/python
    args: [-m, dataviz_mcp]
    timeout: 180
    connect_timeout: 30
```

Verify the exact checked-out commits, the source validation, focused adapter
tests, active gateway, and MCP child process:

```bash
git -C /home/karthik/apps/karthik-data-visualization-skill rev-parse HEAD
git -C /home/karthik/apps/hermes rev-parse HEAD
scripts/run_tests.sh \
  tests/plugins/test_dataviz_release_guard_plugin.py \
  tests/scripts/test_sync_karthik_dataviz.py
systemctl --user is-active hermes-gateway.service
ps -eo pid,args | rg '[d]ataviz_mcp'
```

Start a new conversation after deployment so the process reloads the plugin and
the installed skill text.
