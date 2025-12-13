"""
pedigree_drawer_lib.py (v0.2-dev)

Deterministic renderer: JSON (intermediate representation) -> SVG.

Design goals:
- Output must reflect the JSON strictly (relationships + child order).
- SVG must be clean and editable (draw.io-friendly).
- No external dependencies (standard library only).

Supported (subset, matching v0.1 schema/status):
- gender: "M" (□), "F" (○), "U" (◇)
- status: "affected" (filled), "deceased" (slash "/"), "stillbirth" (sex symbol + slash + SB),
          "miscarriage" (triangle), "abortion" (triangle + "/" slash),
          "pregnancy" (P inside), "presymptomatic_carrier" (vertical line),
          "verified" (*), "proband" (arrow + P), "consultand" (arrow)
- relationships: type "spouse" | "consanguineous" | "divorced"
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

    def load_from_json(self, data: dict) -> None:
        self.people.clear()
        self.families.clear()
        self._input_order.clear()
        self._meta = dict((data or {}).get("meta") or {})

        individuals = (data or {}).get("individuals") or []
        for i, p_data in enumerate(individuals):
            pid = p_data["id"]
            self._input_order[pid] = i

            gen = p_data.get("generation")
            if not gen and "-" in pid:
                gen = _roman_to_int(pid.split("-", 1)[0])
            if not gen:
                gen = 1

            self.people[pid] = Person(
                id=pid,
                gender=(p_data.get("gender") or "U").upper(),
                generation=int(gen),
                status=list(p_data.get("status") or []),
                age=str(p_data.get("age")) if p_data.get("age") is not None else None,
                name=str(p_data.get("name")) if p_data.get("name") is not None else None,
            )
            # Optional (JOHBOC 2022/2024): AMAB/AFAB/UAAB etc.
            sex_at_birth = p_data.get("sex_at_birth")
            if sex_at_birth is not None:
                setattr(self.people[pid], "sex_at_birth", str(sex_at_birth))

        relationships = (data or {}).get("relationships") or []
        for rel in relationships:
            partners = list(rel.get("partners") or [])
            if len(partners) < 2:
                continue
            p1, p2 = partners[0], partners[1]
            if p1 not in self.people or p2 not in self.people:
                continue
            rel_type = (rel.get("type") or "spouse").strip().lower()
            if rel_type not in {"spouse", "consanguineous", "divorced"}:
                rel_type = "spouse"
            children = [cid for cid in (rel.get("children") or []) if cid in self.people]
            self.families.append(Family(partners=(p1, p2), type=rel_type, children=children))

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

        defs = ET.SubElement(svg, "defs")
        marker = ET.SubElement(
            defs,
            "marker",
            {"id": "arrow", "viewBox": "0 0 10 10", "refX": "10", "refY": "5", "markerWidth": "7", "markerHeight": "7", "orient": "auto"},
        )
        ET.SubElement(marker, "path", {"d": "M 0 0 L 10 5 L 0 10 z", "fill": "#000"})

        style = ET.SubElement(svg, "style")
        style.text = (
            f".txt{{font-family:{self.font_family};fill:#000;}}"
            ".id{fill:#666;}"
            ".line{stroke:#000;stroke-width:" + str(self.stroke_width) + ";fill:none;}"
        )

        g_lines = ET.SubElement(svg, "g", {"id": "lines"})
        g_people = ET.SubElement(svg, "g", {"id": "people"})
        g_meta = ET.SubElement(svg, "g", {"id": "meta"})

        self._draw_generation_labels(g_meta)
        self._draw_metadata(g_meta, width, height)

        # Connections
        for fam in self.families:
            p1_id, p2_id = fam.partners
            p1 = self.people.get(p1_id)
            p2 = self.people.get(p2_id)
            if not p1 or not p2:
                continue
            self._draw_spouse_line(g_lines, p1, p2, fam.type)
            children = [self.people[cid] for cid in fam.children if cid in self.people]
            self._draw_children_lines(g_lines, p1, p2, children)

        # People
        for pid in sorted(self.people.keys(), key=lambda k: self._input_order.get(k, 10_000)):
            self._draw_person(g_people, self.people[pid])

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
            t = ET.SubElement(parent, "text", {"class": "txt id", "x": "8", "y": str(y + 4), "font-size": "14"})
            t.text = label

    def _draw_metadata(self, parent: ET.Element, width: int, height: int) -> None:
        author = (self._meta.get("author") or "").strip()
        created = (self._meta.get("date") or "").strip() or date.today().isoformat()
        if not author and not created:
            return
        text = " / ".join([s for s in [created, author] if s])
        t = ET.SubElement(parent, "text", {"class": "txt id", "x": str(width - 8), "y": str(height - 10), "font-size": "12", "text-anchor": "end"})
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
        ET.SubElement(parent, "line", {"class": "line", "x1": str(x1), "y1": str(y), "x2": str(x2), "y2": str(y)})
        if rel_type == "consanguineous":
            offset = 6.0
            ET.SubElement(parent, "line", {"class": "line", "x1": str(x1), "y1": str(y + offset), "x2": str(x2), "y2": str(y + offset)})
        if rel_type == "divorced":
            mid_x = (x1 + x2) / 2
            dy = 10.0
            dx = 6.0
            ET.SubElement(parent, "line", {"class": "line", "x1": str(mid_x - dx), "y1": str(y - dy), "x2": str(mid_x - 3 * dx), "y2": str(y + dy)})
            ET.SubElement(parent, "line", {"class": "line", "x1": str(mid_x + 3 * dx), "y1": str(y - dy), "x2": str(mid_x + dx), "y2": str(y + dy)})

    def _draw_children_lines(self, parent: ET.Element, parent1: Person, parent2: Person, children: List[Person]) -> None:
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

        ET.SubElement(parent, "line", {"class": "line", "x1": str(mx), "y1": str(parent_bottom), "x2": str(mx), "y2": str(mid_y)})
        child_xs = [c.x for c in children]
        min_x, max_x = min(child_xs), max(child_xs)
        ET.SubElement(parent, "line", {"class": "line", "x1": str(min_x), "y1": str(mid_y), "x2": str(max_x), "y2": str(mid_y)})
        for child in children:
            ET.SubElement(parent, "line", {"class": "line", "x1": str(child.x), "y1": str(mid_y), "x2": str(child.x), "y2": str(child.y - self.symbol_size / 2)})

    def _draw_person(self, parent: ET.Element, person: Person) -> None:
        g = ET.SubElement(parent, "g", {"id": f"person_{person.id}"})
        cx, cy = person.x, person.y
        s = self.symbol_size
        half = s / 2
        stroke = {"stroke": "#000", "stroke-width": str(self.stroke_width)}

        is_affected = "affected" in person.status
        fill = "#000" if is_affected else "none"

        def add_line(x1: float, y1: float, x2: float, y2: float) -> None:
            ET.SubElement(g, "line", {"class": "line", "x1": str(x1), "y1": str(y1), "x2": str(x2), "y2": str(y2)})

        def add_text(x: float, y: float, text: str, size: int = 12, anchor: str = "middle", klass: str = "txt") -> None:
            t = ET.SubElement(g, "text", {"class": klass, "x": str(x), "y": str(y), "font-size": str(size), "text-anchor": anchor})
            t.text = text

        if any(st in person.status for st in ("miscarriage", "abortion")):
            points = [(cx, cy - half * 0.9), (cx + half * 0.9, cy + half * 0.9), (cx - half * 0.9, cy + half * 0.9)]
            ET.SubElement(g, "polygon", {"points": " ".join(f"{x},{y}" for x, y in points), "fill": fill, **stroke})
            if "abortion" in person.status:
                # Diagonal line over the symbol (JOHBOC): use the same "/" orientation as deceased/stillbirth.
                add_line(cx - half * 0.8, cy + half * 0.8, cx + half * 0.8, cy - half * 0.8)
        elif "stillbirth" in person.status:
            # Stillbirth: sex symbol (if known) with "/" slash and SB below.
            self._draw_gender_symbol(g, person.gender, cx, cy, fill=fill, stroke=stroke)
            add_text(cx, cy + half + 16, "SB", size=10)
        elif "pregnancy" in person.status:
            self._draw_gender_symbol(g, person.gender, cx, cy, fill=fill, stroke=stroke)
            add_text(cx, cy + 4, "P", size=14)
        else:
            self._draw_gender_symbol(g, person.gender, cx, cy, fill=fill, stroke=stroke)

        if "deceased" in person.status or "stillbirth" in person.status:
            add_line(cx - half - 6, cy + half + 6, cx + half + 6, cy - half - 6)  # "/"

        if "presymptomatic_carrier" in person.status:
            add_line(cx, cy - half, cx, cy + half)

        if "verified" in person.status:
            add_text(cx + half + 10, cy + half - 2, "*", size=18, anchor="start")

        if "proband" in person.status or "consultand" in person.status:
            start_x, start_y = cx - half - 34, cy + half + 26
            end_x, end_y = cx - half * 0.75, cy + half * 0.75
            ET.SubElement(
                g,
                "line",
                {"class": "line", "x1": str(start_x), "y1": str(start_y), "x2": str(end_x), "y2": str(end_y), "marker-end": "url(#arrow)"},
            )
            if "proband" in person.status:
                add_text(start_x + 6, start_y - 6, "P", size=14, anchor="start")

        # Individual number is shown below or bottom-right (JOHBOC). Use bottom-right to avoid collisions.
        add_text(cx + half + 8, cy + half + 4, person.id, size=10, anchor="start", klass="txt id")

        below: List[str] = []
        sex_at_birth = getattr(person, "sex_at_birth", None)
        if sex_at_birth:
            below.append(str(sex_at_birth))
        if person.age:
            age_text = person.age.strip()
            if "deceased" in person.status and not age_text.lower().startswith("d."):
                below.append(f"d. {age_text}")
            else:
                below.append(age_text)
        if person.name:
            below.extend(_wrap_text(person.name, 18))
        for idx, line in enumerate(below):
            add_text(cx, cy + half + 16 + idx * 14, line, size=11)

    def _draw_gender_symbol(self, parent: ET.Element, gender: str, cx: float, cy: float, *, fill: str, stroke: dict) -> None:
        s = self.symbol_size
        half = s / 2
        gender = (gender or "U").upper()
        if gender == "M":
            ET.SubElement(parent, "rect", {"x": str(cx - half), "y": str(cy - half), "width": str(s), "height": str(s), "fill": fill, **stroke})
        elif gender == "F":
            ET.SubElement(parent, "circle", {"cx": str(cx), "cy": str(cy), "r": str(half), "fill": fill, **stroke})
        else:
            points = [(cx, cy - half), (cx + half, cy), (cx, cy + half), (cx - half, cy)]
            ET.SubElement(parent, "polygon", {"points": " ".join(f"{x},{y}" for x, y in points), "fill": fill, **stroke})

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
