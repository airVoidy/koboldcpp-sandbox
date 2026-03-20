# Einstein Search-Until-Blocked Run

- status: `blocked`
- executed_specs: `1`
- deepest_depth: `1`

## Tick Events

| spec_id | created_nodes |
| --- | --- |
| norwegian-next-to-blue | state-8369d7ec995b |

## Deepest State

| house | nationality | color | drink | pet | smoke |
| --- | --- | --- | --- | --- | --- |
| house-1 | norwegian | - | - | - | - |
| house-2 | - | blue | - | - | - |
| house-3 | - | - | milk | - | - |
| house-4 | - | - | - | - | - |
| house-5 | - | - | - | - | - |

## State Graph

| node_id | depth | status | derived_from |
| --- | --- | --- | --- |
| state-753037bcbc16 | 0 | open | - |
| state-8369d7ec995b | 1 | open | state-753037bcbc16->norwegian-next-to-blue |

| edge_id | hypothesis_id | status | to_node_id |
| --- | --- | --- | --- |
| state-753037bcbc16->norwegian-next-to-blue | norwegian-next-to-blue | saturated | state-8369d7ec995b |