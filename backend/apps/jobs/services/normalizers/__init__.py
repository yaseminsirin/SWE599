from .adzuna import AdzunaNormalizer
from .remotive import RemotiveNormalizer
from .usajobs import USAJobsNormalizer

NORMALIZERS = {
    "adzuna": AdzunaNormalizer,
    "usajobs": USAJobsNormalizer,
    "remotive": RemotiveNormalizer,
}
