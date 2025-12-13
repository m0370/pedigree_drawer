"""
pedigree_drawer_lib_v0_2.py (v0.2)

Deterministic renderer: JSON (intermediate representation) -> SVG.

Design goals:
- Output must reflect the JSON strictly (relationships + child order).
- SVG must be clean and editable (draw.io-friendly).
- No external dependencies (standard library only).

Supported (subset, JOHBOC 図1〜4に準拠する範囲):
- gender: "M" (□), "F" (○), "U" (◇)
- status: "affected" (filled), "deceased" (slash "/"), "stillbirth" (sex symbol + slash + SB),
          "miscarriage" (triangle), "abortion" (triangle + "/" slash),
          "pregnancy" (P inside), "presymptomatic_carrier" (vertical line),
          "verified" (*), "proband" (arrow + P), "consultand" (arrow)
- relationships: type "spouse" | "consanguineous" | "divorced"

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
    name: Optional[str] = None
    x: float = 0.0
    y: float = 0.0


@dataclass
class Family:
    partners: Tuple[str, str]
    type: str
    children: List[str] = field(default_factory=list)
    child_meta: Dict[str, dict] = field(default_factory=dict)


class PedigreeChart:
    def __init__(self):
        self.people: Dict[str, Person] = {}
        self.families: List[Family] = []
        self._input_order: Dict[str, int] = {}
        self._meta: Dict[str, str] = {}

        # Layout config (SVG px units)
        self.symbol_size = 40.0
        self.spouse_gap = 24.0
        self.unit_gap = 52.0
        self.gen_gap = 120.0
        self.margin_x = 40.0
        self.margin_y = 40.0
        self.font_family = "Arial, Helvetica, sans-serif"
        self.stroke_width = 2.0
        # Output profile
        # PowerPoint imports SVG best when:
        # - elements are not deeply grouped,
        # - styles are inlined (no <style> / class selectors),
        # - arrow markers are avoided (use explicit polygons).
        self.output_profile = "powerpoint"  # "powerpoint" | "generic"

    def load_from_json(self, data: dict) -> None:
        self.people.clear()
        self.families.clear()
        self._input_order.clear()
        self._meta = dict((data or {}).get("meta") or {})

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
                # v0.2 schema compatibility
                if p_data.get("age_at_death") is not None:
                    age = p_data.get("age_at_death")
                elif p_data.get("current_age") is not None:
                    age = p_data.get("current_age")
                elif p_data.get("death_year") is not None:
                    age = f"d. {p_data.get('death_year')}"
                elif p_data.get("birth_year") is not None:
                    age = f"b. {p_data.get('birth_year')}"

            self.people[pid] = Person(
                id=pid,
                gender=(p_data.get("gender") or "U").upper(),
                generation=int(gen),
                status=list(p_data.get("status") or []),
                age=str(age) if age is not None else None,
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
            if len(partners) < 2:
                continue
            p1, p2 = partners[0], partners[1]
            if p1 not in self.people or p2 not in self.people:
                continue
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
            self.families.append(Family(partners=(p1, p2), type=rel_type, children=children, child_meta=child_meta))

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
            units = self._units_for_generation(gen)

            # Baseline anchors: input order (deterministic)
            for unit in units:
                for pid in unit["members"]:
                    initial_x.setdefault(pid, float(self._input_order.get(pid, 10_000)))

            # Refine anchors: if person is a child of a family in prev gen, anchor under that family midpoint.
            if gen > min_gen:
                for fam in self.families:
                    p1, p2 = fam.partners
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

            for unit in units:
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

    def _units_for_generation(self, generation: int) -> List[dict]:
        members_in_gen = [p.id for p in self.people.values() if p.generation == generation]
        used = set()
        units: List[dict] = []

        def family_sort_key(fam: Family) -> int:
            return min(self._input_order.get(fam.partners[0], 10_000), self._input_order.get(fam.partners[1], 10_000))

        families_in_gen = [
            fam
            for fam in self.families
            if self.people[fam.partners[0]].generation == generation and self.people[fam.partners[1]].generation == generation
        ]
        families_in_gen.sort(key=family_sort_key)

        for fam in families_in_gen:
            p1, p2 = fam.partners
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

        for fam in self.families:
            p1_id, p2_id = fam.partners
            p1 = self.people.get(p1_id)
            p2 = self.people.get(p2_id)
            if not p1 or not p2:
                continue
            self._draw_spouse_line(svg, p1, p2, fam.type)
            children = [self.people[cid] for cid in fam.children if cid in self.people]
            self._draw_children_lines(svg, p1, p2, children, fam.child_meta)

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
        author = (self._meta.get("author") or "").strip()
        created = (self._meta.get("date") or "").strip() or date.today().isoformat()
        if not author and not created:
            return
        text = " / ".join([s for s in [created, author] if s])
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
        t.text = text

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
        mid_y = (parent_bottom + child_top) / 2

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

        if "presymptomatic_carrier" in person.status:
            add_line(cx, cy - half, cx, cy + half, lid=self._sid("carrier", person.id), stroke_color="#fff" if is_affected else "#000")

        if "verified" in person.status:
            add_text(cx + half + 10, cy + half - 2, "*", size=18, anchor="start")

        if "proband" in person.status or "consultand" in person.status:
            start_x, start_y = cx - half - 34, cy + half + 26
            end_x, end_y = cx - half * 0.75, cy + half * 0.75
            self._draw_arrow(g, start_x, start_y, end_x, end_y, arrow_id=self._sid("arrow", person.id))
            if "proband" in person.status:
                add_text(start_x + 6, start_y - 6, "P", size=14, anchor="start")

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

        # Individual number is shown below or bottom-right (JOHBOC). Use bottom-right to avoid collisions.
        add_text(cx + half + 8, cy + half + 4, person.id, size=10, anchor="start", klass="txt id")

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
            below.append(person.age.strip())
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
