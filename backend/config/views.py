from django.shortcuts import redirect, render


def home_view(request):
    return redirect("ui-search")


def search_view(request):
    return render(request, "search.html")


def alerts_view(request):
    return render(request, "alerts.html")
