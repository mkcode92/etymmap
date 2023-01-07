from typing import Mapping, List

from etymmap.graph import Entity


class Entities:
    """
    Simple baseclass to store entities.
    """

    def __init__(self):
        # name -> list of entities with the same name
        self._entities = {}

    @property
    def entities(self):
        return self._entities

    def get(self, name: str, **attrs) -> List[Entity]:
        return [
            c
            for c in self._entities.get(name, [])
            if all(getattr(c, attr) == value for attr, value in attrs.items())
        ]

    def identify(self, name: str, template_data: Mapping = None) -> Entity:
        candidates = self._entities.setdefault(name, [])
        e = Entity.from_template_data(template_data) if template_data else Entity(name)
        for candidate in candidates:
            if self.try_merge(candidate, e):
                return candidate
        candidates.append(e)
        return e

    def try_merge(self, e1: Entity, e2: Entity):
        for attr in ["wplink", "born", "died", "nat"]:
            a1 = getattr(e1, attr)
            a2 = getattr(e2, attr)
            if a1 and a2 and a1 != a2:
                return False
        else:
            # merge occupation (might contain synonyms) if the rest is compatible
            e1.occ = "; ".join([o for o in [e1.occ, e2.occ] if o]) or None
            # for the others, just take one (if present)
            e1.nat = e1.nat or e2.nat
            e1.born = e1.born or e2.born
            e1.died = e1.died or e2.died
            e1.wplink = e1.wplink or e2.wplink
            return True
