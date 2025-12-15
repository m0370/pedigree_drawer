# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## プロジェクト概要

**遺伝学的家系図作成システム (v0.7)**

JOHBOC（日本遺伝性腫瘍学会）および日本人類遺伝学会のガイドライン（Bennett 2022年改訂版、図5記載例準拠）に完全準拠した遺伝診療用家系図作成システム。

- 自然言語での対話から家系情報を構造化し、SVG形式の家系図を自動生成
- JSON中間表現により、同じ入力から常に同じ出力が得られる決定論的レンダリング
- PowerPointで後編集可能なベクターSVG出力

---

## 最重要原則

1. **JOHBOC家系図記載法が最優先**: `家系図の描き方/JOHBOC家系図記載法.md`（特に図5記載例）が最も基本的で最重要な原則
2. **診断時年齢が最重要**: 遺伝性腫瘍評価では診断時年齢が最も重要。45歳 vs 65歳で乳癌 → リスク評価が全く異なる
3. **年齢単位サフィックス必須**: 56y, 3m, 10d（図5記載例準拠）
4. **決定論的レンダリング**: 同じJSON → 同じSVG（pedigree_drawer_lib.py v0.7）
5. **標準ID命名規則**: I-1, I-2, II-1など（'I-2-brother'や'II-1-spouse'は不可）
6. **個人番号表示**: 記号の右上にアラビア数字のみ、左から右に順番に（例：1, 2, 3）

---

## コアファイル構成

### 実装本体
- **[pedigree_drawer_lib.py](pedigree_drawer_lib.py)** (2,086行, v0.7): JSON → SVG決定論的レンダリングエンジン。標準ライブラリのみ（外部依存なし）。SVG出力はPowerPoint編集可能な構造で生成。

### 仕様・ドキュメント
- **[JSON_SCHEMA.md](JSON_SCHEMA.md)**: JSON中間表現の完全仕様（v0.7）。個人情報、関係情報、メタデータ、pregnancy/twin/adoption/genetic testing等の全フィールド定義
- **[JOHBOC家系図記載法.md](家系図の描き方/JOHBOC家系図記載法.md)**: 最重要参照資料。図5記載例を含む標準記載法
- **[genealogy_gpt_instructions.md](genealogy_gpt_instructions.md)** (v0.7): GPTs Instructions用プロンプト（8,000文字以内）
- **[genealogy_gpt_instructions_full.md](genealogy_gpt_instructions_full.md)**: 指示のロング版（編集用・参照用）

### CLI・テスト
- **[render_pedigree.py](render_pedigree.py)**: ローカル環境でJSONからSVGを生成するCLIツール
- **[test_v0_4.py](test_v0_4.py)**: v0.4以降向けのテストスクリプト例

---

## 開発コマンド

### ローカルでSVGを生成
```bash
python3 render_pedigree.py input.json -o output.svg
```

### テストスクリプトを実行
```bash
python3 test_v0_4.py
```

### JSONから直接Pythonで検証（対話的）
```python
from pedigree_drawer_lib import PedigreeChart
import json

data = json.loads(open('test.json').read())
chart = PedigreeChart()
chart.load_from_json(data)
chart.render_and_save('output.svg')
```

---

## JSONスキーマの全体構造

```json
{
  "meta": {
    "date": "2025-12-15",
    "author": "Dr. Name",
    "indication": "家族性乳がん評価",
    "show_legend": false,
    "show_conditions_legend": false,
    "legend_conditions": ["乳癌", "白血病"]
  },
  "individuals": [
    {
      "id": "I-1",
      "gender": "M",
      "current_age": "78",
      "status": ["affected"],
      "diagnoses": [
        {
          "condition": "胃癌",
          "age_at_diagnosis": "65"
        }
      ],
      "genetic_testing": {
        "result": "Pathogenic variant detected",
        "display": "BRCA1 c.1234C>T (p.Arg412*)"
      }
    }
  ],
  "relationships": [
    {
      "type": "spouse",
      "partners": ["I-1", "I-2"],
      "children": ["II-1", "II-2"]
    },
    {
      "type": "siblings",
      "siblings": ["I-1", "I-3"]
    }
  ]
}
```

### 個人情報 (individuals[])
- `id` (必須): 標準形式 I-1, I-2, II-1, II-2, III-1等（重複不可、親が世代I以上なら子は世代II以上）
- `gender`: "M" (□男性), "F" (○女性), "U" (◇性別不明/多様)
- `status`: 配列。"affected" (黒塗り) / "deceased" (斜線/) / "carrier" or "presymptomatic_carrier" (縦線) / "proband" (発端者P↗) / "consultand" (来談者↗) / "verified" (*) / "miscarriage" (△) / "abortion" (△+/) / "stillbirth" (SB+/) / "pregnancy" (内部にP)等
- `current_age`: "48" (数字のみ、単位はy/m/dで自動付与)
- `age_at_death`: "65" (死亡時年齢)
- `diagnoses`: [{condition, age_at_diagnosis, status, notes}]. age_at_diagnosisはMUST HAVE。"55y 乳癌"のように表示
- `medical_notes`: [str]. 既往歴・手術歴（年齢なし。例：["脳血管疾患"]）。 v0.7で自動的に"37歳"→"37y"に正規化
- `genetic_testing`: {result, display}. 検査結果は個体記号下に表示
- 妊娠関連: `pregnancy_event` / `pregnancy_info`
- 双生児: `twin` (推奨) / `twin_info` (互換)
- 養子: `adoption_info` / relationships[].childrenのrelation: "adopted"
- 複数個体: `count`, `count_type`

### 関係情報 (relationships[])
- `type`: "spouse" (婚姻) / "consanguineous" (近親婚、二重線) / "divorced" (//) / "separated" / "siblings" (親なし兄弟の線)
- `partners`: [id, id]. 配偶者（夫婦関係または片親）
- `children`: [id, id]. 子ども
- `siblings`: [id, id, ...]. 親が家系図に含まれない兄弟のみ使用

---

## v0.7新機能（2025-12-14）

- **複数疾患の塗り分け（図2）**: `meta.legend_conditions` で疾患別に塗り分け、同一人物の複数疾患は左右分割で表現
- **凡例制御の分離**: `meta.show_legend`（汎用Legend）と `meta.show_conditions_legend`（Conditionsのみ）を分離
- **medical_notesの年齢表記正規化**: `37歳/37才` → `37y`に自動変換して表示

---

## 重要な禁止事項

- ❌ `age_at_diagnosis` を欠落させない（遺伝性腫瘍評価で最重要）
- ❌ 年齢単位サフィックス（y/m/d）を省略しない
- ❌ JOHBOC非準拠の要素を追加しない
- ❌ ID形式を "I-2-brother" や "II-1-spouse" といった非標準形式にしない
- ❌ ファイル名にバージョン番号を含めない（ファイル内ヘッダーで管理）

---

## pedigree_drawer_lib.py の主要クラス・関数

### PedigreeChart クラス
```python
from pedigree_drawer_lib import PedigreeChart

chart = PedigreeChart()
chart.load_from_json(data)           # JSONを読み込み
chart.render_and_save('output.svg')  # SVGを生成・保存
```

### 主要内部機能
- **ジェネレーション計算**: Roman numeral (I, II, III...) を自動計算
- **シンボル描画**: 性別記号（□○◇）、罹患者（黒塗り）、死亡（斜線）、保因者（縦線）、妊娠（内部P）等
- **関係線**: 婚姻線、親子線、兄弟線、近親婚（二重線）、離婚（//）
- **年齢表記**: age_unit自動付与（y/m/d）
- **診断情報**: 個体記号の下に「年齢 疾患名」で表示
- **遺伝学的検査結果**: 個体記号の下に検査情報を表示
- **個人番号**: 記号の右上に配置順で1,2,3...と表示（図5準拠）
- **凡例**: `meta.show_legend: true` で有効化
- **複数疾患塗り分け**: `meta.legend_conditions` で色分け（図2対応）

### 正規化関数
```python
def _canonical_condition(condition: str) -> str
  # 疾患名の正規化（例：乳癌 → 乳癌）

def _normalize_age_expression(text: str) -> str
  # 年齢表記の正規化（37歳 → 37y, 3m, 10d等）
```

---

## 重要な実装詳細

### 1. ID命名と世代システム
- 新規に個人を追加する際は、親の世代より1世代下を使用
- 例: 親が I-1, I-2 → 子は II-1, II-2, II-3
- 兄弟の順序は左から右（ジェネレーション計算後に左上から右下へトラバース）

### 2. age_at_diagnosis の必須化
```json
{
  "condition": "乳癌",
  "age_at_diagnosis": "45",  // MUST HAVE（"45y"ではなく数字のみ）
  "status": "treated"
}
```
診断時年齢がないと、遺伝性腫瘍評価ができない（臨床的に重要）

### 3. 兄弟関係の表現（親あり vs 親なし）
```json
// 親がいる場合は「親 + children」を使用
{
  "type": "spouse",
  "partners": ["I-1", "I-2"],
  "children": ["II-1", "II-2"]
}

// 親が家系図に含まれない場合のみ「siblings」を使用
{
  "type": "siblings",
  "siblings": ["I-2", "I-3"]
}
```

### 4. PowerPoint 編集対応
- SVGの各要素は `<g id="...">` でグループ化
- PowerPointで「図形に変換」すると個別に選択・編集可能
- 線・文字・記号が独立した要素として出力される

### 5. 決定論的レンダリング
- 同じJSONから常に同じSVGを生成
- JSONの フィールド順序は出力に影響しない（ただし配置順序はindividuals/relationshipsの順序で決定）

---

## 今後の開発予定（優先度順）

### 高優先度（v0.8候補）
- [ ] 複雑な多世代・多人数家系での自動レイアウト改善
- [ ] 双生児の分岐線・一卵性双生児の水平線接続の最適化

### 中優先度（将来版）
- [ ] 異所性妊娠（ECT）のJSON schema フィールド追加
- [ ] 核型情報（Karyotype）の構造化
- [ ] VSC（Variations of Sex Characteristics）の詳細情報

### 低優先度
- [ ] 保因者の複数の塗りつぶしパターン拡張
- [ ] 祖先情報の構造化

---

## テスト・検証

### テストデータ
- `test_johboc_fig5.json`: JOHBOC図5記載例に基づいたテストデータ
- `test_v0.3_simple.json`: シンプルな家系図のテスト
- `test_v0_4.py`: v0.4以降の兄弟関係・レイアウト改善を検証するスクリプト
- `test_run/` ディレクトリ: 各バージョンの検証結果（SVG + マークダウンレポート）

### 検証チェックリスト
1. JSONが有効な形式か（id重複なし、年齢単位サフィックス付き等）
2. 生成されたSVGに文字の重なりはないか
3. 個人番号（右上のアラビア数字）が左から右に1,2,3...と順番か
4. 診断時年齢が記号下に「年齢 疾患名」で表示されているか
5. 遺伝学的検査情報が表示されているか（ある場合）

---

## 日本語ファイル取り扱いルール

- **エンコーディング**: 日本語ファイルは必ずUTF-8（BOM無し）
- **Pythonでの作成**: `encoding='utf-8'` を明示的に指定
- **推奨フォーマット**: Markdown、テキストファイル

---

## 参考資料

- [README.md](README.md): 機能概要とGPTsセットアップ手順
- [JOHBOC家系図記載法.md](家系図の描き方/JOHBOC家系図記載法.md): JOHBOC/Bennett 2022年改訂版ガイドライン（図5記載例）
- [JSON_SCHEMA.md](JSON_SCHEMA.md): JSON中間表現の完全仕様

---

## ライセンス

MIT License
