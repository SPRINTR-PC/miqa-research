from django.db import models

from helpers.db_fields import get_deterministic_hash


class StudyParticipantManager(models.Manager):
    def filter_by_person_source_value(self, person_source_value: str):
        hashed_search_term = get_deterministic_hash(person_source_value)
        return self.get(person_source_value_hash=hashed_search_term)

    def filter_by_person_source_value_list(self, person_source_values: list[str]):
        hashed_search_terms = [
            get_deterministic_hash(person_source_value)
            for person_source_value in person_source_values
        ]
        return self.filter(person_source_value_hash__in=hashed_search_terms)

    def filter_by_name(self, name: str):
        hashed_name = get_deterministic_hash(name)
        return self.filter(name_hash=hashed_name)

    def filter_by_name_list(self, names: list[str]):
        hashed_names = [
            get_deterministic_hash(name)
            for name in names
        ]
        return self.filter(name_hash__in=hashed_names)