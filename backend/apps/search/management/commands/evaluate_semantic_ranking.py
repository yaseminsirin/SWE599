"""Compare semantic-only, lexical-only, and hybrid rankings for report charts."""

import csv
import sys
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.search.services.retrieval_rerank import compute_lexical_score
from apps.search.services.semantic_search import semantic_search_jobs

DEFAULT_QUERIES = (
    "python developer",
    "data analyst",
    "backend engineer",
    "I enjoy building backend systems and designing APIs",
    "dev",
)


def _rank_by(rows: list[dict], key: str) -> list[dict]:
    return sorted(
        rows,
        key=lambda row: (
            float(row[key]),
            float(row["semantic_score"]),
            row["job"].posted_at or row["job"].created_at,
        ),
        reverse=True,
    )


def _rank_map(ranked: list[dict]) -> dict[int, int]:
    return {row["job"].id: index + 1 for index, row in enumerate(ranked)}


class Command(BaseCommand):
    help = (
        "Evaluate semantic vs lexical vs hybrid ranking. "
        "Writes CSV rows for Excel/matplotlib charts (hocanın istediği karşılaştırma)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--query",
            action="append",
            dest="queries",
            help="Search query (repeatable). Defaults to built-in demo queries.",
        )
        parser.add_argument(
            "--top-k",
            type=int,
            default=10,
            help="Number of final results per query (default 10).",
        )
        parser.add_argument(
            "--output",
            type=str,
            default="",
            help="CSV output path (default: stdout).",
        )

    def handle(self, *args, **options):
        queries = options["queries"] or list(DEFAULT_QUERIES)
        top_k = max(1, options["top_k"])
        ws = float(settings.SEMANTIC_RERANK_WEIGHT_SEMANTIC)
        wl = float(settings.SEMANTIC_RERANK_WEIGHT_LEXICAL)
        total = ws + wl or 1.0
        ws, wl = ws / total, wl / total

        self.stdout.write("=== Hybrid ranking weights (semantic-search endpoint) ===")
        self.stdout.write(f"  semantic weight = {ws:.0%}")
        self.stdout.write(f"  lexical weight  = {wl:.0%}")
        self.stdout.write(f"  formula: hybrid = {ws:.2f}*semantic + {wl:.2f}*lexical")
        self.stdout.write("")

        fieldnames = [
            "query",
            "job_id",
            "title",
            "semantic_score",
            "lexical_score",
            "hybrid_score",
            "rank_semantic_only",
            "rank_lexical_only",
            "rank_hybrid",
            "rank_delta_sem_vs_lex",
        ]
        rows_out: list[dict] = []

        for query in queries:
            self.stdout.write(f"--- Query: {query!r} ---")
            try:
                results = semantic_search_jobs(query, top_k=top_k)
            except Exception as exc:
                self.stderr.write(self.style.ERROR(f"  search failed: {exc}"))
                continue

            if not results:
                self.stdout.write("  (no results)")
                continue

            pool = [
                {
                    "job": item["job"],
                    "semantic_score": float(item["semantic_score"]),
                    "lexical_score": float(item.get("lexical_score", compute_lexical_score(query, item["job"]))),
                    "hybrid_score": float(item.get("hybrid_score", item["semantic_score"])),
                }
                for item in results
            ]

            by_sem = _rank_by(pool, "semantic_score")
            by_lex = _rank_by(pool, "lexical_score")
            by_hyb = _rank_by(pool, "hybrid_score")
            sem_rank = _rank_map(by_sem)
            lex_rank = _rank_map(by_lex)
            hyb_rank = _rank_map(by_hyb)

            self.stdout.write(
                f"  top hybrid: {by_hyb[0]['job'].title!r} "
                f"(sem={by_hyb[0]['semantic_score']:.3f}, lex={by_hyb[0]['lexical_score']:.3f}, hyb={by_hyb[0]['hybrid_score']:.3f})"
            )
            if by_sem[0]["job"].id != by_lex[0]["job"].id:
                self.stdout.write(
                    f"  semantic-only #1: {by_sem[0]['job'].title!r} | "
                    f"lexical-only #1: {by_lex[0]['job'].title!r}"
                )

            for item in pool:
                job = item["job"]
                rows_out.append(
                    {
                        "query": query,
                        "job_id": job.id,
                        "title": (job.title or "")[:120],
                        "semantic_score": round(item["semantic_score"], 4),
                        "lexical_score": round(item["lexical_score"], 4),
                        "hybrid_score": round(item["hybrid_score"], 4),
                        "rank_semantic_only": sem_rank[job.id],
                        "rank_lexical_only": lex_rank[job.id],
                        "rank_hybrid": hyb_rank[job.id],
                        "rank_delta_sem_vs_lex": sem_rank[job.id] - lex_rank[job.id],
                    }
                )

        output_path = (options["output"] or "").strip()
        if output_path:
            path = Path(output_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows_out)
            self.stdout.write(self.style.SUCCESS(f"Wrote {len(rows_out)} rows to {path}"))
        else:
            writer = csv.DictWriter(sys.stdout, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows_out)
