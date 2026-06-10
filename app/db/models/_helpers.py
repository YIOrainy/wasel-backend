import enum


def enum_values(enum_cls: type[enum.Enum]) -> list[str]:
    return [str(e.value) for e in enum_cls]
