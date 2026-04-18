# Pipeline Chat

## Overview

Slack-like chat interface at /pipeline-chat. Channels with messages, reactions, user scopes.

## How It Works

1. Client sends CMD via `/api/pchat/exec` (e.g. `/cpost hello`)
2. Server resolves template command, executes in scope
3. Container state updated, rebuild_containers triggered
4. Client receives materialized view

## Panels

Loaded from template views at runtime:
- `channels/views/sidebar.html` + `sidebar.js` — channel list
- `channel/views/content.html` + `content.js` — messages
- `message/views/compact.html` — message card template

## Key Commands

`/cselect`, `/cpost`, `/cmkchannel`, `/cpatch`, `/cedit`, `/cdelete`, `/creact`

All route through container system with automatic rebuild.
