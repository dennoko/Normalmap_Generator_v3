from enum import Enum


class ProfileType(Enum):
    LINEAR = 1
    LOGARITHMIC = 2
    EXPONENTIAL = 3


class NormalMapType(Enum):
    DX = 1
    GL = 2


__all__ = ["ProfileType", "NormalMapType"]
