# リリース手順

この文書は `amivoice-api-client`のバージョンアップとリリース手順をまとめたものです。

## 1. ファイルの更新

`pyproject.toml` の `[project].version` を更新し、`uv lock` と `uv lock --check` を実行して `uv.lock` を更新・確認します。

公開バージョンは `X.Y.Z` 形式（PEP 440）で選定します。
また、未公開の新しいバージョンを出す場合は、本番 PyPI 上に公開されている最新の正式バージョンよりも大きいバージョンである必要があります。以下では `1.0.0` を例にします。

Pull Request の CI がすべて成功することを確認し、レビューを経て `main` ブランチへマージします。

## 2. TestPyPI での事前公開と検証

本番 PyPI へ公開する前に、GitHub リポジトリの「Actions」タブから `Publish TestPyPI`（`.github/workflows/publish-testpypi.yml`）を選択し、`Branch: main` を指定して手動実行します。

実行後、`Smoke test TestPyPI package` を含む全ジョブが成功したことを確認します。

## 3. 本番 PyPI への公開と GitHub Release の作成

TestPyPI での検証が完了したら、GitHub Actions の `Publish PyPI`（`.github/workflows/publish-pypi.yml`）を手動実行します。

> 注意: タグや GitHub Release を事前に手動で作成しないでください。また、呼び出し先の `Finalize GitHub Release`（`.github/workflows/finalize-github-release.yml`）は `workflow_call` 専用の再利用ワークフローであり、単独で手動実行するものではありません。

1. GitHub リポジトリの「Actions」タブから「Publish PyPI」を選択する
2. 「Run workflow」を開き、以下を指定して実行する
   - Use workflow from: `Branch: main`
   - `Formal X.Y.Z version to publish`（入力 `version`）: `pyproject.toml` の `[project].version` と一致する正式バージョン（例: `1.0.0`、`v` は付けない）
3. 全ジョブが成功し、本番 PyPI への公開とタグ `X.Y.Z`・GitHub Release（`AmiVoice API Client X.Y.Z`）の自動作成が完了したことを確認する
