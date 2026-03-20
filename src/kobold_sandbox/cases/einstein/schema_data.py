from __future__ import annotations

from ...core.schema_engine import PuzzleSchema

EINSTEIN_CATEGORY_ORDER = ("color", "nation", "drink", "smoke", "pet")

EINSTEIN_SCHEMA_DATA = {
    "metadata": {
        "name": "Einstein's Riddle",
        "size": 5,
    },
    "categories": {
        "color": ["Red", "Green", "White", "Yellow", "Blue"],
        "nation": ["English", "Spanish", "Ukrainian", "Norwegian", "Japanese"],
        "pet": ["Dog", "Snails", "Fox", "Horse", "Zebra"],
        "drink": ["Coffee", "Tea", "Milk", "Juice", "Water"],
        "smoke": ["Old Gold", "Kool", "Chesterfield", "Lucky Strike", "Parliament"],
    },
    "rules": [
        {"type": "same", "relation_id": "englishman-red", "statement": "Англичанин живёт в красном доме.", "fact": ["nation:English", "color:Red"]},
        {"type": "same", "relation_id": "spaniard-dog", "statement": "У испанца есть собака.", "fact": ["nation:Spanish", "pet:Dog"]},
        {"type": "same", "relation_id": "green-coffee", "statement": "В зелёном доме пьют кофе.", "fact": ["color:Green", "drink:Coffee"]},
        {"type": "same", "relation_id": "ukrainian-tea", "statement": "Украинец пьёт чай.", "fact": ["nation:Ukrainian", "drink:Tea"]},
        {"type": "directly_right", "relation_id": "green-right-of-white", "statement": "Зелёный дом стоит сразу справа от белого дома.", "fact": ["color:White", "color:Green"]},
        {"type": "same", "relation_id": "old-gold-snails", "statement": "Тот, кто курит Old Gold, разводит улиток.", "fact": ["smoke:Old Gold", "pet:Snails"]},
        {"type": "same", "relation_id": "yellow-kool", "statement": "В жёлтом доме курят Kool.", "fact": ["color:Yellow", "smoke:Kool"]},
        {
            "type": "position",
            "relation_id": "center-milk",
            "statement": "В центральном доме пьют молоко.",
            "fact": ["drink:Milk", 2],
            "claim_id": "house-3__milk__yes",
            "category": "drink",
            "row": "house-3",
            "column": "milk",
            "container": "drink_by_house",
            "key": "house-3",
            "value": "milk",
            "title": "House 3 drinks milk",
            "description": "Direct given: Milk is in house 3",
            "consequences": ["einstein-drink:house-3:milk -> yes"],
            "first_step": True,
        },
        {
            "type": "position",
            "relation_id": "norwegian-first",
            "statement": "Норвежец живёт в первом доме.",
            "fact": ["nation:Norwegian", 0],
            "claim_id": "house-1__norwegian__yes",
            "category": "nationality",
            "row": "house-1",
            "column": "norwegian",
            "container": "nationality_by_house",
            "key": "house-1",
            "value": "norwegian",
            "title": "House 1 is Norwegian",
            "description": "Direct given: Norwegian is in house 1",
            "consequences": [
                "einstein-nationality:house-1:norwegian -> yes",
                "house-1 cannot host other nationalities",
            ],
            "first_step": True,
        },
        {"type": "next_to", "relation_id": "chesterfield-next-to-fox", "statement": "Сосед того, кто курит Chesterfield, держит лису.", "fact": ["smoke:Chesterfield", "pet:Fox"]},
        {"type": "next_to", "relation_id": "kool-next-to-horse", "statement": "В доме по соседству с тем, где держат лошадь, курят Kool.", "fact": ["smoke:Kool", "pet:Horse"]},
        {"type": "same", "relation_id": "lucky-strike-orange-juice", "statement": "Тот, кто курит Lucky Strike, пьёт апельсиновый сок.", "fact": ["smoke:Lucky Strike", "drink:Juice"]},
        {"type": "same", "relation_id": "japanese-parliament", "statement": "Японец курит Parliament.", "fact": ["nation:Japanese", "smoke:Parliament"]},
        {"type": "next_to", "relation_id": "norwegian-next-to-blue", "statement": "Норвежец живёт рядом с синим домом.", "fact": ["nation:Norwegian", "color:Blue"]},
    ],
}


def build_einstein_schema() -> PuzzleSchema:
    return PuzzleSchema.from_dict(EINSTEIN_SCHEMA_DATA)
