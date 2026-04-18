from rest_framework import generics, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import JobPostingDetailSerializer, JobPostingSerializer
from .services.job_search import apply_job_filters, get_base_job_queryset
from .services.ranking import rank_jobs
from .services.semantic_search import semantic_search_jobs


class JobListAPIView(generics.ListAPIView):
    serializer_class = JobPostingSerializer

    def get_queryset(self):
        queryset = get_base_job_queryset()
        return apply_job_filters(queryset, self.request.query_params)


class JobDetailAPIView(generics.RetrieveAPIView):
    serializer_class = JobPostingDetailSerializer
    queryset = get_base_job_queryset()


class JobSearchAPIView(generics.ListAPIView):
    serializer_class = JobPostingSerializer

    def get_queryset(self):
        queryset = get_base_job_queryset()
        return apply_job_filters(queryset, self.request.query_params)


class SemanticJobSearchAPIView(APIView):
    pagination_class = PageNumberPagination

    def get(self, request):
        query = (request.query_params.get("q") or "").strip()
        if not query:
            return Response(
                {"detail": "Query parameter 'q' is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        top_k = int(request.query_params.get("top_k", 50))
        scored_results = semantic_search_jobs(query, top_k=top_k)

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(scored_results, request, view=self)
        page = page or []

        jobs = [item["job"] for item in page]
        serializer = JobPostingSerializer(jobs, many=True)
        data = serializer.data
        for idx, item in enumerate(page):
            data[idx]["semantic_score"] = round(float(item["semantic_score"]), 6)

        return paginator.get_paginated_response(data)


class RankedJobSearchAPIView(APIView):
    pagination_class = PageNumberPagination

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
