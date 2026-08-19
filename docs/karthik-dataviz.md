# Karthik data-visualization integration

Hermes provides the client runtime for the external
`karthik-data-visualization-skill` repository. The external repository owns the
workflow principles through its portable skills, repair case state machine, and
MCP server.

## Components

- `scripts/sync_karthik_dataviz.py` validates the external checkout and
  installs its Claude-compatible skill trees into the active profile's
  `skills/data-science` directory.
- The MCP server continues to run from the external checkout's isolated
  environment and is registered under `mcp_servers.karthik_dataviz`.
- Hermes supplies skill loading, MCP transport, visual inspection, optional
  delegation, and native `MEDIA:` delivery. It does not impose a separate chart
  release policy.

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

Verify the exact checked-out commits, source validation, focused sync tests,
active gateway, and MCP child process:

```bash
git -C /home/karthik/apps/karthik-data-visualization-skill rev-parse HEAD
git -C /home/karthik/apps/hermes rev-parse HEAD
scripts/run_tests.sh \
  tests/scripts/test_sync_karthik_dataviz.py
systemctl --user is-active hermes-gateway.service
ps -eo pid,args | rg '[d]ataviz_mcp'
```

Start a new conversation after deployment so the process loads the installed
skill text.
