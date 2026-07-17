---
name: markdown-format
description: 指定した Markdown ファイルを markdownlint-cli2 と textlint で自動整形するスキル。Markdown の体裁と日本語文章の指摘を、ルールに沿ってまとめて直す。
---

# Markdown Format

このスキルは、指定した Markdown ファイルを `markdownlint-cli2` と `textlint` で整形する。

`markdownlint-cli2` と `textlint` は Markdown 整形・CI専用のツールであり、Python ライブラリ本体とは無関係のため、
`tools/markdown/` 配下に隔離している（リポジトリルートには Node.js 関連ファイルを置かない）。

## 使用時

- Markdown ファイルの作成・修正時
- Markdown の整形を依頼されたときに使う。例えば、「この Markdown を整形して」「textlint と markdownlint で直して」といった依頼が対象。

## ワークフロー

次の手順で整形する。すべてのコマンドはリポジトリルートから実行する。
対象ファイルパスはリポジトリルートからの相対パス、またはコマンド実行前に絶対パスへ変換したものを使用する
（`pnpm --dir tools/markdown` はカレントディレクトリを `tools/markdown/` に切り替えて実行するため）。

1. 整形対象の Markdown ファイルパスを 1 つ受け取り、絶対パスに解決する。
2. `pnpm --dir tools/markdown exec markdownlint-cli2 --config <リポジトリルート>/.markdownlint-cli2.jsonc <絶対パス> --fix` を実行。
3. `pnpm --dir tools/markdown exec textlint --config <リポジトリルート>/.textlintrc <絶対パス> --fix` を実行。
4. `pnpm --dir tools/markdown exec textlint --config <リポジトリルート>/.textlintrc <絶対パス>` を実行し、残っているエラーを取得する。
5. 残っている指摘内容を確認し、指摘種別ごとに次の方針で Markdown を修正する。
   - `markdownlint` の指摘: 見出しレベルや順序、箇条書きのインデント、空行やコードブロックなどの Markdown 記法・体裁を、ルールに沿うように修正する。
   - `textlint` の指摘: 誤字脱字や表記ゆれの統一、冗長な表現の簡潔化など、日本語文章そのものを意味が変わらない範囲で書き換えて修正する。
6. 2 〜 5 を繰り返し実行し、指摘が消えるまで実行する。

## 失敗したときの扱い

- もし markdownlint-cli2 や textlint の実行に失敗した場合、`pnpm --dir tools/markdown install --frozen-lockfile` を実行すること。
- 自動修正で直らない指摘が出た場合、内容は変えずに整形だけを行う。
- 同じ指摘が何度直しても消えない場合、無理に深追いしない。残った指摘と理由を短くまとめて止める。

## 境界線

### Always（必ずやる）

- `markdownlint-cli2` と `textlint` を両方実行する。
- 自動修正で意味が変わっていないか確認する。
- 指摘がなくなるか、手動で修正が不可能であると判断するまで繰り返す。

### Never（絶対にやらない）

- ルール設定（`.markdownlint-cli2.jsonc` / `.textlintrc`）の変更。
