"""
pedigree_drawer_lib.py (v0.6)

Deterministic renderer: JSON (intermediate representation) -> SVG.

Version History:
- v0.6 (2025-12-14): Genetic testing display + relationship guidance
  - 遺伝学的検査結果（genetic_testing.result / display）の描画に対応（個体記号の下に表示）
- v0.5 (2025-12-13〜2025-12-14): JOHBOC図5完全準拠への改善
  - 個人番号を右上にアラビア数字のみで表示（図5準拠）
  - 兄弟間横線の位置を下げて親の情報と重ならないよう改善
  - 発端者マーカー（P+矢印）のレイアウト改善（重なり解消、矢印を短縮）
  - 凡例機能の追加（meta.show_legend: trueで有効化）
  - 配偶者間隔の統一（spouse_gap: 36→80px、unit_gapと同じ）
  - 保因者縦線の修正（未発症保因者のみに描画）
  - 世代番号の命名規則明確化（親世代なし→発端者をI世代から開始）
  - 左マージンの拡大（margin_x: 40→60px）
  - **片親のみの親子関係サポート**（JOHBOC図5準拠、partners配列が1人でも可）
- v0.4 (2025-12-13): 兄弟関係の描画改善とレイアウト最適化
  - 親がいない兄弟の線描画対応（sibship line）
  - relationshipsに"siblings"タイプを追加
  - 標準ID命名規則の明確化（I-1, I-2形式必須）
  - レイアウト改善（spouse_gap: 24→36px, unit_gap: 52→80px）
- v0.3 (2025-12-13): JOHBOC図5準拠の改善
  - 年齢単位サフィックス（y/m/d）の自動付与
  - 診断情報（diagnoses）の描画対応
  - 既往歴・手術歴（medical_notes）の描画対応
  - 右下の署名を日付のみに変更（作成者名を削除）
- v0.2: 複数個体記号、双生児、養子、生殖補助技術、近親婚対応
- v0.1: 基本実装

Design goals:
- Output must reflect the JSON strictly (relationships + child order).
- SVG must be clean and editable (PowerPoint-friendly).
- No external dependencies (standard library only).

Supported (subset, JOHBOC 図1〜5に準拠する範囲):
- gender: "M" (□), "F" (○), "U" (◇)
- status: "affected" (filled), "deceased" (slash "/"), "stillbirth" (sex symbol + slash + SB),
          "miscarriage" (triangle), "abortion" (triangle + "/" slash),
          "pregnancy" (P inside), "presymptomatic_carrier" or "carrier" (vertical line),
          "verified" (*), "proband" (arrow + P), "consultand" (arrow)
- relationships: type "spouse" | "consanguineous" | "divorced" | "separated"
- age_unit: "y" (years), "m" (months), "d" (days) with automatic suffix
- diagnoses: [{condition, age_at_diagnosis}] with automatic rendering
- medical_notes: [str] for medical history without age

Optional fields for pregnancy-related symbols (JOHBOC 図4):
- pregnancy_event: {type, gestational_age, lmp, edd, karyotype, note, label}
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from xml.etree import ElementTree as ET


def _roman_to_int(s: str) -> Optional[int]:
    s = (s or "").strip().upper()
    if not s:
        return None
    roman_map = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
    total = 0
    prev = 0
    for ch in reversed(s):
        val = roman_map.get(ch)
        if val is None:
            return None
        if val < prev:
            total -= val
        else:
            total += val
            prev = val
    return total if total > 0 else None


def _wrap_text(s: str, max_chars: int) -> List[str]:
    s = (s or "").strip()
    if not s:
        return []
    if max_chars <= 0:
        return [s]
    return [s[i : i + max_chars] for i in range(0, len(s), max_chars)]


@dataclass
class Person:
    id: str
    gender: str  # "M" | "F" | "U"
    generation: int
    status: List[str] = field(default_factory=list)
    age: Optional[str] = None
    age_unit: str = "y"  # "y" (years), "m" (months), "d" (days)
    diagnoses: List[dict] = field(default_factory=list)
    medical_notes: List[str] = field(default_factory=list)
    genetic_testing: Optional[dict] = None
    name: Optional[str] = None
    x: float = 0.0
    y: float = 0.0
    display_number: int = 0  # Individual number (left to right in each generation)


@dataclass
class Family:
    partners: Tuple[str, ...]  # Single parent (len=1) or couple (len=2)
    type: str
    children: List[str] = field(default_factory=list)
    child_meta: Dict[str, dict] = field(default_factory=dict)


@dataclass
class Sibship:
    """Represents a sibling relationship without parents (for drawing sibship lines)"""
    siblings: List[str] = field(default_factory=list)


class PedigreeChart:
    def __init__(self):
        self.people: Dict[str, Person] = {}
        self.families: List[Family] = []
        self.sibships: List[Sibship] = []
        self._input_order: Dict[str, int] = {}
        self._meta: Dict[str, str] = {}

        # Layout config (SVG px units)
        self.symbol_size = 40.0
        self.spouse_gap = 80.0  # Same as unit_gap for consistent spacing (increased from 36.0)
        self.unit_gap = 80.0     # Increased from 52.0 to prevent text overlap
        # Allow limited horizontal compression when necessary to keep pinned parent-child vertical alignment.
        # Used in crowded generations where fixed unit_gap would otherwise push a single-parent child away.
        self.min_unit_gap = 20.0
        self.gen_gap = 120.0
        self.margin_x = 60.0     # Increased from 40.0 to provide more space between generation labels and symbols
        self.margin_y = 40.0
        self.font_family = "Arial, Helvetica, sans-serif"
        self.stroke_width = 2.0
        # Output profile
        # PowerPoint imports SVG best when:
        # - elements are not deeply grouped,
        # - styles are inlined (no <style> / class selectors),
        # - arrow markers are avoided (use explicit polygons).
        self.output_profile = "powerpoint"  # "powerpoint" | "generic"
        self.show_legend = False  # Set to True to display legend (for complex pedigrees with multiple conditions)

    def load_from_json(self, data: dict) -> None:
        self.people.clear()
        self.families.clear()
        self.sibships.clear()
        self._input_order.clear()
        self._meta = dict((data or {}).get("meta") or {})

        # Enable legend if specified in meta or if multiple disease types are present
        self.show_legend = self._meta.get("show_legend", False)

        individuals = (data or {}).get("individuals") or []
        donors_surrogates = (data or {}).get("donors_surrogates") or []
        if isinstance(donors_surrogates, list) and donors_surrogates:
            # Allow schemas that separate donors/surrogates from the main individuals list.
            individuals = list(individuals) + [d for d in donors_surrogates if isinstance(d, dict)]
        for i, p_data in enumerate(individuals):
            pid = p_data["id"]
            self._input_order[pid] = i

            gen = p_data.get("generation")
            if not gen and "-" in pid:
                gen = _roman_to_int(pid.split("-", 1)[0])
            if not gen:
                gen = 1

            age = p_data.get("age")
            if age is None:
                # v0.2+ schema compatibility
                if p_data.get("age_at_death") is not None:
                    age = p_data.get("age_at_death")
                elif p_data.get("current_age") is not None:
                    age = p_data.get("current_age")
                elif p_data.get("death_year") is not None:
                    age = f"d. {p_data.get('death_year')}"
                elif p_data.get("birth_year") is not None:
                    age = f"b. {p_data.get('birth_year')}"

            age_unit = str(p_data.get("age_unit") or "y").strip()
            diagnoses = list(p_data.get("diagnoses") or [])
            medical_notes = list(p_data.get("medical_notes") or [])
            genetic_testing = p_data.get("genetic_testing")
            if not isinstance(genetic_testing, dict):
                genetic_testing = None

            self.people[pid] = Person(
                id=pid,
                gender=(p_data.get("gender") or "U").upper(),
                generation=int(gen),
                status=list(p_data.get("status") or []),
                age=str(age) if age is not None else None,
                age_unit=age_unit,
                diagnoses=diagnoses,
                medical_notes=medical_notes,
                genetic_testing=dict(genetic_testing) if genetic_testing else None,
                name=str(p_data.get("name")) if p_data.get("name") is not None else None,
            )
            # Optional (JOHBOC 2022/2024): AMAB/AFAB/UAAB etc.
            sex_at_birth = p_data.get("sex_at_birth")
            if sex_at_birth is not None:
                setattr(self.people[pid], "sex_at_birth", str(sex_at_birth))
            adoption_info = p_data.get("adoption_info") or {}
            if isinstance(adoption_info, dict) and adoption_info.get("adopted") is True:
                setattr(self.people[pid], "adoption_bracket", True)
            if "adopted" in (self.people[pid].status or []):
                setattr(self.people[pid], "adoption_bracket", True)
            count = p_data.get("count")
            if count is not None:
                setattr(self.people[pid], "count", str(count))
            twin = p_data.get("twin")
            if isinstance(twin, dict) and twin:
                setattr(self.people[pid], "twin", dict(twin))
            twin_info = p_data.get("twin_info") or {}
            if isinstance(twin_info, dict) and twin_info.get("is_twin") and twin_info.get("twin_sibling_id"):
                sib = str(twin_info.get("twin_sibling_id"))
                a, b = sorted([pid, sib])
                ttype = str(twin_info.get("twin_type") or "").lower()
                z = "unknown"
                if "mono" in ttype:
                    z = "MZ"
                elif "di" in ttype:
                    z = "DZ"
                setattr(self.people[pid], "twin", {"group": f"T_{a}_{b}", "zygosity": z})
            pregnancy_event = p_data.get("pregnancy_event") or {}
            if isinstance(pregnancy_event, dict) and pregnancy_event:
                setattr(self.people[pid], "pregnancy_event", dict(pregnancy_event))
            pregnancy_info = p_data.get("pregnancy_info") or {}
            if isinstance(pregnancy_info, dict) and pregnancy_info and not getattr(self.people[pid], "pregnancy_event", None):
                outcome = str(pregnancy_info.get("pregnancy_outcome") or "").strip().lower()
                ptype = None
                if outcome == "miscarriage":
                    ptype = "SAB"
                elif outcome == "abortion":
                    ptype = "TOP"
                elif outcome == "ectopic":
                    ptype = "ECT"
                setattr(
                    self.people[pid],
                    "pregnancy_event",
                    {
                        "type": ptype,
                        "gestational_age": pregnancy_info.get("gestational_age"),
                        "karyotype": pregnancy_info.get("karyotype"),
                        "lmp": pregnancy_info.get("lmp"),
                        "edd": pregnancy_info.get("edd"),
                        "note": pregnancy_info.get("note"),
                        "label": pregnancy_info.get("label"),
                    },
                )
            elif any(k in p_data for k in ("gestational_age", "karyotype", "lmp", "edd", "pregnancy_event_type")):
                setattr(
                    self.people[pid],
                    "pregnancy_event",
                    {
                        "type": p_data.get("pregnancy_event_type"),
                        "gestational_age": p_data.get("gestational_age"),
                        "karyotype": p_data.get("karyotype"),
                        "lmp": p_data.get("lmp"),
                        "edd": p_data.get("edd"),
                        "note": p_data.get("note"),
                        "label": p_data.get("label"),
                    },
                )

        relationships = (data or {}).get("relationships") or []
        for rel in relationships:
            partners = list(rel.get("partners") or [])
            if len(partners) == 0:
                continue
            # Support single parent (len=1) or couple (len=2)
            if len(partners) == 1:
                p1 = partners[0]
                if p1 not in self.people:
                    continue
                partner_tuple = (p1,)
                rel_type = "single_parent"
            else:  # len >= 2
                p1, p2 = partners[0], partners[1]
                if p1 not in self.people or p2 not in self.people:
                    continue
                partner_tuple = (p1, p2)
                rel_type = (rel.get("type") or "spouse").strip().lower()
                if rel_type not in {"spouse", "consanguineous", "divorced", "separated"}:
                    rel_type = "spouse"

            children: List[str] = []
            child_meta: Dict[str, dict] = {}

            adoption = rel.get("adoption") or {}
            if isinstance(adoption, dict) and adoption.get("adopted_child_id"):
                adopted_child_id = adoption.get("adopted_child_id")
                if adopted_child_id in self.people:
                    child_meta[adopted_child_id] = {"relation": "adopted_in"}
                    setattr(self.people[adopted_child_id], "adoption_bracket", True)
            for entry in (rel.get("children") or []):
                if isinstance(entry, str):
                    cid = entry
                    meta = {}
                elif isinstance(entry, dict):
                    cid = entry.get("id")
                    meta = dict(entry)
                else:
                    continue
                if not cid or cid not in self.people:
                    continue
                children.append(cid)
                if meta:
                    child_meta[cid] = meta
                    relation = str(meta.get("relation") or "").strip().lower()
                    if relation in {"adopted", "adopted_in", "adopted_out", "foster"}:
                        setattr(self.people[cid], "adoption_bracket", True)
            self.families.append(Family(partners=partner_tuple, type=rel_type, children=children, child_meta=child_meta))

        # Process sibling relationships (for individuals without parents in the pedigree)
        for rel in relationships:
            rel_type = (rel.get("type") or "").strip().lower()
            if rel_type == "siblings":
                sibs = list(rel.get("siblings") or [])
                # Filter out invalid IDs
                valid_sibs = [sid for sid in sibs if sid in self.people]
                if len(valid_sibs) >= 2:
                    self.sibships.append(Sibship(siblings=valid_sibs))

        self._auto_layout()

    def render_and_save(self, filename: str = "pedigree.svg") -> str:
        svg = self._render_svg()
        Path(filename).write_text(svg, encoding="utf-8")
        return filename

    # ---------- Layout ----------
    def _auto_layout(self) -> None:
        if not self.people:
            return

        min_gen = min(p.generation for p in self.people.values())
        max_gen = max(p.generation for p in self.people.values())

        initial_x: Dict[str, float] = {}

        for gen in range(min_gen, max_gen + 1):
            pinned_children_in_gen: set = set()
            units = self._units_for_generation(gen)

            # Baseline anchors: input order (deterministic)
            for unit in units:
                for pid in unit["members"]:
                    initial_x.setdefault(pid, float(self._input_order.get(pid, 10_000)))

            # Refine anchors: if person is a child of a family in prev gen, anchor under that family midpoint.
            if gen > min_gen:
                for fam in self.families:
                    if len(fam.partners) == 1:
                        # Single parent: use parent's x position directly
                        p1 = fam.partners[0]
                        if self.people[p1].generation != gen - 1:
                            continue
                        mid = self.people[p1].x
                        # IMPORTANT: For single parent with single child, position child directly under parent (vertical line)
                        # Do not apply child_dx offset - keep child at parent's x position
                        if len(fam.children) == 1:
                            cid = fam.children[0]
                            child = self.people.get(cid)
                            if child and child.generation == gen:
                                initial_x[cid] = mid  # Position child directly under parent
                                pinned_children_in_gen.add(cid)
                            continue
                        # For multiple children, apply standard offset
                        child_dx = self.symbol_size + 36.0
                        n = len(fam.children)
                        for idx, cid in enumerate(fam.children):
                            child = self.people.get(cid)
                            if not child or child.generation != gen:
                                continue
                            offset = (idx - (n - 1) / 2) * child_dx
                            initial_x[cid] = mid + offset
                    else:
                        # Couple: use midpoint
                        p1, p2 = fam.partners[0], fam.partners[1]
                        if self.people[p1].generation != gen - 1 or self.people[p2].generation != gen - 1:
                            continue
                        mid = (self.people[p1].x + self.people[p2].x) / 2
                        child_dx = self.symbol_size + 36.0
                        n = len(fam.children)
                        for idx, cid in enumerate(fam.children):
                            child = self.people.get(cid)
                            if not child or child.generation != gen:
                                continue
                            offset = (idx - (n - 1) / 2) * child_dx
                            initial_x[cid] = mid + offset

            # Calculate anchors for units
            # Special case: if a couple contains a single child of a single parent,
            # anchor the couple under the parent (for vertical line alignment)
            for unit in units:
                if unit["kind"] == "couple":
                    # Check if either member is a single child of a single parent
                    fixed_anchor = None
                    for pid in unit["members"]:
                        for fam in self.families:
                            if len(fam.partners) == 1 and len(fam.children) == 1 and fam.children[0] == pid:
                                # This person is a single child of a single parent
                                parent_id = fam.partners[0]
                                if parent_id in self.people and self.people[parent_id].generation == gen - 1:
                                    # Anchor the couple under the parent
                                    fixed_anchor = self.people[parent_id].x
                                    break
                        if fixed_anchor is not None:
                            break
                    if fixed_anchor is not None:
                        unit["anchor"] = fixed_anchor
                    else:
                        anchors = [initial_x.get(pid, 0.0) for pid in unit["members"]]
                        unit["anchor"] = sum(anchors) / len(anchors) if anchors else 0.0
                else:
                    anchors = [initial_x.get(pid, 0.0) for pid in unit["members"]]
                    unit["anchor"] = sum(anchors) / len(anchors) if anchors else 0.0

            units.sort(key=lambda u: (u["anchor"], min(self._input_order.get(pid, 10_000) for pid in u["members"])))

            cursor_left: Optional[float] = None
            for unit in units:
                width = unit["width"]
                desired_left = unit["anchor"] - width / 2
                if cursor_left is None:
                    left = desired_left
                else:
                    left = max(desired_left, cursor_left)
                unit["left"] = left
                cursor_left = left + width + self.unit_gap

            # Post-pass: try to keep pinned single-parent children vertically aligned by compressing gaps
            # (down to min_unit_gap) instead of letting unit_gap push them away.
            if pinned_children_in_gen and units:
                min_gap = float(getattr(self, "min_unit_gap", self.unit_gap))
                for idx, unit in enumerate(units):
                    if unit.get("kind") != "single":
                        continue
                    pid = (unit.get("members") or [None])[0]
                    if pid not in pinned_children_in_gen:
                        continue
                    desired_left = unit["anchor"] - unit["width"] / 2
                    shift_needed = unit["left"] - desired_left
                    if shift_needed <= 1e-6:
                        continue
                    # Reduce gaps before this unit, starting from the nearest, shifting this unit and all to its right.
                    for j in range(idx - 1, -1, -1):
                        left_unit = units[j]
                        right_unit = units[j + 1]
                        gap = right_unit["left"] - (left_unit["left"] + left_unit["width"])
                        reducible = gap - min_gap
                        if reducible <= 1e-6:
                            continue
                        take = reducible if reducible < shift_needed else shift_needed
                        if take <= 1e-6:
                            continue
                        for k in range(j + 1, len(units)):
                            units[k]["left"] -= take
                        shift_needed -= take
                        if shift_needed <= 1e-6:
                            break

            for unit in units:
                if unit["kind"] == "single":
                    pid = unit["members"][0]
                    self.people[pid].x = unit["left"] + unit["width"] / 2
                else:
                    left_pid, right_pid = unit["members"]
                    left_cx = unit["left"] + self.symbol_size / 2
                    dx = self.symbol_size + self.spouse_gap
                    self.people[left_pid].x = left_cx
                    self.people[right_pid].x = left_cx + dx

            for person in self.people.values():
                if person.generation == gen:
                    person.y = (gen - min_gen) * self.gen_gap

        xs = [p.x for p in self.people.values()]
        ys = [p.y for p in self.people.values()]
        min_x = min(xs) if xs else 0.0
        min_y = min(ys) if ys else 0.0
        for p in self.people.values():
            p.x = p.x - min_x + self.margin_x
            p.y = p.y - min_y + self.margin_y

        # Assign display numbers (left to right in each generation, JOHBOC 図5)
        self._assign_display_numbers()

    def _assign_display_numbers(self) -> None:
        """Assign display numbers (1, 2, 3...) to individuals left to right in each generation"""
        gens = sorted(set(p.generation for p in self.people.values()))
        for gen in gens:
            people_in_gen = [p for p in self.people.values() if p.generation == gen]
            # Sort by x position (left to right)
            people_in_gen.sort(key=lambda p: p.x)
            # Assign numbers 1, 2, 3...
            for idx, person in enumerate(people_in_gen, start=1):
                person.display_number = idx

    def _units_for_generation(self, generation: int) -> List[dict]:
        members_in_gen = [p.id for p in self.people.values() if p.generation == generation]
        used = set()
        units: List[dict] = []

        def family_sort_key(fam: Family) -> int:
            if len(fam.partners) == 1:
                return self._input_order.get(fam.partners[0], 10_000)
            else:
                return min(self._input_order.get(fam.partners[0], 10_000), self._input_order.get(fam.partners[1], 10_000))

        families_in_gen = [
            fam
            for fam in self.families
            if len(fam.partners) >= 2 and
               self.people[fam.partners[0]].generation == generation and
               self.people[fam.partners[1]].generation == generation
        ]
        families_in_gen.sort(key=family_sort_key)

        for fam in families_in_gen:
            p1, p2 = fam.partners[0], fam.partners[1]
            if p1 in used or p2 in used:
                continue
            left_pid, right_pid = self._ordered_partners(p1, p2)
            units.append(
                {
                    "kind": "couple",
                    "members": [left_pid, right_pid],
                    "width": 2 * self.symbol_size + self.spouse_gap,
                    "anchor": 0.0,
                    "left": 0.0,
                }
            )
            used.add(p1)
            used.add(p2)

        remaining = [pid for pid in members_in_gen if pid not in used]
        remaining.sort(key=lambda pid: self._input_order.get(pid, 10_000))
        for pid in remaining:
            units.append({"kind": "single", "members": [pid], "width": self.symbol_size, "anchor": 0.0, "left": 0.0})
        return units

    def _ordered_partners(self, p1_id: str, p2_id: str) -> Tuple[str, str]:
        # Do not reorder by gender; keep JSON order deterministically.
        # (JOHBOC/Bennett 2022 revision removed the "male left, female right" recommendation.)
        return (p1_id, p2_id)

    # ---------- SVG ----------
    def _render_svg(self) -> str:
        width, height = self._estimate_canvas()
        svg = ET.Element(
            "svg",
            {
                "xmlns": "http://www.w3.org/2000/svg",
                "version": "1.1",
                "width": str(width),
                "height": str(height),
                "viewBox": f"0 0 {width} {height}",
            },
        )
        # PowerPoint-friendly: keep structure flat (no mandatory groups/styles/markers).
        self._draw_generation_labels(svg)
        self._draw_metadata(svg, width, height)

        if self.show_legend:
            self._draw_legend(svg, width, height)

        for fam in self.families:
            children = [self.people[cid] for cid in fam.children if cid in self.people]
            if len(fam.partners) == 1:
                # Single parent: draw direct line from parent to children
                p1_id = fam.partners[0]
                p1 = self.people.get(p1_id)
                if not p1:
                    continue
                self._draw_single_parent_lines(svg, p1, children, fam.child_meta)
            else:
                # Couple: draw spouse line and children lines
                p1_id, p2_id = fam.partners[0], fam.partners[1]
                p1 = self.people.get(p1_id)
                p2 = self.people.get(p2_id)
                if not p1 or not p2:
                    continue
                self._draw_spouse_line(svg, p1, p2, fam.type)
                self._draw_children_lines(svg, p1, p2, children, fam.child_meta)

        # Draw sibship lines (for siblings without parents)
        for sibship in self.sibships:
            sibs = [self.people[sid] for sid in sibship.siblings if sid in self.people]
            if len(sibs) >= 2:
                self._draw_sibship_line(svg, sibs)

        for pid in sorted(self.people.keys(), key=lambda k: self._input_order.get(k, 10_000)):
            self._draw_person(svg, self.people[pid])

        return ET.tostring(svg, encoding="unicode")

    def _estimate_canvas(self) -> Tuple[int, int]:
        if not self.people:
            return (int(2 * self.margin_x), int(2 * self.margin_y))
        xs = [p.x for p in self.people.values()]
        ys = [p.y for p in self.people.values()]
        max_x = max(xs) + self.margin_x + self.symbol_size
        max_y = max(ys) + self.margin_y + self.symbol_size + 80
        return (int(max_x), int(max_y))

    def _draw_generation_labels(self, parent: ET.Element) -> None:
        gens = sorted(set(p.generation for p in self.people.values()))
        if not gens:
            return
        min_gen = min(gens)
        for gen in gens:
            y = (gen - min_gen) * self.gen_gap + self.margin_y
            label = self._int_to_roman(gen)
            t = ET.SubElement(
                parent,
                "text",
                {
                    "id": self._sid("gen", label),
                    "x": "8",
                    "y": str(y + 4),
                    "font-size": "14",
                    "font-family": self.font_family,
                    "fill": "#666",
                },
            )
            t.text = label

    def _draw_metadata(self, parent: ET.Element, width: int, height: int) -> None:
        # Display only date, not author (per JOHBOC standard practice)
        created = (self._meta.get("date") or "").strip() or date.today().isoformat()
        if not created:
            return
        t = ET.SubElement(
            parent,
            "text",
            {
                "id": self._sid("meta"),
                "x": str(width - 8),
                "y": str(height - 10),
                "font-size": "12",
                "text-anchor": "end",
                "font-family": self.font_family,
                "fill": "#666",
            },
        )
        t.text = created

    def _draw_legend(self, parent: ET.Element, width: int, height: int) -> None:
        """Draw legend for complex pedigrees (JOHBOC 図5)"""
        # Legend position: bottom-left
        start_x = 10.0
        start_y = height - 120.0
        line_height = 18.0
        symbol_size = 12.0

        legend_items = [
            ("■", "罹患者 (Affected)"),
            ("／", "死亡 (Deceased)"),
            ("P", "発端者 (Proband)"),
            ("*", "記録確認済 (Verified)"),
        ]

        # Title
        t = ET.SubElement(
            parent,
            "text",
            {
                "id": "legend_title",
                "x": str(start_x),
                "y": str(start_y),
                "font-size": "11",
                "font-weight": "bold",
                "font-family": self.font_family,
                "fill": "#000",
            },
        )
        t.text = "凡例 (Legend)"

        # Legend items
        for idx, (symbol, description) in enumerate(legend_items):
            y = start_y + line_height * (idx + 1)

            # Symbol
            t_sym = ET.SubElement(
                parent,
                "text",
                {
                    "id": f"legend_symbol_{idx}",
                    "x": str(start_x + 5),
                    "y": str(y),
                    "font-size": "10",
                    "font-family": self.font_family,
                    "fill": "#000",
                },
            )
            t_sym.text = symbol

            # Description
            t_desc = ET.SubElement(
                parent,
                "text",
                {
                    "id": f"legend_desc_{idx}",
                    "x": str(start_x + 25),
                    "y": str(y),
                    "font-size": "10",
                    "font-family": self.font_family,
                    "fill": "#666",
                },
            )
            t_desc.text = description

    def _draw_spouse_line(self, parent: ET.Element, p1: Person, p2: Person, rel_type: str) -> None:
        if p1.generation != p2.generation:
            return
        # Connect symbol edges (not centers) to avoid lines crossing symbols.
        y = p1.y
        half = self.symbol_size / 2
        if p1.x <= p2.x:
            x1, x2 = p1.x + half, p2.x - half
        else:
            x1, x2 = p1.x - half, p2.x + half
        ET.SubElement(
            parent,
            "line",
            {
                "id": self._sid("spouse", rel_type, p1.id, p2.id),
                "x1": str(x1),
                "y1": str(y),
                "x2": str(x2),
                "y2": str(y),
                "stroke": "#000",
                "stroke-width": str(self.stroke_width),
                "fill": "none",
            },
        )
        if rel_type == "consanguineous":
            offset = 6.0
            ET.SubElement(
                parent,
                "line",
                {
                    "id": self._sid("spouse", "consanguineous2", p1.id, p2.id),
                    "x1": str(x1),
                    "y1": str(y + offset),
                    "x2": str(x2),
                    "y2": str(y + offset),
                    "stroke": "#000",
                    "stroke-width": str(self.stroke_width),
                    "fill": "none",
                },
            )
        if rel_type == "divorced":
            mid_x = (x1 + x2) / 2
            dy = 10.0
            dx = 6.0
            for i, (lx1, ly1, lx2, ly2) in enumerate(
                [
                    (mid_x - dx, y - dy, mid_x - 3 * dx, y + dy),
                    (mid_x + 3 * dx, y - dy, mid_x + dx, y + dy),
                ],
                start=1,
            ):
                ET.SubElement(
                    parent,
                    "line",
                    {
                        "id": self._sid("divorce", str(i), p1.id, p2.id),
                        "x1": str(lx1),
                        "y1": str(ly1),
                        "x2": str(lx2),
                        "y2": str(ly2),
                        "stroke": "#000",
                        "stroke-width": str(self.stroke_width),
                        "fill": "none",
                    },
                )
        if rel_type == "separated":
            mid_x = (x1 + x2) / 2
            dy = 10.0
            dx = 6.0
            ET.SubElement(
                parent,
                "line",
                {
                    "id": self._sid("separated", p1.id, p2.id),
                    "x1": str(mid_x - dx),
                    "y1": str(y - dy),
                    "x2": str(mid_x - 3 * dx),
                    "y2": str(y + dy),
                    "stroke": "#000",
                    "stroke-width": str(self.stroke_width),
                    "fill": "none",
                },
            )

    def _draw_children_lines(self, parent: ET.Element, parent1: Person, parent2: Person, children: List[Person], child_meta: Dict[str, dict]) -> None:
        if not children or parent1.generation != parent2.generation:
            return
        gen = parent1.generation
        if min(c.generation for c in children) != gen + 1:
            return

        mx = (parent1.x + parent2.x) / 2
        # Downward line should originate from the couple relationship line (not from the symbol edge).
        parent_bottom = parent1.y
        child_top = min(c.y for c in children) - self.symbol_size / 2
        # JOHBOC 図5: Lower the sibship line to avoid overlapping with parent's information
        # Use 0.75 ratio (closer to children) to provide more space above for parent's diagnoses
        mid_y = parent_bottom + (child_top - parent_bottom) * 0.75

        ET.SubElement(
            parent,
            "line",
            {
                "id": self._sid("down", parent1.id, parent2.id),
                "x1": str(mx),
                "y1": str(parent_bottom),
                "x2": str(mx),
                "y2": str(mid_y),
                "stroke": "#000",
                "stroke-width": str(self.stroke_width),
                "fill": "none",
            },
        )
        child_xs = [c.x for c in children]
        if len(children) == 1:
            # Single child: draw horizontal line from parent midpoint to child
            min_x = min(mx, child_xs[0])
            max_x = max(mx, child_xs[0])
        else:
            # Multiple children: draw horizontal line across all children
            min_x, max_x = min(child_xs), max(child_xs)
        ET.SubElement(
            parent,
            "line",
            {
                "id": self._sid("sib", parent1.id, parent2.id),
                "x1": str(min_x),
                "y1": str(mid_y),
                "x2": str(max_x),
                "y2": str(mid_y),
                "stroke": "#000",
                "stroke-width": str(self.stroke_width),
                "fill": "none",
            },
        )
        # Twin handling (JOHBOC 図3): share one branch point and split diagonally.
        # We identify twins by individual.twin = {"group": "...", "zygosity": "MZ"|"DZ"|"unknown"}.
        twins_by_group: Dict[str, List[Person]] = {}
        twin_info: Dict[str, dict] = {}
        for child in children:
            twin = getattr(child, "twin", None)
            if isinstance(twin, dict) and twin.get("group"):
                grp = str(twin["group"])
                twins_by_group.setdefault(grp, []).append(child)
                twin_info.setdefault(grp, twin)

        # Children not part of a (>=2) twin group get standard vertical individual lines.
        children_in_twins: set = set()
        for grp, members in twins_by_group.items():
            if len(members) >= 2:
                for m in members:
                    children_in_twins.add(m.id)

        for child in children:
            if child.id in children_in_twins:
                continue
            meta = child_meta.get(child.id, {}) if isinstance(child_meta, dict) else {}
            relation = str(meta.get("relation") or "").strip().lower()
            dash = "6,4" if relation in {"adopted", "adopted_in", "adopted_out", "foster"} else None
            attrs = {
                "id": self._sid("child", parent1.id, parent2.id, child.id),
                "x1": str(child.x),
                "y1": str(mid_y),
                "x2": str(child.x),
                "y2": str(child.y - self.symbol_size / 2),
                "stroke": "#000",
                "stroke-width": str(self.stroke_width),
                "fill": "none",
            }
            if dash:
                attrs["stroke-dasharray"] = dash
            ET.SubElement(parent, "line", attrs)

        # Draw twin groups
        for grp, members in twins_by_group.items():
            if len(members) < 2:
                continue
            members_sorted = sorted(members, key=lambda p: p.x)
            left = members_sorted[0]
            right = members_sorted[-1]
            group_x = (left.x + right.x) / 2
            child_top = min(p.y for p in members_sorted) - self.symbol_size / 2

            branch_y = mid_y + 14.0
            # From sibling bar to branch point
            ET.SubElement(
                parent,
                "line",
                {
                    "id": self._sid("twin", grp, "stem"),
                    "x1": str(group_x),
                    "y1": str(mid_y),
                    "x2": str(group_x),
                    "y2": str(branch_y),
                    "stroke": "#000",
                    "stroke-width": str(self.stroke_width),
                    "fill": "none",
                },
            )
            # Split to each twin
            for child in members_sorted:
                ET.SubElement(
                    parent,
                    "line",
                    {
                        "id": self._sid("twin", grp, "to", child.id),
                        "x1": str(group_x),
                        "y1": str(branch_y),
                        "x2": str(child.x),
                        "y2": str(child_top),
                        "stroke": "#000",
                        "stroke-width": str(self.stroke_width),
                        "fill": "none",
                    },
                )

            # Monozygotic twins: connect the twin branches with a horizontal line.
            z = str((twin_info.get(grp, {}) or {}).get("zygosity") or "").strip().lower()
            if z in {"mz", "mono", "monozygotic", "identical"} and len(members_sorted) == 2:
                # Connect points along diagonals (visually matches the standard MZ connector).
                t = 0.45
                p1x = group_x + (left.x - group_x) * t
                p2x = group_x + (right.x - group_x) * t
                py = branch_y + (child_top - branch_y) * t
                ET.SubElement(
                    parent,
                    "line",
                    {
                        "id": self._sid("twin", grp, "mz"),
                        "x1": str(p1x),
                        "y1": str(py),
                        "x2": str(p2x),
                        "y2": str(py),
                        "stroke": "#000",
                        "stroke-width": str(self.stroke_width),
                        "fill": "none",
                    },
                )

    def _draw_single_parent_lines(self, parent: ET.Element, parent1: Person, children: List[Person], child_meta: Dict[str, dict]) -> None:
        """Draw lines from single parent to children (JOHBOC standard)"""
        if not children:
            return
        gen = parent1.generation
        if min(c.generation for c in children) != gen + 1:
            return

        px = parent1.x
        parent_bottom = parent1.y
        child_top = min(c.y for c in children) - self.symbol_size / 2

        if len(children) == 1:
            # Single child: draw vertical line from parent directly down (JOHBOC standard)
            child = children[0]
            meta = child_meta.get(child.id, {}) if isinstance(child_meta, dict) else {}
            relation = str(meta.get("relation") or "").strip().lower()
            dash = "6,4" if relation in {"adopted", "adopted_in", "adopted_out", "foster"} else None
            attrs = {
                "id": self._sid("child", parent1.id, child.id),
                "x1": str(px),
                "y1": str(parent_bottom),
                "x2": str(px),  # Vertical line: same x position
                "y2": str(child_top),
                "stroke": "#000",
                "stroke-width": str(self.stroke_width),
                "fill": "none",
            }
            if dash:
                attrs["stroke-dasharray"] = dash
            ET.SubElement(parent, "line", attrs)
        else:
            # Multiple children: draw T-shaped connection
            mid_y = parent_bottom + (child_top - parent_bottom) * 0.75
            # Vertical line from parent to sibship line
            ET.SubElement(
                parent,
                "line",
                {
                    "id": self._sid("down", parent1.id),
                    "x1": str(px),
                    "y1": str(parent_bottom),
                    "x2": str(px),
                    "y2": str(mid_y),
                    "stroke": "#000",
                    "stroke-width": str(self.stroke_width),
                    "fill": "none",
                },
            )
            # Horizontal sibship line across children
            child_xs = [c.x for c in children]
            min_x, max_x = min(child_xs), max(child_xs)
            ET.SubElement(
                parent,
                "line",
                {
                    "id": self._sid("sib", parent1.id),
                    "x1": str(min_x),
                    "y1": str(mid_y),
                    "x2": str(max_x),
                    "y2": str(mid_y),
                    "stroke": "#000",
                    "stroke-width": str(self.stroke_width),
                    "fill": "none",
                },
            )
            # Vertical lines from sibship line to each child
            for child in children:
                meta = child_meta.get(child.id, {}) if isinstance(child_meta, dict) else {}
                relation = str(meta.get("relation") or "").strip().lower()
                dash = "6,4" if relation in {"adopted", "adopted_in", "adopted_out", "foster"} else None
                attrs = {
                    "id": self._sid("child", parent1.id, child.id),
                    "x1": str(child.x),
                    "y1": str(mid_y),
                    "x2": str(child.x),
                    "y2": str(child_top),
                    "stroke": "#000",
                    "stroke-width": str(self.stroke_width),
                    "fill": "none",
                }
                if dash:
                    attrs["stroke-dasharray"] = dash
                ET.SubElement(parent, "line", attrs)

    def _draw_sibship_line(self, parent: ET.Element, siblings: List[Person]) -> None:
        """Draw sibship line for siblings without parents (JOHBOC standard)"""
        if len(siblings) < 2:
            return

        # Ensure all siblings are in the same generation
        gen = siblings[0].generation
        if not all(s.generation == gen for s in siblings):
            return

        # Sort siblings by x position (left to right)
        sibs_sorted = sorted(siblings, key=lambda s: s.x)
        left = sibs_sorted[0]
        right = sibs_sorted[-1]

        # Draw horizontal line above the siblings (sibship line)
        y = left.y - self.symbol_size / 2 - 15.0  # Position above the symbols
        min_x = left.x
        max_x = right.x

        # Draw the horizontal sibship line
        ET.SubElement(
            parent,
            "line",
            {
                "id": self._sid("sibship", "_".join(s.id for s in sibs_sorted[:2])),
                "x1": str(min_x),
                "y1": str(y),
                "x2": str(max_x),
                "y2": str(y),
                "stroke": "#000",
                "stroke-width": str(self.stroke_width),
                "fill": "none",
            },
        )

        # Draw vertical lines connecting each sibling to the sibship line
        for sib in sibs_sorted:
            ET.SubElement(
                parent,
                "line",
                {
                    "id": self._sid("sibship", "to", sib.id),
                    "x1": str(sib.x),
                    "y1": str(y),
                    "x2": str(sib.x),
                    "y2": str(sib.y - self.symbol_size / 2),
                    "stroke": "#000",
                    "stroke-width": str(self.stroke_width),
                    "fill": "none",
                },
            )

    def _draw_person(self, parent: ET.Element, person: Person) -> None:
        # PowerPoint-friendly: avoid grouping; emit separate elements with ids.
        g = parent
        cx, cy = person.x, person.y
        s = self.symbol_size
        half = s / 2
        stroke = {"stroke": "#000", "stroke-width": str(self.stroke_width)}

        is_affected = "affected" in person.status
        fill = "#000" if is_affected else "none"

        def add_line(
            x1: float,
            y1: float,
            x2: float,
            y2: float,
            *,
            lid: str,
            stroke_color: str = "#000",
            dash: Optional[str] = None,
        ) -> None:
            ET.SubElement(
                g,
                "line",
                {
                    "id": lid,
                    "x1": str(x1),
                    "y1": str(y1),
                    "x2": str(x2),
                    "y2": str(y2),
                    "stroke": stroke_color,
                    "stroke-width": str(self.stroke_width),
                    "fill": "none",
                },
            )
            if dash:
                # ElementTree doesn't allow setting after creation cleanly here; set on last element.
                g[-1].set("stroke-dasharray", dash)

        def add_text(
            x: float,
            y: float,
            text: str,
            size: int = 12,
            anchor: str = "middle",
            klass: str = "txt",
            *,
            fill_color: Optional[str] = None,
        ) -> None:
            if fill_color is None:
                fill_color = "#666" if "id" in klass else "#000"
            t = ET.SubElement(
                g,
                "text",
                {
                    "id": self._sid("text", person.id, str(int(y)), str(int(x))),
                    "x": str(x),
                    "y": str(y),
                    "font-size": str(size),
                    "text-anchor": anchor,
                    "font-family": self.font_family,
                    "fill": fill_color,
                },
            )
            t.text = text

        preg_event = getattr(person, "pregnancy_event", None) or {}
        preg_type = str((preg_event.get("type") or "")).upper().strip() if isinstance(preg_event, dict) else ""
        preg_label = str((preg_event.get("label") or "")).strip() if isinstance(preg_event, dict) else ""
        gest_age = str((preg_event.get("gestational_age") or "")).strip() if isinstance(preg_event, dict) else ""
        karyotype = str((preg_event.get("karyotype") or "")).strip() if isinstance(preg_event, dict) else ""
        lmp = str((preg_event.get("lmp") or "")).strip() if isinstance(preg_event, dict) else ""
        edd = str((preg_event.get("edd") or "")).strip() if isinstance(preg_event, dict) else ""
        note = str((preg_event.get("note") or "")).strip() if isinstance(preg_event, dict) else ""

        # Pregnancy-related symbols (JOHBOC 図4)
        is_ectopic = "ectopic" in person.status or preg_type == "ECT"

        if any(st in person.status for st in ("miscarriage", "abortion")) or is_ectopic:
            points = [(cx, cy - half * 0.9), (cx + half * 0.9, cy + half * 0.9), (cx - half * 0.9, cy + half * 0.9)]
            ET.SubElement(
                g,
                "polygon",
                {
                    "id": self._sid("sym", person.id),
                    "points": " ".join(f"{x},{y}" for x, y in points),
                    "fill": fill,
                    "stroke": "#000",
                    "stroke-width": str(self.stroke_width),
                },
            )
            if "abortion" in person.status or preg_type == "TOP":
                # Diagonal line over the symbol (JOHBOC): use the same "/" orientation as deceased/stillbirth.
                add_line(
                    cx - half * 0.8,
                    cy + half * 0.8,
                    cx + half * 0.8,
                    cy - half * 0.8,
                    lid=self._sid("slash", person.id),
                    stroke_color="#fff" if is_affected else "#000",
                )
        elif "stillbirth" in person.status:
            # Stillbirth: sex symbol (if known) with "/" slash and SB below.
            self._draw_gender_symbol(g, person.gender, cx, cy, fill=fill, stroke=stroke)
        elif "pregnancy" in person.status:
            self._draw_gender_symbol(g, person.gender, cx, cy, fill=fill, stroke=stroke)
            # For affected fetus pregnancy, the symbol is filled; keep "P" visible.
            add_text(cx, cy + 4, "P", size=14, fill_color="#fff" if is_affected else "#000")
        else:
            self._draw_gender_symbol(g, person.gender, cx, cy, fill=fill, stroke=stroke)

        # Donor / surrogate markers (JOHBOC 図2/図3; simplified)
        if "donor" in person.status:
            add_text(cx, cy + 4, "D", size=14, fill_color="#fff" if is_affected else "#000")
        if "surrogate" in person.status:
            add_text(cx, cy + 4, "S", size=14, fill_color="#fff" if is_affected else "#000")

        if "deceased" in person.status or "stillbirth" in person.status:
            add_line(cx - half - 6, cy + half + 6, cx + half + 6, cy - half - 6, lid=self._sid("deceased", person.id))  # "/"

        # Vertical line only for UNAFFECTED carriers (未発症の保因者のみ)
        if ("presymptomatic_carrier" in person.status or "carrier" in person.status) and not is_affected:
            add_line(cx, cy - half, cx, cy + half, lid=self._sid("carrier", person.id), stroke_color="#000")

        if "verified" in person.status:
            add_text(cx + half + 10, cy + half - 2, "*", size=18, anchor="start")

        if "proband" in person.status or "consultand" in person.status:
            # JOHBOC 図5: Short arrow at 45 degrees, P positioned below
            arrow_length = 18.0  # Further shortened
            # 45 degree angle: dx = dy
            start_x = cx - half - arrow_length
            start_y = cy + half + arrow_length
            end_x = cx - half - 2
            end_y = cy + half + 2
            self._draw_arrow(g, start_x, start_y, end_x, end_y, arrow_id=self._sid("arrow", person.id))
            if "proband" in person.status:
                # Position P below the arrow start point, slightly to the left
                add_text(start_x - 4, start_y + 10, "P", size=12, anchor="middle")

        # Multiple individuals represented by one symbol (JOHBOC 図2)
        count = getattr(person, "count", None)
        if count:
            add_text(cx, cy + 4, str(count), size=14, fill_color="#fff" if is_affected else "#000")

        # Adoption brackets (JOHBOC 図3, simplified): draw brackets around the symbol.
        if getattr(person, "adoption_bracket", False):
            pad = 6.0
            left_x = cx - half - pad
            right_x = cx + half + pad
            top_y = cy - half - pad
            bot_y = cy + half + pad
            cap = 10.0
            add_line(left_x, top_y, left_x, bot_y, lid=self._sid("adopt", person.id, "L"))
            add_line(right_x, top_y, right_x, bot_y, lid=self._sid("adopt", person.id, "R"))
            add_line(left_x, top_y, left_x + cap, top_y, lid=self._sid("adopt", person.id, "LT"))
            add_line(left_x, bot_y, left_x + cap, bot_y, lid=self._sid("adopt", person.id, "LB"))
            add_line(right_x - cap, top_y, right_x, top_y, lid=self._sid("adopt", person.id, "RT"))
            add_line(right_x - cap, bot_y, right_x, bot_y, lid=self._sid("adopt", person.id, "RB"))

        # Individual number (JOHBOC 図5): Display number at top-right (left to right in each generation)
        individual_number = str(person.display_number)
        add_text(cx + half + 4, cy - half - 2, individual_number, size=10, anchor="start", klass="txt id", fill_color="#000")

        below: List[str] = []
        sex_at_birth = getattr(person, "sex_at_birth", None)
        if sex_at_birth:
            below.append(str(sex_at_birth))

        # Pregnancy-related annotations (prefer pregnancy_event fields, fallback to age/name).
        if "stillbirth" in person.status:
            below.append("SB")
        if gest_age:
            below.append(gest_age)
        elif person.age:
            # Add age with unit suffix (JOHBOC standard: "56y", "3m", "10d")
            age_str = person.age.strip()
            # Only add suffix if age doesn't already have a unit suffix or special prefix
            if age_str and not any(age_str.lower().startswith(prefix) for prefix in ("d.", "b.", "lmp", "edd")):
                # Check if the age string already ends with a unit
                if age_str and age_str[-1] not in ("y", "m", "d", "w"):
                    age_str = f"{age_str}{person.age_unit}"
            below.append(age_str)
        if karyotype:
            below.append(karyotype)
        if lmp:
            below.append(f"LMP {lmp}")
        if edd:
            below.append(f"EDD {edd}")
        if is_ectopic and not preg_label:
            preg_label = "ECT"
        if preg_label:
            below.append(preg_label)

        if "deceased" in person.status and person.age:
            # Normalize deceased age display to "d. ..."
            if below and below[0].lower().startswith("d."):
                pass
            else:
                # Replace the first age-like entry if present
                for i, s in enumerate(list(below)):
                    if s and (s[0].isdigit() or s.lower().startswith(("b.", "d."))):
                        if not s.lower().startswith("d."):
                            below[i] = f"d. {s}"
                        break

        # Genetic testing (JOHBOC 図5の「検査情報」欄に相当): show beneath the symbol.
        gt = getattr(person, "genetic_testing", None)
        if isinstance(gt, dict) and (gt.get("tested") is True or str(gt.get("result") or "").strip()):
            gt_label = str(gt.get("display") or gt.get("label") or gt.get("result") or "").strip()
            if not gt_label:
                gt_label = str(gt.get("test_type") or "").strip()
            variant = str(gt.get("variant") or "").strip()
            if variant and variant not in gt_label:
                gt_label = f"{gt_label} ({variant})" if gt_label else variant
            if gt_label:
                below.extend(_wrap_text(gt_label, 18))

        # Add diagnoses (JOHBOC standard: "45y 乳癌", "54y 直腸癌")
        for dx in person.diagnoses:
            if isinstance(dx, dict):
                condition = str(dx.get("condition") or "").strip()
                age_at_dx = str(dx.get("age_at_diagnosis") or "").strip()
                if condition:
                    if age_at_dx:
                        # Add unit suffix to diagnosis age (default: "y")
                        dx_unit = str(dx.get("age_unit") or person.age_unit).strip()
                        if age_at_dx[-1] not in ("y", "m", "d", "w"):
                            age_at_dx = f"{age_at_dx}{dx_unit}"
                        below.append(f"{age_at_dx} {condition}")
                    else:
                        below.append(condition)

        # Add medical notes (JOHBOC standard: "脳血管疾患")
        for note_item in person.medical_notes:
            if isinstance(note_item, str) and note_item.strip():
                below.append(note_item.strip())

        if note:
            below.extend(_wrap_text(note, 18))
        if person.name:
            below.extend(_wrap_text(person.name, 18))

        start_y = cy + half + 16
        # If stillbirth, "SB" is already part of below list; keep spacing consistent.
        for idx, line in enumerate(below):
            add_text(cx, start_y + idx * 14, line, size=11)

    def _draw_gender_symbol(self, parent: ET.Element, gender: str, cx: float, cy: float, *, fill: str, stroke: dict) -> None:
        s = self.symbol_size
        half = s / 2
        gender = (gender or "U").upper()
        if gender == "M":
            ET.SubElement(
                parent,
                "rect",
                {
                    "id": self._sid("sym", "M", str(int(cx)), str(int(cy))),
                    "x": str(cx - half),
                    "y": str(cy - half),
                    "width": str(s),
                    "height": str(s),
                    "fill": fill,
                    "stroke": "#000",
                    "stroke-width": str(self.stroke_width),
                },
            )
        elif gender == "F":
            ET.SubElement(
                parent,
                "circle",
                {
                    "id": self._sid("sym", "F", str(int(cx)), str(int(cy))),
                    "cx": str(cx),
                    "cy": str(cy),
                    "r": str(half),
                    "fill": fill,
                    "stroke": "#000",
                    "stroke-width": str(self.stroke_width),
                },
            )
        else:
            points = [(cx, cy - half), (cx + half, cy), (cx, cy + half), (cx - half, cy)]
            ET.SubElement(
                parent,
                "polygon",
                {
                    "id": self._sid("sym", "U", str(int(cx)), str(int(cy))),
                    "points": " ".join(f"{x},{y}" for x, y in points),
                    "fill": fill,
                    "stroke": "#000",
                    "stroke-width": str(self.stroke_width),
                },
            )

    def _draw_arrow(self, parent: ET.Element, x1: float, y1: float, x2: float, y2: float, *, arrow_id: str) -> None:
        # PowerPoint-friendly arrow: a line + explicit triangle head.
        import math

        ET.SubElement(
            parent,
            "line",
            {"id": arrow_id + "_shaft", "x1": str(x1), "y1": str(y1), "x2": str(x2), "y2": str(y2), "stroke": "#000", "stroke-width": str(self.stroke_width), "fill": "none"},
        )
        dx, dy = x2 - x1, y2 - y1
        length = math.hypot(dx, dy)
        if length <= 1e-6:
            return
        ux, uy = dx / length, dy / length
        head_len = 10.0
        head_w = 7.0
        bx, by = x2 - ux * head_len, y2 - uy * head_len
        px, py = -uy, ux
        p1 = (x2, y2)
        p2 = (bx + px * head_w / 2, by + py * head_w / 2)
        p3 = (bx - px * head_w / 2, by - py * head_w / 2)
        ET.SubElement(
            parent,
            "polygon",
            {
                "id": arrow_id + "_head",
                "points": " ".join(f"{x},{y}" for x, y in (p1, p2, p3)),
                "fill": "#000",
                "stroke": "none",
            },
        )

    def _sid(self, *parts: str) -> str:
        s = "_".join([str(p) for p in parts if p is not None and str(p) != ""])
        out = []
        for ch in s:
            if ch.isalnum() or ch in ("_", "-"):
                out.append(ch)
            else:
                out.append("_")
        return "".join(out)[:180]

    def _int_to_roman(self, n: int) -> str:
        if n <= 0:
            return ""
        vals = [
            (1000, "M"),
            (900, "CM"),
            (500, "D"),
            (400, "CD"),
            (100, "C"),
            (90, "XC"),
            (50, "L"),
            (40, "XL"),
            (10, "X"),
            (9, "IX"),
            (5, "V"),
            (4, "IV"),
            (1, "I"),
        ]
        out: List[str] = []
        x = n
        for v, sym in vals:
            while x >= v:
                out.append(sym)
                x -= v
        return "".join(out)
