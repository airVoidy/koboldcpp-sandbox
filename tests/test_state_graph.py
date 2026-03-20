from kobold_sandbox.core import (
    ArgumentEnvelope,
    ArgumentRef,
    CellBinding,
    DecisionTree,
    DomainRuleLambda,
    EntityRef,
    EntityValue,
    HypothesisResult,
    PossibleArgumentMatrix,
    RuleBinding,
    RuleRegistry,
    RuleStage,
    SlotRef,
    StateGraph,
    StateSnapshot,
    WorkerCell,
    WorkerRef,
    apply_result_to_snapshot,
    attach_argument_to_worker,
    attach_operation_to_worker,
    connect_worker_neighbors,
    compute_candidate_domains,
    expand_state_node,
)
from kobold_sandbox.einstein_example import (
    ALL_RELATION_ORDER,
    EINSTEIN_NODE_SPECS,
    HOUSES,
    apply_first_atomic_rule_lambda,
    apply_atomic_rule_lambda,
    attach_first_relation_rule_to_house_slots,
    bind_first_atomic_rules_to_slots,
    bind_atomic_rule_pipeline_to_slots,
    bind_atomic_rules_to_slots,
    build_atomic_rule_pipeline,
    build_atomic_rule_lambdas,
    build_atomic_rule_slot_grid,
    build_entity_link_z_layers,
    build_positional_filter_z_layers,
    build_first_atomic_rule_lambdas,
    build_first_atomic_rule_slot_grid,
    build_einstein_argument_envelopes,
    build_einstein_entities,
    build_einstein_house_slots,
    build_einstein_worker_cells,
    build_direct_givens_context,
    build_demo_relation_frontier,
    build_first_text_frontier,
    build_ordered_frontier_from_context,
    collect_relation_links,
    choose_relation_search_frontier,
    collect_linked_relation_ids,
    expand_relation_decision_branch,
    expand_and_auto_reconcile_relation_decision_branch,
    auto_reconcile_relation_decision_branch,
    reconcile_relation_decision_branch,
    search_linked_relation_graph_until_blocked,
    search_relation_graph_n,
    search_relation_graph_step,
    search_relation_graph_until_blocked,
    build_relation_candidate_checklist,
    build_relation_state_graph,
    build_relation_state_sequence_graph,
    FIRST_TEXT_RELATION_ORDER,
    EINSTEIN_SOLVER_ORDER,
    LoopPolicy,
    render_loop_events_table,
    render_solver_run_markdown,
    run_linked_relation_loop_trace,
    run_linked_relation_loop,
    run_einstein_solver_until_blocked,
    run_relation_graph_until_blocked,
    run_relation_graph_two_phase_until_blocked,
    summarize_state_graph,
    throw_argument_across_atomic_z,
    throw_argument_across_entity_links_z,
    throw_argument_across_positional_z,
    tick_relation_graph_n,
    tick_linked_relation_graph_n,
    tick_relation_graph_once,
    tick_relation_graph_until_blocked,
)
from kobold_sandbox.core.node_specs import HypothesisLink, SameHousePair, TickPlanner, node_instance_to_entry


def test_expand_state_node_creates_child_snapshot_for_passed_same_house_relation() -> None:
    snapshot = StateSnapshot.from_values(
        {
            "nationality_by_house": {"house-2": "englishman"},
            "color_by_house": {"house-2": "red"},
        }
    )
    graph = StateGraph.from_snapshot(snapshot)
    entries = [entry for entry in build_relation_candidate_checklist(relation_id="englishman-red") if entry.metadata["house"] == "house-2"]

    created = expand_state_node(graph, graph.root_node_id, entries, max_depth=1)

    assert len(created) == 1
    child = graph.nodes[created[0]]
    assert child.depth == 1
    assert child.snapshot.values["nationality_by_house"]["house-2"] == "englishman"
    assert child.snapshot.values["color_by_house"]["house-2"] == "red"
    assert child.snapshot.values["__eliminations__"]["nationality_by_house"]["house-1"] == ["englishman"]
    assert child.snapshot.values["__eliminations__"]["color_by_house"]["house-5"] == ["red"]
    assert f"{graph.root_node_id}->englishman-red-house-2" in graph.edges


def test_worker_cells_cover_each_house_and_category_domain() -> None:
    workers = build_einstein_worker_cells()

    assert workers[WorkerRef("color_by_house", "house-1")].domain == {"red", "green", "white", "yellow", "blue"}
    assert workers[WorkerRef("nationality_by_house", "house-5")].domain == {
        "englishman",
        "spaniard",
        "ukrainian",
        "norwegian",
        "japanese",
    }
    assert len([ref for ref in workers if ref.worker_type == "drink_by_house"]) == len(HOUSES)
    assert workers[WorkerRef("color_by_house", "house-3")].neighbor_refs["left"] == WorkerRef("color_by_house", "house-2")
    assert workers[WorkerRef("color_by_house", "house-3")].neighbor_refs["right"] == WorkerRef("color_by_house", "house-4")


def test_einstein_entities_keep_house_and_values_on_same_level() -> None:
    entities = build_einstein_entities()

    assert entities[EntityRef("house", "house-1")] == EntityValue(
        ref=EntityRef("house", "house-1"),
        labels=("house-1",),
    )
    assert entities[EntityRef("color", "red")].ref == EntityRef("color", "red")
    assert entities[EntityRef("nationality", "englishman")].ref == EntityRef("nationality", "englishman")


def test_house_slots_are_containers_not_domain_entities() -> None:
    slots = attach_first_relation_rule_to_house_slots(build_einstein_house_slots())

    house_1 = slots[SlotRef("house_slot", "house-1")]
    assert EntityRef("nationality", "englishman") in house_1.candidate_entities
    assert EntityRef("color", "red") in house_1.candidate_entities
    assert EntityRef("house", "house-1") not in house_1.candidate_entities
    assert house_1.rule_ids == ["englishman-red"]


def test_first_atomic_rule_lambdas_are_built_from_same_house_rules() -> None:
    rules = build_first_atomic_rule_lambdas()

    englishman_red = next(rule for rule in rules if rule.rule_id == "englishman-red")
    assert englishman_red.rule_id == "englishman-red"
    assert englishman_red.container_type == "house_slot"
    assert englishman_red.left_type_ref == "nationality"
    assert englishman_red.right_type_ref == "color"
    assert englishman_red.left_entity == EntityRef("nationality", "englishman")
    assert englishman_red.right_entity == EntityRef("color", "red")
    assert englishman_red.metadata["relation_kind"] == "same_house_pair"


def test_atomic_rule_lambda_returns_possible_argument_matrix_for_trigger() -> None:
    matrix = apply_first_atomic_rule_lambda(
        "englishman-red",
        EntityRef("nationality", "englishman"),
        slots=build_first_atomic_rule_slot_grid(),
    )

    assert matrix == PossibleArgumentMatrix(
        rule_id="englishman-red",
        trigger=EntityRef("nationality", "englishman"),
        rows=tuple(matrix.rows),
    )
    assert len(matrix.rows) == len(HOUSES)
    assert all(row.possible_entities == (EntityRef("color", "red"),) for row in matrix.rows)


def test_atomic_rules_are_managed_independently_and_bound_through_slots() -> None:
    registry, bindings, slots = bind_first_atomic_rules_to_slots()

    assert isinstance(registry, RuleRegistry)
    assert registry.get("englishman-red").rule_id == "englishman-red"
    assert CellBinding(
        binding_id="englishman-red::house-1",
        rule_id="englishman-red",
        slot_ref=SlotRef("house_slot", "house-1"),
    ) in bindings
    assert "englishman-red" in slots[SlotRef("house_slot", "house-1")].rule_ids
    assert len(bindings) == len(HOUSES) * len(build_first_atomic_rule_lambdas())


def test_atomic_rule_pipeline_splits_entity_links_and_positional_filters() -> None:
    stages = build_atomic_rule_pipeline()

    assert stages == (
        RuleStage(
            stage_id="entity-link",
            stage_kind="entity_link",
            rule_ids=(
                "englishman-red",
                "spaniard-dog",
                "green-coffee",
                "ukrainian-tea",
                "old-gold-snails",
                "yellow-kool",
                "lucky-strike-orange-juice",
                "japanese-parliament",
            ),
        ),
        RuleStage(
            stage_id="positional-filter",
            stage_kind="positional_filter",
            rule_ids=(
                "norwegian-next-to-blue",
                "chesterfield-next-to-fox",
                "kool-next-to-horse",
                "green-right-of-white",
            ),
        ),
    )


def test_atomic_rule_field_binds_all_rules_to_single_slot_grid() -> None:
    registry, bindings, slots = bind_atomic_rules_to_slots()

    assert registry.get("green-right-of-white").relation_kind == "offset_pair"
    assert registry.get("norwegian-next-to-blue").relation_kind == "adjacent_pair"
    assert len(bindings) == len(HOUSES) * len(build_atomic_rule_lambdas())
    assert "green-right-of-white" in slots[SlotRef("house_slot", "house-3")].rule_ids


def test_atomic_rule_pipeline_binds_by_stage_on_single_field() -> None:
    registry, stage_bindings, slots = bind_atomic_rule_pipeline_to_slots()

    assert isinstance(registry, RuleRegistry)
    assert set(stage_bindings) == {"entity-link", "positional-filter"}
    assert len(stage_bindings["entity-link"]) == len(HOUSES) * 8
    assert len(stage_bindings["positional-filter"]) == len(HOUSES) * 4
    assert "norwegian-next-to-blue" in slots[SlotRef("house_slot", "house-2")].rule_ids


def test_positional_filters_are_split_into_four_z_layers() -> None:
    layers = build_positional_filter_z_layers()

    assert [layer.stage_id for layer in layers] == [
        "z-filter-1",
        "z-filter-2",
        "z-filter-3",
        "z-filter-4",
    ]
    assert [layer.rule_ids[0] for layer in layers] == [
        "norwegian-next-to-blue",
        "chesterfield-next-to-fox",
        "kool-next-to-horse",
        "green-right-of-white",
    ]


def test_entity_links_are_split_into_eight_z_layers() -> None:
    layers = build_entity_link_z_layers()

    assert [layer.stage_id for layer in layers] == [
        "z-link-1",
        "z-link-2",
        "z-link-3",
        "z-link-4",
        "z-link-5",
        "z-link-6",
        "z-link-7",
        "z-link-8",
    ]
    assert [layer.rule_ids[0] for layer in layers] == [
        "englishman-red",
        "spaniard-dog",
        "green-coffee",
        "ukrainian-tea",
        "old-gold-snails",
        "yellow-kool",
        "lucky-strike-orange-juice",
        "japanese-parliament",
    ]


def test_throw_argument_across_entity_links_z_fills_only_matching_link_layer() -> None:
    layers, slots = throw_argument_across_entity_links_z(EntityRef("nationality", "englishman"))

    assert [layer.rule_id for layer in layers] == [
        "englishman-red",
        "spaniard-dog",
        "green-coffee",
        "ukrainian-tea",
        "old-gold-snails",
        "yellow-kool",
        "lucky-strike-orange-juice",
        "japanese-parliament",
    ]
    assert len(layers[0].matrix.rows) == len(HOUSES)
    assert all(not layer.matrix.rows for layer in layers[1:])
    house_2 = next(row for row in layers[0].matrix.rows if row.slot_ref == SlotRef("house_slot", "house-2"))
    assert house_2.possible_entities == (EntityRef("color", "red"),)
    assert not slots[SlotRef("house_slot", "house-1")].z_exclusions


def test_throw_argument_across_positional_z_fills_only_matching_filter_layers() -> None:
    layers, slots = throw_argument_across_positional_z(EntityRef("color", "white"))

    assert [layer.rule_id for layer in layers] == [
        "norwegian-next-to-blue",
        "chesterfield-next-to-fox",
        "kool-next-to-horse",
        "green-right-of-white",
    ]
    assert all(layer.trigger == EntityRef("color", "white") for layer in layers)
    assert all(not layer.matrix.rows for layer in layers[:-1])
    final_layer = layers[-1]
    house_1 = next(row for row in final_layer.matrix.rows if row.slot_ref == SlotRef("house_slot", "house-1"))
    house_5 = next(row for row in final_layer.matrix.rows if row.slot_ref == SlotRef("house_slot", "house-5"))
    assert house_1.possible_entities == (EntityRef("color", "green"),)
    assert EntityRef("color", "green") in house_5.excluded_entities
    assert EntityRef("color", "green") in slots[SlotRef("house_slot", "house-5")].z_exclusions[
        "green-right-of-white:color:white"
    ]


def test_throw_argument_across_positional_z_can_fill_middle_filter() -> None:
    layers, slots = throw_argument_across_positional_z(EntityRef("smoke", "kool"))

    matching = next(layer for layer in layers if layer.rule_id == "kool-next-to-horse")
    house_1 = next(row for row in matching.matrix.rows if row.slot_ref == SlotRef("house_slot", "house-1"))
    house_3 = next(row for row in matching.matrix.rows if row.slot_ref == SlotRef("house_slot", "house-3"))
    assert house_1.possible_entities == (EntityRef("pet", "horse"),)
    assert house_3.possible_entities == (EntityRef("pet", "horse"),)
    assert EntityRef("pet", "horse") in slots[SlotRef("house_slot", "house-5")].z_exclusions[
        "kool-next-to-horse:smoke:kool"
    ]


def test_throw_argument_across_atomic_z_runs_link_and_filter_conveyors_together() -> None:
    entity_layers, positional_layers, slots = throw_argument_across_atomic_z(EntityRef("color", "white"))

    assert len(entity_layers) == 8
    assert len(positional_layers) == 4
    assert all(not layer.matrix.rows for layer in entity_layers)
    assert len(positional_layers[-1].matrix.rows) == len(HOUSES)
    assert EntityRef("color", "green") in slots[SlotRef("house_slot", "house-5")].z_exclusions[
        "green-right-of-white:color:white"
    ]


def test_positional_atomic_rule_lambda_returns_possible_and_excluded_entities() -> None:
    slots = build_atomic_rule_slot_grid()

    matrix = apply_atomic_rule_lambda(
        "green-right-of-white",
        EntityRef("color", "white"),
        slots=slots,
    )

    house_1 = next(row for row in matrix.rows if row.slot_ref == SlotRef("house_slot", "house-1"))
    house_5 = next(row for row in matrix.rows if row.slot_ref == SlotRef("house_slot", "house-5"))
    assert house_1.possible_entities == (EntityRef("color", "green"),)
    assert house_5.possible_entities == ()
    assert EntityRef("color", "green") in house_5.excluded_entities
    assert EntityRef("color", "green") in slots[SlotRef("house_slot", "house-5")].z_exclusions[
        "green-right-of-white:color:white"
    ]


def test_argument_envelopes_bind_same_house_relation_to_house_workers() -> None:
    envelopes, bindings = build_einstein_argument_envelopes(relation_ids=("englishman-red",))

    arg_ref = ArgumentRef("same_house_pair", "englishman-red")
    assert envelopes[arg_ref] == ArgumentEnvelope(
        ref=arg_ref,
        subtype="same_house_pair",
        values={"englishman", "red"},
        metadata={
            "rule_id": "englishman-red",
            "left_ns": "nationality_by_house",
            "right_ns": "color_by_house",
        },
    )
    bound_workers = {binding.worker_ref for binding in bindings}
    assert WorkerRef("nationality_by_house", "house-1") in bound_workers
    assert WorkerRef("color_by_house", "house-5") in bound_workers
    assert len(bindings) == len(HOUSES) * 2


def test_attach_argument_to_worker_returns_binding_wrapper() -> None:
    worker = build_einstein_worker_cells()[WorkerRef("color_by_house", "house-2")]
    argument = ArgumentEnvelope(
        ref=ArgumentRef("adjacent_pair", "norwegian-next-to-blue"),
        subtype="adjacent_pair",
        values={"norwegian", "blue"},
        metadata={"rule_id": "norwegian-next-to-blue"},
    )

    binding = attach_argument_to_worker(worker, argument, rule_id="norwegian-next-to-blue")

    assert binding == RuleBinding(
        binding_id="norwegian-next-to-blue::house-2::norwegian-next-to-blue",
        rule_id="norwegian-next-to-blue",
        worker_ref=WorkerRef("color_by_house", "house-2"),
        argument_ref=ArgumentRef("adjacent_pair", "norwegian-next-to-blue"),
    )
    assert worker.attached_rule_ids == ["norwegian-next-to-blue"]
    assert worker.operations == ["norwegian-next-to-blue"]
    assert worker.facts["argument_refs"] == [ArgumentRef("adjacent_pair", "norwegian-next-to-blue")]


def test_connect_worker_neighbors_builds_linear_left_right_links() -> None:
    refs = tuple(WorkerRef("line", f"slot-{index}") for index in range(3))
    workers = {ref: WorkerCell(ref=ref, domain={"x"}) for ref in refs}

    connect_worker_neighbors(workers, refs)

    assert workers[refs[0]].neighbor_refs["right"] == refs[1]
    assert "left" not in workers[refs[0]].neighbor_refs
    assert workers[refs[1]].neighbor_refs["left"] == refs[0]
    assert workers[refs[1]].neighbor_refs["right"] == refs[2]
    assert refs[1] in workers[refs[0]].links


def test_attach_operation_to_worker_keeps_unique_operation_ids() -> None:
    worker = build_einstein_worker_cells()[WorkerRef("pet_by_house", "house-3")]

    attach_operation_to_worker(worker, "right_of")
    attach_operation_to_worker(worker, "right_of")

    assert worker.operations == ["right_of"]


def test_relation_specs_can_link_directly_to_next_hypotheses() -> None:
    englishman_red = next(item for item in EINSTEIN_NODE_SPECS if item.node_id == "englishman-red")

    assert englishman_red.links == (
        HypothesisLink(
            kind="activates",
            target_spec_id="spaniard-dog",
            metadata={"activation": "group"},
        ),
        HypothesisLink(
            kind="activates",
            target_spec_id="green-coffee",
            metadata={"activation": "group"},
        ),
    )
    assert collect_linked_relation_ids("englishman-red", max_hops=3) == (
        "englishman-red",
        "spaniard-dog",
        "green-coffee",
        "ukrainian-tea",
        "green-right-of-white",
        "old-gold-snails",
    )


def test_relation_specs_can_declare_branch_and_exclusion_groups() -> None:
    ukrainian_links = collect_relation_links("ukrainian-tea")

    assert HypothesisLink(
        kind="branches_to",
        target_spec_id="ukrainian-tea-candidates",
        metadata={"branch_group": "ukrainian-tea-candidates"},
    ) in ukrainian_links
    assert HypothesisLink(
        kind="excludes",
        target_spec_id="ukrainian-tea-candidates",
        metadata={"exclusion_group": "ukrainian-tea-candidates"},
    ) in ukrainian_links


def test_build_relation_state_graph_limits_to_depth_one() -> None:
    graph = build_relation_state_graph(
        "englishman-red",
        {
            "nationality_by_house": {"house-2": "englishman"},
            "color_by_house": {"house-2": "red"},
        },
        house="house-2",
        max_depth=1,
    )

    assert len(graph.nodes) == 2
    assert len(graph.edges) == 1
    child = next(node for node in graph.nodes.values() if node.depth == 1)
    assert child.snapshot.values["color_by_house"]["house-2"] == "red"


def test_build_relation_state_graph_applies_positional_assignments() -> None:
    graph = build_relation_state_graph(
        "green-right-of-white",
        {
            "color_house": {"white": 2, "green": 3},
        },
        max_depth=1,
    )

    root = graph.nodes[graph.root_node_id]
    assert len(graph.nodes) == 1
    assert root.snapshot.values["color_house"]["white"] == 2
    assert root.snapshot.values["color_house"]["green"] == 3


def test_build_relation_state_sequence_graph_expands_tree_step_by_step() -> None:
    entries = [
        next(item for item in build_relation_candidate_checklist(relation_id="englishman-red") if item.metadata["house"] == "house-1"),
        next(item for item in build_relation_candidate_checklist(relation_id="spaniard-dog") if item.metadata["house"] == "house-2"),
    ]

    graph = build_relation_state_sequence_graph(
        entries,
        {
            "nationality_by_house": {"house-1": "englishman", "house-2": "spaniard"},
            "color_by_house": {"house-1": "red"},
            "pet_by_house": {"house-2": "dog"},
        },
        max_depth=2,
    )

    depths = sorted(node.depth for node in graph.nodes.values())
    assert depths == [0, 1, 2]
    deepest = next(node for node in graph.nodes.values() if node.depth == 2)
    assert deepest.snapshot.values["nationality_by_house"]["house-2"] == "spaniard"
    assert deepest.snapshot.values["pet_by_house"]["house-2"] == "dog"


def test_demo_relation_frontier_builds_depth_four_when_consistent() -> None:
    entries, context = build_demo_relation_frontier()

    graph = build_relation_state_sequence_graph(entries, context, max_depth=4)

    assert sorted(node.depth for node in graph.nodes.values()) == [0, 1, 2, 3]
    deepest = max(graph.nodes.values(), key=lambda node: (node.depth, node.node_id))
    assert deepest.depth == 3
    assert deepest.snapshot.values["drink_by_house"]["house-5"] == "coffee"
    assert deepest.snapshot.values["color_by_house"]["house-4"] == "white"
    summary = summarize_state_graph(graph)
    assert "| edge_id | hypothesis_id | status | to_node_id |" in summary
    assert "| state-" in summary


def test_demo_relation_frontier_stops_growth_on_contradiction() -> None:
    entries, context = build_demo_relation_frontier(contradictory=True)

    graph = build_relation_state_sequence_graph(entries, context, max_depth=4)

    assert sorted(node.depth for node in graph.nodes.values()) == [0, 1, 2, 3]
    contradictory_edge = next(edge for edge in graph.edges.values() if edge.hypothesis_id == "green-right-of-white")
    assert contradictory_edge.status == "contradicted"


def test_first_text_frontier_builds_deeper_state_tree() -> None:
    entries, context = build_first_text_frontier()

    graph = build_relation_state_sequence_graph(entries, context, max_depth=7)

    assert sorted(node.depth for node in graph.nodes.values()) == [0, 1, 2, 3]
    deepest = max(graph.nodes.values(), key=lambda node: (node.depth, node.node_id))
    assert deepest.depth == 3
    assert deepest.snapshot.values["smoke_by_house"]["house-2"] == "kool"
    assert deepest.snapshot.values["drink_by_house"]["house-3"] == "tea"


def test_ordered_frontier_is_resolved_from_context() -> None:
    context = {
        "nationality_by_house": {"house-1": "englishman", "house-2": "spaniard", "house-3": "ukrainian"},
        "color_by_house": {"house-1": "red", "house-2": "yellow", "house-4": "white", "house-5": "green"},
        "pet_by_house": {"house-2": "dog", "house-1": "snails"},
        "drink_by_house": {"house-5": "coffee", "house-3": "tea"},
        "smoke_by_house": {"house-1": "old-gold", "house-2": "kool"},
        "color_house": {"red": 1, "yellow": 2, "white": 4, "green": 5},
    }

    entries = build_ordered_frontier_from_context(FIRST_TEXT_RELATION_ORDER, context)

    assert [entry.hypothesis_id for entry in entries] == [
        "englishman-red-house-1",
        "spaniard-dog-house-2",
        "green-coffee-house-5",
        "ukrainian-tea-house-3",
        "green-right-of-white",
        "old-gold-snails-house-1",
        "yellow-kool-house-2",
    ]


def test_tick_planner_materializes_same_house_spec_from_snapshot() -> None:
    planner = TickPlanner()
    spec = next(item for item in EINSTEIN_NODE_SPECS if item.node_id == "englishman-red")
    assert isinstance(spec.payload, SameHousePair)
    snapshot = StateSnapshot.from_values(
        {
            "nationality_by_house": {"house-2": "englishman"},
            "color_by_house": {"house-2": "red"},
        }
    )

    instances = planner.materialize(spec, snapshot)

    assert len(instances) == 1
    assert instances[0].bindings == {"house": "house-2", "materialization_kind": "anchored"}
    entry = node_instance_to_entry(spec, instances[0])
    assert entry.hypothesis_id == "englishman-red-house-2"


def test_compute_candidate_domains_uses_eliminations_and_inverse_assignments() -> None:
    domains = compute_candidate_domains(
        {
            "color_by_house": {
                "house-1": "red",
                "house-2": "yellow",
                "house-4": "white",
            },
            "color_house": {
                "red": 1,
                "yellow": 2,
                "white": 4,
            },
            "__eliminations__": {
                "color_by_house": {
                    "house-1": ["green"],
                    "house-2": ["green"],
                    "house-3": ["red", "yellow", "white"],
                    "house-4": ["green"],
                    "house-5": ["red", "yellow", "white"],
                }
            },
        },
        "color_by_house",
    )

    assert domains["by_house"]["house-3"] == ("green",)
    assert domains["by_house"]["house-5"] == ("green",)
    assert domains["by_value"]["green"] == ("house-3", "house-5")


def test_tick_planner_materializes_same_house_spec_from_candidate_domains() -> None:
    planner = TickPlanner()
    spec = next(item for item in EINSTEIN_NODE_SPECS if item.node_id == "green-coffee")
    snapshot = StateSnapshot.from_values(
        {
            "color_by_house": {
                "house-1": "red",
                "house-2": "yellow",
                "house-4": "white",
            },
            "color_house": {
                "red": 1,
                "yellow": 2,
                "white": 4,
            },
            "drink_by_house": {
                "house-3": "tea",
            },
            "drink_house": {
                "tea": 3,
            },
            "__eliminations__": {
                "color_by_house": {
                    "house-1": ["green"],
                    "house-2": ["green"],
                    "house-3": ["red", "yellow", "white"],
                    "house-4": ["green"],
                },
                "drink_by_house": {
                    "house-1": ["coffee"],
                    "house-2": ["coffee"],
                    "house-3": ["coffee"],
                    "house-4": ["coffee"],
                },
            },
        }
    )

    instances = planner.materialize(spec, snapshot)

    assert len(instances) == 1
    assert instances[0].bindings == {"house": "house-5", "materialization_kind": "anchored"}


def test_tick_planner_generates_same_house_domain_branches() -> None:
    planner = TickPlanner(max_branch_candidates=2)
    spec = next(item for item in EINSTEIN_NODE_SPECS if item.node_id == "green-coffee")
    snapshot = StateSnapshot.from_values(
        {
            "color_by_house": {
                "house-1": "red",
                "house-2": "yellow",
            },
            "color_house": {
                "red": 1,
                "yellow": 2,
            },
            "drink_by_house": {
                "house-1": "tea",
            },
            "drink_house": {
                "tea": 1,
            },
            "__eliminations__": {
                "color_by_house": {
                    "house-1": ["green"],
                    "house-2": ["green"],
                    "house-4": ["green"],
                },
                "drink_by_house": {
                    "house-1": ["coffee"],
                    "house-2": ["coffee"],
                    "house-4": ["coffee"],
                },
            },
        }
    )

    instances = planner.materialize(spec, snapshot)

    assert [item.bindings for item in instances] == [
        {"house": "house-3", "materialization_kind": "domain_branch"},
        {"house": "house-5", "materialization_kind": "domain_branch"},
    ]



def test_tick_planner_generates_adjacent_domain_branches() -> None:
    planner = TickPlanner(max_branch_candidates=2)
    spec = next(item for item in EINSTEIN_NODE_SPECS if item.node_id == "norwegian-next-to-blue")
    snapshot = StateSnapshot.from_values(
        {
            "nationality_house": {"norwegian": 3},
        }
    )

    instances = planner.materialize(spec, snapshot)

    assert [item.bindings for item in instances] == [
        {
            "materialization_kind": "domain_branch",
            "anchor_side": "left",
            "candidate_position": 2,
            "branch_id": "blue-2",
        },
        {
            "materialization_kind": "domain_branch",
            "anchor_side": "left",
            "candidate_position": 4,
            "branch_id": "blue-4",
        },
    ]


def test_tick_planner_generates_offset_domain_branches() -> None:
    planner = TickPlanner(max_branch_candidates=3)
    spec = next(item for item in EINSTEIN_NODE_SPECS if item.node_id == "green-right-of-white")
    snapshot = StateSnapshot.from_values(
        {
            "nationality_house": {"norwegian": 1},
            "color_house": {"blue": 2},
        }
    )

    instances = planner.materialize(spec, snapshot)

    assert [item.bindings for item in instances] == [
        {
            "materialization_kind": "domain_branch",
            "left_position": 4,
            "right_position": 3,
            "branch_id": "white-3_green-4",
        },
        {
            "materialization_kind": "domain_branch",
            "left_position": 5,
            "right_position": 4,
            "branch_id": "white-4_green-5",
        },
    ]


def test_tick_planner_generates_adjacent_domain_pair_branches() -> None:
    planner = TickPlanner(max_branch_candidates=3)
    spec = next(item for item in EINSTEIN_NODE_SPECS if item.node_id == "kool-next-to-horse")
    snapshot = StateSnapshot.from_values(
        {
            "smoke_house": {"kool": 5},
        }
    )

    instances = planner.materialize(spec, snapshot)

    assert [item.bindings for item in instances] == [
        {
            "materialization_kind": "anchored",
            "anchor_side": "left",
            "candidate_position": 4,
        },
    ]


def test_expand_state_node_creates_adjacent_branch_children() -> None:
    planner = TickPlanner(max_branch_candidates=2)
    spec = next(item for item in EINSTEIN_NODE_SPECS if item.node_id == "norwegian-next-to-blue")
    snapshot = StateSnapshot.from_values(
        {
            "nationality_house": {"norwegian": 3},
        }
    )
    graph = StateGraph.from_snapshot(snapshot)

    entries = [node_instance_to_entry(spec, instance) for instance in planner.materialize(spec, snapshot)]
    created = expand_state_node(graph, graph.root_node_id, entries, max_depth=1)

    assert len(created) == 2
    branched_snapshots = [graph.nodes[node_id].snapshot.values for node_id in created]
    assert any(item["color_house"].get("blue") == 2 for item in branched_snapshots)
    assert any(item["color_house"].get("blue") == 4 for item in branched_snapshots)
def test_expand_state_node_creates_branch_children_from_candidate_domains() -> None:
    planner = TickPlanner(max_branch_candidates=2)
    spec = next(item for item in EINSTEIN_NODE_SPECS if item.node_id == "green-coffee")
    snapshot = StateSnapshot.from_values(
        {
            "color_by_house": {
                "house-1": "red",
                "house-2": "yellow",
            },
            "color_house": {
                "red": 1,
                "yellow": 2,
            },
            "drink_by_house": {
                "house-1": "tea",
            },
            "drink_house": {
                "tea": 1,
            },
            "__eliminations__": {
                "color_by_house": {
                    "house-1": ["green"],
                    "house-2": ["green"],
                    "house-4": ["green"],
                },
                "drink_by_house": {
                    "house-1": ["coffee"],
                    "house-2": ["coffee"],
                    "house-4": ["coffee"],
                },
            },
        }
    )
    graph = StateGraph.from_snapshot(snapshot)

    entries = [node_instance_to_entry(spec, instance) for instance in planner.materialize(spec, snapshot)]
    created = expand_state_node(graph, graph.root_node_id, entries, max_depth=1)

    assert len(created) == 2
    branched_snapshots = [graph.nodes[node_id].snapshot.values for node_id in created]
    assert any(item["color_by_house"].get("house-3") == "green" and item["drink_by_house"].get("house-3") == "coffee" for item in branched_snapshots)
    assert any(item["color_by_house"].get("house-5") == "green" and item["drink_by_house"].get("house-5") == "coffee" for item in branched_snapshots)


def test_expand_relation_decision_branch_creates_if_then_alternatives() -> None:
    graph = StateGraph.from_snapshot(
        StateSnapshot.from_values(
            {
                "nationality_by_house": {"house-2": "englishman", "house-4": "spaniard"},
                "color_by_house": {"house-2": "red", "house-3": "green"},
                "pet_by_house": {"house-4": "dog"},
                "color_house": {"white": 2, "green": 3},
            }
        )
    )

    _, created_seed = search_relation_graph_step(
        graph,
        relation_ids=FIRST_TEXT_RELATION_ORDER,
        max_depth=7,
        consumed_spec_ids={"englishman-red", "spaniard-dog"},
    )
    seed_node_id = created_seed[0]

    tree, decision, created = expand_relation_decision_branch(
        graph,
        relation_id="ukrainian-tea",
        node_id=seed_node_id,
        max_depth=7,
        tree=DecisionTree.empty(),
    )

    assert decision is not None
    assert decision.spec_id == "ukrainian-tea"
    assert decision.status == "branched"
    assert len(decision.branch_instance_ids) == 2
    assert len(created) == 2
    branched_snapshots = [graph.nodes[node_id].snapshot.values for node_id in created]
    assert any(item["nationality_by_house"].get("house-1") == "ukrainian" and item["drink_by_house"].get("house-1") == "tea" for item in branched_snapshots)
    assert any(item["nationality_by_house"].get("house-5") == "ukrainian" and item["drink_by_house"].get("house-5") == "tea" for item in branched_snapshots)
    assert len(tree.edges) == 2


def test_reconcile_relation_decision_branch_excludes_sibling_alternatives() -> None:
    graph = StateGraph.from_snapshot(
        StateSnapshot.from_values(
            {
                "nationality_by_house": {"house-2": "englishman", "house-4": "spaniard"},
                "color_by_house": {"house-2": "red", "house-3": "green"},
                "pet_by_house": {"house-4": "dog"},
                "color_house": {"white": 2, "green": 3},
            }
        )
    )

    _, created_seed = search_relation_graph_step(
        graph,
        relation_ids=FIRST_TEXT_RELATION_ORDER,
        max_depth=7,
        consumed_spec_ids={"englishman-red", "spaniard-dog"},
    )
    tree, decision, _ = expand_relation_decision_branch(
        graph,
        relation_id="ukrainian-tea",
        node_id=created_seed[0],
        max_depth=7,
        tree=DecisionTree.empty(),
    )

    assert decision is not None
    reconciled = reconcile_relation_decision_branch(
        tree,
        decision.decision_id,
        "ukrainian-tea-house-1",
    )

    assert reconciled.status == "reconciled"
    assert reconciled.branch_group_id == "ukrainian-tea-candidates"
    assert reconciled.exclusion_group_id == "ukrainian-tea-candidates"
    assert tree.edges[f"{decision.decision_id}->ukrainian-tea-house-1"].status == "saturated"
    assert tree.edges[f"{decision.decision_id}->ukrainian-tea-house-5"].status == "excluded"


def test_auto_reconcile_relation_decision_branch_when_one_survivor_remains() -> None:
    graph = StateGraph.from_snapshot(
        StateSnapshot.from_values(
            {
                "nationality_by_house": {"house-2": "englishman", "house-4": "spaniard"},
                "color_by_house": {"house-2": "red", "house-3": "green"},
                "pet_by_house": {"house-4": "dog"},
                "color_house": {"white": 2, "green": 3},
            }
        )
    )
    _, created_seed = search_relation_graph_step(
        graph,
        relation_ids=FIRST_TEXT_RELATION_ORDER,
        max_depth=7,
        consumed_spec_ids={"englishman-red", "spaniard-dog"},
    )
    tree, decision, _ = expand_relation_decision_branch(
        graph,
        relation_id="ukrainian-tea",
        node_id=created_seed[0],
        max_depth=7,
        tree=DecisionTree.empty(),
    )

    assert decision is not None
    tree.edges[f"{decision.decision_id}->ukrainian-tea-house-5"] = type(tree.edges[f"{decision.decision_id}->ukrainian-tea-house-5"])(
        edge_id=tree.edges[f"{decision.decision_id}->ukrainian-tea-house-5"].edge_id,
        decision_id=tree.edges[f"{decision.decision_id}->ukrainian-tea-house-5"].decision_id,
        branch_instance_id=tree.edges[f"{decision.decision_id}->ukrainian-tea-house-5"].branch_instance_id,
        hypothesis_id=tree.edges[f"{decision.decision_id}->ukrainian-tea-house-5"].hypothesis_id,
        to_state_id=tree.edges[f"{decision.decision_id}->ukrainian-tea-house-5"].to_state_id,
        status="contradicted",
    )

    accepted = auto_reconcile_relation_decision_branch(tree, decision.decision_id)

    assert accepted == "ukrainian-tea-house-1"
    assert tree.decisions[decision.decision_id].status == "reconciled"
    assert tree.edges[f"{decision.decision_id}->ukrainian-tea-house-5"].status == "excluded"


def test_expand_and_auto_reconcile_relation_decision_branch_collapses_single_survivor() -> None:
    graph = StateGraph.from_snapshot(
        StateSnapshot.from_values(
            {
                "nationality_by_house": {"house-2": "englishman", "house-4": "spaniard"},
                "color_by_house": {"house-2": "red", "house-3": "green"},
                "pet_by_house": {"house-4": "dog"},
                "color_house": {"white": 2, "green": 3},
            }
        )
    )
    _, created_seed = search_relation_graph_step(
        graph,
        relation_ids=FIRST_TEXT_RELATION_ORDER,
        max_depth=7,
        consumed_spec_ids={"englishman-red", "spaniard-dog"},
    )
    tree, decision, _ = expand_relation_decision_branch(
        graph,
        relation_id="ukrainian-tea",
        node_id=created_seed[0],
        max_depth=7,
        tree=DecisionTree.empty(),
    )
    assert decision is not None
    tree.edges[f"{decision.decision_id}->ukrainian-tea-house-5"] = type(tree.edges[f"{decision.decision_id}->ukrainian-tea-house-5"])(
        edge_id=tree.edges[f"{decision.decision_id}->ukrainian-tea-house-5"].edge_id,
        decision_id=tree.edges[f"{decision.decision_id}->ukrainian-tea-house-5"].decision_id,
        branch_instance_id=tree.edges[f"{decision.decision_id}->ukrainian-tea-house-5"].branch_instance_id,
        hypothesis_id=tree.edges[f"{decision.decision_id}->ukrainian-tea-house-5"].hypothesis_id,
        to_state_id=tree.edges[f"{decision.decision_id}->ukrainian-tea-house-5"].to_state_id,
        status="contradicted",
    )

    tree, reconciled, created, accepted = expand_and_auto_reconcile_relation_decision_branch(
        graph,
        relation_id="ukrainian-tea",
        node_id=created_seed[0],
        max_depth=7,
        tree=tree,
    )

    assert accepted == "ukrainian-tea-house-1"
    assert reconciled is not None
    assert reconciled.status == "reconciled"
    assert created == []

def test_same_house_partial_propagation_derives_missing_pair_value() -> None:
    graph = StateGraph.from_snapshot(
        StateSnapshot.from_values(
            {
                "nationality_by_house": {"house-1": "englishman"},
                "nationality_house": {"englishman": 1},
            }
        )
    )
    consumed: set[str] = set()

    events, status = tick_relation_graph_until_blocked(
        graph,
        relation_ids=("englishman-red",),
        max_depth=5,
        consumed_spec_ids=consumed,
    )

    assert status == "exhausted"
    assert [spec_id for spec_id, _ in events] == ["englishman-red"]
    deepest = next(node for node in graph.nodes.values() if node.depth == 1)
    assert deepest.snapshot.values["color_by_house"]["house-1"] == "red"
    assert deepest.snapshot.values["color_house"]["red"] == 1


def test_apply_result_to_snapshot_promotes_singletons_from_eliminations() -> None:
    snapshot = StateSnapshot.from_values(
        {
            "color_by_house": {
                "house-1": "red",
                "house-2": "yellow",
                "house-4": "white",
            },
            "color_house": {
                "red": 1,
                "yellow": 2,
                "white": 4,
            },
                "__eliminations__": {
                    "color_by_house": {
                        "house-1": ["green"],
                        "house-2": ["green"],
                        "house-3": ["red", "yellow", "white", "green"],
                        "house-4": ["green"],
                        "house-5": ["red", "yellow", "white"],
                    }
                },
        }
    )
    result = HypothesisResult(
        hypothesis_id="noop",
        title="noop",
        entrypoint="noop",
        status="saturated",
        passed=True,
        metadata={"propagation_effects": {"assignments": (), "eliminations": ()}},
    )

    next_snapshot = apply_result_to_snapshot(snapshot, result)

    assert next_snapshot.values["color_by_house"]["house-5"] == "green"
    assert next_snapshot.values["color_house"]["green"] == 5


def test_first_text_frontier_exposes_late_collision() -> None:
    entries, context = build_first_text_frontier(contradictory=True)

    graph = build_relation_state_sequence_graph(entries, context, max_depth=7)

    assert sorted(node.depth for node in graph.nodes.values()) == [0, 1, 2, 3]
    assert all(edge.status == "saturated" for edge in graph.edges.values())



def test_choose_relation_search_frontier_prefers_narrowest_branching_spec() -> None:
    graph = StateGraph.from_snapshot(
        StateSnapshot.from_values(
            {
                "nationality_by_house": {"house-2": "englishman", "house-4": "spaniard"},
                "color_by_house": {"house-2": "red", "house-3": "green"},
                "pet_by_house": {"house-4": "dog"},
                "color_house": {"white": 2, "green": 3},
            }
        )
    )

    spec_id, entries = choose_relation_search_frontier(
        graph,
        relation_ids=FIRST_TEXT_RELATION_ORDER,
        consumed_spec_ids=set(),
    )

    assert spec_id == "englishman-red"
    assert len(entries) == 1


def test_search_relation_graph_step_uses_narrowest_frontier() -> None:
    graph = StateGraph.from_snapshot(
        StateSnapshot.from_values(
            {
                "nationality_by_house": {"house-2": "englishman", "house-4": "spaniard"},
                "color_by_house": {"house-2": "red", "house-3": "green"},
                "pet_by_house": {"house-4": "dog"},
                "color_house": {"white": 2, "green": 3},
            }
        )
    )
    consumed: set[str] = set()

    spec_id, created = search_relation_graph_step(
        graph,
        relation_ids=FIRST_TEXT_RELATION_ORDER,
        max_depth=7,
        consumed_spec_ids=consumed,
    )

    assert spec_id == "englishman-red"
    assert len(created) == 1
    assert "englishman-red" in consumed


def test_search_relation_graph_n_advances_multiple_best_first_steps() -> None:
    graph = StateGraph.from_snapshot(
        StateSnapshot.from_values(
            {
                "nationality_by_house": {"house-2": "englishman", "house-4": "spaniard"},
                "color_by_house": {"house-2": "red", "house-3": "green"},
                "pet_by_house": {"house-4": "dog"},
                "color_house": {"white": 2, "green": 3},
            }
        )
    )
    consumed: set[str] = set()

    events = search_relation_graph_n(
        graph,
        relation_ids=FIRST_TEXT_RELATION_ORDER,
        steps=3,
        max_depth=7,
        consumed_spec_ids=consumed,
    )

    assert [spec_id for spec_id, _ in events] == [
        "englishman-red",
        "spaniard-dog",
        "green-coffee",
    ]
    assert consumed == {"englishman-red", "spaniard-dog", "green-coffee"}


def test_search_relation_graph_until_blocked_stops_after_best_first_frontier() -> None:
    graph = StateGraph.from_snapshot(
        StateSnapshot.from_values(
            {
                "nationality_by_house": {"house-2": "englishman", "house-4": "spaniard"},
                "color_by_house": {"house-2": "red", "house-3": "green"},
                "pet_by_house": {"house-4": "dog"},
                "color_house": {"white": 2, "green": 3},
            }
        )
    )
    consumed: set[str] = set()

    events, status = search_relation_graph_until_blocked(
        graph,
        relation_ids=FIRST_TEXT_RELATION_ORDER,
        max_depth=7,
        consumed_spec_ids=consumed,
    )

    assert status == "exhausted"
    assert [spec_id for spec_id, _ in events] == [
        "englishman-red",
        "spaniard-dog",
        "green-coffee",
        "green-right-of-white",
        "ukrainian-tea",
        "yellow-kool",
        "old-gold-snails",
    ]
    assert "green-right-of-white" in consumed
    assert "ukrainian-tea" in consumed


def test_search_linked_relation_graph_until_blocked_uses_activation_chain() -> None:
    graph = StateGraph.from_snapshot(
        StateSnapshot.from_values(
            {
                "nationality_by_house": {"house-2": "englishman", "house-4": "spaniard"},
                "color_by_house": {"house-2": "red", "house-3": "green"},
                "pet_by_house": {"house-4": "dog"},
                "color_house": {"white": 2, "green": 3},
            }
        )
    )
    consumed: set[str] = set()

    events, status = search_linked_relation_graph_until_blocked(
        graph,
        start_relation_id="englishman-red",
        max_depth=7,
        consumed_spec_ids=consumed,
    )

    assert status == "exhausted"
    assert [spec_id for spec_id, _ in events] == [
        "englishman-red",
        "spaniard-dog",
        "green-coffee",
        "green-right-of-white",
        "ukrainian-tea",
        "yellow-kool",
        "old-gold-snails",
    ]


def test_tick_relation_graph_once_advances_one_spec_at_a_time() -> None:
    _, context = build_first_text_frontier()
    graph = StateGraph.from_snapshot(StateSnapshot.from_values(context))
    consumed: set[str] = set()

    first_spec, created_first = tick_relation_graph_once(
        graph,
        relation_ids=FIRST_TEXT_RELATION_ORDER,
        max_depth=7,
        consumed_spec_ids=consumed,
    )
    assert first_spec == "englishman-red"
    assert len(created_first) == 1

    second_spec, created_second = tick_relation_graph_once(
        graph,
        relation_ids=FIRST_TEXT_RELATION_ORDER,
        node_id=created_first[0],
        max_depth=7,
        consumed_spec_ids=consumed,
    )
    assert second_spec == "spaniard-dog"
    assert len(created_second) == 1
    assert sorted(node.depth for node in graph.nodes.values()) == [0, 1, 2]


def test_tick_relation_graph_n_advances_multiple_specs_in_order() -> None:
    _, context = build_first_text_frontier()
    graph = StateGraph.from_snapshot(StateSnapshot.from_values(context))
    consumed: set[str] = set()

    events = tick_relation_graph_n(
        graph,
        relation_ids=FIRST_TEXT_RELATION_ORDER,
        steps=3,
        max_depth=7,
        consumed_spec_ids=consumed,
    )

    assert [spec_id for spec_id, _ in events] == [
        "englishman-red",
        "spaniard-dog",
        "green-coffee",
    ]
    assert sorted(node.depth for node in graph.nodes.values()) == [0, 1, 2, 3]
    assert consumed == {"englishman-red", "spaniard-dog", "green-coffee"}


def test_tick_linked_relation_graph_n_follows_hypothesis_links() -> None:
    _, context = build_first_text_frontier()
    graph = StateGraph.from_snapshot(StateSnapshot.from_values(context))
    consumed: set[str] = set()

    events = tick_linked_relation_graph_n(
        graph,
        start_relation_id="englishman-red",
        steps=3,
        max_depth=7,
        consumed_spec_ids=consumed,
    )

    assert [spec_id for spec_id, _ in events] == [
        "englishman-red",
        "spaniard-dog",
        "green-coffee",
    ]
    assert consumed == {"englishman-red", "spaniard-dog", "green-coffee"}


def test_tick_relation_graph_until_blocked_reports_exhausted_for_consistent_frontier() -> None:
    _, context = build_first_text_frontier()
    graph = StateGraph.from_snapshot(StateSnapshot.from_values(context))
    consumed: set[str] = set()

    events, status = tick_relation_graph_until_blocked(
        graph,
        relation_ids=FIRST_TEXT_RELATION_ORDER,
        max_depth=7,
        consumed_spec_ids=consumed,
    )

    assert status == "exhausted"
    assert [spec_id for spec_id, _ in events] == list(FIRST_TEXT_RELATION_ORDER)
    assert sorted(node.depth for node in graph.nodes.values()) == [0, 1, 2, 3, 4]


def test_tick_relation_graph_until_blocked_reports_blocked_when_later_specs_cannot_materialize() -> None:
    graph = StateGraph.from_snapshot(
        StateSnapshot.from_values(
            {
                "nationality_by_house": {
                    "house-2": "englishman",
                    "house-4": "spaniard",
                },
                "color_by_house": {
                    "house-2": "red",
                    "house-3": "green",
                },
                "pet_by_house": {
                    "house-4": "dog",
                },
                "color_house": {"white": 2, "green": 3},
            }
        )
    )
    consumed: set[str] = set()

    events, status = tick_relation_graph_until_blocked(
        graph,
        relation_ids=FIRST_TEXT_RELATION_ORDER,
        max_depth=7,
        consumed_spec_ids=consumed,
    )

    assert status == "exhausted"
    assert [spec_id for spec_id, _ in events] == [
        "englishman-red",
        "spaniard-dog",
        "green-coffee",
        "ukrainian-tea",
        "green-right-of-white",
        "yellow-kool",
        "old-gold-snails",
    ]
    green_coffee_event = next(created for spec_id, created in events if spec_id == "green-coffee")
    assert len(green_coffee_event) == 1
    derived_node = graph.nodes[green_coffee_event[0]]
    assert derived_node.snapshot.values["drink_by_house"]["house-3"] == "coffee"
    ukrainian_events = next(created for spec_id, created in events if spec_id == "ukrainian-tea")
    assert len(ukrainian_events) == 2
    assert "ukrainian-tea" in consumed


def test_run_relation_graph_until_blocked_from_direct_givens_stops_unsolved() -> None:
    graph, events, status = run_relation_graph_until_blocked(
        build_direct_givens_context(),
        relation_ids=ALL_RELATION_ORDER,
        max_depth=20,
        consumed_spec_ids=set(),
    )

    assert status == "blocked"
    assert [spec_id for spec_id, _ in events] == [
        "ukrainian-tea",
        "englishman-red",
        "spaniard-dog",
        "green-coffee",
        "yellow-kool",
        "old-gold-snails",
        "lucky-strike-orange-juice",
        "japanese-parliament",
        "chesterfield-next-to-fox",
        "kool-next-to-horse",
    ]
    assert len(graph.nodes) >= 10

    markdown = render_solver_run_markdown(graph, events, status)
    assert "- status: `blocked`" in markdown
    assert "- deepest_depth: `10`" in markdown
    assert "| house-1 | norwegian | green | coffee | snails | old-gold |" in markdown
    assert "| house-2 | ukrainian | yellow | tea | fox | kool |" in markdown
    assert "| house-3 | englishman | red | milk | horse | chesterfield |" in markdown
    assert "| house-4 | spaniard | - | orange-juice | dog | lucky-strike |" in markdown
    assert "| house-5 | japanese | - | water | zebra | parliament |" in markdown


def test_run_relation_graph_until_blocked_from_direct_givens_advances_beyond_first_step() -> None:
    graph, events, status = run_relation_graph_until_blocked(
        build_direct_givens_context(),
        relation_ids=ALL_RELATION_ORDER,
        max_depth=50,
        consumed_spec_ids=set(),
    )

    assert status in {"blocked", "exhausted"}
    assert [spec_id for spec_id, _ in events][:2] == ["ukrainian-tea", "englishman-red"]
    assert len(graph.nodes) >= 3


def test_run_linked_relation_loop_returns_ticks_and_branch_decisions() -> None:
    context = {
        "nationality_by_house": {"house-2": "englishman", "house-4": "spaniard"},
        "color_by_house": {"house-2": "red", "house-3": "green"},
        "pet_by_house": {"house-4": "dog"},
        "color_house": {"white": 2, "green": 3},
    }

    graph, tree, tick_events, decision_events, status = run_linked_relation_loop(
        context,
        start_relation_id="englishman-red",
        max_depth=7,
    )

    assert status == "exhausted"
    assert [spec_id for spec_id, _ in tick_events] == [
        "englishman-red",
        "spaniard-dog",
        "green-coffee",
        "green-right-of-white",
        "ukrainian-tea",
        "yellow-kool",
        "old-gold-snails",
    ]
    assert decision_events
    assert any(spec_id == "ukrainian-tea" for spec_id, _ in decision_events)
    assert graph.nodes


def test_run_linked_relation_loop_trace_returns_unified_event_stream() -> None:
    context = {
        "nationality_by_house": {"house-2": "englishman", "house-4": "spaniard"},
        "color_by_house": {"house-2": "red", "house-3": "green"},
        "pet_by_house": {"house-4": "dog"},
        "color_house": {"white": 2, "green": 3},
    }

    graph, tree, events, status = run_linked_relation_loop_trace(
        context,
        start_relation_id="englishman-red",
        max_depth=7,
    )

    assert status == "exhausted"
    assert events
    assert events[0].kind == "tick"
    assert any(event.kind == "branch" and event.spec_id == "ukrainian-tea" for event in events)
    assert events[-1].kind == "exhausted"
    markdown = render_loop_events_table(events)
    assert "| kind | spec_id | node_id | created_nodes | accepted_branch | status |" in markdown
    assert graph.nodes
    assert tree is not None


def test_run_linked_relation_loop_trace_respects_branch_depth_policy() -> None:
    context = {
        "nationality_by_house": {"house-2": "englishman", "house-4": "spaniard"},
        "color_by_house": {"house-2": "red", "house-3": "green"},
        "pet_by_house": {"house-4": "dog"},
        "color_house": {"white": 2, "green": 3},
    }

    _, _, events, status = run_linked_relation_loop_trace(
        context,
        start_relation_id="englishman-red",
        policy=LoopPolicy(max_depth=7, max_branch_depth=0, max_parallel_branches=2),
    )

    assert status == "exhausted"
    assert not any(event.kind == "branch" for event in events)


def test_two_phase_solver_fixpoint_is_stable_across_relation_order() -> None:
    context = {
        "nationality_by_house": {"house-2": "englishman", "house-4": "spaniard"},
        "color_by_house": {"house-2": "red", "house-3": "green"},
        "pet_by_house": {"house-4": "dog"},
        "drink_by_house": {"house-3": "coffee"},
    }
    relation_ids = ("englishman-red", "spaniard-dog", "green-coffee")

    graph_a, events_a, status_a = run_relation_graph_two_phase_until_blocked(
        context,
        relation_ids=relation_ids,
        max_depth=10,
    )
    graph_b, events_b, status_b = run_relation_graph_two_phase_until_blocked(
        context,
        relation_ids=tuple(reversed(relation_ids)),
        max_depth=10,
    )

    deepest_a = max(graph_a.nodes.values(), key=lambda node: (node.depth, node.node_id))
    deepest_b = max(graph_b.nodes.values(), key=lambda node: (node.depth, node.node_id))
    assert status_a == status_b == "blocked"
    assert set(spec_id for spec_id, _ in events_a) == set(relation_ids)
    assert set(spec_id for spec_id, _ in events_b) == set(relation_ids)
    assert deepest_a.snapshot.values == deepest_b.snapshot.values


def test_run_einstein_solver_until_blocked_uses_solver_order() -> None:
    graph, events, status = run_einstein_solver_until_blocked(max_depth=50)

    assert status == "blocked"
    assert list(dict.fromkeys(spec_id for spec_id, _ in events)) == [
        "norwegian-next-to-blue",
        "green-right-of-white",
        "englishman-red",
        "green-coffee",
        "ukrainian-tea",
        "yellow-kool",
        "kool-next-to-horse",
        "spaniard-dog",
        "old-gold-snails",
        "lucky-strike-orange-juice",
        "japanese-parliament",
        "chesterfield-next-to-fox",
    ]
    deepest = max(graph.nodes.values(), key=lambda node: (node.depth, node.node_id))
    assert deepest.snapshot.values["color_by_house"]["house-5"] == "yellow"
    assert deepest.snapshot.values["smoke_by_house"]["house-5"] == "kool"
