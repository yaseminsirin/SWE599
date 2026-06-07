from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .pagination import JobResultsPagination
from .serializers import JobPostingDetailSerializer, JobPostingSerializer
from .services.job_search import apply_job_filters, get_base_job_queryset
from .services.ranking import rank_jobs
from .services.embeddings.types import EmbeddingProviderError
from .services.semantic_search import semantic_search_jobs


class JobListAPIView(generics.ListAPIView):
    serializer_class = JobPostingSerializer
    pagination_class = JobResultsPagination

    def get_queryset(self):
        queryset = get_base_job_queryset()
        return apply_job_filters(queryset, self.request.query_params)


class JobDetailAPIView(generics.RetrieveAPIView):
    serializer_class = JobPostingDetailSerializer
    queryset = get_base_job_queryset()


class JobSearchAPIView(generics.ListAPIView):
    serializer_class = JobPostingSerializer
    pagination_class = JobResultsPagination

    def get_queryset(self):
        queryset = get_base_job_queryset()
        return apply_job_filters(queryset, self.request.query_params)


class SemanticJobSearchAPIView(APIView):
    pagination_class = JobResultsPagination

    def get(self, request):
        query = (request.query_params.get("q") or "").strip()
        if not query:
            return Response(
                {"detail": "Query parameter 'q' is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        top_k = min(int(request.query_params.get("top_k", 20)), 50)
        tech_only = request.query_params.get("tech_only", "").strip().lower()
        if tech_only in {"1", "true", "yes"}:
            tech_filter = True
        else:
            tech_filter = False
        try:
            scored_results = semantic_search_jobs(query, top_k=top_k, tech_only=tech_filter)
        except EmbeddingProviderError as exc:
            return Response(
                {
                    "detail": str(exc),
                    "error_code": "embedding_provider_unavailable",
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        filter_params = {
            "location": request.query_params.get("location") or "",
            "employment_type": request.query_params.get("employment_type") or "",
            "is_remote": request.query_params.get("is_remote") or "",
        }
        if any(v for v in filter_params.values()):
            allowed_ids = set(
                apply_job_filters(get_base_job_queryset(), filter_params).values_list("id", flat=True)
            )
            scored_results = [row for row in scored_results if row["job"].id in allowed_ids]

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(scored_results, request, view=self)
        page = page or []

        jobs = [item["job"] for item in page]
        serializer = JobPostingSerializer(jobs, many=True)
        data = serializer.data
        for idx, item in enumerate(page):
            data[idx]["semantic_score"] = round(float(item["semantic_score"]), 6)
            data[idx]["hybrid_score"] = round(float(item.get("hybrid_score", item["semantic_score"])), 6)
            data[idx]["lexical_score"] = round(float(item.get("lexical_score", 0.0)), 6)
            data[idx]["role_alignment_score"] = round(float(item.get("role_alignment_score", 0.0)), 6)
            data[idx]["final_rank_score"] = round(
                float(item.get("final_rank_score", item.get("hybrid_score", item["semantic_score"]))),
                6,
            )

        return paginator.get_paginated_response(data)


class RankedJobSearchAPIView(APIView):
    pagination_class = JobResultsPagination

    def get(self, request):
        query = (request.query_params.get("keyword") or "").strip()
        queryset = get_base_job_queryset()
        queryset = apply_job_filters(queryset, request.query_params)
        ranked = rank_jobs(
            queryset,
            query=query,
            user=request.user,
            limit=int(request.query_params.get("top_k", 100)),
        )

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(ranked, request, view=self)
        page = page or []
        jobs = [item["job"] for item in page]
        serializer = JobPostingSerializer(jobs, many=True)
        data = serializer.data
        for idx, item in enumerate(page):
            data[idx]["rank_position"] = item["rank_position"]
            data[idx]["keyword_score"] = round(float(item["keyword_score"]), 6)
            data[idx]["semantic_score"] = round(float(item["semantic_score"]), 6)
            data[idx]["click_score"] = round(float(item["click_score"]), 6)
            data[idx]["final_score"] = round(float(item["final_score"]), 6)
        return paginator.get_paginated_response(data)
