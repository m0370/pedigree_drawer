1. 基準となる本人は48歳女性。45歳時に乳癌発症、現在生存して治療中。
2. 本人の夫は50歳。
3. 本人には二人の子がおり、長男が20歳、長女が18歳。
4. 本人には兄と姉がいる。兄は55歳で、50歳の妻と30歳の息子を持つ。姉は52歳で、48歳で卵巣癌を発症した。
5. 本人の両親は、父が78歳であり、65歳の時に胃癌を発症して手術を受けたがその後は再発なく健康に過ごしている。
6. 母は55歳の時に乳がんを発症し、10年前に60歳で乳癌により死亡した。
7. 母には72歳の兄がいる。
8. 母の兄は5年前に胃癌を発症し、2年前に他界した。

ありがとうございます。ご提示いただいた情報を JOHBOC家系図記載法（Bennett et al. 2022）／JSON v0.2 に基づいて整理し、**診断時年齢を重視した家系図（SVG）**を作成しました。

作成した家系図（SVG）

👉 家系図をダウンロード

反映内容の確認（重要ポイント）

発端者（本人）

48歳・女性

45歳時 乳癌発症（治療中） ← 若年発症として明確に反映

同胞

兄：55歳（配偶者50歳、子30歳・男）

姉：52歳、48歳時 卵巣癌

両親

父：78歳、65歳時 胃癌（術後再発なし）

母：55歳時 乳癌、60歳で乳癌死

母方伯父

67歳時 胃癌、70歳で死亡（年齢整合性をとって記載）

子

長男20歳、長女18歳

すべてのがん罹患者について、診断時年齢を明示してあります。

次のステップ（必要に応じて）

BRCA1/2 など遺伝学的検査結果の追加

祖父母世代の情報追加

病理サブタイプ（例：トリプルネガティブ）や左右の追記

カウンセリング用に「確認済み（*）」表記の追加

修正や追加があれば、文章でそのまま教えてください。家系図を更新します。

途中経過のJSONを出力して。

了解しました。以下が、**今回の家系図作成に用いた途中経過の JSON（v0.2 準拠）**です。
※そのまま PedigreeChart.load_from_json() に投入できる内容です。

{
  "meta": {
    "date": "2025-12-13",
    "author": "遺伝学的家系図作成GPT"
  },
  "individuals": [
    {
      "id": "II-2",
      "gender": "F",
      "current_age": "48",
      "status": ["affected", "proband"],
      "diagnoses": [
        {
          "condition": "乳癌",
          "age_at_diagnosis": "45",
          "status": "治療中"
        }
      ]
    },
    {
      "id": "II-2-sp",
      "gender": "M",
      "current_age": "50"
    },
    {
      "id": "III-1",
      "gender": "M",
      "current_age": "20"
    },
    {
      "id": "III-2",
      "gender": "F",
      "current_age": "18"
    },
    {
      "id": "II-1",
      "gender": "M",
      "current_age": "55"
    },
    {
      "id": "II-1-sp",
      "gender": "F",
      "current_age": "50"
    },
    {
      "id": "III-3",
      "gender": "M",
      "current_age": "30"
    },
    {
      "id": "II-3",
      "gender": "F",
      "current_age": "52",
      "status": ["affected"],
      "diagnoses": [
        {
          "condition": "卵巣癌",
          "age_at_diagnosis": "48"
        }
      ]
    },
    {
      "id": "I-1",
      "gender": "M",
      "current_age": "78",
      "status": ["affected"],
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
          "age_at_diagnosis": "55",
          "notes": "死因"
        }
      ]
    },
    {
      "id": "I-3",
      "gender": "M",
      "status": ["affected", "deceased"],
      "age_at_death": "70",
      "diagnoses": [
        {
          "condition": "胃癌",
          "age_at_diagnosis": "67"
        }
      ]
    }
  ],
  "relationships": [
    {
      "partners": ["II-2", "II-2-sp"],
      "type": "spouse",
      "children": ["III-1", "III-2"]
    },
    {
      "partners": ["II-1", "II-1-sp"],
      "type": "spouse",
      "children": ["III-3"]
    },
    {
      "partners": ["I-1", "I-2"],
      "type": "spouse",
      "children": ["II-1", "II-2", "II-3"]
    }
  ]
}

補足（専門的観点）

**乳癌（45歳）＋姉の卵巣癌（48歳）＋母の乳癌（55歳）**という集積は、
HBOC を強く疑う構造として家系図上も明確に表現されています。

すべての罹患者で 診断時年齢が欠落していない 点は、遺伝カウンセリング・検査適応判断に適しています。

次は

遺伝学的検査結果の追記

祖父母世代の追加

v0.2 → 記録確認済み（*）表記

なども対応できます。どこを次に調整しますか。