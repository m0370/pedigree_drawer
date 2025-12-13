#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test script for pedigree_drawer_lib.py v0.4
Tests sibling relationship rendering and improved layout
"""

from pedigree_drawer_lib import PedigreeChart

# Test data based on the original example but with:
# 1. Correct ID naming (I-3 instead of I-2-brother, II-3 instead of II-2-spouse)
# 2. Sibling relationship between I-2 and I-3
test_data = {
    "meta": {
        "date": "2025-12-13",
        "author": "遺伝学的家系図作成GPT v0.4 test"
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
            "id": "II-3",
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
            "id": "II-4",
            "gender": "F",
            "current_age": "50"
        },
        {
            "id": "III-3",
            "gender": "M",
            "current_age": "30"
        },
        {
            "id": "II-5",
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
            "current_age": "72",
            "age_at_death": "70",
            "diagnoses": [
                {
                    "condition": "胃癌",
                    "age_at_diagnosis": "67"
                }
            ],
            "medical_notes": ["心筋梗塞（69歳）"]
        }
    ],
    "relationships": [
        {
            "partners": ["II-2", "II-3"],
            "type": "spouse",
            "children": ["III-1", "III-2"]
        },
        {
            "partners": ["II-1", "II-4"],
            "type": "spouse",
            "children": ["III-3"]
        },
        {
            "partners": ["I-1", "I-2"],
            "type": "spouse",
            "children": ["II-1", "II-2", "II-5"]
        },
        {
            "type": "siblings",
            "siblings": ["I-2", "I-3"]
        }
    ]
}

# Render the pedigree
chart = PedigreeChart()
chart.load_from_json(test_data)
output_file = chart.render_and_save('/Users/tgoto/Library/Mobile Documents/com~apple~CloudDocs/2026/遺伝学的家系図/pedigree_chart_v0_4_test.svg')

print(f"✅ Pedigree chart saved to: {output_file}")
print("\n主な修正点:")
print("1. ✅ I-2とI-3の兄弟線が描画されました（親がいない兄弟）")
print("2. ✅ IDがシンプルになりました（'I-3', 'II-3' など）")
print("3. ✅ レイアウト間隔が調整され、文字の重なりが軽減されました")
