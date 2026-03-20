# Chess Position

| r/c | a | b | c | d | e | f | g | h |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 8 | . | . | . | . | . | . | . | ♚ |
| 7 | . | . | . | . | . | ♟ | ♟ | ♟ |
| 6 | ♟ | ♟ | ♟ | . | . | . | . | . |
| 5 | . | . | . | . | . | . | . | . |
| 4 | ♙ | ♙ | ♙ | . | . | . | . | . |
| 3 | . | . | . | . | . | . | . | . |
| 2 | . | . | . | . | . | . | . | . |
| 1 | . | . | . | . | . | . | . | ♔ |

## Phase 1

- `prefix_line`: `b4-b5, a6-b5, c4-c5, b6-c5, a4-a5`
- `runner_square`: `a5`
- `promotion_square`: `a8`
- `side_to_move_after_prefix`: `black`
- `black_prep_moves`: `2`

# Chess Position

| r/c | a | b | c | d | e | f | g | h |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 8 | . | . | . | . | . | . | . | ♚ |
| 7 | . | . | . | . | . | ♟ | ♟ | ♟ |
| 6 | . | . | ♟ | . | . | . | . | . |
| 5 | ♙ | ♟ | ♟ | . | . | . | . | . |
| 4 | . | . | . | . | . | . | . | . |
| 3 | . | . | . | . | . | . | . | . |
| 2 | . | . | . | . | . | . | . | . |
| 1 | . | . | . | . | . | . | . | ♔ |

## Phase 2

- `candidate_count`: `48`
- `recommended_index`: `0`

### Recommended

- `prep_line`: `g7-g5, a5-a6, h8-g7, a6-a7`
- `heuristic`: `129`
- `immediate_mate`: `False`
- `survival_moves`: `13`
- `phase3_side_to_move`: `black`

# Chess Position

| r/c | a | b | c | d | e | f | g | h |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 8 | . | . | . | . | . | . | . | . |
| 7 | ♙ | . | . | . | . | ♟ | ♚ | ♟ |
| 6 | . | . | ♟ | . | . | . | . | . |
| 5 | . | ♟ | ♟ | . | . | . | ♟ | . |
| 4 | . | . | . | . | . | . | . | . |
| 3 | . | . | . | . | . | . | . | . |
| 2 | . | . | . | . | . | . | . | . |
| 1 | . | . | . | . | . | . | . | ♔ |

### All Candidates

- `0`: `g7-g5, a5-a6, h8-g7, a6-a7` | heuristic=`129` | immediate_mate=`False` | survival_moves=`13` | side_to_move=`black`
- `1`: `g7-g6, a5-a6, h8-g7, a6-a7` | heuristic=`119` | immediate_mate=`False` | survival_moves=`12` | side_to_move=`black`
- `2`: `h7-h5, a5-a6, h8-h7, a6-a7` | heuristic=`128` | immediate_mate=`False` | survival_moves=`11` | side_to_move=`black`
- `3`: `c5-c4, a5-a6, g7-g5, a6-a7` | heuristic=`139` | immediate_mate=`False` | survival_moves=`10` | side_to_move=`black`
- `4`: `c5-c4, a5-a6, h7-h5, a6-a7` | heuristic=`139` | immediate_mate=`False` | survival_moves=`10` | side_to_move=`black`
- `5`: `g7-g5, a5-a6, h8-g8, a6-a7` | heuristic=`130` | immediate_mate=`False` | survival_moves=`10` | side_to_move=`black`
- `6`: `h7-h5, a5-a6, h8-g8, a6-a7` | heuristic=`130` | immediate_mate=`False` | survival_moves=`10` | side_to_move=`black`
- `7`: `c5-c4, a5-a6, g7-g6, a6-a7` | heuristic=`129` | immediate_mate=`False` | survival_moves=`10` | side_to_move=`black`
- `8`: `c5-c4, a5-a6, h7-h6, a6-a7` | heuristic=`129` | immediate_mate=`False` | survival_moves=`10` | side_to_move=`black`
- `9`: `g7-g6, a5-a6, h8-g8, a6-a7` | heuristic=`120` | immediate_mate=`False` | survival_moves=`10` | side_to_move=`black`
- `10`: `h7-h6, a5-a6, h8-g8, a6-a7` | heuristic=`120` | immediate_mate=`False` | survival_moves=`10` | side_to_move=`black`
- `11`: `h7-h6, a5-a6, h8-h7, a6-a7` | heuristic=`118` | immediate_mate=`False` | survival_moves=`10` | side_to_move=`black`
- `12`: `h8-g8, a5-a6, g8-f8, a6-a7` | heuristic=`111` | immediate_mate=`False` | survival_moves=`10` | side_to_move=`black`
- `13`: `g7-g5, a5-a6, h7-h5, a6-a7` | heuristic=`149` | immediate_mate=`False` | survival_moves=`9` | side_to_move=`black`
- `14`: `b5-b4, a5-a6, g7-g5, a6-a7` | heuristic=`139` | immediate_mate=`False` | survival_moves=`9` | side_to_move=`black`
- `15`: `b5-b4, a5-a6, h7-h5, a6-a7` | heuristic=`139` | immediate_mate=`False` | survival_moves=`9` | side_to_move=`black`
- `16`: `g7-g5, a5-a6, g5-g4, a6-a7` | heuristic=`139` | immediate_mate=`False` | survival_moves=`9` | side_to_move=`black`
- `17`: `g7-g5, a5-a6, h7-h6, a6-a7` | heuristic=`139` | immediate_mate=`False` | survival_moves=`9` | side_to_move=`black`
- `18`: `g7-g6, a5-a6, h7-h5, a6-a7` | heuristic=`139` | immediate_mate=`False` | survival_moves=`9` | side_to_move=`black`
- `19`: `h7-h5, a5-a6, h5-h4, a6-a7` | heuristic=`139` | immediate_mate=`False` | survival_moves=`9` | side_to_move=`black`
- `20`: `f7-f5, a5-a6, h8-g8, a6-a7` | heuristic=`130` | immediate_mate=`False` | survival_moves=`9` | side_to_move=`black`
- `21`: `b5-b4, a5-a6, g7-g6, a6-a7` | heuristic=`129` | immediate_mate=`False` | survival_moves=`9` | side_to_move=`black`
- `22`: `b5-b4, a5-a6, h7-h6, a6-a7` | heuristic=`129` | immediate_mate=`False` | survival_moves=`9` | side_to_move=`black`
- `23`: `g7-g6, a5-a6, g6-g5, a6-a7` | heuristic=`129` | immediate_mate=`False` | survival_moves=`9` | side_to_move=`black`
- `24`: `g7-g6, a5-a6, h7-h6, a6-a7` | heuristic=`129` | immediate_mate=`False` | survival_moves=`9` | side_to_move=`black`
- `25`: `h7-h6, a5-a6, h6-h5, a6-a7` | heuristic=`129` | immediate_mate=`False` | survival_moves=`9` | side_to_move=`black`
- `26`: `f7-f6, a5-a6, h8-g8, a6-a7` | heuristic=`120` | immediate_mate=`False` | survival_moves=`9` | side_to_move=`black`
- `27`: `f7-f5, a5-a6, g7-g5, a6-a7` | heuristic=`149` | immediate_mate=`False` | survival_moves=`8` | side_to_move=`black`
- `28`: `f7-f5, a5-a6, h7-h5, a6-a7` | heuristic=`149` | immediate_mate=`False` | survival_moves=`8` | side_to_move=`black`
- `29`: `f7-f5, a5-a6, g7-g6, a6-a7` | heuristic=`139` | immediate_mate=`False` | survival_moves=`8` | side_to_move=`black`
- `30`: `f7-f5, a5-a6, h7-h6, a6-a7` | heuristic=`139` | immediate_mate=`False` | survival_moves=`8` | side_to_move=`black`
- `31`: `f7-f6, a5-a6, g7-g5, a6-a7` | heuristic=`139` | immediate_mate=`False` | survival_moves=`8` | side_to_move=`black`
- `32`: `f7-f6, a5-a6, h7-h5, a6-a7` | heuristic=`139` | immediate_mate=`False` | survival_moves=`8` | side_to_move=`black`
- `33`: `f7-f6, a5-a6, g7-g6, a6-a7` | heuristic=`129` | immediate_mate=`False` | survival_moves=`8` | side_to_move=`black`
- `34`: `f7-f6, a5-a6, h7-h6, a6-a7` | heuristic=`129` | immediate_mate=`False` | survival_moves=`8` | side_to_move=`black`
- `35`: `b5-b4, a5-a6, h8-g8, a6-a7` | heuristic=`120` | immediate_mate=`False` | survival_moves=`7` | side_to_move=`black`
- `36`: `c5-c4, a5-a6, h8-g8, a6-a7` | heuristic=`120` | immediate_mate=`False` | survival_moves=`7` | side_to_move=`black`
- `37`: `b5-b4, a5-a6, f7-f5, a6-a7` | heuristic=`139` | immediate_mate=`False` | survival_moves=`5` | side_to_move=`black`
- `38`: `c5-c4, a5-a6, f7-f5, a6-a7` | heuristic=`139` | immediate_mate=`False` | survival_moves=`5` | side_to_move=`black`
- `39`: `f7-f5, a5-a6, f5-f4, a6-a7` | heuristic=`139` | immediate_mate=`False` | survival_moves=`5` | side_to_move=`black`
- `40`: `b5-b4, a5-a6, f7-f6, a6-a7` | heuristic=`129` | immediate_mate=`False` | survival_moves=`5` | side_to_move=`black`
- `41`: `c5-c4, a5-a6, f7-f6, a6-a7` | heuristic=`129` | immediate_mate=`False` | survival_moves=`5` | side_to_move=`black`
- `42`: `f7-f6, a5-a6, f6-f5, a6-a7` | heuristic=`129` | immediate_mate=`False` | survival_moves=`5` | side_to_move=`black`
- `43`: `b5-b4, a5-a6, b4-b3, a6-a7` | heuristic=`129` | immediate_mate=`False` | survival_moves=`4` | side_to_move=`black`
- `44`: `b5-b4, a5-a6, c5-c4, a6-a7` | heuristic=`129` | immediate_mate=`False` | survival_moves=`4` | side_to_move=`black`
- `45`: `c5-c4, a5-a6, c4-c3, a6-a7` | heuristic=`129` | immediate_mate=`False` | survival_moves=`4` | side_to_move=`black`
- `46`: `c5-c4, a5-a6, c6-c5, a6-a7` | heuristic=`129` | immediate_mate=`False` | survival_moves=`4` | side_to_move=`black`
- `47`: `h8-g8, a5-a6, g8-h8, a6-a7` | heuristic=`109` | immediate_mate=`False` | survival_moves=`4` | side_to_move=`black`

## Phase 3

### Top Candidate Finishes

- `candidate 1`: outcome=`unknown` score=`368` line=`f7-f6, a7-a8=Q, b5-b4, a8-c6`
- `candidate 7`: outcome=`unknown` score=`368` line=`c4-c3, a7-a8=Q, h8-g7, a8-c6`
- `candidate 21`: outcome=`unknown` score=`368` line=`b4-b3, a7-a8=Q, h8-g7, a8-c6`
- `candidate 33`: outcome=`unknown` score=`368` line=`b5-b4, a7-a8=Q, h8-g7, a8-c6`
- `candidate 40`: outcome=`unknown` score=`368` line=`g7-g6, a7-a8=Q, h8-g7, a8-c6`
- `candidate 41`: outcome=`unknown` score=`368` line=`g7-g6, a7-a8=Q, h8-g7, a8-c6`
- `candidate 43`: outcome=`unknown` score=`368` line=`g7-g6, a7-a8=Q, h8-g7, a8-c6`
- `candidate 44`: outcome=`unknown` score=`368` line=`g7-g6, a7-a8=Q, h8-g7, a8-c6`
- `candidate 45`: outcome=`unknown` score=`368` line=`g7-g6, a7-a8=Q, h8-g7, a8-c6`
- `candidate 8`: outcome=`unknown` score=`365` line=`g7-g6, a7-a8=Q, h8-g7, a8-c6`

## Phase 3 Stockfish

- `candidate 1`: best_move=`c5c4` eval=`cp:328` black_score=`-328`
- `candidate 0`: best_move=`c5c4` eval=`cp:343` black_score=`-343`
- `candidate 3`: best_move=`h8g7` eval=`cp:353` black_score=`-353`
- `candidate 2`: best_move=`b5b4` eval=`cp:356` black_score=`-356`
- `candidate 14`: best_move=`h8g7` eval=`cp:356` black_score=`-356`
- `candidate 7`: best_move=`h8g7` eval=`cp:372` black_score=`-372`
- `candidate 6`: best_move=`g8h7` eval=`cp:374` black_score=`-374`
- `candidate 8`: best_move=`g7g6` eval=`cp:379` black_score=`-379`
- `candidate 44`: best_move=`g7g5` eval=`cp:380` black_score=`-380`
- `candidate 45`: best_move=`g7g5` eval=`cp:380` black_score=`-380`

## Phase 3 Stockfish Tree

- `candidate 43`: black_score=`0` line=`b3-b2, a7-a8=Q` eval=`mate:0`
- `candidate 44`: black_score=`-184` line=`b4-b3, h1-g1, b3-b2, g1-g2` eval=`cp:184`
- `candidate 45`: black_score=`-249` line=`c3-c2, h1-h2, b5-b4, h2-g2` eval=`cp:249`
- `candidate 46`: black_score=`-310` line=`c4-c3, h1-g2, c3-c2, g2-h2` eval=`cp:310`
- `candidate 1`: black_score=`-365` line=`b5-b4, a7-a8=Q, b4-b3, a8-a1` eval=`cp:365`
- `candidate 13`: black_score=`-366` line=`c5-c4, h1-g2, h5-h4, a7-a8=Q` eval=`cp:366`
- `candidate 2`: black_score=`-371` line=`f7-f6, a7-a8=Q, h5-h4, a8-c6` eval=`cp:371`
- `candidate 14`: black_score=`-371` line=`h8-g7, a7-a8=Q, c5-c4, h1-g2` eval=`cp:371`
- `candidate 12`: black_score=`-373` line=`f8-e7, a7-a8=Q, e7-d6, h1-g2` eval=`cp:373`
- `candidate 4`: black_score=`-379` line=`g7-g6, h1-g2, h8-g7, a7-a8=Q` eval=`cp:379`

## Phase 3 Stockfish Beam

- `candidate 21`: black_score=`714` nodes=`1309` line=`c5-c4, h1-h2, c4-c3, h2-g1, h8-g7, a7-a8=R` eval=`cp:-714`
- `candidate 45`: black_score=`624` nodes=`1279` line=`g7-g5, h1-h2, h8-g8, h2-h1, c3-c2, a7-a8=R` eval=`cp:-624`
- `candidate 12`: black_score=`622` nodes=`1330` line=`f8-e7, h1-g2, e7-d6, g2-f1, d6-c7, a7-a8=B` eval=`cp:-622`
- `candidate 18`: black_score=`615` nodes=`1341` line=`c5-c4, h1-g2, c4-c3, g2-f3, c3-c2, a7-a8=R` eval=`cp:-615`
- `candidate 14`: black_score=`613` nodes=`1315` line=`b4-b3, h1-g1, c5-c4, g1-f2, b3-b2, a7-a8=R` eval=`cp:-613`
- `candidate 1`: black_score=`604` nodes=`1365` line=`c5-c4, h1-g2, h7-h6, g2-g3, c4-c3, a7-a8=R` eval=`cp:-604`
- `candidate 0`: black_score=`592` nodes=`1365` line=`c5-c4, h1-g2, h7-h6, g2-f3, c4-c3, a7-a8=R` eval=`cp:-592`
- `candidate 7`: black_score=`591` nodes=`1312` line=`h8-g7, h1-g2, c4-c3, g2-f3, h7-h6, a7-a8=R` eval=`cp:-591`
- `candidate 3`: black_score=`587` nodes=`1318` line=`h8-g7, h1-h2, g5-g4, h2-g2, c4-c3, a7-a8=R` eval=`cp:-587`
- `candidate 46`: black_score=`584` nodes=`1283` line=`g7-g5, h1-h2, c4-c3, h2-g3, c3-c2, a7-a8=R` eval=`cp:-584`