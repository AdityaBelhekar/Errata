"""A runnable demonstration of the comparator, for people who need to see it rather than read it.

Deliberately narrow. This shows the ONE thing R0 has actually established: given a catalog value
and a datasheet value, the comparator decides whether they disagree, how badly, and says why -- and
stays silent when they are the same fact in different words.

It does NOT demonstrate evidence grounding. The product's whole claim is that it can point at the
box on the page a value came from (FR-1.2-1.5), and that pipeline does not exist. The datasheet
values here are supplied, not located, and the report says so on its face. A demo that implied
otherwise would be selling the one thing that has not been built.

Every value pair is pulled from the hand-labelled, cited equivalence suite by case id, so the demo
cannot drift away from the thing the R0 gate measures.
"""

from __future__ import annotations

from .run import DemoAttribute, DemoResult, DemoSku, load_demo, render_html, render_text, run_demo

__all__ = [
    "DemoAttribute",
    "DemoResult",
    "DemoSku",
    "load_demo",
    "render_html",
    "render_text",
    "run_demo",
]
