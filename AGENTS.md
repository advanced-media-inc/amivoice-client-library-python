# AGENTS.md

## What This Repository Is

This is a Python client library for developing speech recognition applications that use the AmiVoice API.
This library makes it easy to use the various features of the AmiVoice API.

## Environment

This project uses the following environment and tools:

- Python 3.11+
- uv
- pnpm

## Commits

`prek` is used as the pre-commit hook.
Do not include the `--no-verify` option when committing.
If a commit fails, fix the lint errors. However, the pre-commit hook may have modified files, so first check the files that caused the commit to fail.

## Commits and PR Titles

Use conventional commit-style messages and PR titles: `type(scope): summary`.
You may add a detailed commit message after a blank line.

Valid types:

- `feat`
- `fix`
- `docs`
- `style`
- `refactor`
- `perf`
- `test`
- `build`
- `ci`
- `chore`
- `revert`

Scopes are optional; use the affected package or area when helpful.

Commit messages may be written in English or Japanese.

## AmiVoice API Information

Refer to the official documentation for information about the AmiVoice API. Obtain any necessary information from the following sources.

- [AmiVoice Cloud Platform Official Website](https://github.com/advanced-media-inc/amivoice-api-client-library#:~:text=AmiVoice%20Cloud%20Platform%20公式サイト)
- [AmiVoice API Manual](https://docs.amivoice.com/amivoice-api/manual/getting-started)

## Do (Recommended Practices)

- Best practices for each language and framework are documented in `.github/instructions/{language}.instructions.md`. Check the applicable file for the type of file you are working on and follow its instructions.
- Unless a program is a simple one with fewer than 100 lines, object-oriented design is recommended.
- Follow the single-responsibility principle: each function should focus on one task.

## Don't (Prohibited Practices)

- Do not include credentials, confidential information, or API keys in code. If they are absolutely necessary, read their values from environment variables or use a `.env` file and add it to `.gitignore`.

## Python Development Best Practices

### Python Version

This project uses Python 3.11 or later. You should not use the `__future__` module.
Python 3.11 compatibility must be maintained. Using features deprecated in the latest version is not recommended.
However, programs must run on all Python versions from 3.11 through the latest version.

Unit tests must pass on all Python versions from 3.11 through the latest version.
If feature compatibility between different 3.xx point releases is a concern, check the closest `pyproject.toml`'s `requires-python` field.
This field specifies the minimum supported runtime version.

## Commands

### pnpm

This project manages Node.js tools dedicated to Markdown formatting and CI under `tools/markdown/` and uses `pnpm` as its package manager.
Run all commands from the repository root with `--dir tools/markdown` (there is no need to `cd` into `tools/markdown`).

- `pnpm --dir tools/markdown install --frozen-lockfile`: Install dependencies. Do not use `pnpm install` by default.
- `pnpm --dir tools/markdown exec <package-name>`: Run the command specified by package name.

### uv

This project uses `uv` for Python virtual environments.

- `uv init`: Initialize a uv environment. Do not run this if `pyproject.toml` already exists.
- `uv add <package-name>`: Install the package specified by package name and add it to `pyproject.toml`.
- `uv sync`: Install dependencies based on `pyproject.toml`.
- `uv run <python-file-name>`: Run a command in the uv environment.

Other commands may be used as needed.
However, generally do not use `uv pip` or `uv python`.
