# Einstein Decision Branch Demo

- decision: `ukrainian-tea`
- branch_count: `2`
- created_states: `2`

## Decision Tree

| decision_id | state_node_id | spec_id | status | branches |
| --- | --- | --- | --- | --- |
| state-aa517c6abb66::ukrainian-tea | state-aa517c6abb66 | ukrainian-tea | branched | ukrainian-tea-house-1, ukrainian-tea-house-5 |

| edge_id | decision_id | branch_instance_id | hypothesis_id | status | to_state_id |
| --- | --- | --- | --- | --- | --- |
| state-aa517c6abb66::ukrainian-tea->ukrainian-tea-house-1 | state-aa517c6abb66::ukrainian-tea | ukrainian-tea-house-1 | ukrainian-tea-house-1 | saturated | state-edb7e53fa19f |
| state-aa517c6abb66::ukrainian-tea->ukrainian-tea-house-5 | state-aa517c6abb66::ukrainian-tea | ukrainian-tea-house-5 | ukrainian-tea-house-5 | saturated | state-344a274b658b |

## State state-edb7e53fa19f

| house | nationality | color | drink | pet | smoke |
| --- | --- | --- | --- | --- | --- |
| house-1 | ukrainian | - | tea | - | - |
| house-2 | englishman | red | - | - | - |
| house-3 | - | green | coffee | - | - |
| house-4 | spaniard | - | - | dog | - |
| house-5 | - | - | - | - | - |

## State state-344a274b658b

| house | nationality | color | drink | pet | smoke |
| --- | --- | --- | --- | --- | --- |
| house-1 | - | - | - | - | - |
| house-2 | englishman | red | - | - | - |
| house-3 | - | green | coffee | - | - |
| house-4 | spaniard | - | - | dog | - |
| house-5 | ukrainian | - | tea | - | - |