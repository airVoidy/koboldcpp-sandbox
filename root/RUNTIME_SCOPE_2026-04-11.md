# Runtime Scope: 2026-04-11

## Зачем этот документ

Это рабочий снимок текущего scope по runtime-архитектуре.

Здесь зафиксировано:
- какие инварианты уже согласованы
- что реально уже сделано в коде
- что пока только в виде рабочей гипотезы
- что делать следующим

Документ специально отделён от старых заметок:
- старый [`/C:/llm/KoboldCPP agentic sandbox/root/ARCHITECTURE_NEXT.md`](/C:/llm/KoboldCPP%20agentic%20sandbox/root/ARCHITECTURE_NEXT.md) частично устарел
- в нём сломана кодировка
- там смешаны старые pchat/view идеи и новые runtime-инварианты

## 1. Базовые инварианты

### 1.1 Source of truth

Главный инвариант:
- source of truth = immutable ordered exec log
- порядок сообщений = порядок причинности
- старые exec messages не патчатся
- один запрос на сервер = один exec message
- один exec message разворачивается в один exec batch
- после полного resolve этого message batch исполняется целиком
- только потом обрабатывается следующий message

Следствие:
- state не является truth
- snapshots и projections являются производными
- любые cards, tables, channels, messages это runtime-представления поверх L0

### 1.2 Node

На runtime-уровне:
- `Node` всегда просто `Node`
- не нужно разводить отдельные сущности `fs_node/json_node/list_node/...`
- структура не определяется типом объекта
- структура определяется projection/lambda-правилами

То есть:
- у нас есть node tree / node list
- а list/table/json/card это уже способы читать одну и ту же структуру

### 1.3 List-first projection

Зафиксирован полезный инвариант:
- если представление встретилось хотя бы один раз, мы разворачиваем его как множественное
- даже одиночный элемент живёт как `List(T)` длины 1

Важно:
- `.0` не является частью базовой структуры
- `.0/.1/...` появляются только на позднем projection/view-слое
- сами объекты не обязаны храниться как массив

### 1.4 Template-first structure

Шаблон нужен как source of truth для структуры:
- template задаёт относительные field paths
- template задаёт aliases и pattern matching
- template задаёт команды, компоненты, transform/bind rules

Данные при этом живут отдельно:
- root atomic field table
- canonical `path -> value`

Именно это позволяет:
- перестраивать структуру по template patch
- не теряя самих данных

## 2. Runtime model, которую сейчас считаем целевой

### 2.1 L0

L0 мыслится как 1D immutable exec log.

Каждый элемент L0:
- root exec message
- содержит raw input
- содержит meta
- при resolve может породить вложенные runtime-объекты

Но сам L0:
- остаётся append-only
- не меняется задним числом

### 2.2 Wrappers and projections

Все остальные структуры это projection/wrapper layers:
- bind
- alias
- template-relative paths
- virtual lists
- virtual tables
- cards
- replies
- grouped messages by channel/type/template

Ключевая идея:
- мы не меняем старую дату
- мы дописываем новые обёртки и transform rules
- один и тот же L0 читается разными способами

### 2.3 Exec processing model

Уточнённый пайплайн:

1. берём текущее сообщение
2. разворачиваем только его
3. во время разворота можно допушить новые команды в resolve queue этого же message
4. когда разворот стабилизировался, получаем плоский exec batch
5. исполняем этот batch как одну транзакцию
6. возвращаем один ответ
7. переходим к следующему message

Это важно для chat/bash-like модели.

## 3. Atomic / field layer

### 3.1 Field-first

Основная рабочая модель:
- базовый atom = field
- field имеет canonical identity
- дальнейшие object/table/card формы лишь ссылаются на field

Сильная рабочая гипотеза:
- canonical field по сути singleton по `global_atomic_canonical_path`
- field id = canonical path

### 3.2 Canonical vs local

Нужно держать разделение:
- canonical path = identity
- local path = projection/template-relative naming

Это даёт:
- гибкость локальных представлений
- устойчивость identity

### 3.3 Flat root field table

Зафиксировано как обязательный слой:
- без flat root field table runtime будет хрупким
- с ним структура может перестраиваться через template-патчи

То есть:
- canonical data layer = flat table of fields
- structure / json / lists / tables = производные

## 4. Runtime projections и aliases

### 4.1 Промежуточный alias layer

Сейчас agreed shape такой:
- в runtime удобно иметь projection layer для временных alias-ов
- при трансформах не всегда хочется сразу оперировать внешними canonical paths
- сначала собираются временные bindings
- потом они схлопываются в прямые links

### 4.2 Flat projection store

В качестве практического промежуточного слоя выбрана форма:

`full_relative_path -> [hash, full_relative_path, value]`

Идея:
- `hash` = быстрый identity для конкретной projection entry
- `full_relative_path` = навигация и debug
- `value` = resolved значение

Плюс сверху:
- `view_filters`
- готовые `views`

Это нужно для:
- runtime переключения view
- jsonata/select/query
- будущих aliases и локальных transforms

## 5. JSONata как transform/query engine

### 5.1 Почему подходит

JSONata очень хорошо совпадает с нашими задачами:
- path-like syntax
- variables
- bindings
- closures
- higher-order functions
- partial application
- chain operators
- compact joins and projections
- object/list functions
- extension API через custom lambdas

Практически это означает:
- свой mini-language для transforms можно не писать с нуля
- можно использовать JSONata как embedded transform engine внутри exec/runtime

### 5.2 Что из JSONata нам особенно полезно

- `$`, `$$`
- `:=`
- `[...]`
- object projection
- `$keys`, `$lookup`, `$spread`, `$merge`, `$each`, `$type`
- `~>`
- локальные variables/bindings
- `register_lambda` / `registerFunction`

### 5.3 Ограничение на сейчас

В shell-like command parser строки с кавычками внутри выражения сейчас режутся.

То есть:
- JSONata engine уже подключён
- runtime data для него уже подготовлена
- но shell parser ещё не умеет безопасно пропускать raw multiline/raw-tail expression

Это не проблема JSONata.
Это проблема способа передачи expression в exec command.

## 6. Что уже реально сделано

Ниже только фактические изменения, уже сделанные в коде.

### 6.1 Message slot local exec log

В [`/C:/llm/KoboldCPP agentic sandbox/src/kobold_sandbox/server.py`](/C:/llm/KoboldCPP%20agentic%20sandbox/src/kobold_sandbox/server.py) добавлен базовый local exec log для message slot:

- `_exec_log_path(...)`
- `_append_exec_entry(...)`

Сейчас:
- `post` пишет append-only entry в `msg_*/_exec.jsonl`

Это пока минимальный первый шаг.

### 6.2 Message projection builder

Добавлен `_build_message_projection(...)`.

Он строит projection для message node со слоями:
- `_meta`
- `_data`
- `fields`
- `flat_store`
- `view_filters`
- `views`

### 6.3 Flat runtime projection store

В projection теперь есть:
- `flat_store[path] = [hash, path, value]`
- `view_filters`
- `views.all`
- `views._meta`
- `views._data`

Это уже даёт минимальный runtime flat layer для transforms.

### 6.4 Message checkpoint

Добавлено:
- `create_message_checkpoint(...)`
- `cmd_mcheckpoint(...)`
- command file [`/C:/llm/KoboldCPP agentic sandbox/root/templates/root/commands/mcheckpoint.py`](/C:/llm/KoboldCPP%20agentic%20sandbox/root/templates/root/commands/mcheckpoint.py)

Checkpoint сейчас:
- создаёт child node внутри message slot
- сохраняет текущий projection
- сохраняет resolved snapshot
- дописывает `checkpoint` entry в `_exec.jsonl`

Это тестовый checkpoint slice, не финальная архитектура.

### 6.5 JSONata runtime eval over message projection

Добавлено:
- `eval_message_projection_jsonata(...)`
- `cmd_mjsonata(...)`
- command file [`/C:/llm/KoboldCPP agentic sandbox/root/templates/root/commands/mjsonata.py`](/C:/llm/KoboldCPP%20agentic%20sandbox/root/templates/root/commands/mjsonata.py)

В JSONata сейчас пробрасываются:
- `$projection`
- `$flat_store`
- `$views`

И runtime lambdas:
- `$field(path)`
- `$value(path)`
- `$view(name)`

Что уже работает:
- eval по `view`
- eval по `flat_store`
- introspection вроде `$keys($)` и `$views`

Что пока неудобно:
- raw string arguments inside shell-like command

### 6.6 Отдельная ветка с этим slice

Текущий runtime/jsonata slice зафиксирован в ветке:
- `codex/runtime-jsonata-slice`

Коммит:
- `06d2ffe` — `Add message projection checkpoint and JSONata runtime eval`

## 7. Что уже сделано раньше и остаётся релевантным

Ранее уже был собран отдельный слой runtime containers / projections / virtual tables.

Из важного:
- type-based runtime atomic-dsl view specs
- bind-oriented runtime shape
- `define-field`
- projection containers
- modular projection ops
- modular table ops
- `load_children`
- `load_child_log`
- `tablewindow`
- `before_ref/after_ref` paging
- `current_channel_messages` как table container

Это всё остаётся полезным, но сейчас мы отдельно выстраиваем более фундаментальный runtime слой вокруг immutable exec и field/projection logic.

## 8. Что ещё не сделано

### 8.1 Самое важное

Пока не сделано главное:
- materialize state из runtime/exec truth без опоры на mutable snapshot как на истину

Сейчас:
- `_meta/_data` ещё используются как удобный snapshot/cache

Цель:
- state/resolved object должен собираться из immutable exec log + runtime projections

### 8.2 Shell-safe raw expression transport

Нужно дать raw expression mode для JSONata в shell-like exec:
- multiline payload
- raw tail после `--`
- heredoc-подобный вариант
- или локальный editor/buffer для compose before send

### 8.3 Projection ops на JSONata

Сейчас JSONata подключена только как тестовый eval over message projection.

Нужно:
- начать использовать JSONata как generic projection/transform op
- не только как отладочную команду

### 8.4 Template-driven path resolution

Нужно аккуратно свести вместе:
- template-relative structure
- canonical field table
- runtime aliases
- projections

Пока это зафиксировано концептуально, но ещё не собрано в один исполняемый слой.

### 8.5 Unified runtime model without FS assumptions

Сейчас часть кода ещё pchat/FS-oriented.

Нужно перейти к явной модели:
- runtime first
- storage second

То есть:
- сначала понять exec + node + projection + template + field layer
- потом уже аккуратно обвязать FS

## 9. Практический план дальше

### Этап A. Нормализовать JSONata transport

Сделать shell-friendly raw expression mode:
- вариант `--` raw tail
- или multiline compose buffer

Цель:
- без боли передавать выражения с кавычками, скобками и вложенными calls

### Этап B. Использовать JSONata не только для debug

Следующий практический шаг:
- поднять один generic transform op на JSONata
- принимать `input + expr + bindings`
- возвращать не только result, но и projection-ready data

### Этап C. Exec message как полноценный runtime object

Нужно выделить устойчивую форму `exec_item`:
- `_meta`
- `_data.input`
- `_data.exec`
- `_data.output`
- derived projections

Это должно стать базовым runtime object для L0 messages.

### Этап D. Input/reply messages как projections

Важно дожать идею:
- input message projection
- reply message projection
- оба derived из exec_item
- оба могут жить в local `List(message)`

### Этап E. Type/template aggregated projections

Нужно отдельно вернуться к идее:
- `msg` без индекса как template/type root
- `msg_1`, `msg_2` как instances
- type root агрегирует local instances

Это даст:
- query by type
- pattern matching
- удобную template-level валидацию

### Этап F. Unified alias/link layer

Нужно решить финальную форму для:
- runtime aliases
- links
- symlink-like projections
- local path overrides

Сейчас это частично представлено через `flat_store + views`, но это только стартовый слой.

## 10. Неприятные места / риски

### 10.1 Не смешать truth и snapshot

Главный риск:
- снова незаметно скатиться в mutable `_meta/_data` как в truth

Этого делать нельзя.

Они допустимы как:
- snapshot
- cache
- checkpoint
- materialized view

Но не как L0 truth.

### 10.2 Не разрастить сервер хардкодом

JSONata и runtime projections должны уменьшать хардкод, а не увеличивать его.

Если каждую новую transform-идею добавлять в `server.py` руками, архитектура снова расползётся.

### 10.3 Не смешать storage shape и runtime shape

Сейчас это особенно важно.

На текущем этапе лучше мыслить так:
- runtime = главное
- FS/storage = потом

Иначе можно снова начать решать storage-проблемы раньше, чем согласована runtime-модель.

## 11. Текущая короткая формулировка состояния

Сейчас мы находимся в точке, где:
- immutable exec log уже признан главным truth
- field/projection model уже сформулирована
- message projection flat store уже существует в коде
- JSONata уже подключена и может читать projection runtime data
- но полноценный generic runtime executor поверх этого ещё не собран

То есть база уже есть.
Следующий настоящий шаг — не новый UI и не новый storage, а приведение exec/projection/JSONata к одному исполняемому runtime-контуру.

## 12. Notes: выводы из обсуждений

Ниже не история диалога, а короткие выводы, которые стоит считать рабочими решениями до дальнейшего пересмотра.

### 12.1 Runtime containers лучше хранить как atomic-dsl rows

Промежуточный вывод:
- runtime container state лучше хранить не как произвольный `state.json`
- а как канонический flat rows-слой

Практическая форма:
- `rows`
- `patch_log`
- optional `manifest`

А всё остальное производно:
- `state.json = rows_to_json(rows)`
- `resolved.json = resolve(rows, manifest)`
- `tree/cards/table` = другие serializers

Причина:
- с rows удобнее делать patch по path
- rows удобнее отлаживать
- rows естественно ложатся на atomic-dsl
- не нужно писать новый большой snapshot на каждую мутацию

Итог:
- `state.json` не должен быть truth
- truth контейнера на runtime-уровне лучше мыслить как `rows + patch_log`

### 12.2 Update Containers должны быть runtime-операциями

Из этого следует:
- update container не должен означать “пересобрать и перезаписать большой json”
- update container должен означать “применить patch к rows”

Правильный контур:
1. есть `rows`
2. приходит patch
3. patch меняет rows
4. derived views пересчитываются по запросу или лениво

Итог:
- update containers становятся runtime-операциями
- rebuild containers по смыслу превращается в `re-resolve containers`

### 12.3 Алиасы и representation лучше сводить к field-to-field links

Вывод по alias-слою:
- representation aliases лучше не держать как отдельную магию поверх values
- правильнее сводить их к прямым link-отношениям `field -> field`

Но не сразу.

Нужен промежуточный слой:
- временные runtime bindings
- временные relative paths
- временные projection aliases

После стабилизации transform:
- bindings схлопываются в прямые field-to-field links

Итог:
- authoring остаётся гибким
- runtime становится чище
- конечная модель не зависит от текстовых path-подстановок на каждом шаге

### 12.4 Полезен shadow runtime object для навигации и sync

Отдельный вывод:
- нужен shadow-слой, который не является truth, но помогает runtime navigation и sync

Удобная рабочая форма:
- вместо “только value”
- держать промежуточный объект вида `path -> [hash, path, value]`

Потенциальное развитие:
- хранить для runtime object списки atomic paths, которые ведут к одному и тому же значению
- тогда patch по одному объекту можно отражать на остальные связанные runtime representations
- без повторного patch ко всем alias-объектам

То есть:
- source-of-truth не меняется
- runtime sync делается по map linked paths

### 12.5 Shadow-JSON / shadow-atomic слой полезен как middleware

Обсуждение свелось к такому выводу:
- нужен shadow middleware layer между canonical fields и пользовательскими representations

Его задача:
- навигация
- runtime alias resolution
- переключение views
- дешёвый sync связанных representations

Это может быть:
- shadow-json
- или лучше shadow-atomic runtime object

Важно:
- это middleware
- не новый truth layer

### 12.6 JSONata выглядит подходящим transform engine

Промежуточный вывод по JSONata:
- она очень хорошо совпадает с задачами runtime DSL
- особенно для select / map / filter / reshape / object projection / bindings

Практический вывод:
- JSONata стоит использовать как embedded transform engine
- не как замену всей архитектуры
- а как generic transform/query слой внутри exec/runtime

Сильные стороны:
- compact syntax
- closures and bindings
- higher-order functions
- registerable lambdas
- object/list ops
- joins

### 12.7 Shell-like интерфейс для JSONata правильнее, чем отдельный endpoint

Согласованный вывод:
- не нужен отдельный “сырой JSONata endpoint”
- правильнее оставаться в exec/shell-like модели

Но:
- parser должен уметь безопасно пропускать raw expression

Значит дальше нужен:
- raw-tail mode
- multiline compose buffer
- или другой shell-friendly способ передать expression целиком

### 12.8 Runtime-first, storage-second

Отдельно зафиксирован важный приоритет:
- пока проектируем runtime, лучше не мыслить через FS как через главную модель
- FS потом будет обвязкой

Это значит:
- сначала договориться о `exec + rows + projections + aliases + transforms`
- потом уже аккуратно материализовать это в FS

### 12.9 L0/L1/L2 split

На текущий момент рабочий split выглядит так:

- `L0` = immutable exec/messages/patches
- `L1` = rows / linked runtime field layer
- `L2` = resolved serializations, lists, tables, cards, trees

Это сейчас наиболее цельная формулировка того, к чему всё сводится.

### 12.10 Симлинки как physical representation layer

Отдельный важный вывод:
- FS symlink очень хорошо подходит как physical representation для runtime links
- в нашей модели он не обязан быть единственным механизмом link-ов
- но как carrier для проекций он очень удобен

Почему это полезно:
- symlink почти ничего не весит
- выглядит как реальный объект/папка
- с ним можно работать почти как с обычным путём
- relative local-path внутри linked scope читается естественно

То есть:
- physical symlink на FS
- и runtime alias/lambda-link

по смыслу являются аналогами одного и того же механизма:
- один canonical source
- несколько входов в него
- разные локальные пути и имена

Рабочая формулировка:
- FS symlink = physical link representation
- runtime alias/link = programmatic link representation

### 12.11 Template root как source of inherited structure

Ещё один важный вывод:
- template должен быть отдельным source of truth для структуры, а не просто папкой с примерами

В практической форме это выглядит так:
- рядом с `msg_1`, `msg_2`, ... существует `msg`
- `msg` не instance, а template/type root
- instances наследуют от него structure-level rules

Что должно жить на template root:
- field declarations
- relative template paths
- commands
- components
- projection rules
- bind/transform rules
- optional symlinks на допустимые child/template scopes

Итог:
- template root задаёт форму
- instances заполняют data/runtime часть
- патч template root наследуется вниз
- патч child instance не поднимается обратно в template

То есть наследование строго:
- сверху вниз по template
- без обратного протекания

### 12.12 Template patching

Отдельно согласовано правило:
- apply patch к root template object наследуется всеми children
- apply patch к child не меняет template

Это особенно важно для:
- добавления новых полей
- переименования/alias-ов
- внедрения новых local representations
- расширения bind/transform rules

Следствие:
- структуру можно перестраивать без переписывания всех instances
- если canonical path resolution зависит от template relative path, instances продолжают жить, а navigation меняется через template layer

### 12.13 Template и aggregated projections by type

Template root полезен не только как schema source, но и как aggregated type-projection.

Например:
- `msg` может агрегировать локальные `msg_*`
- это даёт type-level query surface
- это упрощает автокомплит, валидацию и pattern matching

То есть `msg` можно мыслить одновременно как:
- template root
- command surface
- type index
- aggregate projection for local instances

Это как раз та прослойка, которой не хватало между:
- голыми local nodes
- и готовыми runtime views

### 12.14 Симлинки на templates

Отдельная полезная идея:
- симлинки можно класть не только на data nodes, но и на templates

Например:
- рядом с нодой держать symlink на её template root
- в контейнере держать symlink-и на templates разрешённых child types

Это даёт:
- cheap inheritance surface
- явную type visibility на FS
- возможность быстро определить допустимые children
- основу для будущей “почти статической типизации” контейнеров

Практическая польза:
- list/cards container может знать допустимые child templates
- по template roots можно делать autocomplete и validation
- template traversal становится selector-слоем сам по себе

### 12.15 FS-level and runtime-level links should coexist

Не нужно противопоставлять:
- реальные FS symlink-и
- и runtime lambda/alias links

Правильнее считать так:
- FS symlink = хороший physical carrier
- runtime link = логика поверх него

Где physical symlink невозможен или неудобен:
- остаётся runtime link

Где symlink удобен:
- он делает representation прозрачнее

Итог:
- один и тот же link semantics может иметь две формы
- physical on FS
- logical in runtime
