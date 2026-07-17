---
applyTo: "tests/**"
---

<!-- ユニットテストについてのカスタムインストラクション。但しpytestを想定 -->

ユニットテストのモジュールには`pytest`を使用する。

Given-When-Thenパターンを意識してテストコードを記述すること。また、各ステップにおいてはコメントで区切り、何をしているのかを簡潔に説明すること。

```python
def test_example() -> None:
    """exampleについてのテストケース"""
    # Given: 前提条件の設定
    ...
    # When: テスト対象の操作
    ...
    # Then: 結果の検証
    ...
```

## テスト戦略（TDD）

t-wada流のテスト駆動開発（TDD）を徹底

### サイクル
🔴 Red » 🟢 Green » 🔵 Refactor

### 手順
1. TODO作成
2. 失敗テスト
3. 最小実装（仮実装OK）
4. リファクタ

### 原則
- 小さなステップで進める
- 三角測量で一般化
- 不安な部分から着手
- テストリストを常に更新

#### 三角測量の例
```python
# 1. 仮実装: return 5
assert add(2, 3) == 5

# 2. 一般化: return a + b
assert add(10, 20) == 30

# 3. エッジケース確認
assert add(-1, -2) == -3
```

#### 注意点
- 1test::1behavior
- Red»Greenでコミット
- リファクタ: 重複|可読性|SOLID違反時

### テスト種別
1. **単体**: 基本動作 `template/tests/unit/`
2. **統合**: 連携テスト `template/tests/integration/`

### テスト命名

以下の命名規則に従い、**英語**で命名すること。

`test_<function>_<primary_condition_or_branch>_<scenario>_<expected>()`

- function: テスト対象の関数名。
- primary_condition_or_branch: テストの主要な条件や分岐。例：correct_param, missing_param
- scenario: テストの状況や条件。valid, invalid, edgeのみを使用すること。
- expected: 期待される結果や動作。return, raiseなどを使用すること。

例：`test_add_correct_param_valid_return_sum()`
`test_add_str_param_invalid_raise_TypeError()`

命名はスネークケースで行うこと。但し、例外を出すことを確認するテストの場合、例外名のみCamelCaseを使用して良い。

例：`test_add_invalid_raise_TypeError()`
