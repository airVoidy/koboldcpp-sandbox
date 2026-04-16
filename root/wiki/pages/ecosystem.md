# Ecosystem & Dependencies

## Planned Client Stack (TypeScript/React)

- **shadcn/ui** — component library
- **cmdk** — command palette (maps to CMD architecture)
- **rjsf** — schema.json -> auto-generated forms
- **ahooks** — utility hooks (virtual lists, requests, websockets)
- **CopilotKit** patterns — agent-UI shared state, generative UI

## Server/LLM

- **LiteLLM** — unified LLM proxy, scheduling, tool wrappers, dashboard
- **LangChain/LangGraph** — dynamic tools, graph orchestration, pipeline visualization
- **DuckDB** — in-process analytical DB, SQL over JSON/flatten_json rows

## Data/Admin UI

- **Refine** — headless React CRUD framework with custom data providers
- **GraphQL** — typed query layer over FS tree

## Protocols

- **gRPC + protobuf** — typed binary protocol for server-to-server
