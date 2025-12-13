# 遺伝学的家系図 JSON スキーマ v0.2

**最終更新**: 2025-12-13
**準拠**: JOHBOC家系図記載法 (Bennett et al. 2022準拠)

## 概要

このJSONスキーマは、JOHBOC（日本遺伝性腫瘍学会）および日本人類遺伝学会のガイドラインに完全準拠した家系情報を記録するための中間表現形式です。

## 実装（SVGレンダラ）との関係

現在の決定論的レンダラ（`pedigree_drawer_lib_v0_2.PedigreeChart`）は、スキーマのうち「描画に必要な最小サブセット」を必ず解釈してSVGへ反映します。臨床情報として有用なフィールド（`diagnoses`/`genetic_testing`等）は保持できますが、**描画には反映しない（または注記として任意で反映する）**場合があります。

レンダラが描画に使用する主なフィールド：
- `individuals[].gender`, `individuals[].sex_at_birth`
- `individuals[].status`
- 年齢系: `age`（v0.1互換）/ `current_age` / `age_at_death` / `birth_year` / `death_year`
- 妊娠イベント: `pregnancy_event`（推奨）または `pregnancy_info`（互換）
- 双生児: `twin`（推奨）または `twin_info`（互換）
- 複数個体記号: `count`
- 養子: `adoption_info.adopted` または `relationships[].children` の `relation` / `relationships[].adoption`
- 関係線: `relationships[].type`（`spouse`/`consanguineous`/`divorced`/`separated`）

### v0.2の主な改善点

| 項目 | v0.1 | v0.2 |
|-----|------|------|
| 診断時年齢 | ❌ 記録不可 | ✅ `diagnoses[].age_at_diagnosis` |
| 疾患名 | ❌ 記録不可 | ✅ `diagnoses[].condition` |
| 複数疾患 | ❌ 不可 | ✅ `diagnoses[]` 配列 |
| 遺伝学的検査 | ❌ 不可 | ✅ `genetic_testing` |
| 双生児 | ⚠️ 不完全 | ✅ `twin_info` |
| 養子 | ❌ 不可 | ✅ `adoption_info` |
| 生殖補助技術 | ❌ 不可 | ✅ `art_info` |
| 近親婚詳細 | ❌ 不可 | ✅ `consanguinity` |
| 複数個体の一括表記 | ❌ 不可 | ✅ `count` / `count_type` |

---

## 1. トップレベル構造

```json
{
  "meta": { ... },              // メタデータ（任意）
  "individuals": [ ... ],       // 個人情報（必須）
  "relationships": [ ... ],     // 関係情報（必須）
  "donors_surrogates": [ ... ]  // 提供者・代理母（任意）
}
```

---

## 2. メタデータ (`meta`)

```json
{
  "meta": {
    "date": "2025-12-13",           // 作成日（推奨）
    "author": "Dr. Tanaka",         // 作成者（推奨）
    "indication": "家族性乳がん評価", // 適応（任意）
    "historian": "本人（発端者）"    // 情報提供者（任意）
  }
}
```

---

## 3. 個人情報 (`individuals[]`)

### 3.1 基本情報（必須）

```json
{
  "id": "II-3",          // 個体番号（必須、例: I-1, II-2, III-3）
  "gender": "F",         // ジェンダー（必須）: "M"=男性, "F"=女性, "U"=不明/多様
  "sex_at_birth": "AFAB" // 出生時割当（任意）: "AMAB", "AFAB", "UAAB"
}
```

### 3.1.5 複数個体の一括表記 (`count`) ⭐新規

JOHBOC記載法では、複数の同胞を1つの記号で表すことができます。記号内に数字を記載し、その数字が何人いるかを示します（例：□内に5 = 5人の男性）。

```json
{
  "id": "II-4",
  "gender": "M",
  "count": 5,              // 複数個体を1記号で表す場合の人数（任意）
  "count_type": "exact",   // "exact"（正確）または "approximate"（約n人）（任意、デフォルト: "exact"）
  "status": [],
  "current_age": null,     // 複数個体の場合、個別年齢は通常不明
  "notes": "5人の兄弟"
}
```

**使用条件**:
- `count` が2以上の場合、複数個体を表す
- `count` が未定義または1の場合、通常の単一個体
- 複数個体の場合、`current_age`、`age_at_death`、`diagnoses` などの詳細情報は通常記録できない（全員に共通する情報がある場合は `notes` に記載）
- `count_type` で「正確に5人」か「約5人」かを区別可能

### 3.2 年齢情報

```json
{
  "current_age": "48",      // 現在年齢（生存者の場合）
  "age_at_death": null,     // 死亡年齢（死亡者の場合）
  "birth_year": "1977",     // 出生年（任意）
  "death_year": null        // 死亡年（任意）
}
```

**使い分け**:
- 生存者: `current_age` のみ
- 死亡者: `age_at_death` (必須)、`current_age` はnull

### 3.3 状態フラグ (`status[]`)

```json
{
  "status": [
    "affected",                 // 罹患者（黒塗り）
    "proband"                   // 発端者（P + 矢印）
  ]
}
```

**利用可能な値**:
- `"affected"` - 罹患者（黒塗り）
- `"deceased"` - 死亡（左下→右上斜線）
- `"proband"` - 発端者（P + 矢印）
- `"consultand"` - 来談者（矢印のみ）
- `"verified"` - 記録確認済み（*）
- `"presymptomatic_carrier"` - 無症状変異保有者（縦線）
- `"pregnancy"` - 妊娠中（記号内にP）
- `"miscarriage"` - 自然流産（△）
- `"abortion"` - 人工妊娠中絶（△+斜線）
- `"stillbirth"` - 死産（記号+斜線+SB）
- `"adopted"` - 養子（大括弧）
- `"donor"` - 配偶子提供者（記号内にD）
- `"surrogate"` - 代理懐胎（記号内にS）

### 3.4 診断情報 (`diagnoses[]`) ⭐新規

複数の疾患を記録できます。

```json
{
  "diagnoses": [
    {
      "condition": "乳癌",               // 疾患名（必須）
      "age_at_diagnosis": "45",         // 診断時年齢（必須）⭐最重要
      "type": "Triple negative",        // サブタイプ（任意）
      "laterality": "右",               // 左右（任意）
      "status": "治療中",               // 現在の状態（任意）
      "treatment": "手術+化学療法",      // 治療内容（任意）
      "outcome": "寛解",                // 転帰（任意）
      "recurrence": false,              // 再発有無（任意）
      "notes": "術後5年経過"            // 備考（任意）
    },
    {
      "condition": "卵巣癌",
      "age_at_diagnosis": "47"
    }
  ]
}
```

**重要**: 遺伝性腫瘍の評価では `age_at_diagnosis`（診断時年齢）が最重要です。

### 3.5 遺伝学的検査情報 (`genetic_testing`) ⭐新規

```json
{
  "genetic_testing": {
    "tested": true,                         // 検査実施有無
    "test_type": "BRCA1/2 panel",          // 検査種類
    "result": "BRCA1 pathogenic variant",  // 結果
    "variant": "c.1687C>T",                // バリアント（任意）
    "date": "2024-01-15"                   // 検査日（任意）
  }
}
```

### 3.6 妊娠関連情報 (`pregnancy_info`) ⭐拡張

```json
{
  "pregnancy_info": {
    "gestational_age": "20週",         // 在胎週数
    "lmp": "2024-06-01",              // 最終月経日（任意）
    "edd": "2025-03-08",              // 出産予定日（任意）
    "fetal_sex": "F",                 // 胎児の性別（判明している場合）
    "pregnancy_outcome": null         // 転帰: "live_birth", "miscarriage", "abortion", "stillbirth"
  }
}
```

### 3.7 双生児情報 (`twin_info`) ⭐新規

```json
{
  "twin_info": {
    "is_twin": true,
    "twin_type": "monozygotic",    // "monozygotic"（一卵性）or "dizygotic"（二卵性）
    "twin_sibling_id": "III-3"     // 双生児のきょうだいID
  }
}
```

### 3.8 養子情報 (`adoption_info`) ⭐新規

```json
{
  "adoption_info": {
    "adopted": true,
    "biological_parents_known": false,
    "notes": "生物学的両親は不明"
  }
}
```

### 3.9 その他の情報

```json
{
  "name": "岡崎翔子",           // 名前（任意、匿名化推奨）
  "notes": "トリプルネガティブ", // 自由記述
  "ethnicity": "日本人"         // 民族（臨床的に関連する場合）
}
```

---

## 4. 関係情報 (`relationships[]`)

### 4.1 基本構造

```json
{
  "partners": ["I-1", "I-2"],   // パートナーのID（必須）
  "type": "spouse",              // 関係タイプ（必須）
  "children": ["II-1", "II-2"]  // 子のID配列（出生順）
}
```

**`type` の値**:
- `"spouse"` - 婚姻
- `"consanguineous"` - 近親婚（二重線）
- `"divorced"` - 離婚（//）
- `"separated"` - 別居

### 4.2 近親婚 (`consanguinity`) ⭐新規

```json
{
  "partners": ["I-3", "I-4"],
  "type": "consanguineous",
  "consanguinity": {
    "degree": "いとこ同士",
    "notes": "父方と母方の祖父母がいとこ同士"
  },
  "children": ["II-1"]
}
```

### 4.3 離婚・再婚

```json
// 離婚
{
  "partners": ["II-1", "II-6"],
  "type": "divorced",
  "children": ["III-4"],
  "divorce_year": "2010"
}

// 再婚
{
  "partners": ["II-1", "II-7"],
  "type": "spouse",
  "children": ["III-5"],
  "marriage_year": "2012"
}
```

### 4.4 子なし (`no_children`) ⭐新規

```json
{
  "partners": ["II-8", "II-9"],
  "type": "spouse",
  "children": [],
  "no_children": {
    "status": true,
    "reason": "infertility"  // "infertility", "by_choice", "sterilization_male", "sterilization_female"
  }
}
```

### 4.5 生殖補助技術 (`art_info`) ⭐新規

```json
{
  "partners": ["II-10", "II-11"],
  "type": "spouse",
  "children": ["III-6"],
  "art_info": {
    "used": true,
    "donor_type": "egg",       // "sperm", "egg", "embryo"
    "donor_id": "DONOR-1",     // 提供者ID（記載する場合）
    "surrogate_id": null       // 代理母ID（記載する場合）
  }
}
```

### 4.6 養子関係 (`adoption`) ⭐新規

```json
{
  "partners": ["II-12", "II-13"],
  "type": "spouse",
  "children": ["III-7"],
  "adoption": {
    "adopted_child_id": "III-7",
    "biological_parents": null  // 不明の場合null、判明している場合は[ID1, ID2]
  }
}
```

---

## 5. 配偶子提供者・代理母 (`donors_surrogates[]`) ⭐新規

家系図に提供者・代理母を記載する場合に使用します。

```json
{
  "donors_surrogates": [
    {
      "id": "DONOR-1",
      "type": "egg_donor",              // "egg_donor", "sperm_donor", "surrogate"
      "gender": "F",
      "status": ["donor"],
      "relationship_to_family": "母の妹" // 血縁者の場合
    }
  ]
}
```

---

## 6. 完全な例

### 例1: 基本的な家系（発端者: 48歳女性、45歳時に乳癌発症）

```json
{
  "meta": {
    "date": "2025-12-13",
    "author": "遺伝カウンセラー",
    "indication": "家族性乳がん評価"
  },
  "individuals": [
    {
      "id": "I-1",
      "gender": "M",
      "status": ["affected"],
      "current_age": "78",
      "diagnoses": [
        {
          "condition": "胃癌",
          "age_at_diagnosis": "65",
          "notes": "手術後再発なし"
        }
      ]
    },
    {
      "id": "I-2",
      "gender": "F",
      "status": ["affected", "deceased"],
      "age_at_death": "60",
      "diagnoses": [
        {
          "condition": "乳癌",
          "age_at_diagnosis": "55"
        },
        {
          "condition": "卵巣癌",
          "age_at_diagnosis": "60",
          "notes": "死因"
        }
      ]
    },
    {
      "id": "II-1",
      "gender": "F",
      "status": ["affected", "proband"],
      "current_age": "48",
      "diagnoses": [
        {
          "condition": "乳癌",
          "age_at_diagnosis": "45",
          "type": "Triple negative",
          "status": "治療中"
        }
      ],
      "genetic_testing": {
        "tested": true,
        "test_type": "BRCA1/2 panel",
        "result": "BRCA1 pathogenic variant"
      }
    }
  ],
  "relationships": [
    {
      "partners": ["I-1", "I-2"],
      "type": "spouse",
      "children": ["II-1"]
    }
  ]
}
```

### 例2: 双生児

```json
{
  "individuals": [
    {
      "id": "III-1",
      "gender": "F",
      "current_age": "12",
      "twin_info": {
        "is_twin": true,
        "twin_type": "monozygotic",
        "twin_sibling_id": "III-2"
      }
    },
    {
      "id": "III-2",
      "gender": "F",
      "current_age": "12",
      "twin_info": {
        "is_twin": true,
        "twin_type": "monozygotic",
        "twin_sibling_id": "III-1"
      }
    }
  ]
}
```

### 例3: 妊娠・流産

```json
{
  "individuals": [
    {
      "id": "II-3",
      "gender": "F",
      "status": ["pregnancy"],
      "pregnancy_info": {
        "gestational_age": "28週",
        "edd": "2025-03-15",
        "fetal_sex": "F"
      }
    },
    {
      "id": "II-4",
      "gender": "U",
      "status": ["miscarriage"],
      "pregnancy_info": {
        "gestational_age": "8週",
        "pregnancy_outcome": "miscarriage"
      }
    }
  ]
}
```

### 例4: 複数個体の一括表記 ⭐新規

```json
{
  "individuals": [
    {
      "id": "I-1",
      "gender": "M",
      "current_age": "75"
    },
    {
      "id": "I-2",
      "gender": "F",
      "current_age": "73"
    },
    {
      "id": "II-1",
      "gender": "F",
      "status": ["proband"],
      "current_age": "48"
    },
    {
      "id": "II-2",
      "gender": "M",
      "count": 5,
      "count_type": "exact",
      "status": [],
      "notes": "5人の兄弟（詳細不明）"
    },
    {
      "id": "II-3",
      "gender": "F",
      "count": 3,
      "count_type": "exact",
      "status": [],
      "notes": "3人の姉妹（詳細不明）"
    }
  ],
  "relationships": [
    {
      "partners": ["I-1", "I-2"],
      "type": "spouse",
      "children": ["II-1", "II-2", "II-3"]
    }
  ]
}
```

**説明**: 発端者（II-1）には5人の兄弟と3人の姉妹がいるが、詳細は不明。JOHBOC記載法に従い、□内に「5」、○内に「3」と記載する。

---

## 7. 後方互換性

v0.1スキーマとの主な違い：

| フィールド | v0.1 | v0.2 |
|----------|------|------|
| `age` | 使用 | 非推奨（`current_age` または `age_at_death` を使用） |
| `diagnoses` | - | ✅ 新規追加 |
| `genetic_testing` | - | ✅ 新規追加 |
| `twin_info` | - | ✅ 新規追加 |

v0.1形式のJSONも引き続きサポートされますが、診断情報が欠落します。

---

## 8. バリデーションルール

### 必須フィールド
- `id`: 空でない文字列
- `gender`: "M", "F", "U" のいずれか
- `diagnoses[].condition`: 診断がある場合必須
- `diagnoses[].age_at_diagnosis`: 診断がある場合必須

### 推奨フィールド
- `current_age` または `age_at_death`: 少なくとも一方
- `meta.date`: 作成日
- `meta.author`: 作成者

---

## 9. 今後の拡張予定

- [ ] 国際疾患分類（ICD-10/ICD-11）コード対応
- [ ] FHIR形式への変換サポート
- [ ] 表現型オントロジー（HPO）対応
- [ ] 家系図の差分更新機能
