<!-- Managed by /coding-rules:apply — do not edit rule blocks by hand -->
<!-- codex: enabled -->

# Version
3

Increase this version number whenever this rule file changes.

# Common Rules (All Languages)

These rules apply to all projects, regardless of language. Language-specific rules live in the
corresponding `*_RULES.md` files.

---

## Keep CODING_RULES.md in Sync

When working on a project, copy all relevant rules into the project's `CODING_RULES.md` file
(project root). The project's `CLAUDE.md` carries only a small versioned pointer block that
mandates reading `CODING_RULES.md` before code work — never the full rules, and never an
`@import` of `CODING_RULES.md` (imports auto-expand into context every turn).

- Always include all rules from `COMMON_RULES.md` and `AI_RULES.md`
- Also include applicable language-specific, project-type, and supplemental rule files
  (see `PROJECT_TYPES.md` for the project-type overview)
- Include optional addon rule files only when the user has opted in to that addon
- If applicability is unclear, ask the user which rules to include
- Include each source file's `# Version` block with its copied rules
- If `CODING_RULES.md` already exists, compare each source file's version with the corresponding
  copied rule block and update only stale or unversioned blocks, keeping the result deduplicated
- If `CLAUDE.md` contains inlined rule blocks or coding-rule `@import` lines from an earlier run,
  migrate that content into `CODING_RULES.md` and leave only the pointer block in `CLAUDE.md`

---

## Use Objects for Related Values

When multiple related values must be passed between classes or methods, bundle them into a
dedicated object (e.g., DTO/Settings/Config) instead of passing many parameters. This improves
readability, reduces call-site churn, and makes changes safer.

---

## No Bag-of-Keys Returns at Module Boundaries

When a public method on a manager/repository/service returns data that crosses a module
boundary, the return type must be a typed object (DTO, value object, or domain model) — never
a raw associative array indexed by string keys. Plain `array` returns silently swallow shape
bugs: a missing key reads as `null`, a list-vs-single mix-up reads as "no data", and renames
go undetected by static analysis.

- **Anti-pattern.** `getSettingsValue(...)` returns `array|null`; callers do `$result['value']`,
  `$result['type']`. A consumer mis-indexes `$result[0]['value']` after a refactor; nothing
  flags the change. The function silently returns `null` and downstream defaults take over.
- **Correct pattern.** Return a class — `getSettingsElement(...): ?SettingsElement`. The class
  exposes `getValue()`, `getType()`, `exists()`. Typed, autocompleted, statically checked;
  renames propagate via the IDE.
- **Lists vs single must be obvious from the type and the name.** `getThing(): ?Thing`
  (zero or one) vs `getThings(): ThingList` or `iterable<Thing>`. Never overload the same
  return type to mean both.
- **Distinguish absent from empty.** `null` from a lookup means "not found"; an empty
  collection means "found, but had nothing". A typed return makes this contract explicit;
  a bag-of-keys array hides it.
- **JSON-decoded blobs are arrays too.** The rule applies equally to `json_decode($column, true)`
  results that cross a module boundary — wrap them in a value object before they leave the
  layer that owns the schema.
- **Internal helpers may stay arrays.** This rule targets *public* API on managers and the
  boundary where a domain abstraction starts. Pure-private array juggling inside a single
  method is fine.

---

## Reuse Existing Models Before Inventing Array Shapes

Before designing a new return type or DTO, search the codebase for an existing domain class
that already owns the same data. Most "should this be a DTO?" decisions are actually
"is there already a `Contest` / `User` / `Order` class that should absorb this method?"

- Grep for the table name, the primary key, and the most distinctive column.
- If a model already exists with a constructor that accepts the row shape, use it — don't
  invent a parallel array shape that mirrors the same columns.
- Adding a `getXxxObject()` alongside a legacy `getXxxData()` is acceptable as a migration
  step; keep both only until consumers are migrated, then delete the array-returning version.

---

## Tests Pin the Shape Before the Refactor

When converting a bag-of-keys return to a typed object, write a **characterization test
first** that locks the current behavior using the existing API, run it green against the
unrefactored code, and then refactor. The same test (or a renamed-but-equivalent one) must
remain green afterward.

This converts "I think the new object preserves behavior" into "the test proves it." Pair
with the "Test-Driven Development" rule below — characterization tests are TDD applied to
refactors instead of new features.

---

## Test-Driven Development for Features and Bug Fixes

Follow TDD when implementing features or fixing bugs:

1. Write tests first
2. Run the tests and confirm they fail
3. Implement the change or fix
4. Run the tests again and confirm they pass

---

## Integration Tests

Every project must include integration tests in addition to unit tests. Integration tests verify that
components work correctly together and catch issues that unit tests alone cannot detect.

---

## Test Runner Scripts

Every project must provide the following batch files in the `tools/` directory:

- `tools/run_tests.bat` — runs unit tests
- `tools/run_integration_tests.bat` — runs integration tests

These scripts ensure a consistent way to execute tests across environments.

---

## Prefer Type-Safe Values

Use strong, explicit types instead of loosely typed or stringly typed values (e.g., typed DTOs,
enums, generics, typed settings). This ensures mistakes are caught at compile time or by tests
early in development.

---

## String Constants

Centralize string constants in a dedicated module/class. Do not scatter raw strings across
the codebase. Use language-appropriate patterns for constants and reuse them consistently.

---

## Reusable Tooling

Before building project-specific infrastructure scripts (audits, codemods,
build helpers, lint checks, etc.) for a project, check the matching
language's `*_setup_files/` folder under this `coding-rules` repo for an
existing equivalent. If found, copy or reference it. If not:

1. Build the script in the project and prove it on real data.
2. Copy the script into the right `*_setup_files/tools/` folder.
3. Document it in that language's `*_RULES.md` so the next project picks
   it up automatically.

This keeps cross-project tooling consistent and prevents the same script
from being re-invented in every new project.

---

## README.md is Mandatory

Every project must have a `README.md` file in the root directory. It should include:

- Project name and description
- Installation/setup instructions
- Usage examples
- Dependencies and requirements

---

## Don't Repeat Yourself (DRY)

Avoid code duplication. If the same logic appears in multiple places, extract it into a
reusable function, class, module, or utility.

- Duplicate code is harder to maintain and leads to bugs
- Extract shared logic into helpers or base abstractions
- Use constants for repeated values

---

## Derive, Don't Duplicate — One Value Owns the Derivation

When one value strictly determines another, pass only the determinant and derive the rest —
never thread both side-by-side through call sites, constructors, and events. Two co-varying
parameters are a functional dependency in disguise; passing both lets them drift into illegal
combinations.

- **Anti-pattern.** `createLog(ActionCategory $cat, ActionType $type)` threaded through ~10
  sites. Nothing stops a caller passing `category: email, type: lead.created`.
- **Correct pattern.** The richer type owns the relationship: `ActionType::category()` returns
  its `ActionCategory` via a single exhaustive `match`. Call sites pass only `ActionType`;
  category is always derived, so a mismatch is unconstructable.
- **Apply when** one value *determines* the other (a true functional dependency).
- **Don't apply when** the relationship is many-to-many or genuinely independent — forcing a
  derivation that doesn't exist couples things that should stay separate.
- **Keep derivation cheap and pure** — a getter/match, no DB or IO behind a call that looks free.
- **Keep the mapping exhaustive** (enum + exhaustive match) so a new case cannot silently skip
  its derived value.

This is Single Source of Truth applied to parameters, and a form of "make illegal states
unrepresentable." Pairs with "Prefer Type-Safe Values" and "Self-Describing Classes".

---

## Keep It Simple (KISS)

Prefer the simplest solution that actually works. Complicated logic for a simple result must be
kept to a minimum — a future maintainer (or you, at 3am) has to understand it.

- **YAGNI.** Don't build for a need that isn't here yet: no interface with a single
  implementation, no factory for one product, no config for a value that never changes.
- **Boring over clever.** Clever is what someone decodes later. The obvious solution wins.
- **Deletion over addition.** The shortest working change is usually the right one.
- Pairs with "Don't Repeat Yourself" and "No God Classes" — simplicity is what those rules
  are protecting.

---

## Confirm Dependency Versions

Before adding any new package or library, confirm the version with the user to ensure we use
up-to-date dependencies.

- Do not assume which version to use
- Ask the user to verify the latest stable version
- Avoid outdated packages that may have security vulnerabilities or missing features

---

## Error Handling & Logging Strategy

Every project must have a centralized error handler rather than ad-hoc try/catch blocks scattered
throughout the codebase.

- Use structured logging (not `print`/`console.log`/`echo`)
- Log at appropriate levels: debug, info, warning, error
- Include context in log messages (module name, operation, relevant IDs)

---

## Centralized Logger — Single Off Switch

Route all logging through one dedicated logger class/module. Never call the language's
built-in output directly for logging (`print`, `console.log`, `echo`, `Debug.Log`,
`System.out`). Code calls the project logger; the project logger wraps the underlying sink.

- **One toggle.** Because every log goes through one place, logging can be turned off,
  level-filtered, or redirected (file, console, remote) from a single config flag — without
  touching call sites. Example: a `logEnabled` / `logLevel` setting the logger checks once.
- **Levels live in the logger.** Callers pass a level (debug/info/warning/error); the logger
  decides what is emitted based on central config. Callers never branch on "should I log?".
- **Wrap, don't scatter.** Built-in calls (`print`, framework loggers, `Debug.Log`) appear
  in exactly one file — the logger implementation. Everywhere else imports the logger.
- **Language specifics** still apply (e.g. Unity `[Conditional]` stripping, Flutter `logger`
  package, Python `logging`) — but they are configured inside the central logger, not at
  call sites.

The logger's name is fixed per language so it is the same known type in every project (see each
`*_RULES.md` for details):

| Language      | Class / export     | File                |
|---------------|--------------------|---------------------|
| Python        | `AppLogger`        | `app_logger.py`     |
| PHP           | `Logger`           | `Logger.php`        |
| Dart/Flutter  | `AppLogger`        | `app_logger.dart`   |
| Kotlin        | `AppLogger`        | `AppLogger.kt`      |
| C# (plain)    | `AppLogger`        | `AppLogger.cs`      |
| Unity C#      | `GameLog` (static) | `GameLog.cs`        |
| Svelte/JS/TS  | `logger` (export)  | `logger.ts`         |
| Arduino       | `Log`              | `Log.h` / `Log.cpp` |

---

## Input Validation at Boundaries

Always validate data at system boundaries — API inputs, user input, file uploads, external service
responses.

- Never trust external data; validate before processing
- Use language-appropriate validation libraries (e.g., Pydantic, Zod, FluentValidation)
- Fail fast with clear error messages when validation fails

---

## Maximum File Length — 300 Lines

Split files when they exceed 300 lines to keep code navigable during fast iteration.

- Extract classes, functions, or components into separate modules
- Group related extractions logically (by domain, not by type)
- Exceptions: generated files, configuration files, test files with many similar cases

---

## Naming Conventions

Be consistent within a project. Follow these defaults unless the language or framework dictates
otherwise:

- Files: `snake_case` (or language convention, e.g., `PascalCase` for C# classes)
- Classes: `PascalCase`
- Functions/methods: language convention (`snake_case` for Python/PHP, `camelCase` for Dart/JS/C#)
- Constants: `UPPER_SNAKE_CASE`
- Variables: language convention (`snake_case` for Python/PHP, `camelCase` for Dart/JS/C#)

---

## Comments Explain Why, Not What

Comment intent and non-obvious reasoning — not a restatement of the code. Good names carry the
*what*; comments carry the *why*.

- **Anti-pattern.** `i++ // increment i`. Redundant comments add noise and rot the moment the
  code changes.
- **Correct pattern.** Document *why* a workaround exists, why a non-obvious algorithm was
  chosen, or a constraint that isn't visible locally (`// API rejects batches > 500`).
- Prefer self-documenting code (clear names, small functions) over a comment that compensates
  for unclear code — see "Naming Conventions" and "Keep It Simple".
- Document the purpose of each module/class at its top.
- Keep comments in sync with the code; delete stale ones rather than letting them mislead.

---

## Security Baseline

Every project must follow these minimum security practices:

- Never commit secrets (`.env`, API keys, credentials, private keys)
- Escape output to prevent XSS/injection attacks
- Use parameterized queries or ORM-provided methods — never concatenate user input into queries
- Validate and sanitize all user input at system boundaries
- Keep dependencies updated to avoid known vulnerabilities

---

## No Hardcoded Environment Values

Never hardcode environment-specific values in code — filesystem paths, hostnames, IP addresses,
ports, base URLs. They differ across machines and environments and make code non-portable.

- **Anti-pattern.** `connect("192.168.1.50:5432")`, `open("C:\\Users\\bob\\data\\out.json")`.
- **Correct pattern.** Read them from the project's central config (the config class each
  `*_RULES.md` already mandates), with a committed `.example` template documenting every key.
- Distinct from the secrets rule above: this is about **portability** (runs anywhere), not
  secrecy. A non-secret hostname still belongs in config, not in code.

---

## No God Classes

A class that handles too many responsibilities becomes fragile, hard to test, and impossible to
reuse. Keep each class focused on a single purpose.

- **Warning signs**: more than 5 public methods, more than 4 constructor dependencies, or methods that span unrelated domains (e.g., a class that validates input, queries the database, and sends emails)
- Split by responsibility: extract collaborators (e.g., a `Validator`, a `Repository`, a `Notifier`) rather than piling logic into one class
- If you struggle to name the class without using "Manager", "Handler", "Service", or "Helper" as a catch-all, it likely does too much
- This complements the 300-line file rule — a short class can still be a god class if it owns too many concerns

---

## Self-Describing Classes

When behavior depends on which fields or properties a class has — such as search, serialization,
display, validation, or auditing — the class itself must declare those fields through a contract
(interface, abstract method, attribute/annotation, or introspection pattern). Never hardcode field
lists in consuming code.

- **Anti-pattern**: A search service contains a hardcoded list of fields to index for each entity;
  adding a new field requires updating every consumer manually
- **Correct pattern**: Each class implements a contract (e.g., `GetSearchableFields()`,
  `GetDisplayColumns()`) that returns its own relevant fields, so adding a field in one place
  automatically propagates everywhere
- This applies to any cross-cutting concern that operates over class fields: search, filtering,
  export, form generation, diffing, logging, etc.
- Combine with compile-time checks where the language supports them (e.g., sealed interfaces,
  exhaustive matching) to ensure new fields cannot be silently ignored

---

## Inject Collaborators, Don't Fold Dependencies In

Composition reuse comes in two shapes, and they differ sharply in how much coupling they add to
the reusing class. **Folding** a helper into a class (mixin, trait, multiple inheritance, copy-in
include) merges *all of the helper's own dependencies* into that class — reuse five such helpers
and every one of their imports is now the host's coupling. **Injecting** a collaborator adds a
single dependency: the collaborator, which is built once and shared as a hub.

Prefer injected collaborators. Reserve fold-in reuse for helpers that are stateless and carry no
dependencies of their own.

- **Anti-pattern**: A controller reuses five behavior mixins/traits; each brings its own service,
  DTO, and constant imports, so the controller transitively depends on a few dozen things and is
  hard to test in isolation.
- **Correct pattern**: Extract that behavior into a collaborator object injected via the
  constructor. The controller depends on the collaborator; the collaborator is reused across many
  controllers as a shared, well-tested hub.

### Inject services; never instantiate one inside a method

Constructing a service with `new` (or the language equivalent) inside a method hides the
dependency from the class's public contract and makes it impossible to substitute in a test. Pass
collaborators in through the constructor.

- **Anti-pattern**: A method does `helper = new EmailPreparer(); helper.prepare(...)`. Nothing in
  the class signature reveals the dependency, and no test can replace it.
- **Correct pattern**: Inject `EmailPreparer` once; the method calls the injected instance.

### Collapse config-callback swarms into one value object

When a base class pulls its configuration from the subclass through many small overridable getters
that the subclass fills in one-line-each, each getter is a separate touch-point and the wiring is
spread across dozens of methods. Bundle the related values into a single config object built once
and handed to the base (see **Use Objects for Related Values**). This also keeps such classes off
the wrong side of **No God Classes**.

- **Anti-pattern**: A subclass implements `getSendEndpoint()`, `getSendSuccessKey()`,
  `getSendFailureRedirect()`, and a dozen more one-line getters, each naming one constant.
- **Correct pattern**: The subclass builds one `SendConfig` value object once; the base reads its
  fields.

---

# Version
8

Increase this version number whenever this rule file changes.

# AI Workflow Rules (All Languages)

See `COMMON_RULES.md` for rules that apply to all languages.

Unlike the per-language `*_RULES.md` files, these rules are **language-independent** and
**always apply**. They are not subject to the "some rules may not apply to this project"
filtering — include them in every project's `CODING_RULES.md`.

These rules define the end-to-end workflow an AI agent must follow when planning and
implementing changes. Each step is an existing skill referenced by its slash name; run the
skill rather than reimplementing its behavior.

---

## Codex toggle

Some of the workflow steps below can be delegated to the Codex CLI. Whether a
project uses Codex is controlled by a marker near the top of `CODING_RULES.md`:

- `<!-- codex: enabled -->` — run the `codex exec` commands below.
- `<!-- codex: disabled -->` or no marker — do NOT run Codex; perform the same
  checks yourself via the listed fallback skills.

The marker is managed by `/coding-rules:codex on|off|status` (or set during
`/coding-rules:apply`). Do not flip it yourself without the user asking.

## Feature / Change Workflow

After a plan is proposed and the user approves it, follow this chain. The DRY
gate is a precondition for implementing — not just an earlier step.

The approved plan must first exist as an explicit Markdown file. Pass that same
path to both plan-DRY commands.

```
plan approved

plan DRY check
  codex enabled:
    codex exec --dangerously-bypass-approvals-and-sandbox "FULL PATH TO PLAN - Can you check the plan for DRY opportunities and if you find any, apply them to the original plan file. Only edit the plan file — do NOT modify any source code or implement the plan. Always add a summary at the end called SUMMARY DRY — if you made changes, describe what and why; if you found nothing, write 'No DRY opportunities found.'"
  codex disabled:
    /plan:dry <plan-file>

plan convention check
  codex enabled:
    codex exec --dangerously-bypass-approvals-and-sandbox "FULL PATH TO PLAN $convention-check - If you want to make any changes, apply them to the original plan file. Only edit the plan file — do NOT modify any source code or implement the plan. Always add a summary at the end called SUMMARY CONVENTION CHECK — if you made changes, describe what and why; if you found nothing, write 'No convention issues found.'"
  codex disabled:
    /convention:check — apply findings to the plan file

/plan:dry-checked    reload the DRY and convention adjusted plan

restate Definition-of-Done aloud

implement
  While implementing, keep the list of every file you created or modified in THIS
  session — you know it from your own edits; do NOT derive it from git (other
  sessions may have concurrent uncommitted changes). After implementing, write the
  list (one path per line) to a changed-files file next to the plan, named after it:
  <plan-file-path-without-.md>-changed-files.md
  (e.g. claude-plans/my-feature-changed-files.md). The plan file is unique per
  session, so concurrent sessions never collide.
  Include only source-code files. Exclude documentation and other non-code
  files (`.md`, plain-text docs, the plan file itself) — the DRY audit only
  looks at code.

post-implementation DRY audit — scope is ONLY the changed-files file above
  codex enabled:
    codex exec --dangerously-bypass-approvals-and-sandbox "Read FULL PATH TO CHANGED-FILES FILE and check ONLY the files listed there for DRY opportunities. Do not use git status or git diff to widen the scope — other sessions may have concurrent uncommitted changes. Do NOT modify any code. Write your suggestions to claude-plans/post-implementation-check.md, overwriting the file if it already exists. Include for each finding the affected files and a short rationale. Always write the file, even if you found nothing — in that case write a SUMMARY block stating 'No DRY opportunities found.'"
    then read claude-plans/post-implementation-check.md and discuss/apply the findings with the user
  codex disabled:
    /dry:check <files from the changed-files file, as pathspec>

Post-Feature Verification + Post-Implementation Code Analysis (project-specific, below)

```

### DRY gate (precondition for implementing)

Do not write a single line until ALL are true. Restate this gate aloud at the
moment you start implementing — if you cannot, the gate is not cleared:

- [ ] `/plan:dry <plan-file>` adjusted that file and completed its Ponytail pass.
- [ ] `/plan:dry-checked <plan-file>` reloaded the same adjusted plan.
- [ ] `/convention:check` found the existing utilities/patterns to reuse.

The gate survives the `implement` step: if mid-implementation you add a new
helper, type, or pattern the gate would have caught, stop and re-clear it
before continuing.

### Definition of Done — restate aloud before implementing

Before the first edit, state in chat what "done" means for THIS change:

- [ ] Scope: <one line — what changes, what does not>
- [ ] Reuse: <existing function/component this builds on, with path>
- [ ] DRY gate cleared (above)
- [ ] `/dry:check <session changed-files>` clean (scoped to the changed-files file, never bare)
- [ ] `/verify:after-change` green (tests + analysis)

### Post-implementation DRY audit — paste-in template

Run `/dry:check` scoped to the session's changed-files file, then paste and fill:

```
DRY audit — <change name>
Changed files:     <list from the changed-files file, not git>
Duplication found: <none | describe>
Consolidated into: <shared fn/module + path | n/a>
Convention reused: <name + path>
Verdict:           <clean | needs rework>
```

---

## Bug-Fix Workflow

Bug fixes use a shorter variant (no plan-DRY phase):

```
bugs:fix
  → /verify:after-change
```

---

## Optional Addons

These live in `ai_rules_addons/` and are **not** always-on. Each is opt-in per project — ASK
the user whether they want it before wiring it into that project's `CODING_RULES.md`.

- [`ai_rules_addons/graphify.md`](ai_rules_addons/graphify.md) — graphify knowledge graph:
  scoped + directed AST build, folder layout, gitignore, and the query/refresh rules to paste
  into a project's `CODING_RULES.md`.

---

# Version
1

Increase this version number whenever this rule file changes.

# Python Rules (uv)

See `COMMON_RULES.md` for rules that apply to all languages.

## Template Engine

Keep Python, HTML, CSS, and JS separated.
This means using a template engine.

Use Jinja2:

```bash
uv add jinja2
```

Do not put JS code into templates. Use separate `.js` files.

Example structure:

```
project/
├── app/
├── templates/
└── static/
    ├── css/
    └── js/
```

Example template:

```html
<!-- templates/page.html -->
<!doctype html>
<html>
  <head>
    <link rel="stylesheet" href="/static/css/app.css">
  </head>
  <body>
    <h1>{{ title }}</h1>
    <script src="/static/js/app.js"></script>
  </body>
</html>
```

---

## GUI Framework

For **desktop GUI** applications use **PySide6** (Qt for Python). Always install the
latest version — do not pin an old one:

```bash
uv add pyside6
```

This is separate from the web template engine above: Jinja2 renders web HTML,
PySide6 builds native desktop windows. Pick by app type.

---

## Localization

Use the `python-localization` library for multi-language support:
https://github.com/BenjaminKobjolke/python-localization

### Installation (uv)

#### Option A (recommended): Add as dependency to the project

```bash
uv add "git+https://github.com/BenjaminKobjolke/python-localization.git"
```

#### Option B: Install into the current environment (without adding to project deps)

```bash
uv pip install "git+https://github.com/BenjaminKobjolke/python-localization.git"
```

### Directory Structure

```
project/
├── lang/
│   ├── en.json    # English (default)
│   ├── de.json    # German
│   └── fr.json    # French
├── app/
└── templates/
```

### Translation File Format

Create `lang/en.json` with nested structure:

```json
{
  "nav": {
    "dashboard": "Dashboard",
    "settings": "Settings",
    "logout": "Logout"
  },
  "auth": {
    "login_title": "Login",
    "signin_subtitle": "Sign in to access your dashboard",
    "error": {
      "auth_failed": "Authentication failed. Please try again.",
      "rate_limited": "Too many attempts. Please try again later."
    }
  },
  "flash": {
    "success": {
      "saved": "Changes saved successfully.",
      "deleted": "Item deleted successfully."
    },
    "error": {
      "not_found": "Item not found.",
      "invalid_id": "Invalid ID."
    }
  },
  "common": {
    "cancel": "Cancel",
    "save": "Save",
    "delete": "Delete",
    "edit": "Edit"
  }
}
```

### Python Setup

#### Container Integration

Add a method to your DI container:

```py
# app/container.py
from pathlib import Path

# Adjust import to the real package name of your library
# from python_localization import Localization

class Container:
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self._localization = None

    def get_localization(self):
        if self._localization is None:
            self._localization = Localization(
                driver="json",
                lang_dir=str(self.base_dir / "lang"),
                default_lang="en",
                fallback_lang="en",
            )
        return self._localization
```

#### Controller Helper

Add translation helper to your base controller:

```py
# app/web/base_controller.py
class BaseController:
    def __init__(self, container):
        self.container = container

    def get_localization(self):
        return self.container.get_localization()

    def t(self, key: str, params: dict[str, object] | None = None) -> str:
        return self.get_localization().t(key, params or {})
        # or .translate(...) / .lang(...), depending on your library
```

Usage in controllers:

```py
from app.i18n.keys import TK

# Simple translation
self.add_flash("success", self.t(TK.FLASH_SUCCESS_SAVED))

# With placeholders
self.add_flash("info", self.t("messages.welcome", {":name": user.name}))
```

---

## Jinja2 Integration

### Add the `t()` Function

Where you configure Jinja2:

```py
# app/web/templates.py
from jinja2 import Environment, FileSystemLoader
from app.i18n.keys import TK

def create_env(localization, templates_dir: str) -> Environment:
    env = Environment(loader=FileSystemLoader(templates_dir), autoescape=True)

    def t(key: str, params: dict[str, object] | None = None) -> str:
        return localization.t(key, params or {})

    env.globals["t"] = t
    env.globals["TK"] = TK
    return env
```

### Usage in Templates

Simple translations:

```html
<h1>{{ t(TK.NAV_DASHBOARD) }}</h1>
<button>{{ t(TK.COMMON_SAVE) }}</button>
<a href="/logout">{{ t(TK.NAV_LOGOUT) }}</a>
```

With placeholders (define in JSON as `:placeholder`):

```json
{
  "messages": {
    "welcome": "Hello, :name!",
    "items_count": "You have :count items"
  }
}
```

```html
<p>{{ t("messages.welcome", {":name": user.name}) }}</p>
<p>{{ t("messages.items_count", {":count": items|length}) }}</p>
```

Conditional content:

```html
{% if error == "auth_failed" %}
  {{ t("auth.error.auth_failed") }}
{% elif error == "rate_limited" %}
  {{ t("auth.error.rate_limited") }}
{% endif %}
```

In attributes:

```html
<a href="/back" title="{{ t('common.back') }}">
  <i class="icon-back"></i>
</a>

<button onclick="return confirm('{{ t('confirm.delete') }}')">
  {{ t('common.delete') }}
</button>
```

---

## Translation Key Naming Convention

Use dot notation with logical grouping:

```
section.subsection.key

nav.dashboard            - Navigation items
auth.login_title         - Authentication related
flash.success.saved      - Flash messages by type
flash.error.not_found
form.label.name          - Form labels
form.placeholder.email   - Form placeholders
form.validation.required - Validation messages
common.save              - Reusable UI elements
errors.404.title         - Error pages
```

---

## Translation Keys as Constants

Using raw strings like `t("nav.dashboard")` is error-prone. Create a `TK` class with all keys as constants for IDE autocomplete and refactoring safety.

Create `app/i18n/keys.py`:

```py
# app/i18n/keys.py
class TK:
    # Navigation
    NAV_DASHBOARD = "nav.dashboard"
    NAV_SETTINGS = "nav.settings"
    NAV_LOGOUT = "nav.logout"

    # Auth
    AUTH_LOGIN_TITLE = "auth.login_title"
    AUTH_ERROR_AUTH_FAILED = "auth.error.auth_failed"

    # Flash messages
    FLASH_SUCCESS_SAVED = "flash.success.saved"
    FLASH_ERROR_NOT_FOUND = "flash.error.not_found"

    # Common
    COMMON_CANCEL = "common.cancel"
    COMMON_SAVE = "common.save"
```

Usage in controllers:

```py
from app.i18n.keys import TK
self.add_flash("success", self.t(TK.FLASH_SUCCESS_SAVED))
```

Usage in templates:

```html
{{ t(TK.NAV_DASHBOARD) }}
```

### Benefits

* IDE autocomplete for all translation keys
* Refactoring support
* Easy to find all usages of a key
* Fewer typos / runtime missing-key bugs

---

## Adding New Languages

1. Copy `lang/en.json` to `lang/de.json`
2. Translate all values (keep keys identical)
3. Change language in configuration:

```py
self._localization = Localization(
    driver="json",
    lang_dir=str(self.base_dir / "lang"),
    default_lang="de",
    fallback_lang="en",
)
```

---

## Project Setup Scripts

Copy the setup batch files from the `python_setup_files/` folder bundled with the
coding-rules plugin (next to this rules file).

### install.bat

Initial project setup:

- Checks if `uv` is installed
- Creates virtual environment via `uv sync --all-extras`
- Runs tests to verify setup

### update.bat

Update all dependencies:

- Updates lock file with `uv lock --upgrade`
- Syncs updated dependencies
- Runs linting checks (`ruff`, `mypy`)
- Runs tests to verify compatibility

### tools/run_tests.bat

Run the test suite:

- Runs `pytest tests/ -v` with verbose output
- Shows pass/fail summary
- Projects that split unit/integration point it at `tests/unit`

### tools/run_integration_tests.bat

Run the integration test suite:

- Runs `pytest tests/integration -v`
- Same uv check + summary as run_tests.bat

### Usage

```bash
# First time setup
install.bat

# Run tests
tools\run_tests.bat

# Update dependencies
update.bat
```

---

## Release Workflow

Set up the release system with `/release:setup`. Reusable pieces live in
`python_setup_files/`:

- `tools/release/build_number.py` — self-contained helper: manages the integer in
  `build_version.txt` (project root) and prints the `<version>_<build>` label
  (version from `pyproject.toml`). Actions: `get | increment | decrement | label`.
- `tools/build_get.bat`, `tools/build_increment.bat`, `tools/build_decrement.bat`,
  `tools/version_get.bat` — thin `uv run` wrappers over the helper.
- `CREATE_NEW_RELEASE.template.md` — fill-in-the-blanks for `docs/CREATE_NEW_RELEASE.md`.
- The Python stack recipe read by `/release:create-release-notes` lives in the shared
  `coding-rules/CREATE_RELEASE_NOTES.md` (`## Python / uv` section), not here.

Conventions:

- **Release label** = `<version>_<build>` (e.g. `0.1.0_22`). `version` is semver in
  `pyproject.toml` (bumped by hand); `build` is an integer in `build_version.txt`.
- **Release notes** = `release_notes/<version>_<build>/<locale>.json`. The actual
  text is the `notes` array. Author **only `en.json`**; generate other locales with
  a translation bat (mandatory — never skip).
- **Bundle `release_notes/` into the build** so the in-app view ships with the binary
  (PyInstaller: add to spec `datas` + `copy_metadata(<pkg>)`).
- **In-app view**: load all releases, sort **newest first**, show the latest first
  with Older/Newer navigation, fall back to `en.json` when a locale is missing.

---

# 8 Essential Additional Rules (must-have)

## 1) Use `pyproject.toml` as the single source of truth

No scattered config files. Keep tooling config in `pyproject.toml` (and commit `uv.lock`).

Recommended baseline:

* Python version pinned (e.g. `>=3.11,<3.13`)
* Dependencies managed via `uv add ...`
* Lockfile committed: `uv.lock`

---

## 2) Enforce formatting + linting + type checking in CI

Minimum toolchain:

```bash
uv add --dev ruff mypy
```

Rules:

* Ruff handles lint + formatting (replace black/isort/flake8).
* MyPy (or pyright) for typing.
* CI must run: `ruff check`, `ruff format --check`, `mypy`.

---

## 3) Require type hints on public APIs

Rule of thumb:

* All public functions/classes/methods: typed parameters + return types.
* Use `typing` well: `Sequence`, `Mapping`, `Protocol`, `TypedDict`, `Literal` when helpful.
* Avoid `Any` unless you have a boundary (I/O, third-party libs).

---

## 4) Centralize configuration with environment-driven settings

No “magic values” in code. Use a single settings module with env overrides.

```py
# app/config/settings.py
from dataclasses import dataclass
import os

@dataclass(frozen=True)
class Settings:
    env: str = os.getenv("APP_ENV", "dev")
    debug: bool = os.getenv("DEBUG", "0") == "1"
    default_lang: str = os.getenv("DEFAULT_LANG", "en")
```

Everything reads from `Settings`, not directly from `os.getenv()` scattered around.

---

## 5) Tests are mandatory, fast, and isolated

Use pytest:

```bash
uv add --dev pytest
```

Rules:

* Unit tests for core logic.
* No network in unit tests.
* Use tmp dirs / fixtures; no reliance on developer machine state.
* Run tests in CI on every push.

---

## 6) Database access uses SQLAlchemy ORM

If a database is needed, use SQLAlchemy ORM (not raw SQL or ad-hoc drivers).

---

## 7) Use `spec=` with MagicMock to catch interface mismatches

`MagicMock` without `spec` accepts **any** attribute, even non-existent ones:

```python
# BAD - No interface validation
mock = MagicMock()
mock.nonexistent_attribute = "test"  # Silently works
mock.typo_method()                   # Also works - won't catch bugs!
```

**Always use `spec=ClassName`** to validate against the real interface:

```python
# GOOD - Validates against real class
from unittest.mock import MagicMock
from mylib import EmailMessage

mock = MagicMock(spec=EmailMessage)
mock.nonexistent = "test"  # AttributeError - catches the bug!
```

### Common Pitfall: Mocking Methods vs Attributes

If the real class has a **method**, mock it as a method:

```python
# Real class has: def get_body(self) -> str
class EmailMessage:
    def get_body(self) -> str:
        return "content"

# WRONG - Creates fake attribute that doesn't exist
mock = MagicMock()
mock.body = "test"  # EmailMessage has no .body attribute!

# CORRECT - Mock the actual method
mock = MagicMock(spec=EmailMessage)
mock.get_body.return_value = "test"
```

### Quick Reference

```python
from unittest.mock import MagicMock, patch

# Mock with spec (recommended)
mock_obj = MagicMock(spec=RealClass)

# Mock method return value
mock_obj.method_name.return_value = "value"

# Mock method to raise exception
mock_obj.method_name.side_effect = ValueError("error")

# Mock property (use PropertyMock)
from unittest.mock import PropertyMock
type(mock_obj).prop_name = PropertyMock(return_value="value")

# Patch with spec
with patch("module.ClassName", spec=RealClass) as mock_cls:
    mock_cls.return_value.method.return_value = "value"
```

---

## 8) Required Batch Files

Every project must include these batch files:

* `start.bat` - In the root directory, starts the application
* `tools/run_tests.bat` - Runs the test suite

---

## Async Patterns

Use `asyncio` for I/O-bound tasks (network requests, file I/O, database queries). Avoid blocking
calls (`time.sleep`, synchronous HTTP) in async contexts — they block the entire event loop.

---

## Validation

Use Pydantic for request and data validation at API boundaries. Define models for incoming data
and let Pydantic handle type coercion and error reporting.

---

## Structured Logging

Use `structlog` or the `logging` module with JSON formatters — not `print()`. Configure a
centralized logging setup that all modules use consistently.

Route all logging through one class named **`AppLogger`** (`app_logger.py`) that wraps
`structlog`/`logging`. Feature code calls `AppLogger`, never `logging.getLogger(...)` or
`print()` directly — this gives a single enable/level toggle without touching call sites.

---

## Self-Describing Classes

Implement the common "Self-Describing Classes" rule using a Protocol/ABC or dataclass field
metadata.

### Option A: Protocol with abstract method

```python
from typing import Protocol


class Searchable(Protocol):
    def get_searchable_fields(self) -> list[str]: ...


class Customer:
    def __init__(self, name: str, email: str, phone: str) -> None:
        self.name = name
        self.email = email
        self.phone = phone

    def get_searchable_fields(self) -> list[str]:
        return [self.name, self.email, self.phone]
```

### Option B: Dataclass field metadata

```python
from dataclasses import dataclass, field, fields

SEARCHABLE = "searchable"


@dataclass
class Customer:
    name: str = field(metadata={SEARCHABLE: True})
    email: str = field(metadata={SEARCHABLE: True})
    internal_notes: str = field(default="", metadata={SEARCHABLE: False})


def get_searchable_values(obj: object) -> list[str]:
    return [getattr(obj, f.name) for f in fields(obj) if f.metadata.get(SEARCHABLE)]
```

Prefer the Protocol approach for simple cases. Use dataclass metadata when you need declarative
per-field control without writing boilerplate methods.

---

# Version
5

Increase this version number whenever this rule file changes.

# graphify Knowledge Graph (Optional Addon)

graphify turns a code folder into a queryable knowledge graph — god nodes, communities,
cross-file relationships, fan-in/fan-out. The build is AST-only: no LLM, no API cost. Use it to
orient before grep and to spot god classes. In this project the code lives in `src/`.

### Using the graph

- For codebase questions, run `graphify query "<question>"` first when `graphify-out/graph.json`
  exists. `graphify path "<A>" "<B>"` for relationships; `graphify explain "<concept>"` for a
  focused node. These return a small scoped subgraph vs. reading GRAPH_REPORT.md or raw grep.
- Judge coupling by direction: high **fan-in** + low fan-out (shared base / constants / DTO) is
  healthy; high **fan-out** (>~20 outgoing deps) is god-class risk and a refactor signal.
- Read `graphify-out/GRAPH_REPORT.md` only for broad architecture review, or when
  query/path/explain do not surface enough context.

### Refreshing after a code change

- After a feature or any code change, rebuild via the **directed skill flow**: re-run
  `/graphify src/ --directed`, writing to the project-root `graphify-out/`.
- Do NOT use the bare `graphify update src/` CLI — it has no `--directed` flag and writes a
  full UNDIRECTED graph into `src/graphify-out/` (wrong location), desyncing the live
  graph. If that stray graph appears, delete `src/graphify-out/graph.json` (keep `cache/`).
- Verify after rebuild: `graph.json` has `directed: true` and lives in root `graphify-out/`.
  For a **multi-path merge**, also grep `graph.json` for a node-ID prefix belonging to a second
  scanned dir (e.g. `framework_`) to prove that dir actually landed — `directed: true` passes even
  if one dir silently dropped out of the merge.

### In-tree vendored code — exclude it, scoping alone won't

`--directed`-scoping the build to `src/` keeps external `vendor/`/`node_modules/` out
automatically, but a **committed** third-party library living *inside* `src/` (a bundled
SDK, a copied library folder) is not gitignored, so graphify scans it like first-party code.
Symptom: god-nodes / oversized communities in `GRAPH_REPORT.md` whose class names belong to a
library, not the app (e.g. hundreds of `Facebook*`/`GraphNode*` nodes from an in-tree Facebook
SDK).

Fix once per project:

1. Spot the vendored folder(s) under `src/` (e.g. `application/libs/`). Committed
   **asset/sprite dirs** are the same kind of noise — bundled UI images (jQuery-UI/colorbox
   sprites, e.g. `extensions/backend/assets/images/`) aren't code but graphify still scans them;
   exclude them the same way.
2. Drop a `.graphifyignore` at the scan root (gitignore syntax, honored by default):
   ```
   # Vendored / third-party code + bundled assets — not our architecture, noise in the graph
   libs/
   ```
3. Rebuild. A narrower corpus is a *smaller* graph, which trips the shrink guard (#479) — delete
   the stale `graphify-out/graph.json` first (keep `graphify-out/cache/`), then re-run
   `/graphify src/ --directed`.
4. Verify: grep the vendored library's distinctive class name in the new `graph.json` — it
   should return only first-party code that *uses* the library (e.g. your own `FacebookManager`),
   never the library's own classes.
