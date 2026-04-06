# Architecture Next: CMD-обёртки, Console Scopes, Message-based L0

## Контекст

Pipeline Chat переписан с последовательных HTTP (5-12 запросов на действие) на batch + view (2 запроса). Следующий шаг: generic console scopes, CMD как универсальная обёртка, message-based L0.

## 1. CMD как универсальная обёртка

CMD — не просто консольная команда, а **контейнер-обёртка** на всех уровнях:

- **Валидатор** — проверяет данные до патча, не пропускает мусор
- **Контекст** — несёт автора, selected объект, любые кастомные поля через точечную нотацию (`.cmd`, `.name`, `.emoji` — any)
- **Логика** — toggle, increment, slot allocation — внутри обёртки
- **Composable** — cmd передаёт в следующую cmd, pipeline из одноатомных шагов
- **Лямбда** — `cmd x -> applyCommand(x)`, разворачивается при вызове

### cmd объект

```javascript
{ cmd: 'react', target: 'msg_1', emoji: '👍', user: 'alice', _ts: Date.now() }
```

- `cmd.cmd` — первое слово ввода (opcode)
- Остальные поля — произвольные, заполняются парсером или контекстом
- После `select` cmd наследует поля выбранного объекта
- `_raw` — оригинальная строка для лога
- `_ctx` — контекст (selected component, scope)

### Пример: reactions через CMD

```
cmd { cmd: 'react', target: 'msg_1', emoji: '👍' }
```

CMD-обёртка для reactions:
1. Принимает emoji-объект
2. Ищет слот с таким же emoji в контейнере
3. Нашла: передаёт в sub-cmd с автором → та проверяет: тот же автор = delete, другой = counter++
4. Клиентская часть знает автора → рисует рамочку для `self`

### Расширение через monkey-patch

```javascript
const _origApplyCommand = applyCommand;
applyCommand = function(cmd) {
  if (cmd.cmd === 'save') { saveToServer(); return; }
  _origApplyCommand(cmd);
};
```

Каждый модуль добавляет свои команды, не трогая ядро. Middleware chain.

## 2. Console Scopes (не синглтон)

Текущая проблема: `self.cwd` — один на весь сервер. Два клиента / агент + пользователь = гонки.

### Решение: именованные scopes

```python
class ConsoleScope:
    """Один виртуальный терминал: свой cwd, свой лог, свой redo."""
    def __init__(self, name, root, redo=True):
        self.name = name       # "chat", "agent-1", "panel-sidebar"
        self.cwd = root
        self.log = []          # cmd history
        self.redo = redo       # enable undo/redo
        self.redo_stack = []
```

- Workspace хранит `dict[str, ConsoleScope]`, создаёт по запросу
- Клиент передаёт `scope: "chat"` в каждом запросе
- Один scope = один cwd = один лог
- Параллельных терминалов — сколько угодно
- Панельки = обёрточные консольки со своим именем
- Агенту — свой scope, пользователю — свой

### Пользовательский scope = синглтон (ок)

Для интерактивного терминала пользователя — синглтон правильно. Для панельных обёрток и агентов — отдельные.

## 3. Батчинг через CMD-лямбды

Вместо N последовательных HTTP: клиент собирает CMD-лямбды локально, отправляет батчем.

```javascript
// Клиент собирает
const batch = [
  { cmd: 'select', path: 'pchat' },
  { cmd: 'select', path: 'channels' },
  { cmd: 'post', text: 'hello' },
];
// Один HTTP запрос
await api('POST', '/api/pchat/batch', { cmds: batch, scope: 'chat' });
```

Можно не просто склеивать, а сериализовать: передавать метку/количество, чтобы сервер отдавал только актуальное.

## 4. Панельки как контейнеры

Не "дай мне список channels + список messages", а **"заполни контейнер Chat"**.

- Панель = виртуальный контейнер, знает свой размер (сколько элементов вмещает)
- Один запрос: "у меня пусто, скинь Chat" — сервер отдаёт channels + messages для активного канала
- Количество диктует контейнер (viewport), не клиент вручную

## 5. {Type}{ID} tuples вместо полного JSON

Большинство случаев не нужен полный JSON — достаточно tuple:

```
"channel323"  →  type=channel, id=323
"msg_1"       →  type=msg, id=1
```

Клиенту — одним полем `{Type}{ID}`. Чиселку от строки отделить по маске быстрее, чем два поля JSON парсить.

Полную дату запрашивать только когда реально нужна. Остальное — patch или список tuples.

## 6. Init на загрузке страницы

**Сделано:**
- localStorage cache → мгновенный рендер из кэша
- Один POST `/api/pchat/view` → свежие данные с сервера
- Session start = `cmd_session` (user joined)

**Доработать:**
- Session start должен быть видимым сообщением "[user joined]" в чате
- FS layer: проверять файловую систему пока сервер не ответил
- Авторизация потом, сейчас — аутентификация через username

## 7. Патчи как сообщения

Всё — message в L0 стеке:

```
L0: message stack
  └─ container (channel/node/slot)
       └─ cmd messages (FIFO)
            └─ каждая cmd = lambda + context + payload
                 └─ внутри: patch / sub-cmd / bind trigger
```

- Patch = cmd-сообщение с `{target: path, value, reason}`
- Edit message = `patch(msg.content, newText)`
- Reaction = `patch(msg.reactions, toggle(emoji, user))`
- Delete = `patch(msg, tombstone)`
- Всё через один `applyCommand` → в лог → бинды подхватывают

Concurrency: FIFO per container, нет локов. Undo = pop. Replay = прочитать стек.

Optimistic updates: клиент знает логику cmd → apply локально сразу → серверный ответ = подтверждение или корректировка.

## 8. Бинды как контракты

```
workers.card <- each data.worker_list as item
workers.card.status <- item.url | probe_status :: ok=g fail=r ?=y
```

- Бинд = декларация факта: "это поле = эта проекция данных"
- Pull-based reactivity: при рендере берёт текущее значение
- `each` = итератор + template instantiation + data binding для детей
- `|` = pipe через трансформ
- `::` = color map прямо в bind expression
- Двусторонние: `n_6.input` (object→field) и `input.n_6` (field→object)

## 9. Двумерные таблицы для всего

`flatten_json` → плоская таблица `[{field, type, value, path, group}]` → inline edit → `applyPatch(path, newVal)` → `rows_to_json` обратно.

Максимальная плотность данных на 2D экране. Удобно и программно (dot-path адресация), и визуально (таблица).

## 10. Node[Slots] рекурсия

Один объект — две роли:
- **Slot** в родительском контейнере (элемент списка)
- **Node** для своих детей (контейнер)

```
Chat (node)
  └─ channels (slots)
       └─ general (slot ↔ node)
            └─ messages (slots)
                 └─ msg_1 (slot ↔ node)
                      └─ reactions (slots)
```

Каждый уровень — одна структура. Тип определяет template + бинды.

## Текущее состояние (2026-04-06)

### Сделано в этой сессии:
- Batch endpoint `/api/pchat/batch` — массив команд за один HTTP
- View endpoint `/api/pchat/view` — channels + messages за один запрос
- `cmd_query` — чтение по абсолютному path без мутации cwd
- `cmd_session` — старт сессии
- Клиент: localStorage cache + init из кэша + один fetch
- HTTP запросов на действие: 2 вместо 5-12

### Следующие шаги:
1. Generic ConsoleScope (не синглтон cwd)
2. CMD-обёртки для клиентских панелей
3. {Type}{ID} tuples в responses
4. Session start как видимое сообщение в чате
5. FS layer между localStorage и сервером
6. Параметризация redo per scope
